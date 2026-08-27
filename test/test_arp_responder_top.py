import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, ReadOnly, NextTimeStep

BUS_BYTES = 8  # 64-bit bus


def build_arp_request(sha, spa, tha, tpa, opcode=1,
                       htype=0x0001, ptype=0x0800, hlen=0x06, plen=0x04):
    """
    Build a 28-byte ARP payload as a bytes object. htype/ptype/hlen/plen
    default to the standard Ethernet/IPv4 constants but can be overridden
    to build a deliberately malformed request.
    """
    pkt = bytearray()
    pkt += htype.to_bytes(2, "big")      # HTYPE
    pkt += ptype.to_bytes(2, "big")      # PTYPE
    pkt += hlen.to_bytes(1, "big")       # HLEN
    pkt += plen.to_bytes(1, "big")       # PLEN
    pkt += opcode.to_bytes(2, "big")     # OPER
    pkt += sha.to_bytes(6, "big")        # SHA
    pkt += spa.to_bytes(4, "big")        # SPA
    pkt += tha.to_bytes(6, "big")        # THA
    pkt += tpa.to_bytes(4, "big")        # TPA
    assert len(pkt) == 28
    return bytes(pkt)


def to_beats(payload: bytes, bus_bytes=BUS_BYTES):
    """
    Split a payload into (tdata, tkeep, tlast) beats for an AXI-S bus.
    Last beat is padded with zeros; tkeep marks which bytes are valid.
    tdata is packed big-endian-per-byte into the word (byte0 -> bits[63:56]).
    """
    beats = []
    n = len(payload)
    for i in range(0, n, bus_bytes):
        chunk = payload[i:i + bus_bytes]
        is_last = (i + bus_bytes) >= n
        valid_bytes = len(chunk)
        chunk_padded = chunk + bytes(bus_bytes - valid_bytes)

        tdata = 0
        for b_idx, b in enumerate(chunk_padded):
            shift = 8 * (bus_bytes - 1 - b_idx)
            tdata |= (b << shift)

        tkeep = (1 << valid_bytes) - 1

        beats.append({
            "tdata": tdata,
            "tkeep": tkeep,
            "tlast": 1 if is_last else 0,
        })
    return beats


async def reset_dut(dut, own_mac, own_ip, cycles=5):
    """Reset the DUT, and hold device identity + m_tready steady from here on."""
    dut.rst_n.value = 0
    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0
    dut.s_tdata.value = 0
    dut.s_tkeep.value = 0
    dut.s_tuser.value = 0
    dut.own_mac.value = own_mac
    dut.own_ip.value = own_ip
    # m_tready is an input the DUT needs driven -- nothing upstream ties it
    # high the way request_capture's s_axis_tready is tied high internally.
    dut.m_tready.value = 1
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def send_arp_request(dut, payload: bytes, tuser=0):
    """Drive an ARP payload in as AXI-S beats on the s_* port group."""
    beats = to_beats(payload)
    for beat in beats:
        dut.s_tdata.value = beat["tdata"]
        dut.s_tkeep.value = beat["tkeep"]
        dut.s_tlast.value = beat["tlast"]
        dut.s_tuser.value = tuser if beat["tlast"] else 0
        dut.s_tvalid.value = 1

        while True:
            await ReadOnly()
            accepted = (dut.s_tvalid.value == 1 and dut.s_tready.value == 1)
            await RisingEdge(dut.clk)
            if accepted:
                break

    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0


