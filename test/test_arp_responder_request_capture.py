# SPDX-FileCopyrightText: © 2026 UW-ASIC
# SPDX-License-Identifier: Apache-2.0

# Testbench for RTL/arp_responder_request_capture.v
# Run from the test/ directory with:
#   make -B UNIT=arp_responder_request_capture
# (If your Verilog module name differs from the file name, add TOPLEVEL=<module_name>)

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles, ReadOnly, Timer
import random

BUS_BYTES = 8  # 64-bit bus
 
def build_arp_request(sha, spa, tha, tpa, opcode=1):
    """Build the 28-byte ARP payload as a bytes object."""
    pkt = bytearray()
    pkt += (0x0001).to_bytes(2, "big")   # HTYPE
    pkt += (0x0800).to_bytes(2, "big")   # PTYPE
    pkt += (0x06).to_bytes(1, "big")     # HLEN
    pkt += (0x04).to_bytes(1, "big")     # PLEN
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
    tdata is packed big-endian-per-byte into the word (byte0 -> bits[7:0]).
    """
    beats = []
    n = len(payload)
    for i in range(0, n, bus_bytes):
        chunk = payload[i:i + bus_bytes]
        is_last = (i + bus_bytes) >= n
        valid_bytes = len(chunk)
        chunk_padded = chunk + bytes(bus_bytes - valid_bytes)
 
        # Big-endian / network-order packing: byte 0 -> tdata[63:56], ...,
        # byte 7 -> tdata[7:0]. Matches ext_opcode <= s_axis_tdata[15:0]
        # capturing bytes 6-7 (OPER) in the RTL.
        tdata = 0
        for b_idx, b in enumerate(chunk_padded):
            shift = 8 * (bus_bytes - 1 - b_idx)
            tdata |= (b << shift)
 
        tkeep = (1 << valid_bytes) - 1  # e.g. 4 valid bytes -> 0b0000_1111
 
        beats.append({
            "tdata": tdata,
            "tkeep": tkeep,
            "tlast": 1 if is_last else 0,
        })
    return beats
 
 
async def reset_dut(dut, cycles=5):
    dut.rst_n.value = 0
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tkeep.value = 0
    dut.s_axis_tuser.value = 0
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
 
 
async def drive_beats(dut, beats, tuser_on_last=1):
    """
    Drive a list of beats onto s_axis_*, respecting tready (backpressure),
    one beat per cycle once accepted (tvalid & tready).
    """
    for idx, beat in enumerate(beats):
        dut.s_axis_tdata.value = beat["tdata"]
        dut.s_axis_tkeep.value = beat["tkeep"]
        dut.s_axis_tlast.value = beat["tlast"]
        dut.s_axis_tuser.value = tuser_on_last if beat["tlast"] else 0
        dut.s_axis_tvalid.value = 1
 
        # Wait until DUT accepts this beat (tvalid & tready sampled together)
        while True:
            await ReadOnly()
            accepted = (dut.s_axis_tvalid.value == 1 and dut.s_axis_tready.value == 1)
            await RisingEdge(dut.clk)
            if accepted:
                break
 
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
 
 
def pad_payload(payload: bytes, total_len=64):
    """Pad a payload with trailing zero bytes up to total_len (models the
    Ethernet minimum-frame padding that arrives before tlast)."""
    if len(payload) >= total_len:
        return payload
    return payload + bytes(total_len - len(payload))
 
 
async def send_arp_packet(dut, payload: bytes, tuser=1, idle_prob=0.0,
                           max_idle_cycles=2):
    """
    Drive an ARP payload (optionally already padded) as AXI-S beats.
    With idle_prob > 0, randomly deassert tvalid for a few cycles before
    a given beat to model gaps within a packet. Returns after the cycle
    in which the tlast beat is accepted -- capture_done/ext_* are already
    valid (registered, same-edge visibility) by the time this returns.
    """
    beats = to_beats(payload)
    for beat in beats:
        if idle_prob > 0 and random.random() < idle_prob:
            dut.s_axis_tvalid.value = 0
            for _ in range(random.randint(1, max_idle_cycles)):
                await RisingEdge(dut.clk)
 
        dut.s_axis_tdata.value = beat["tdata"]
        dut.s_axis_tkeep.value = beat["tkeep"]
        dut.s_axis_tlast.value = beat["tlast"]
        dut.s_axis_tuser.value = tuser if beat["tlast"] else 0
        dut.s_axis_tvalid.value = 1
 
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        # s_axis_tready is tied high in this design, so every beat with
        # tvalid=1 is accepted on this edge -- no acceptance check needed.
 
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
 
 
@cocotb.test()
async def test_basic_capture(dut):
    """Send one well-formed ARP request; check all captured fields at tlast."""
 
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
 
    # --- Test vector ---
    expected_sha    = 0xAABBCCDDEEFF
    expected_spa    = 0xC0A80101          # 192.168.1.1
    expected_tha    = 0x000000000000       # unknown/broadcast in a request
    expected_tpa    = 0xC0A80102          # 192.168.1.2
    expected_opcode = 0x0001              # ARP request
    expected_tuser  = 1
 
    payload = build_arp_request(
        sha=expected_sha,
        spa=expected_spa,
        tha=expected_tha,
        tpa=expected_tpa,
        opcode=expected_opcode,
    )
    beats = to_beats(payload)
 
    # Drive the packet in, sampling DUT outputs right after the beat
    # carrying tlast is accepted.
    for beat in beats:
        dut.s_axis_tdata.value = beat["tdata"]
        dut.s_axis_tkeep.value = beat["tkeep"]
        dut.s_axis_tlast.value = beat["tlast"]
        dut.s_axis_tuser.value = expected_tuser if beat["tlast"] else 0
        dut.s_axis_tvalid.value = 1
 
        while True:
            await ReadOnly()
            accepted = (dut.s_axis_tvalid.value == 1
                        and dut.s_axis_tready.value == 1)
            await RisingEdge(dut.clk)
            if accepted:
                break
 
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
 
    # ext_* outputs and capture_done are registered (nonblocking assignment),
    # so they update on the same edge that accepted the tlast beat and are
    # already valid by the time we reach ReadOnly() here -- no extra
    # RisingEdge needed.
    await FallingEdge(dut.clk)
 
    assert int(dut.capture_done.value) == 1, \
        "capture_done did not assert on the cycle after tlast was accepted"
 
    assert int(dut.ext_opcode.value) == expected_opcode, \
        f"opcode mismatch: got {int(dut.ext_opcode.value):#06x}, " \
        f"expected {expected_opcode:#06x}"
 
    assert int(dut.ext_sha.value) == expected_sha, \
        f"SHA mismatch: got {int(dut.ext_sha.value):#014x}, " \
        f"expected {expected_sha:#014x}"
 
    assert int(dut.ext_spa.value) == expected_spa, \
        f"SPA mismatch: got {int(dut.ext_spa.value):#010x}, " \
        f"expected {expected_spa:#010x}"
 
    assert int(dut.ext_tpa.value) == expected_tpa, \
        f"TPA mismatch: got {int(dut.ext_tpa.value):#010x}, " \
        f"expected {expected_tpa:#010x}"
 
    assert int(dut.ext_tuser.value) == expected_tuser, \
        f"tuser mismatch: got {int(dut.ext_tuser.value)}, " \
        f"expected {expected_tuser}"
 
    dut._log.info("Basic capture test passed.")
 
 
@cocotb.test()
async def test_spa_beat_boundary_straddle(dut):
    """
    SPA straddles the beat1/beat2 boundary (bytes 14-17: upper 16b latched
    in state BEAT0, lower 16b latched in state BEAT1). Check the partial
    value mid-stream, not just the final result -- this catches an
    off-by-one byte split that happens to cancel out by the final beat.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
 
    # Distinct, non-repeating bytes so any shift/off-by-one is obviously wrong
    sha    = 0x112233445566
    spa    = 0xAABBCCDD   # upper 16b = 0xAABB, lower 16b = 0xCCDD
    tha    = 0x000000000000
    tpa    = 0x99887766
    opcode = 1
 
    payload = build_arp_request(sha=sha, spa=spa, tha=tha, tpa=tpa, opcode=opcode)
    beats = to_beats(payload)
    assert len(beats) == 4, "expected exactly 4 beats for a 28B ARP payload"
 
    # beat0 (opcode): state IDLE -> BEAT0
    dut.s_axis_tdata.value = beats[0]["tdata"]
    dut.s_axis_tkeep.value = beats[0]["tkeep"]
    dut.s_axis_tlast.value = 0
    dut.s_axis_tvalid.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
 
    # beat1 (SHA + SPA upper half): state BEAT0 -> BEAT1
    dut.s_axis_tdata.value = beats[1]["tdata"]
    dut.s_axis_tkeep.value = beats[1]["tkeep"]
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
 
    # ext_sha and ext_spa[31:16] should now be latched; ext_spa[15:0] is
    # not valid yet (BEAT1 hasn't been processed).
    got_sha = int(dut.ext_sha.value)
    got_spa_upper = (int(dut.ext_spa.value) >> 16) & 0xFFFF
    assert got_sha == sha, \
        f"SHA mismatch at beat boundary: got {got_sha:#014x}, expected {sha:#014x}"
    assert got_spa_upper == (spa >> 16) & 0xFFFF, \
        f"SPA upper half mismatch at beat boundary: got {got_spa_upper:#06x}, " \
        f"expected {(spa >> 16) & 0xFFFF:#06x}"
 
    # beat2 (SPA lower half): state BEAT1 -> BEAT2
    dut.s_axis_tdata.value = beats[2]["tdata"]
    dut.s_axis_tkeep.value = beats[2]["tkeep"]
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
 
    got_spa_full = int(dut.ext_spa.value)
    assert got_spa_full == spa, \
        f"Full SPA mismatch after beat2: got {got_spa_full:#010x}, expected {spa:#010x}"
 
    # beat3 (TPA, tlast): state BEAT2 -> IDLE, capture_done pulses
    dut.s_axis_tdata.value = beats[3]["tdata"]
    dut.s_axis_tkeep.value = beats[3]["tkeep"]
    dut.s_axis_tlast.value = 1
    dut.s_axis_tuser.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
 
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
 
    assert int(dut.capture_done.value) == 1, "capture_done did not pulse on final beat"
    assert int(dut.ext_tpa.value) == tpa, \
        f"TPA mismatch: got {int(dut.ext_tpa.value):#010x}, expected {tpa:#010x}"
    assert int(dut.ext_spa.value) == spa, "SPA changed unexpectedly on final beat"
 
    dut._log.info("SPA beat-boundary straddle test passed.")
 
 
