# SPDX-FileCopyrightText: © 2026 UW-ASIC
# SPDX-License-Identifier: Apache-2.0
#
# Integration-level cocotb test for frame_parser_arp_top.
# Drives one clean, non-VLAN Ethernet II frame in over the s_axis-style
# slave port and checks the resulting `metadata` word.
#
# Run with:
#   make -B UNIT=frame_parser_arp_top
#
# Byte convention (matches test_frame_parser_header_datapath.py):
# out_tdata[7:0] / s_tdata[7:0] is the earliest byte in the beat.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, ReadOnly

CLK_PERIOD_NS = 10


def pack64(byte_list):
    """Pack 8 bytes into a 64-bit word with byte 0 in bits [7:0]."""
    assert len(byte_list) == 8
    value = 0
    for lane, byte in enumerate(byte_list):
        assert 0 <= byte <= 0xFF
        value |= byte << (8 * lane)
    return value


def mac48(byte_list):
    assert len(byte_list) == 6
    value = 0
    for byte in byte_list:
        value = (value << 8) | byte
    return value


def u16(hi, lo):
    return ((hi & 0xFF) << 8) | (lo & 0xFF)


def bswap64(value):
    """Reverse the 8 bytes of a 64-bit word (lane-order <-> wire-order)."""
    return int.from_bytes(value.to_bytes(8, "little"), "big")


async def reset_dut(dut, cycles=5):
    dut.rst_n.value = 0
    dut.ena.value = 1
    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0
    dut.s_tdata.value = 0
    dut.s_tkeep.value = 0
    dut.s_tuser.value = 0
    # reply_tready is an input the ARP responder side needs driven and held
    # high throughout so the two new end-to-end tests never see backpressure
    dut.reply_tready.value = 1
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def collect_reply(dut, max_wait_cycles=100):
    """
    Wait for reply_tvalid to assert, then capture beats until reply_tlast.
    Returns (reply_as_one_384_bit_int, [tkeep_per_beat]). Assumes
    reply_tready is already held high by reset_dut (no backpressure).
    max_wait_cycles is generous because the ARP reply has to travel the
    whole chain -- frame parser -> axi_switch's byte swap -> the full ARP
    responder pipeline -- not just a direct hit on arp_responder_top.
    """
    for _ in range(max_wait_cycles):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if dut.reply_tvalid.value == 1:
            break
    else:
        raise TimeoutError("reply_tvalid never asserted -- no ARP reply was sent")

    beats = []
    tkeeps = []
    beat_num = 0
    while True:
        assert dut.reply_tvalid.value == 1, f"reply_tvalid dropped mid-reply at beat {beat_num}"
        # reply_tdata leaves this module in MAC-facing lane order (wire byte 0
        # in bits [7:0]), matching s_tdata. Reverse each beat's bytes to get
        # them back into wire order for field extraction.
        beats.append(bswap64(int(dut.reply_tdata.value)))
        tkeeps.append(int(dut.reply_tkeep.value))
        tlast = int(dut.reply_tlast.value)

        await RisingEdge(dut.clk)
        beat_num += 1
        if tlast:
            break
        if beat_num > 8:
            raise AssertionError("reply ran past 8 beats without tlast")
        await ReadOnly()

    # The reply image is the first 6 beats (384 bits); with PAD_TO_MIN the
    # remaining beats are Ethernet minimum-length padding and must be zero.
    data_384 = 0
    for b in beats[:6]:
        data_384 = (data_384 << 64) | b
    for i, b in enumerate(beats[6:], start=6):
        assert b == 0, f"padding beat {i} should be all zeros, got {b:#018x}"

    return data_384, tkeeps