async def collect_reply(dut, max_wait_cycles=50):
    """
    Wait for m_tvalid to assert, then capture beats until m_tlast.
    Returns (reply_as_one_384_bit_int, [tkeep_per_beat]).
    Assumes m_tready is already held high by the caller (no backpressure).
    """
    for _ in range(max_wait_cycles):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if dut.m_tvalid.value == 1:
            break
    else:
        raise TimeoutError("m_tvalid never asserted -- no reply was sent")

    beats = []
    tkeeps = []
    beat_num = 0
    while True:
        assert dut.m_tvalid.value == 1, f"m_tvalid dropped mid-reply at beat {beat_num}"
        beats.append(int(dut.m_tdata.value))
        tkeeps.append(int(dut.m_tkeep.value))
        tlast = int(dut.m_tlast.value)

        await RisingEdge(dut.clk)
        beat_num += 1
        if tlast:
            break
        if beat_num > 8:
            raise AssertionError("reply ran past 8 beats without tlast")
        await ReadOnly()

    # The reply image is the first 6 beats (384 bits). With PAD_TO_MIN the
    # remaining beats are Ethernet minimum-length padding and must be zero.
    data_384 = 0
    for b in beats[:6]:
        data_384 = (data_384 << 64) | b
    for i, b in enumerate(beats[6:], start=6):
        assert b == 0, f"padding beat {i} should be all zeros, got {b:#018x}"

    return data_384, tkeeps


async def assert_no_reply(dut, wait_cycles=30):
    """Wait wait_cycles clocks and confirm m_tvalid never asserts."""
    for cyc in range(wait_cycles):
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert dut.m_tvalid.value == 0, \
            f"m_tvalid asserted at cycle {cyc} when no reply was expected"
    # Advance past the ReadOnly phase so callers can safely drive signals
    # (e.g. a follow-up reset_dut()) right after this returns.
    await RisingEdge(dut.clk)


def parse_reply(data_384: int) -> dict:
    """
    Slice a 384-bit concatenated reply into its named fields, per the
    layout documented in arp_responder_reply_beat_mux.v.
    """
    def field(offset_from_top, num_bits):
        shift = 384 - offset_from_top - num_bits
        mask = (1 << num_bits) - 1
        return (data_384 >> shift) & mask

    return {
        "dest_mac":  field(0, 48),
        "src_mac":   field(48, 48),
        "ethertype": field(96, 16),
        "htype":     field(112, 16),
        "ptype":     field(128, 16),
        "hlen":      field(144, 8),
        "plen":      field(152, 8),
        "oper":      field(160, 16),
        "sha":       field(176, 48),
        "spa":       field(224, 32),
        "tha":       field(256, 48),
        "tpa":       field(304, 32),
        "padding":   field(336, 48),
    }


@cocotb.test()
async def test_basic_arp_reply(dut):
    """
    Send one well-formed ARP request asking for our own IP; check the
    reply that comes out m_* is a complete, correct ARP reply.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    own_mac = 0xDABCAB123456
    own_ip = 0xC0A80101            # 192.168.1.1

    requester_sha = 0xAABBCCDDEEFF
    requester_spa = 0xC0A80164     # 192.168.1.100

    await reset_dut(dut, own_mac, own_ip)

    payload = build_arp_request(
        sha=requester_sha,
        spa=requester_spa,
        tha=0x000000000000,   # unknown/broadcast in a request
        tpa=own_ip,           # asking about us
        opcode=1,             # ARP request
    )

    await send_arp_request(dut, payload, tuser=0)

    data_384, tkeeps = await collect_reply(dut)
    reply = parse_reply(data_384)

    assert reply["dest_mac"] == requester_sha, \
        f"dest MAC should be requester's SHA: got {reply['dest_mac']:#014x}"
    assert reply["src_mac"] == own_mac, \
        f"src MAC should be our own_mac: got {reply['src_mac']:#014x}"
    assert reply["ethertype"] == 0x0806, \
        f"EtherType must be 0x0806: got {reply['ethertype']:#06x}"
    assert reply["htype"] == 0x0001
    assert reply["ptype"] == 0x0800
    assert reply["hlen"] == 0x06
    assert reply["plen"] == 0x04
    assert reply["oper"] == 0x0002, \
        f"OPER must be 2 (reply): got {reply['oper']:#06x}"
    assert reply["sha"] == own_mac, "reply SHA should be our own_mac"
    assert reply["spa"] == own_ip, "reply SPA should be our own_ip"
    assert reply["tha"] == requester_sha, "reply THA should be requester's SHA"
    assert reply["tpa"] == requester_spa, "reply TPA should be requester's SPA"
    assert reply["padding"] == 0, "trailing padding must be zero"

    # PAD_TO_MIN pads to the 64-byte Ethernet minimum: 8 beats, every one
    # fully valid (the pad bytes are real bytes that must be transmitted).
    assert len(tkeeps) == 8, f"expected 8 reply beats, got {len(tkeeps)}"
    assert tkeeps == [0xFF] * 8, f"all padded beats should be fully valid: {tkeeps}"

    dut._log.info("Basic ARP reply test passed.")


@cocotb.test()
async def test_no_reply_wrong_target_ip(dut):
    """
    A well-formed ARP request whose target_ip doesn't match our own_ip
    must not produce a reply. Proves own_ip is wired into
    validate_match.local_ip and actually compared against target_ip --
    test_basic_arp_reply used a match by construction, so it couldn't
    have caught a swapped or misrouted own_ip wire.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    own_mac = 0xDABCAB123456
    own_ip = 0xC0A80101      # 192.168.1.1
    wrong_ip = 0xC0A80199    # not us

    await reset_dut(dut, own_mac, own_ip)

    payload = build_arp_request(
        sha=0xAABBCCDDEEFF,
        spa=0xC0A80164,
        tha=0x000000000000,
        tpa=wrong_ip,          # asking about someone else
        opcode=1,
    )
    await send_arp_request(dut, payload, tuser=0)
    await assert_no_reply(dut)

    dut._log.info("No-reply-on-wrong-target-ip test passed.")