@cocotb.test()
async def test_padding_drain(dut):
    """
    ARP payload (28B) followed by zero-padding up to Ethernet minimum frame
    (64B) before tlast. Capture must ignore the padding: latched fields
    should reflect only the real ARP bytes, and tready must stay asserted
    throughout the padding beats (WAIT_TLAST just absorbs them).
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
 
    sha    = 0x0A0B0C0D0E0F
    spa    = 0x0A000001
    tha    = 0x000000000000
    tpa    = 0x0A000002
    opcode = 1
 
    core_payload = build_arp_request(sha=sha, spa=spa, tha=tha, tpa=tpa, opcode=opcode)
    padded_payload = pad_payload(core_payload, total_len=64)  # +36B padding
    beats = to_beats(padded_payload)
    assert len(beats) == 8, f"expected 8 beats for a padded 64B frame, got {len(beats)}"
 
    tready_low_seen = False
    for beat in beats:
        dut.s_axis_tdata.value = beat["tdata"]
        dut.s_axis_tkeep.value = beat["tkeep"]
        dut.s_axis_tlast.value = beat["tlast"]
        dut.s_axis_tuser.value = 1 if beat["tlast"] else 0
        dut.s_axis_tvalid.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        if int(dut.s_axis_tready.value) != 1:
            tready_low_seen = True
 
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
 
    assert not tready_low_seen, "tready deasserted during padding beats"
    assert int(dut.capture_done.value) == 1, "capture_done did not pulse at tlast"
    assert int(dut.ext_opcode.value) == opcode
    assert int(dut.ext_sha.value) == sha, "SHA corrupted by padding"
    assert int(dut.ext_spa.value) == spa, "SPA corrupted by padding"
    assert int(dut.ext_tpa.value) == tpa, "TPA corrupted by padding"
 
    dut._log.info("Padding drain test passed.")
 
 
@cocotb.test()
async def test_tready_always_high(dut):
    """
    Request Capture must never backpressure the Arbiter: s_axis_tready is
    tied high regardless of tvalid, tdata, or internal FSM state. Checked
    every clock cycle, not just once.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
 
    random.seed(1)
    for cyc in range(300):
        dut.s_axis_tvalid.value = random.choice([0, 0, 1, 1, 1])
        dut.s_axis_tdata.value = random.getrandbits(64)
        dut.s_axis_tlast.value = random.choice([0, 0, 0, 1])
        dut.s_axis_tuser.value = random.getrandbits(1)
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        assert int(dut.s_axis_tready.value) == 1, \
            f"tready deasserted at cycle {cyc} -- Request Capture must always be ready"
 
    dut._log.info("tready-always-high test passed (300 random cycles).")
 
 
