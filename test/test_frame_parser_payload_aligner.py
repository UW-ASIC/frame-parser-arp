import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer


CLK_PERIOD_NS = 10


def pack64(byte_list):
    """Pack 8 bytes into a 64-bit word with byte 0 in bits [7:0]."""
    assert len(byte_list) == 8
    value = 0
    for lane, byte in enumerate(byte_list):
        assert 0 <= byte <= 0xFF
        value |= byte << (8 * lane)
    return value


async def reset_dut(dut):
    dut.rst_n.value = 0
    dut.ena.value = 0
    dut.tdata.value = 0
    dut.tkeep.value = 0
    dut.tvalid.value = 0
    dut.tlast.value = 0
    dut.payload_valid.value = 0
    dut.payload_bit_offset.value = 0
    dut.is_vlan_frame.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    dut.ena.value = 1
    await ClockCycles(dut.clk, 2)


@cocotb.test()
async def test_basic_nonvlan(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    dst_mac = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    src_mac = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66]
    ethertype = [0x08, 0x00]
    arp_payload = list(range(28))  # distinctive bytes: 0x00..0x1B, not all zero
    payload = arp_payload + [0x00] * (50 - len(arp_payload))

    frame_bytes = dst_mac + src_mac + ethertype + payload
    assert len(frame_bytes) == 64
    beats = [frame_bytes[i:i + 8] for i in range(0, 64, 8)]

    observed_payload = []

    async def collect_payload():
        if dut.p_tvalid.value:
            data = int(dut.p_tdata.value)
            keep = int(dut.p_tkeep.value)
            observed_payload.extend((data >> (8 * lane)) & 0xFF for lane in range(8) if keep & (1 << lane))

    for i, beat in enumerate(beats):
        dut.tdata.value = pack64(beat)
        dut.tkeep.value = 0xFF
        dut.tvalid.value = 1
        dut.tlast.value = 1 if i == len(beats) - 1 else 0
        dut.is_vlan_frame.value = 0

        if i == 0:
            dut.payload_valid.value = 0
            dut.payload_bit_offset.value = 0
        elif i == 1:
            dut.payload_valid.value = 1
            dut.payload_bit_offset.value = 48
        else:
            dut.payload_valid.value = 1
            dut.payload_bit_offset.value = 0

        await RisingEdge(dut.clk)
        await collect_payload()

    dut.tvalid.value = 0
    dut.tlast.value = 0
    dut.payload_valid.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
        await collect_payload()
    assert observed_payload[:28] == arp_payload



@cocotb.test()
async def test_basic_vlan(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    dst_mac = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    src_mac = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66]
    TPID = [0x81, 0x00]
    pcp = 0b101
    dei = 0
    vlan_id = 0x123
    TCI = (pcp << 13) | (dei << 12) | vlan_id
    TCI_bytes = [(TCI >> 8) & 0xFF, TCI & 0xFF]
    ethertype = [0x08, 0x00]  # IPv4
    arp_payload = list(range(28))  # distinctive bytes: 0x00..0x1B, not all zero
    payload = arp_payload + [0x00] * (46 - len(arp_payload))
    

    frame_bytes = dst_mac + src_mac + [0x81,0x00] + TCI_bytes + ethertype + payload
    assert len(frame_bytes) == 64
    beats = [frame_bytes[i:i + 8] for i in range(0, 64, 8)]

    observed_payload = []

    async def collect_payload():
        if dut.p_tvalid.value:
            data = int(dut.p_tdata.value)
            keep = int(dut.p_tkeep.value)
            observed_payload.extend((data >> (8 * lane)) & 0xFF for lane in range(8) if keep & (1 << lane))

    for i, beat in enumerate(beats):
        dut.tdata.value = pack64(beat)
        dut.tkeep.value = 0xFF
        dut.tvalid.value = 1
        dut.tlast.value = 1 if i == len(beats) - 1 else 0
        dut.is_vlan_frame.value = 1

        if i == 0:
            dut.payload_valid.value = 0
            dut.payload_bit_offset.value = 0
        elif i == 1:
            dut.payload_valid.value = 0
            dut.payload_bit_offset.value = 0
        elif i == 2:
            dut.payload_valid.value = 1
            dut.payload_bit_offset.value = 16
        else:
            dut.payload_valid.value = 1
            dut.payload_bit_offset.value = 0

        await RisingEdge(dut.clk)
        await collect_payload()

    dut.tvalid.value = 0
    dut.tlast.value = 0
    dut.payload_valid.value = 0

    for _ in range(3):
        await RisingEdge(dut.clk)
        await collect_payload()

    assert observed_payload[:28] == arp_payload