def parse_reply(data_384: int) -> dict:
    """
    Slice a 384-bit concatenated ARP reply into named fields, per the
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


def check_metadata(snapshot, exp_dst_mac_bytes, exp_src_mac_bytes, exp_ethertype_bytes, label):
    valid = (snapshot >> 144) & 0x1
    frame_len = (snapshot >> 130) & 0x3FFF
    fcs_ok = (snapshot >> 129) & 0x1
    frame_type = (snapshot >> 127) & 0x3
    pcp = (snapshot >> 124) & 0x7
    vlan_id = (snapshot >> 112) & 0xFFF
    got_ethertype = (snapshot >> 96) & 0xFFFF
    got_src_mac = (snapshot >> 48) & 0xFFFFFFFFFFFF
    got_dst_mac = snapshot & 0xFFFFFFFFFFFF

    exp_dst_mac = mac48(exp_dst_mac_bytes)
    exp_src_mac = mac48(exp_src_mac_bytes)
    exp_ethertype = u16(exp_ethertype_bytes[0], exp_ethertype_bytes[1])

    assert valid == 1, f"{label}: metadata valid bit should be set"
    assert fcs_ok == 1, f"{label}: fcs_ok should be 1"
    assert frame_type == 0, f"{label}: frame_type should be 0"
    assert got_ethertype == exp_ethertype, f"{label}: ethertype mismatch: got {got_ethertype:#06x} exp {exp_ethertype:#06x}"
    assert got_src_mac == exp_src_mac, f"{label}: src_mac mismatch: got {got_src_mac:#014x} exp {exp_src_mac:#014x}"
    assert got_dst_mac == exp_dst_mac, f"{label}: dst_mac mismatch: got {got_dst_mac:#014x} exp {exp_dst_mac:#014x}"
    assert frame_len == 64, f"{label}: frame_len mismatch: got {frame_len}, expected 64"




@cocotb.test()
async def test_basic_non_vlan_frame(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    dst_mac = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    src_mac = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66]
    ethertype = [0x08, 0x00]  # IPv4
    payload = [0x00] * 50     # pad so total frame == 64 bytes (min valid length)

    frame_bytes = dst_mac + src_mac + ethertype + payload
    assert len(frame_bytes) == 64
    beats = [frame_bytes[i:i + 8] for i in range(0, 64, 8)]

    for i, beat in enumerate(beats):
        dut.s_tdata.value = pack64(beat)
        dut.s_tkeep.value = 0xFF
        dut.s_tvalid.value = 1
        dut.s_tlast.value = 1 if i == len(beats) - 1 else 0
        dut.s_tuser.value = 0
        await RisingEdge(dut.clk)

    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0

    # metadata_assembler's valid bit (metadata[144]) is a one-cycle strobe,
    # not a level -- it drops back to 0 the cycle right after eof. Capture
    # the snapshot on the exact cycle it's high instead of sampling later.
    metadata = None
    for _ in range(10):
        await RisingEdge(dut.clk)
        snapshot = int(dut.metadata.value)
        if (snapshot >> 144) & 0x1:
            metadata = snapshot
            break

    assert metadata is not None, "metadata valid strobe never pulsed within 10 cycles of the frame's last beat"

    valid = (metadata >> 144) & 0x1
    frame_len = (metadata >> 130) & 0x3FFF
    fcs_ok = (metadata >> 129) & 0x1
    frame_type = (metadata >> 127) & 0x3
    pcp = (metadata >> 124) & 0x7
    vlan_id = (metadata >> 112) & 0xFFF
    got_ethertype = (metadata >> 96) & 0xFFFF
    got_src_mac = (metadata >> 48) & 0xFFFFFFFFFFFF
    got_dst_mac = metadata & 0xFFFFFFFFFFFF

    exp_dst_mac = mac48(dst_mac)
    exp_src_mac = mac48(src_mac)
    exp_ethertype = u16(ethertype[0], ethertype[1])

    dut._log.info(f"metadata          = {metadata:#039x}")
    dut._log.info(f"valid={valid} fcs_ok={fcs_ok} frame_type={frame_type} pcp={pcp} vlan_id={vlan_id:#x}")
    dut._log.info(f"frame_len reported = {frame_len} (true frame length = 64)")
    dut._log.info(f"ethertype: got={got_ethertype:#06x} exp={exp_ethertype:#06x}")
    dut._log.info(f"src_mac:   got={got_src_mac:#014x} exp={exp_src_mac:#014x}")
    dut._log.info(f"dst_mac:   got={got_dst_mac:#014x} exp={exp_dst_mac:#014x}")

    assert valid == 1, "metadata valid bit should be set after a clean, accepted frame"
    assert fcs_ok == 1, "fcs_ok should be 1 -- s_tuser was held low the whole frame"
    assert frame_type == 0, "non-VLAN frame should encode frame_type == 0"
    assert pcp == 0
    assert vlan_id == 0
    assert got_ethertype == exp_ethertype, f"ethertype mismatch: got {got_ethertype:#06x} exp {exp_ethertype:#06x}"
    assert got_src_mac == exp_src_mac, f"src_mac mismatch: got {got_src_mac:#014x} exp {exp_src_mac:#014x}"
    assert got_dst_mac == exp_dst_mac, f"dst_mac mismatch: got {got_dst_mac:#014x} exp {exp_dst_mac:#014x}"
    assert frame_len == 64, (
        f"frame_len mismatch: got {frame_len}, expected 64. "
        "Check frame_parser_frame_control.v's final_frame_len assignment -- "
        "it may be missing '+ bytes_kept' for the last beat."
    )

@cocotb.test()
async def test_vlan_tagged_frame(dut):
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
    payload = [0x00] * 46     # pad so total frame == 64 bytes (min valid length)


    frame_bytes = dst_mac + src_mac + TPID + TCI_bytes + ethertype + payload
    assert len(frame_bytes) == 64
    beats = [frame_bytes[i:i + 8] for i in range(0, 64, 8)]

    for i, beat in enumerate(beats):
        dut.s_tdata.value = pack64(beat)
        dut.s_tkeep.value = 0xFF
        dut.s_tvalid.value = 1
        dut.s_tlast.value = 1 if i == len(beats) - 1 else 0
        dut.s_tuser.value = 0
        await RisingEdge(dut.clk)

    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0

    # metadata_assembler's valid bit (metadata[144]) is a one-cycle strobe,
    # not a level -- it drops back to 0 the cycle right after eof. Capture
    # the snapshot on the exact cycle it's high instead of sampling later.
    metadata = None
    for _ in range(10):
        await RisingEdge(dut.clk)
        snapshot = int(dut.metadata.value)
        if (snapshot >> 144) & 0x1:
            metadata = snapshot
            break

    assert metadata is not None, "metadata valid strobe never pulsed within 10 cycles of the frame's last beat"

    valid = (metadata >> 144) & 0x1
    frame_len = (metadata >> 130) & 0x3FFF
    fcs_ok = (metadata >> 129) & 0x1
    frame_type = (metadata >> 127) & 0x3
    got_pcp = (metadata >> 124) & 0x7
    got_vlan_id = (metadata >> 112) & 0xFFF
    got_ethertype = (metadata >> 96) & 0xFFFF
    got_src_mac = (metadata >> 48) & 0xFFFFFFFFFFFF
    got_dst_mac = metadata & 0xFFFFFFFFFFFF

    exp_dst_mac = mac48(dst_mac)
    exp_src_mac = mac48(src_mac)
    exp_ethertype = u16(ethertype[0], ethertype[1])

    dut._log.info(f"metadata          = {metadata:#039x}")
    dut._log.info(f"valid={valid} fcs_ok={fcs_ok} frame_type={frame_type} pcp={got_pcp} vlan_id={got_vlan_id:#x}")
    dut._log.info(f"frame_len reported = {frame_len} (true frame length = 64)")
    dut._log.info(f"ethertype: got={got_ethertype:#06x} exp={exp_ethertype:#06x}")
    dut._log.info(f"src_mac:   got={got_src_mac:#014x} exp={exp_src_mac:#014x}")
    dut._log.info(f"dst_mac:   got={got_dst_mac:#014x} exp={exp_dst_mac:#014x}")

    assert valid == 1, "metadata valid bit should be set after a clean, accepted frame"
    assert fcs_ok == 1, "fcs_ok should be 1 -- s_tuser was held low the whole frame"
    assert frame_type == 1, "VLAN-tagged frame should encode frame_type == 1"
    assert got_pcp == pcp
    assert got_vlan_id == vlan_id
    assert got_ethertype == exp_ethertype, f"ethertype mismatch: got {got_ethertype:#06x} exp {exp_ethertype:#06x}"
    assert got_src_mac == exp_src_mac, f"src_mac mismatch: got {got_src_mac:#014x} exp {exp_src_mac:#014x}"
    assert got_dst_mac == exp_dst_mac, f"dst_mac mismatch: got {got_dst_mac:#014x} exp {exp_dst_mac:#014x}"
    assert frame_len == 64, (
        f"frame_len mismatch: got {frame_len}, expected 64. "
        "Check frame_parser_frame_control.v's final_frame_len assignment -- "
        "it may be missing '+ bytes_kept' for the last beat."
    )


@cocotb.test()
async def test_runt_frame(dut):
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
    payload = [0x00] * 30    # pad so total frame == 64 bytes (min valid length)


    frame_bytes = dst_mac + src_mac + TPID + TCI_bytes + ethertype + payload
    assert len(frame_bytes) == 48
    beats = [frame_bytes[i:i + 8] for i in range(0, len(frame_bytes), 8)]

    for i, beat in enumerate(beats):
        dut.s_tdata.value = pack64(beat)
        dut.s_tkeep.value = 0xFF
        dut.s_tvalid.value = 1
        dut.s_tlast.value = 1 if i == len(beats) - 1 else 0
        dut.s_tuser.value = 0
        await RisingEdge(dut.clk)

    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0

    # metadata_assembler's valid bit (metadata[144]) is a one-cycle strobe,
    # not a level -- it drops back to 0 the cycle right after eof. Capture
    # the snapshot on the exact cycle it's high instead of sampling later.
    metadata = None
    for _ in range(10):
        await RisingEdge(dut.clk)
        snapshot = int(dut.metadata.value)
        if (snapshot >> 144) & 0x1:
            metadata = snapshot
            break

    assert metadata is None, "strobe should never have appeared"

@cocotb.test()
async def test_oversized_frame(dut):
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
    payload = [0x00] * 1582


    frame_bytes = dst_mac + src_mac + TPID + TCI_bytes + ethertype + payload
    assert len(frame_bytes) == 1600
    beats = [frame_bytes[i:i + 8] for i in range(0, len(frame_bytes), 8)]

    for i, beat in enumerate(beats):
        dut.s_tdata.value = pack64(beat)
        dut.s_tkeep.value = 0xFF
        dut.s_tvalid.value = 1
        dut.s_tlast.value = 1 if i == len(beats) - 1 else 0
        dut.s_tuser.value = 0
        await RisingEdge(dut.clk)

    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0

    # metadata_assembler's valid bit (metadata[144]) is a one-cycle strobe,
    # not a level -- it drops back to 0 the cycle right after eof. Capture
    # the snapshot on the exact cycle it's high instead of sampling later.
    metadata = None
    for _ in range(10):
        await RisingEdge(dut.clk)
        snapshot = int(dut.metadata.value)
        if (snapshot >> 144) & 0x1:
            metadata = snapshot
            break

    assert metadata is None, "strobe should never have appeared"


@cocotb.test()
async def test_bad_FCS(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)


    dst_mac = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    src_mac = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66]
    ethertype = [0x08, 0x00]  # IPv4
    payload = [0x00] * 50     # pad so total frame == 64 bytes (min valid length)

    frame_bytes = dst_mac + src_mac + ethertype + payload
    assert len(frame_bytes) == 64
    beats = [frame_bytes[i:i + 8] for i in range(0, 64, 8)]

    for i, beat in enumerate(beats):
        dut.s_tdata.value = pack64(beat)
        dut.s_tkeep.value = 0xFF
        dut.s_tvalid.value = 1
        is_last = (i == len(beats) - 1)
        dut.s_tlast.value = 1 if is_last else 0
        dut.s_tuser.value = 1 if is_last else 0
        await RisingEdge(dut.clk)

    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0

    # metadata_assembler's valid bit (metadata[144]) is a one-cycle strobe,
    # not a level -- it drops back to 0 the cycle right after eof. Capture
    # the snapshot on the exact cycle it's high instead of sampling later.
    metadata = None
    for _ in range(10):
        await RisingEdge(dut.clk)
        snapshot = int(dut.metadata.value)
        if (snapshot >> 144) & 0x1:
            metadata = snapshot
            break

    assert metadata is None, "strobe should never have appeared"


@cocotb.test()
async def test_back_to_back_frames(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    dst_mac0 = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    src_mac0 = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66]
    ethertype = [0x08, 0x00]  # IPv4
    payload = [0x00] * 50     # pad so total frame == 64 bytes (min valid length)

    frame_bytes = dst_mac0 + src_mac0 + ethertype + payload
    assert len(frame_bytes) == 64
    beats0 = [frame_bytes[i:i + 8] for i in range(0, 64, 8)]

    dst_mac1 = [0x00, 0x11, 0x22, 0x33, 0x44, 0x55]
    src_mac1 = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    ethertype = [0x08, 0x00]  # IPv4
    payload = [0x00] * 50     # pad so total frame == 64 bytes (min valid length)

    frame_bytes = dst_mac1 + src_mac1 + ethertype + payload
    assert len(frame_bytes) == 64
    beats1 = [frame_bytes[i:i + 8] for i in range(0, 64, 8)]

    all_beats = beats0 + beats1

    snapshots = []

    for i, beat in enumerate(all_beats):
        dut.s_tdata.value = pack64(beat)
        dut.s_tkeep.value = 0xFF
        dut.s_tvalid.value = 1
        is_tlast = (i == len(beats0) - 1) or (i == len(all_beats) - 1)
        dut.s_tlast.value = 1 if is_tlast else 0
        dut.s_tuser.value = 0
        await RisingEdge(dut.clk)
        snap = int(dut.metadata.value)
        if (snap >> 144) & 0x1:
            snapshots.append(snap)

    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0

    # metadata_assembler's valid bit (metadata[144]) is a one-cycle strobe,
    # not a level -- it drops back to 0 the cycle right after eof. Capture
    # the snapshot on the exact cycle it's high instead of sampling later.
    for _ in range(10):
        await RisingEdge(dut.clk)
        snap = int(dut.metadata.value)
        if (snap >> 144) & 0x1:
            snapshots.append(snap)
            if len(snapshots) == 2:
                break

    

    assert len(snapshots)== 2, "expected 2 metadata strobes, got {len(snapshots)}"

    check_metadata(snapshots[0], dst_mac0, src_mac0, ethertype, "frame 0")
    check_metadata(snapshots[1], dst_mac1, src_mac1, ethertype, "frame 1")


@cocotb.test()
async def test_arp_request_end_to_end(dut):
    """
    Drive a real Ethernet+ARP request frame in at the MAC-facing port and
    check both the metadata word and the ARP reply that comes out the
    other end. This is the first test that exercises the full byte-order
    path (frame parser -> axi_switch's byte swap -> arp_responder_top)
    end-to-end -- the Phase 5 gate from the integration plan, and the
    test that would have caught F-01 if the byte swap were still missing.
    """
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    own_mac = 0xDABCAB123456  # matches OWN_MAC in frame_parser_arp_top.v
    own_ip = 0xC0A80101       # matches OWN_IP in frame_parser_arp_top.v

    dst_mac = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]   # broadcast, as a real ARP request would use
    src_mac = [0x02, 0x00, 0x00, 0x00, 0x00, 0x01]   # requester's MAC -- also used as ARP SHA
    ethertype = [0x08, 0x06]                          # ARP

    requester_sha = mac48(src_mac)
    requester_spa = 0xC0A80164  # 192.168.1.100

    arp_payload = bytearray()
    arp_payload += (0x0001).to_bytes(2, "big")       # HTYPE
    arp_payload += (0x0800).to_bytes(2, "big")       # PTYPE
    arp_payload += (0x06).to_bytes(1, "big")         # HLEN
    arp_payload += (0x04).to_bytes(1, "big")         # PLEN
    arp_payload += (0x0001).to_bytes(2, "big")       # OPER (request)
    arp_payload += requester_sha.to_bytes(6, "big")  # SHA
    arp_payload += requester_spa.to_bytes(4, "big")  # SPA
    arp_payload += (0).to_bytes(6, "big")            # THA (unknown in a request)
    arp_payload += own_ip.to_bytes(4, "big")         # TPA -- asking about us
    assert len(arp_payload) == 28

    frame_bytes = dst_mac + src_mac + ethertype + list(arp_payload)
    frame_bytes += [0x00] * (64 - len(frame_bytes))  # pad to 64 bytes total
    assert len(frame_bytes) == 64
    beats = [frame_bytes[i:i + 8] for i in range(0, 64, 8)]

    for i, beat in enumerate(beats):
        dut.s_tdata.value = pack64(beat)
        dut.s_tkeep.value = 0xFF
        dut.s_tvalid.value = 1
        dut.s_tlast.value = 1 if i == len(beats) - 1 else 0
        dut.s_tuser.value = 0
        await RisingEdge(dut.clk)

    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0

    # Metadata comes out first, tied to tlast -- same pattern as every
    # other test in this file.
    metadata = None
    for _ in range(10):
        await RisingEdge(dut.clk)
        snapshot = int(dut.metadata.value)
        if (snapshot >> 144) & 0x1:
            metadata = snapshot
            break
    assert metadata is not None, "metadata valid strobe never pulsed for the ARP request frame"
    check_metadata(metadata, dst_mac, src_mac, ethertype, "ARP request frame")

    # The ARP reply takes longer -- it has to travel through the whole ARP
    # chain after axi_switch's byte swap.
    data_384, tkeeps = await collect_reply(dut)
    reply = parse_reply(data_384)

    assert reply["dest_mac"] == requester_sha, \
        f"dest MAC should be requester's SHA: got {reply['dest_mac']:#014x}"
    assert reply["src_mac"] == own_mac, \
        f"src MAC should be OWN_MAC: got {reply['src_mac']:#014x}"
    assert reply["ethertype"] == 0x0806, \
        f"EtherType must be 0x0806: got {reply['ethertype']:#06x}"
    assert reply["htype"] == 0x0001
    assert reply["ptype"] == 0x0800
    assert reply["hlen"] == 0x06
    assert reply["plen"] == 0x04
    assert reply["oper"] == 0x0002, \
        f"OPER must be 2 (reply): got {reply['oper']:#06x}"
    assert reply["sha"] == own_mac, "reply SHA should be OWN_MAC"
    assert reply["spa"] == own_ip, "reply SPA should be OWN_IP"
    assert reply["tha"] == requester_sha, "reply THA should be requester's SHA"
    assert reply["tpa"] == requester_spa, "reply TPA should be requester's SPA"
    assert reply["padding"] == 0, "trailing padding must be zero"

    # PAD_TO_MIN pads the reply to the 64-byte Ethernet minimum: 8 beats,
    # every one fully valid. tkeep is lane-order so it needs no reversal --
    # an all-ones mask is symmetric.
    assert len(tkeeps) == 8, f"expected 8 reply beats, got {len(tkeeps)}"
    assert tkeeps == [0xFF] * 8, f"all padded beats should be fully valid: {tkeeps}"

    dut._log.info("ARP request end-to-end test passed -- metadata and reply both correct.")


@cocotb.test()
async def test_non_arp_frame_no_reply(dut):
    """
    A plain (non-ARP) frame must still produce correct metadata, but must
    never produce an ARP reply. Proves axi_switch's EtherType gate
    (w_final_ethertype == 0x0806) is wired to the real, resolved EtherType
    from header_datapath in the full system -- axi_switch's own unit test
    already checks this gate in isolation, but not with a real upstream
    driver behind it.
    """
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    dst_mac = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    src_mac = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66]
    ethertype = [0x08, 0x00]  # IPv4, not ARP
    payload = [0x00] * 50     # pad so total frame == 64 bytes (min valid length)

    frame_bytes = dst_mac + src_mac + ethertype + payload
    assert len(frame_bytes) == 64
    beats = [frame_bytes[i:i + 8] for i in range(0, 64, 8)]

    for i, beat in enumerate(beats):
        dut.s_tdata.value = pack64(beat)
        dut.s_tkeep.value = 0xFF
        dut.s_tvalid.value = 1
        dut.s_tlast.value = 1 if i == len(beats) - 1 else 0
        dut.s_tuser.value = 0
        await RisingEdge(dut.clk)

    dut.s_tvalid.value = 0
    dut.s_tlast.value = 0

    metadata = None
    for _ in range(10):
        await RisingEdge(dut.clk)
        snapshot = int(dut.metadata.value)
        if (snapshot >> 144) & 0x1:
            metadata = snapshot
            break
    assert metadata is not None, "metadata valid strobe never pulsed for a valid non-ARP frame"
    check_metadata(metadata, dst_mac, src_mac, ethertype, "non-ARP frame")

    # No ARP reply should ever appear for a non-ARP frame.
    for cyc in range(40):
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert dut.reply_tvalid.value == 0, \
            f"reply_tvalid asserted at cycle {cyc} for a non-ARP frame"

    dut._log.info("Non-ARP frame correctly produced metadata and no ARP reply.")