@cocotb.test()
async def test_early_tlast_passthrough(dut):
    """
    Request Capture does not validate frame length/opcode -- that's
    Validate + Match's job. If tlast arrives early (short frame), Capture
    must still pulse capture_done with whatever partial fields it has (no
    hang, no error flagging), and be ready for the next packet right away.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
 
    # tlast asserted on the very first beat -- only opcode has been
    # latched; sha/spa/tpa are stale/undefined. Capture should not care.
    early_opcode = 0x0001
    dut.s_axis_tdata.value = early_opcode  # occupies tdata[15:0], rest 0
    dut.s_axis_tkeep.value = 0x03
    dut.s_axis_tlast.value = 1
    dut.s_axis_tuser.value = 1
    dut.s_axis_tvalid.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
 
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
 
    assert int(dut.capture_done.value) == 1, \
        "capture_done should still pulse on an early/short tlast"
    assert int(dut.ext_opcode.value) == early_opcode, \
        "opcode should reflect whatever was captured before tlast"
    # No assertion on sha/spa/tpa here -- undefined/stale by design;
    # judging validity is Validate+Match's job, not Capture's.
 
    # Confirm the FSM returned to IDLE and is immediately ready for a
    # fresh packet (no lockup after a short frame).
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    assert int(dut.s_axis_tready.value) == 1
 
    dut._log.info("Early tlast passthrough test passed.")
 
 
@cocotb.test()
async def test_no_tlast_no_false_done(dut):
    """
    If tlast never arrives, capture_done must never assert -- Capture just
    keeps absorbing beats (via WAIT_TLAST once past BEAT2) without ever
    signaling a spurious done, and without hanging tready.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
 
    for i in range(20):
        dut.s_axis_tdata.value = i
        dut.s_axis_tkeep.value = 0xFF
        dut.s_axis_tlast.value = 0
        dut.s_axis_tvalid.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        assert int(dut.capture_done.value) == 0, \
            f"capture_done asserted with no tlast (cycle {i})"
        assert int(dut.s_axis_tready.value) == 1
 
    dut.s_axis_tvalid.value = 0
    dut._log.info("No-tlast / no-false-done test passed.")
 
 