@cocotb.test()
async def test_no_reply_bad_format(dut):
    """
    Malformed ARP headers -- wrong HTYPE, PTYPE, HLEN, PLEN, or an opcode
    that's a reply rather than a request -- must each be dropped, not
    replied to. This is the real proof that ext_htype/ext_ptype/ext_hlen/
    ext_plen are wired into the matching validate_match inputs:
    test_basic_arp_reply only ever sent the standard constants, so it
    never could have caught two of these fields being swapped.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    own_mac = 0xDABCAB123456
    own_ip = 0xC0A80101

    bad_variants = [
        {"name": "wrong HTYPE", "htype": 0x0006},
        {"name": "wrong PTYPE", "ptype": 0x0806},
        {"name": "wrong HLEN", "hlen": 0x04},
        {"name": "wrong PLEN", "plen": 0x06},
        {"name": "opcode=REPLY not REQUEST", "opcode": 2},
    ]

    for variant in bad_variants:
        name = variant["name"]
        overrides = {k: v for k, v in variant.items() if k != "name"}

        await reset_dut(dut, own_mac, own_ip)
        payload = build_arp_request(
            sha=0xAABBCCDDEEFF,
            spa=0xC0A80164,
            tha=0x000000000000,
            tpa=own_ip,
            **overrides,
        )
        await send_arp_request(dut, payload, tuser=0)
        await assert_no_reply(dut)
        dut._log.info(f"No-reply-on-bad-format ({name}) passed.")


@cocotb.test()
async def test_no_reply_frame_error(dut):
    """
    A well-formed, correctly-targeted ARP request with the upstream
    frame-error flag (tuser) set on tlast must not produce a reply --
    proves ext_tuser is wired into validate_match.frame_error correctly.
    test_basic_arp_reply always sent tuser=0, so it never exercised this.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    own_mac = 0xDABCAB123456
    own_ip = 0xC0A80101

    await reset_dut(dut, own_mac, own_ip)

    payload = build_arp_request(
        sha=0xAABBCCDDEEFF,
        spa=0xC0A80164,
        tha=0x000000000000,
        tpa=own_ip,
        opcode=1,
    )
    await send_arp_request(dut, payload, tuser=1)  # frame marked bad
    await assert_no_reply(dut)

    dut._log.info("No-reply-on-frame-error test passed.")


