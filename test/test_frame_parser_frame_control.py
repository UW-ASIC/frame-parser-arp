# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0
#  make -B UNIT=frame_parser_frame_control

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, Timer

# helper fcn to reset dut
async def reset_dut(dut):
    dut._log.info("Resetting")
    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.ena.value = 1
    
    # AXI-S Inputs
    dut.tdata.value = 0
    dut.tkeep.value = 0
    dut.tvalid.value = 0
    dut.tlast.value = 0
    dut.tuser_0.value = 0
    
    # Metadata Inputs
    dut.ethertype.value = 0

    await Timer(20, units="ns")
    dut.rst_n.value = 1
    await Timer(10, units="ns")
    await RisingEdge(dut.clk)
    dut._log.info("Reset Complete")

def check_enables(dut, bitString):
    """
    Bitstring Values: 0, 1, x (don't care)
    Bitstring ordering: is_vlan, dst_mac, src_mac1, src_mac2, ethertype, data
    """
    if (bitString[0] != 'x'):
        assert dut.is_vlan_frame.value == int(bitString[0]), f"Failed; is_vlan_frame == {dut.is_vlan_frame.value}, expected {bitString[0]}"
    if (bitString[1] != 'x'):
        assert dut.en_dst_mac.value == int(bitString[1]), f"Failed; en_dst_mac == {dut.en_dst_mac.value}, expected {bitString[1]}"
    if (bitString[2] != 'x'):
        assert dut.en_src_mac_part1.value == int(bitString[2]), f"Failed; en_src_mac_part1 == {dut.en_src_mac_part1.value}, expected {bitString[2]}"
    if (bitString[3] != 'x'):
        assert dut.en_src_mac_part2.value == int(bitString[3]), f"Failed; en_src_mac_part2 == {dut.en_src_mac_part2.value}, expected {bitString[3]}"
    if (bitString[4] != 'x'):
        assert dut.en_ethertype.value == int(bitString[4]), f"Failed; en_ethertype == {dut.en_ethertype.value}, expected {bitString[4]}"
    if (bitString[5] != 'x'):
        assert dut.en_data.value == int(bitString[5]),f"Failed; en_data == {dut.en_data.value}, expected {bitString[5]}"