@cocotb.test()
async def test_back_to_back_packets_no_gap(dut):
    """
    Packet B's beat0 starts the cycle immediately after packet A's tlast
    beat -- no idle bubble. Confirm B's fields cleanly overwrite A's with
    no leftover state from A (e.g. OR'd/mixed bits).
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
 
    # Packet A: all-1s fields
    payload_a = build_arp_request(
        sha=0xFFFFFFFFFFFF, spa=0xFFFFFFFF, tha=0xFFFFFFFFFFFF,
        tpa=0xFFFFFFFF, opcode=0xFFFF,
    )
    beats_a = to_beats(payload_a)
 
    # Packet B: all-0s fields (distinct opcode marker) -- any leftover
    # 1-bit from A would be immediately visible.
    payload_b = build_arp_request(
        sha=0x000000000000, spa=0x00000000, tha=0x000000000000,
        tpa=0x00000000, opcode=0x0002,
    )
    beats_b = to_beats(payload_b)
 
    all_beats = beats_a + beats_b  # no gap: B's beat0 follows A's last beat
 
    for i, beat in enumerate(all_beats):
        dut.s_axis_tdata.value = beat["tdata"]
        dut.s_axis_tkeep.value = beat["tkeep"]
        dut.s_axis_tlast.value = beat["tlast"]
        dut.s_axis_tuser.value = 1 if beat["tlast"] else 0
        dut.s_axis_tvalid.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
 
        if i == len(beats_a) - 1:
            # Just processed A's tlast beat -- confirm A's fields landed cleanly
            assert int(dut.capture_done.value) == 1
            assert int(dut.ext_sha.value) == 0xFFFFFFFFFFFF
            assert int(dut.ext_spa.value) == 0xFFFFFFFF
            assert int(dut.ext_opcode.value) == 0xFFFF
 
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
 
    # After B's tlast, fields must be purely B's -- zero, no leftover bits
    assert int(dut.capture_done.value) == 1
    assert int(dut.ext_sha.value) == 0x000000000000, \
        f"SHA leaked bits from packet A: {int(dut.ext_sha.value):#014x}"
    assert int(dut.ext_spa.value) == 0x00000000, \
        f"SPA leaked bits from packet A: {int(dut.ext_spa.value):#010x}"
    assert int(dut.ext_tpa.value) == 0x00000000, \
        f"TPA leaked bits from packet A: {int(dut.ext_tpa.value):#010x}"
    assert int(dut.ext_opcode.value) == 0x0002, \
        f"opcode leaked bits from packet A: {int(dut.ext_opcode.value):#06x}"
 
    dut._log.info("Back-to-back packet isolation test passed.")
 
 
@cocotb.test()
async def test_randomized_stress(dut):
    """
    Randomized ARP field values, randomized inter-beat idle gaps, and
    randomized trailing padding length, run back-to-back for many packets.
    Checked against a reference model matching the RTL's own field-to-beat
    mapping (not just "the ARP spec"), since Capture doesn't validate
    semantics -- it only latches by beat position.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
 
    random.seed(42)
    NUM_PACKETS = 40
 
    for pkt_idx in range(NUM_PACKETS):
        sha    = random.getrandbits(48)
        spa    = random.getrandbits(32)
        tha    = random.getrandbits(48)
        tpa    = random.getrandbits(32)
        opcode = random.choice([1, 2])       # Capture doesn't care which
        tuser  = random.getrandbits(1)
        pad_total = random.choice([28, 40, 64])  # no pad / partial / min-frame
 
        payload = build_arp_request(sha=sha, spa=spa, tha=tha, tpa=tpa, opcode=opcode)
        payload = pad_payload(payload, total_len=pad_total)
 
        await send_arp_packet(
            dut, payload, tuser=tuser,
            idle_prob=0.3, max_idle_cycles=2,
        )
 
        assert int(dut.capture_done.value) == 1, \
            f"packet {pkt_idx}: capture_done did not pulse"
        assert int(dut.ext_opcode.value) == opcode, \
            f"packet {pkt_idx}: opcode mismatch"
        assert int(dut.ext_sha.value) == sha, \
            f"packet {pkt_idx}: SHA mismatch"
        assert int(dut.ext_spa.value) == spa, \
            f"packet {pkt_idx}: SPA mismatch"
        assert int(dut.ext_tpa.value) == tpa, \
            f"packet {pkt_idx}: TPA mismatch"
        assert int(dut.ext_tuser.value) == tuser, \
            f"packet {pkt_idx}: tuser mismatch"
 
    dut._log.info(f"Randomized stress test passed ({NUM_PACKETS} packets).")

