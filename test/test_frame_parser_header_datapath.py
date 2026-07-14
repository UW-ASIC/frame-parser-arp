# SPDX-FileCopyrightText: © 2026 UW-ASIC
# SPDX-License-Identifier: Apache-2.0
#
# Cocotb testbench for tt_um_header_extractor.
#
# Place this file under test/test_header_extractor.py.
# Example invocation may look like:
#   make -B UNIT=header_extractor TOPLEVEL=tt_um_header_extractor
# depending on the repository's Makefile/module naming.
#
# Test assumptions:
# - out_tdata is an aligned 64-bit stream beat.
# - out_tdata[7:0] is the earliest byte in the beat.
# - en_* controls are already aligned to the beat being accepted.
# - A beat is accepted when out_tvalid && tready.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge, Timer


CLK_PERIOD_NS = 10


def pack64(byte_list):
    """Pack 8 bytes into tdata with byte 0 in bits [7:0]."""
    assert len(byte_list) == 8
    value = 0
    for lane, byte in enumerate(byte_list):
        assert 0 <= byte <= 0xFF
        value |= byte << (8 * lane)
    return value


def mac48(byte_list):
    """Convert six network-order bytes into a 48-bit integer."""
    assert len(byte_list) == 6
    value = 0
    for byte in byte_list:
        value = (value << 8) | byte
    return value


def u16(hi, lo):
    return ((hi & 0xFF) << 8) | (lo & 0xFF)


async def reset_dut(dut):
    dut.rst_n.value = 0
    dut.ena.value = 0

    dut.out_tdata.value = 0
    dut.out_tkeep.value = 0
    dut.out_tvalid.value = 0
    dut.out_tlast.value = 0
    dut.out_tuser.value = 0
    dut.tready.value = 0

    dut.is_vlan_frame.value = 0
    dut.en_dst_mac.value = 0
    dut.en_src_mac_part1.value = 0
    dut.en_src_mac_part2.value = 0
    dut.en_ethertype.value = 0
    dut.en_data.value = 0

    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    dut.ena.value = 1
    await ClockCycles(dut.clk, 1)


async def drive_inputs(
    dut,
    *,
    tdata=0,
    tkeep=0xFF,
    tvalid=1,
    tlast=0,
    tuser=0,
    tready=1,
    is_vlan_frame=0,
    en_dst_mac=0,
    en_src_mac_part1=0,
    en_src_mac_part2=0,
    en_ethertype=0,
    en_data=0,
):
    """Drive one cycle's worth of inputs during the safe half-cycle."""
    await FallingEdge(dut.clk)
    dut.out_tdata.value = tdata
    dut.out_tkeep.value = tkeep
    dut.out_tvalid.value = tvalid
    dut.out_tlast.value = tlast
    dut.out_tuser.value = tuser
    dut.tready.value = tready

    dut.is_vlan_frame.value = is_vlan_frame
    dut.en_dst_mac.value = en_dst_mac
    dut.en_src_mac_part1.value = en_src_mac_part1
    dut.en_src_mac_part2.value = en_src_mac_part2
    dut.en_ethertype.value = en_ethertype
    dut.en_data.value = en_data

    # Let combinational outputs settle before optional pre-clock checks.
    await Timer(1, unit="ns")


async def tick_and_sample(dut):
    await RisingEdge(dut.clk)
    await ReadOnly()


async def idle_cycle(dut):
    await drive_inputs(dut, tvalid=0, tready=1)
    await tick_and_sample(dut)