@cocotb.test()
async def test_standard_frame_pass(dut):
    dut._log.info("Test Begin: Standard Frame Pass")
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # idle state
    dut._log.info("STATE: IDLE")
    assert dut.is_vlan_frame.value == 0, "Failed; is_vlan_frame == 1, expected 0"
    assert dut.en_dst_mac.value == 0,"Failed; en_dst_mac == 1, expected 0"
    assert dut.en_src_mac_part1.value == 0, "Failed; en_src_mac_part1 == 1, expected 0"
    assert dut.en_src_mac_part2.value == 0,"Failed; en_src_mac_part2 == 1, expected 0"
    assert dut.en_ethertype.value == 0, "Failed; en_ethertype == 1, expected 0"
    assert dut.en_data.value == 0,"Failed; en_data.value == 1, expected 0"

    # beat1
    dut._log.info("STATE: BEAT1")
    dut.tvalid.value = 1
    dut.tkeep.value = 0xFF
    # await RisingEdge(dut.clk)
    await ClockCycles(dut.clk, 1)
    assert dut.is_vlan_frame.value == 0, "Failed; is_vlan_frame == 1, expected 0"
    assert dut.en_dst_mac.value == 1,"Failed; en_dst_mac == 0, expected 1"
    assert dut.en_src_mac_part1.value == 1, "Failed; en_src_mac_part1 == 0, expected 1"
    assert dut.en_src_mac_part2.value == 0,"Failed; en_src_mac_part2 == 1, expected 0"
    assert dut.en_ethertype.value == 0, "Failed; en_ethertype == 1, expected 0"
    assert dut.en_data.value == 0,"Failed; en_data.value == 1, expected 0"

    # beat2
    dut._log.info("STATE: BEAT2")
    await RisingEdge(dut.clk)
    assert dut.is_vlan_frame.value == 0, "Failed; is_vlan_frame == 1, expected 0"
    assert dut.en_dst_mac.value == 0,"Failed; en_dst_mac == 1, expected 0"
    assert dut.en_src_mac_part1.value == 0, "Failed; en_src_mac_part1 == 0, expected 1"
    assert dut.en_src_mac_part2.value == 1,"Failed; en_src_mac_part2 == 0, expected 1"
    assert dut.en_ethertype.value == 1, "Failed; en_ethertype == 0, expected 1"
    assert dut.en_data.value == 1,"Failed; en_data.value == 0, expected 1"

    # wait eof
    dut._log.info("STATE: WAIT EOF")
    for i in range(5):
        await RisingEdge(dut.clk)
        assert dut.is_vlan_frame.value == 0, "Failed; is_vlan_frame == 1, expected 0"
        assert dut.en_dst_mac.value == 0,"Failed; en_dst_mac == 1, expected 0"
        assert dut.en_src_mac_part1.value == 0, "Failed; en_src_mac_part1 == 1, expected 0"
        assert dut.en_src_mac_part2.value == 0,"Failed; en_src_mac_part2 == 1, expected 0"
        assert dut.en_ethertype.value == 0, "Failed; en_ethertype == 1, expected 0"
        assert dut.en_data.value == 1,"Failed; en_data.value == 0, expected 1"

    # Final Beat
    dut._log.info("STATE: LAST BEAT")
    dut.tlast.value = 1
    dut.tuser_0.value = 0 # FCS good
    await RisingEdge(dut.clk)
    assert dut.is_vlan_frame.value == 0, "Failed; is_vlan_frame == 1, expected 0"
    assert dut.en_dst_mac.value == 0,"Failed; en_dst_mac == 1, expected 0"
    assert dut.en_src_mac_part1.value == 0, "Failed; en_src_mac_part1 == 1, expected 0"
    assert dut.en_src_mac_part2.value == 0,"Failed; en_src_mac_part2 == 1, expected 0"
    assert dut.en_ethertype.value == 0, "Failed; en_ethertype == 1, expected 0"
    assert dut.en_data.value == 1,"Failed; en_data.value == 0, expected 1"
    assert dut.drop.value == 0, "Incorrectly dropped valid 64B standard frame"

    dut.tvalid.value = 1
    dut.tlast.value = 0
    await RisingEdge(dut.clk)