@cocotb.test()
async def test_non_multiple_8_bytes(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    dst_mac = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    src_mac = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66]
    ethertype = [0x08, 0x00]
    arp_payload = list(range(28))  # distinctive bytes: 0x00..0x1B, not all zero
    payload = arp_payload  # no padding at all -- frame ends right where real data ends

    frame_bytes = dst_mac + src_mac + ethertype + payload
    assert len(frame_bytes) == 42  # not a multiple of 8: last beat only has 2 real bytes
    beats = [frame_bytes[i:i + 8] for i in range(0, len(frame_bytes), 8)]

    observed_payload = []

    async def collect_payload():
        if dut.p_tvalid.value:
            data = int(dut.p_tdata.value)
            keep = int(dut.p_tkeep.value)
            observed_payload.extend((data >> (8 * lane)) & 0xFF for lane in range(8) if keep & (1 << lane))

    for i, beat in enumerate(beats):
        real_len = len(beat)
        padded_beat = beat + [0x00] * (8 - real_len)
        dut.tdata.value = pack64(padded_beat)
        dut.tkeep.value = (1 << real_len) - 1
        dut.tvalid.value = 1
        dut.tlast.value = 1 if i == len(beats) - 1 else 0
        dut.is_vlan_frame.value = 0

        if i == 0:
            dut.payload_valid.value = 0
            dut.payload_bit_offset.value = 0
        elif i == 1:
            dut.payload_valid.value = 1
            dut.payload_bit_offset.value = 48
        else:
            dut.payload_valid.value = 1
            dut.payload_bit_offset.value = 0

        await RisingEdge(dut.clk)
        await collect_payload()

    dut.tvalid.value = 0
    dut.tlast.value = 0
    dut.payload_valid.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
        await collect_payload()

    dut._log.info(f"observed ({len(observed_payload)} bytes) = {observed_payload}")
    dut._log.info(f"expected ({len(arp_payload)} bytes) = {arp_payload}")
    assert len(observed_payload) == len(arp_payload), (
        f"got {len(observed_payload)} bytes out, expected exactly {len(arp_payload)} -- "
        "extra bytes likely mean tkeep isn't being respected on a partial beat"
    )
    assert observed_payload == arp_payload


@cocotb.test()
async def test_back_to_back_frames(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    dst_mac_a = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    src_mac_a = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66]
    ethertype = [0x08, 0x00]
    payload_a = list(range(28))  # 0..27
    payload_full_a = payload_a + [0x00] * (50 - len(payload_a))
    frame_bytes_a = dst_mac_a + src_mac_a + ethertype + payload_full_a
    assert len(frame_bytes_a) == 64
    beats_a = [frame_bytes_a[i:i + 8] for i in range(0, 64, 8)]

    dst_mac_b = [0x00, 0x11, 0x22, 0x33, 0x44, 0x55]
    src_mac_b = [0x66, 0x77, 0x88, 0x99, 0xAA, 0xBB]
    payload_b = list(range(100, 128))  # 100..127, clearly distinct from payload_a
    payload_full_b = payload_b + [0x00] * (50 - len(payload_b))
    frame_bytes_b = dst_mac_b + src_mac_b + ethertype + payload_full_b
    assert len(frame_bytes_b) == 64
    beats_b = [frame_bytes_b[i:i + 8] for i in range(0, 64, 8)]

    all_beats = beats_a + beats_b

    observed_payload = []

    async def collect_payload():
        if dut.p_tvalid.value:
            data = int(dut.p_tdata.value)
            keep = int(dut.p_tkeep.value)
            observed_payload.extend((data >> (8 * lane)) & 0xFF for lane in range(8) if keep & (1 << lane))

    for i, beat in enumerate(all_beats):
        dut.tdata.value = pack64(beat)
        dut.tkeep.value = 0xFF
        dut.tvalid.value = 1
        is_tlast = (i == len(beats_a) - 1) or (i == len(all_beats) - 1)
        dut.tlast.value = 1 if is_tlast else 0
        dut.is_vlan_frame.value = 0

        beat_pos = i if i < len(beats_a) else i - len(beats_a)
        if beat_pos == 0:
            dut.payload_valid.value = 0
            dut.payload_bit_offset.value = 0
        elif beat_pos == 1:
            dut.payload_valid.value = 1
            dut.payload_bit_offset.value = 48
        else:
            dut.payload_valid.value = 1
            dut.payload_bit_offset.value = 0

        await RisingEdge(dut.clk)
        await collect_payload()

    dut.tvalid.value = 0
    dut.tlast.value = 0
    dut.payload_valid.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
        await collect_payload()

    dut._log.info(f"observed ({len(observed_payload)} bytes) = {observed_payload}")

    frame_a_out = observed_payload[:50]
    frame_b_out = observed_payload[50:100]

    assert len(observed_payload) == 100, (
        f"expected 100 total bytes (50 per frame), got {len(observed_payload)} -- "
        "back-to-back framing is likely broken"
    )
    assert frame_a_out[:28] == payload_a, "frame A's real payload came out wrong"
    assert frame_b_out[:28] == payload_b, "frame B's real payload came out wrong"