@cocotb.test()
async def test_reset_clears_registered_outputs(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    assert int(dut.dst_mac.value) == 0
    assert int(dut.src_mac.value) == 0
    assert int(dut.final_ethertype.value) == 0
    assert int(dut.vlan_TCI.value) == 0
    assert int(dut.payload_valid.value) == 0
    assert int(dut.payload_bit_offset.value) == 0


@cocotb.test()
async def test_tuser_passthrough_is_combinational(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    await drive_inputs(dut, tvalid=0, tuser=1)
    await ReadOnly()
    assert int(dut.tuser.value) == 1

    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.out_tuser.value = 0
    await Timer(1, unit="ns")
    await ReadOnly()
    assert int(dut.tuser.value) == 0


@cocotb.test()
async def test_non_vlan_header_extracts_mac_ethertype_and_payload_offset(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    dst = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    src = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66]
    ethertype = 0x0806  # ARP

    # Beat 1: Ethernet bytes 0-7 = dst[0:6], src[0:2]
    beat0 = pack64(dst + src[:2])
    await drive_inputs(
        dut,
        tdata=beat0,
        tvalid=1,
        tready=1,
        en_dst_mac=1,
        en_src_mac_part1=1,
    )
    await tick_and_sample(dut)

    assert int(dut.dst_mac.value) == mac48(dst)
    assert int(dut.src_mac.value) >> 32 == u16(src[0], src[1])
    assert int(dut.payload_valid.value) == 0
    assert int(dut.payload_bit_offset.value) == 0

    # Beat 2: Ethernet bytes 8-15 = src[2:6], ethertype, first 2 payload bytes.
    beat1 = pack64(src[2:] + [0x08, 0x06, 0xDE, 0xAD])
    await drive_inputs(
        dut,
        tdata=beat1,
        tvalid=1,
        tready=1,
        en_src_mac_part2=1,
        en_ethertype=1,  # Non-VLAN: final ethertype comes from lanes 4 and 5.
        en_data=1,
    )

    # Combinational type field for frame control should show bytes 12-13.
    await ReadOnly()
    assert int(dut.ethertype.value) == ethertype

    await tick_and_sample(dut)
    assert int(dut.src_mac.value) == mac48(src)
    assert int(dut.final_ethertype.value) == ethertype
    assert int(dut.vlan_TCI.value) == 0
    assert int(dut.payload_valid.value) == 1
    assert int(dut.payload_bit_offset.value) == 48


@cocotb.test()
async def test_vlan_header_extracts_tci_inner_ethertype_and_payload_offset(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    dst = [0x01, 0x23, 0x45, 0x67, 0x89, 0xAB]
    src = [0xFE, 0xDC, 0xBA, 0x98, 0x76, 0x54]
    vlan_tci = 0x0123
    inner_ethertype = 0x0800  # IPv4

    beat0 = pack64(dst + src[:2])
    await drive_inputs(
        dut,
        tdata=beat0,
        tvalid=1,
        tready=1,
        en_dst_mac=1,
        en_src_mac_part1=1,
    )
    await tick_and_sample(dut)

    assert int(dut.dst_mac.value) == mac48(dst)
    assert int(dut.payload_valid.value) == 0

    # Beat 2 of VLAN frame: src[2:6], TPID 0x8100, VLAN TCI.
    # Frame control would see ethertype == 0x8100 here and keep en_ethertype low.
    beat1 = pack64(src[2:] + [0x81, 0x00, 0x01, 0x23])
    await drive_inputs(
        dut,
        tdata=beat1,
        tvalid=1,
        tready=1,
        is_vlan_frame=1,
        en_src_mac_part2=1,
        en_ethertype=0,
        en_data=0,
    )
    await ReadOnly()
    assert int(dut.ethertype.value) == 0x8100

    await tick_and_sample(dut)
    assert int(dut.src_mac.value) == mac48(src)
    assert int(dut.vlan_TCI.value) == vlan_tci
    assert int(dut.final_ethertype.value) == 0
    assert int(dut.payload_valid.value) == 0
    assert int(dut.payload_bit_offset.value) == 0

    # Beat 3 of VLAN frame: inner EtherType in lanes 0-1, payload starts at lane 2.
    beat2 = pack64([0x08, 0x00, 0xCA, 0xFE, 0xBA, 0xBE, 0x12, 0x34])
    await drive_inputs(
        dut,
        tdata=beat2,
        tvalid=1,
        tready=1,
        is_vlan_frame=1,
        en_ethertype=1,
        en_data=1,
    )
    await tick_and_sample(dut)

    assert int(dut.final_ethertype.value) == inner_ethertype
    assert int(dut.payload_valid.value) == 1
    assert int(dut.payload_bit_offset.value) == 16


@cocotb.test()
async def test_payload_only_beat_sets_full_beat_payload_offset_zero(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    await drive_inputs(
        dut,
        tdata=pack64([0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80]),
        tvalid=1,
        tready=1,
        en_data=1,
    )
    await tick_and_sample(dut)

    assert int(dut.payload_valid.value) == 1
    assert int(dut.payload_bit_offset.value) == 0

    # payload_valid is intentionally a pulse; it should clear when no accepted data beat arrives.
    await idle_cycle(dut)
    assert int(dut.payload_valid.value) == 0
    assert int(dut.payload_bit_offset.value) == 0


@cocotb.test()
async def test_tready_low_prevents_registered_capture(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    dst = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    src = [0x11, 0x22]
    beat0 = pack64(dst + src)

    await drive_inputs(
        dut,
        tdata=beat0,
        tvalid=1,
        tready=0,
        en_dst_mac=1,
        en_src_mac_part1=1,
    )
    await tick_and_sample(dut)

    assert int(dut.dst_mac.value) == 0
    assert int(dut.src_mac.value) == 0
    assert int(dut.payload_valid.value) == 0

    # Same beat accepted one cycle later should now capture.
    await drive_inputs(
        dut,
        tdata=beat0,
        tvalid=1,
        tready=1,
        en_dst_mac=1,
        en_src_mac_part1=1,
    )
    await tick_and_sample(dut)

    assert int(dut.dst_mac.value) == mac48(dst)
    assert int(dut.src_mac.value) >> 32 == u16(0x11, 0x22)


@cocotb.test()
async def test_out_tvalid_low_prevents_registered_capture(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    beat0 = pack64([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x11, 0x22])
    await drive_inputs(
        dut,
        tdata=beat0,
        tvalid=0,
        tready=1,
        en_dst_mac=1,
        en_src_mac_part1=1,
    )
    await tick_and_sample(dut)

    assert int(dut.dst_mac.value) == 0
    assert int(dut.src_mac.value) == 0
    assert int(dut.payload_valid.value) == 0


@cocotb.test()
async def test_combinational_ethertype_follows_beat2_type_field_only_when_enabled(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    beat = pack64([0x33, 0x44, 0x55, 0x66, 0x86, 0xDD, 0x00, 0x00])

    await drive_inputs(dut, tdata=beat, tvalid=1, tready=1, en_src_mac_part2=0)
    await ReadOnly()
    assert int(dut.ethertype.value) == 0

    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.en_src_mac_part2.value = 1
    dut.out_tdata.value = beat
    await Timer(1, unit="ns")
    await ReadOnly()
    assert int(dut.ethertype.value) == 0x86DD


@cocotb.test()
async def test_reset_mid_parse_clears_previous_partial_header(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    beat0 = pack64([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x11, 0x22])
    await drive_inputs(dut, tdata=beat0, tvalid=1, tready=1, en_dst_mac=1, en_src_mac_part1=1)
    await tick_and_sample(dut)

    assert int(dut.dst_mac.value) == 0xAABBCCDDEEFF

    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)
    await ReadOnly()

    assert int(dut.dst_mac.value) == 0
    assert int(dut.src_mac.value) == 0
    assert int(dut.final_ethertype.value) == 0
    assert int(dut.vlan_TCI.value) == 0
    assert int(dut.payload_valid.value) == 0
    assert int(dut.payload_bit_offset.value) == 0


@cocotb.test()
async def test_tkeep_tlast_do_not_affect_current_header_extractor_outputs(dut):
    """
    This module currently marks out_tkeep/out_tlast unused. This test documents
    that behavior so an accidental future dependency is caught by regression.
    Frame length/drop checks belong in frame_control, not here.
    """
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    dst = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    beat0 = pack64(dst + [0x11, 0x22])

    await drive_inputs(
        dut,
        tdata=beat0,
        tkeep=0x01,   # intentionally not full; this DUT does not inspect it
        tvalid=1,
        tlast=1,     # intentionally asserted; this DUT does not inspect it
        tready=1,
        en_dst_mac=1,
        en_src_mac_part1=1,
    )
    await tick_and_sample(dut)

    assert int(dut.dst_mac.value) == mac48(dst)


@cocotb.test()
async def test_back_to_back_non_vlan_then_vlan_headers(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    # First frame: non-VLAN ARP.
    dst1 = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    src1 = [0x10, 0x20, 0x30, 0x40, 0x50, 0x60]
    await drive_inputs(dut, tdata=pack64(dst1 + src1[:2]), tvalid=1, tready=1, en_dst_mac=1, en_src_mac_part1=1)
    await tick_and_sample(dut)
    await drive_inputs(dut, tdata=pack64(src1[2:] + [0x08, 0x06, 0x00, 0x01]), tvalid=1, tready=1, en_src_mac_part2=1, en_ethertype=1, en_data=1)
    await tick_and_sample(dut)
    assert int(dut.dst_mac.value) == mac48(dst1)
    assert int(dut.src_mac.value) == mac48(src1)
    assert int(dut.final_ethertype.value) == 0x0806
    assert int(dut.payload_bit_offset.value) == 48

    # One idle cycle like a clean inter-frame gap.
    await idle_cycle(dut)

    # Second frame: VLAN IPv4. New header should overwrite old fields.
    dst2 = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06]
    src2 = [0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6]
    await drive_inputs(dut, tdata=pack64(dst2 + src2[:2]), tvalid=1, tready=1, en_dst_mac=1, en_src_mac_part1=1)
    await tick_and_sample(dut)
    await drive_inputs(dut, tdata=pack64(src2[2:] + [0x81, 0x00, 0x0A, 0xBC]), tvalid=1, tready=1, is_vlan_frame=1, en_src_mac_part2=1)
    await tick_and_sample(dut)
    await drive_inputs(dut, tdata=pack64([0x08, 0x00, 0xDE, 0xAD, 0xBE, 0xEF, 0x00, 0x00]), tvalid=1, tready=1, is_vlan_frame=1, en_ethertype=1, en_data=1)
    await tick_and_sample(dut)

    assert int(dut.dst_mac.value) == mac48(dst2)
    assert int(dut.src_mac.value) == mac48(src2)
    assert int(dut.vlan_TCI.value) == 0x0ABC
    assert int(dut.final_ethertype.value) == 0x0800
    assert int(dut.payload_valid.value) == 1
    assert int(dut.payload_bit_offset.value) == 16