@cocotb.test()
async def test_vlan_frame_pass(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # beat 1
    dut.tvalid.value = 1
    dut.tkeep.value = 0xFF
    await RisingEdge(dut.clk)

    # beat 2
    dut.ethertype.value = 0x8100 
    await RisingEdge(dut.clk)
    
    # beat 3 (vlan)
    await RisingEdge(dut.clk)
    assert dut.is_vlan_frame.value == 1, "Failed to flag VLAN frame"
    assert dut.en_ethertype.value == 1, "en_ethertype should be high in VLAN state"

    # Push to 64 bytes total
    for _ in range(4):
        await RisingEdge(dut.clk)
        
    dut.tlast.value = 1
    await RisingEdge(dut.clk)
    
    assert dut.drop.value == 0, "Incorrectly dropped valid VLAN frame"

@cocotb.test()
async def test_standard_frame_length_boundary_check(dut):
    dut._log.info("TEST: test_standard_frame_length_boundary_check")
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # idle state
    dut._log.info("STATE: IDLE")
    check_enables(dut, "000000")

    # beat 1
    dut._log.info("STATE: BEAT 1")
    dut.tvalid.value = 1
    dut.tkeep.value = 0xFF
    await RisingEdge(dut.clk)
    check_enables(dut, "011000")

    # beat 2
    dut._log.info("STATE: BEAT 2")
    dut.tvalid.value = 1
    dut.tkeep.value = 0xFF
    await RisingEdge(dut.clk)
    check_enables(dut, "000111")

    # wait eof; loop to reach max length
    dut._log.info("STATE: WAIT EOF")
    for i in range(187):
        dut.tvalid.value = 1
        dut.tkeep.value = 0xFF
        await RisingEdge(dut.clk)
        check_enables(dut, "000001")

    # second last frame
    dut._log.info("STATE: SECOND LAST FRAME")
    dut.tvalid.value = 1    
    dut.tkeep.value = 0b00111111
    await RisingEdge(dut.clk)
    check_enables(dut, "000001")
    assert dut.drop.value == 0, f"Received: drop == {dut.drop.value}, expected: 0. Frame is max length but should not have been dropped."

    # last frame
    dut._log.info("STATE: LAST FRAME; LENGTH EXCEEDED")
    dut.tvalid.value = 1    
    dut.tkeep.value = 0b00000001
    dut.tlast.value = 1
    await RisingEdge(dut.clk)
    check_enables(dut, "000001")
    assert dut.drop.value == 1, f"Received: drop == {dut.drop.value}, expected: 1. Frame exceeded 1518 bytes."
    dut.tlast.value = 0

@cocotb.test()
async def test_VLAN_frame_length_boundary_check(dut):
    dut._log.info("TEST: test_standard_frame_length_boundary_check")
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # idle state
    dut._log.info("STATE: IDLE")
    check_enables(dut, "000000")

    # beat 1
    dut._log.info("STATE: BEAT 1")
    dut.tvalid.value = 1
    dut.tkeep.value = 0xFF
    await RisingEdge(dut.clk)
    check_enables(dut, "011000")

    # beat 2
    dut._log.info("STATE: BEAT 2")
    dut.ethertype.value = 0x8100 
    await RisingEdge(dut.clk)
    check_enables(dut, "100100")

    # beat 3
    dut._log.info("STATE: BEAT 3, VLAN")
    dut.tvalid.value = 1
    dut.tkeep.value = 0xFF
    await RisingEdge(dut.clk)
    check_enables(dut, "100011")

    # wait eof; loop to reach max length
    dut._log.info("STATE: WAIT EOF")
    for i in range(187):
        dut.tvalid.value = 1
        dut.tkeep.value = 0xFF
        await RisingEdge(dut.clk)
        check_enables(dut, "100001")

    # last frame
    dut._log.info("STATE: SECOND LAST FRAME")
    dut.tvalid.value = 1    
    dut.tkeep.value = 0b00000011
    await RisingEdge(dut.clk)
    check_enables(dut, "100001")
    assert dut.drop.value == 0, f"Received: drop == {dut.drop.value}, expected: 0. Frame is max length but should not have been dropped."

    dut._log.info("STATE: LAST FRAME; LENGTH EXCEEDED")
    dut.tvalid.value = 1    
    dut.tkeep.value = 0b00000001
    dut.tlast.value = 1
    await RisingEdge(dut.clk)
    check_enables(dut, "100001")
    assert dut.drop.value == 1, f"Received: drop == {dut.drop.value}, expected: 1. Frame exceeded 1522 bytes."
    dut.tlast.value = 0

@cocotb.test()
async def test_standard_frame_runt(dut):
    dut._log.info("TEST: test_standard_frame_runt")
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # idle state
    dut._log.info("STATE: IDLE")
    check_enables(dut, "000000")

    # beat 1
    dut._log.info("STATE: BEAT 1")
    dut.tvalid.value = 1
    dut.tkeep.value = 0xFF
    await RisingEdge(dut.clk)
    check_enables(dut, "011000")

    # beat 2
    dut._log.info("STATE: BEAT 2")
    dut.tvalid.value = 1
    dut.tkeep.value = 0xFF
    await RisingEdge(dut.clk)
    check_enables(dut, "000111")

    # wait eof; loop to reach max length
    dut._log.info("STATE: WAIT EOF")
    for i in range(4):
        dut.tvalid.value = 1
        dut.tkeep.value = 0xFF
        await RisingEdge(dut.clk)
        check_enables(dut, "000001")

    # last frame
    dut._log.info("STATE: LAST FRAME; LENGTH TOO SHORT")
    dut.tvalid.value = 1    
    dut.tkeep.value = 0xFF
    dut.tlast.value = 1
    await RisingEdge(dut.clk)
    check_enables(dut, "000001")
    assert dut.drop.value == 1, f"Received: drop == {dut.drop.value}, expected: 1. Frame exceeded 1518 bytes."
    dut.tlast.value = 0