@cocotb.test()
async def test_busy_interlock_drops_second_request(dut):
    """
    Send request A, then immediately (back-to-back, no gap) send request
    B while A's reply is still transmitting. B must be dropped: A's reply
    must still complete correctly, and no second reply may ever appear.
    This is the only test that exercises the tx_serializer.busy ->
    validate_match.tx_busy feedback wire at all.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    own_mac = 0xDABCAB123456
    own_ip = 0xC0A80101

    await reset_dut(dut, own_mac, own_ip)

    payload_a = build_arp_request(
        sha=0xAAAAAAAAAAAA, spa=0xC0A80111, tha=0x000000000000, tpa=own_ip, opcode=1,
    )
    payload_b = build_arp_request(
        sha=0xBBBBBBBBBBBB, spa=0xC0A80122, tha=0x000000000000, tpa=own_ip, opcode=1,
    )

    await send_arp_request(dut, payload_a, tuser=0)

    # A's reply starts streaming out well before B's 4 beats finish being
    # driven in -- collect it concurrently, or the early beats get missed
    # while this coroutine is still busy driving B on the s_* side.
    reply_task = cocotb.start_soon(collect_reply(dut))

    await send_arp_request(dut, payload_b, tuser=0)  # no gap -- lands while A is busy

    # A's reply must come out correctly, untouched by B.
    data_384, tkeeps = await reply_task
    reply = parse_reply(data_384)
    assert reply["sha"] == own_mac
    assert reply["tha"] == 0xAAAAAAAAAAAA, \
        "reply must be for request A, not overwritten by request B"
    assert reply["tpa"] == 0xC0A80111
    assert len(tkeeps) == 8

    # No second reply for B should ever appear.
    await assert_no_reply(dut, wait_cycles=30)

    dut._log.info("Busy interlock test passed -- B correctly dropped while A was in flight.")


@cocotb.test()
async def test_second_request_after_busy_clears(dut):
    """
    After a full request/reply cycle finishes, a second, independent
    request must still get its own correct reply -- the busy interlock
    must release cleanly and not leave the module stuck.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    own_mac = 0xDABCAB123456
    own_ip = 0xC0A80101

    await reset_dut(dut, own_mac, own_ip)

    payload_a = build_arp_request(
        sha=0xAAAAAAAAAAAA, spa=0xC0A80111, tha=0x000000000000, tpa=own_ip, opcode=1,
    )
    await send_arp_request(dut, payload_a, tuser=0)
    data_384_a, _ = await collect_reply(dut)
    reply_a = parse_reply(data_384_a)
    assert reply_a["tha"] == 0xAAAAAAAAAAAA

    # A couple cycles of margin for the busy interlock to fully release.
    await ClockCycles(dut.clk, 3)

    payload_b = build_arp_request(
        sha=0xBBBBBBBBBBBB, spa=0xC0A80122, tha=0x000000000000, tpa=own_ip, opcode=1,
    )
    await send_arp_request(dut, payload_b, tuser=0)
    data_384_b, tkeeps_b = await collect_reply(dut)
    reply_b = parse_reply(data_384_b)
    assert reply_b["tha"] == 0xBBBBBBBBBBBB, \
        "second, independent request did not get its own correct reply"
    assert reply_b["tpa"] == 0xC0A80122
    assert len(tkeeps_b) == 8

    dut._log.info("Second request after busy clears got a correct independent reply.")


