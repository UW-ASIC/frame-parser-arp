# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

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


@cocotb.test()
async def test_standard_frame_pass(dut):
    dut._log.info("Test Begin: Standard Frame Pass")
    cocotb.startsoon(Clock(dut.clk, 10, units="ns").start())
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
    dut.tvalid.value = 1
    dut.tkeep.value = 0xFF
    await RisingEdge(dut.clk)
    assert dut.is_vlan_frame.value == 0, "Failed; is_vlan_frame == 1, expected 0"
    assert dut.en_dst_mac.value == 1,"Failed; en_dst_mac == 0, expected 1"
    assert dut.en_src_mac_part1.value == 1, "Failed; en_src_mac_part1 == 0, expected 1"
    assert dut.en_src_mac_part2.value == 0,"Failed; en_src_mac_part2 == 1, expected 0"
    assert dut.en_ethertype.value == 0, "Failed; en_ethertype == 1, expected 0"
    assert dut.en_data.value == 0,"Failed; en_data.value == 1, expected 0"

    # beat2
    await RisingEdge(dut.clk)
    assert dut.is_vlan_frame.value == 0, "Failed; is_vlan_frame == 1, expected 0"
    assert dut.en_dst_mac.value == 0,"Failed; en_dst_mac == 1, expected 0"
    assert dut.en_src_mac_part1.value == 0, "Failed; en_src_mac_part1 == 0, expected 1"
    assert dut.en_src_mac_part2.value == 1,"Failed; en_src_mac_part2 == 0, expected 1"
    assert dut.en_ethertype.value == 1, "Failed; en_ethertype == 0, expected 1"
    assert dut.en_data.value == 1,"Failed; en_data.value == 0, expected 1"

    # wait eof
    for i in range(5):
        await RisingEdge(dut.clk)
        assert dut.is_vlan_frame.value == 0, "Failed; is_vlan_frame == 1, expected 0"
        assert dut.en_dst_mac.value == 0,"Failed; en_dst_mac == 1, expected 0"
        assert dut.en_src_mac_part1.value == 0, "Failed; en_src_mac_part1 == 1, expected 0"
        assert dut.en_src_mac_part2.value == 0,"Failed; en_src_mac_part2 == 0, expected 1"
        assert dut.en_ethertype.value == 0, "Failed; en_ethertype == 1, expected 0"
        assert dut.en_data.value == 1,"Failed; en_data.value == 1, expected 0"

    # Final Beat
    dut.tlast.value = 1
    dut.tuser_0.value = 0 # FCS good
    await RisingEdge(dut.clk)
    assert dut.drop.value == 0, "Incorrectly dropped valid 64B standard frame"

    dut.tvalid.value = 1
    dut.tlast.value = 0
    await RisingEdge(dut.clk)

@cocotb.test()
async def test_vlan_frame_pass(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
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