@cocotb.test()
async def test_m_tready_backpressure(dut):
    """
    Stall m_tready partway through the reply; m_tdata/m_tkeep must hold
    steady and m_tvalid must stay asserted until the stall lifts, and the
    reply must still complete correctly once it does. tx_serializer's own
    backpressure logic is already unit-tested; this confirms nothing gets
    lost in the top-level pass-through of m_tready.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    own_mac = 0xDABCAB123456
    own_ip = 0xC0A80101
    requester_sha = 0xCCCCCCCCCCCC
    requester_spa = 0xC0A80133

    await reset_dut(dut, own_mac, own_ip)

    payload = build_arp_request(
        sha=requester_sha, spa=requester_spa, tha=0x000000000000, tpa=own_ip, opcode=1,
    )
    await send_arp_request(dut, payload, tuser=0)

    # Wait for the reply to start.
    for _ in range(50):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if dut.m_tvalid.value == 1:
            break
    else:
        raise TimeoutError("m_tvalid never asserted")

    # Capture beat 0 while still in the settled read-only phase, then move
    # to a writable phase before driving m_tready low -- stalling before
    # this beat's transfer can happen at the next clock edge.
    beat0_tdata = int(dut.m_tdata.value)
    beat0_tkeep = int(dut.m_tkeep.value)
    await NextTimeStep()
    dut.m_tready.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert dut.m_tvalid.value == 1, "m_tvalid dropped while stalled"
        assert int(dut.m_tdata.value) == beat0_tdata, "m_tdata changed while stalled"
        assert int(dut.m_tkeep.value) == beat0_tkeep, "m_tkeep changed while stalled"

    # Release backpressure and collect the rest of the reply normally.
    await NextTimeStep()
    dut.m_tready.value = 1
    beats = []
    tkeeps = []
    beat_num = 0
    while True:
        assert dut.m_tvalid.value == 1, f"m_tvalid dropped mid-reply at beat {beat_num}"
        beats.append(int(dut.m_tdata.value))
        tkeeps.append(int(dut.m_tkeep.value))
        tlast = int(dut.m_tlast.value)
        await RisingEdge(dut.clk)
        beat_num += 1
        if tlast:
            break
        if beat_num > 8:
            raise AssertionError("reply ran past 8 beats without tlast")
        await ReadOnly()

    # Reply image is the first 6 beats; the rest is minimum-length padding.
    data_384 = 0
    for b in beats[:6]:
        data_384 = (data_384 << 64) | b
    for i, b in enumerate(beats[6:], start=6):
        assert b == 0, f"padding beat {i} should be all zeros, got {b:#018x}"

    reply = parse_reply(data_384)
    assert reply["tha"] == requester_sha
    assert reply["tpa"] == requester_spa
    assert len(tkeeps) == 8
    assert tkeeps == [0xFF] * 8

    dut._log.info("m_tready backpressure test passed.")


@cocotb.test()
async def test_randomized_stress(dut):
    """
    Many independent, valid ARP requests with randomized SHA/SPA, each
    given enough time to get its own reply before the next is sent.
    Checks every field of every reply against a reference model.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    own_mac = 0xDABCAB123456
    own_ip = 0xC0A80101

    await reset_dut(dut, own_mac, own_ip)

    random.seed(7)
    NUM_PACKETS = 15

    for pkt_idx in range(NUM_PACKETS):
        sha = random.getrandbits(48)
        spa = random.getrandbits(32)

        payload = build_arp_request(
            sha=sha, spa=spa, tha=0x000000000000, tpa=own_ip, opcode=1,
        )
        await send_arp_request(dut, payload, tuser=0)

        data_384, tkeeps = await collect_reply(dut)
        reply = parse_reply(data_384)

        assert reply["dest_mac"] == sha, f"packet {pkt_idx}: dest MAC mismatch"
        assert reply["src_mac"] == own_mac, f"packet {pkt_idx}: src MAC mismatch"
        assert reply["oper"] == 0x0002, f"packet {pkt_idx}: OPER mismatch"
        assert reply["sha"] == own_mac, f"packet {pkt_idx}: reply SHA mismatch"
        assert reply["spa"] == own_ip, f"packet {pkt_idx}: reply SPA mismatch"
        assert reply["tha"] == sha, f"packet {pkt_idx}: reply THA mismatch"
        assert reply["tpa"] == spa, f"packet {pkt_idx}: reply TPA mismatch"
        assert len(tkeeps) == 8, f"packet {pkt_idx}: expected 8 beats"

        # Margin so the next request's decision doesn't land inside this
        # reply's busy window (that scenario is covered separately above).
        await ClockCycles(dut.clk, 3)

    dut._log.info(f"Randomized stress test passed ({NUM_PACKETS} packets).")
