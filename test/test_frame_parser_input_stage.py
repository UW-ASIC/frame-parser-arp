# SPDX-FileCopyrightText: © 2026 UW-ASIC
# SPDX-License-Identifier: Apache-2.0

# Testbench for RTL/frame_parser_input_stage.v
# Run from the test/ directory with:
#   make -B UNIT=frame_parser_input_stage
# (If your Verilog module name differs from the file name, add TOPLEVEL=<module_name>)

import cocotb
from cocotb.triggers import Timer
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import FallingEdge
from cocotb.triggers import ClockCycles
from cocotb.types import Logic
from cocotb.types import LogicArray
import random

async def reset_module(dut):
    dut._log.info("Reset")
    dut.rst_n.value = 0
    dut.tvalid.value = 0
    dut.frame_ready.value = 1
    dut.header_ready.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

async def drive_frame(dut):
    dut.tdata.value = random.getrandbits(64)
    dut.tkeep.value = 0xFF
    dut.tvalid.value = 1
    dut.tlast.value = 0
    dut.tuser.value = 0
    await ClockCycles(dut.clk, 1)
    dut.tvalid.value = 0
    await ClockCycles(dut.clk, 5)
    
# test driving a frame then idling to ensure valid drops
@cocotb.test()
async def test_valid_drops(dut):
    dut._log.info("Start tvalid Drops on Idle Buffer Test")

    # Set the clock period to 100 ns (10 MHz)
    clock = Clock(dut.clk, 100, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset Module
    await reset_module(dut)
    
    # Drive a frame
    await drive_frame(dut)

    # Check valid drops
    assert dut.out_tvalid.value == 0, f"Expected out_tvalid to clear, was high"

    dut._log.info("tvalid Drops on Idle Buffer Test completed successfully")

    

# stalling downstream mid-frame to ensure no dropped beats
@cocotb.test()
async def test_skid_buffer_stall(dut):
    dut._log.info("Start Stall Test")

    # Set the clock period to 100 ns (10 MHz)
    clock = Clock(dut.clk, 100, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset Module
    await reset_module(dut)
    
    # Drive a few frames
    for i in range(5):
        await drive_frame(dut)

    dut.frame_ready.value = 0
    await ClockCycles(dut.clk, 5)
    assert dut.out_tready.value == 0, f"Expected active low out_tready, stall logic fails"

    dut.frame_ready.value = 1
    await ClockCycles(dut.clk, 5)

    dut.header_ready.value = 0
    await ClockCycles(dut.clk, 5)
    assert dut.out_tready.value == 0, f"Expected active low out_tready, stall logic fails"

    dut.header_ready.value = 1
    await ClockCycles(dut.clk, 5)
    assert dut.out_tready.value == 1, f"Expected active low out_tready, stall logic fails"

    dut._log.info("Stall Test completed successfully")

# injecting a tvalid bubble mid-frame to ensure no garbage beats
@cocotb.test()
async def test_tvalid_bubble(dut):
    dut._log.info("Start tvalid Bubble Test")

    # Set the clock period to 100 ns (10 MHz)
    clock = Clock(dut.clk, 100, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset Module
    await reset_module(dut)
    
    # Drive a few frames
    for i in range(3):
        await drive_frame(dut)

    await ClockCycles(dut.clk, 5)

    # Drive tvalid mid-frame
    await RisingEdge(dut.clk)
    dut.tdata.value = random.getrandbits(64)
    dut.tkeep.value = 0xFF
    dut.tvalid.value = 0
    dut.tlast.value = 0
    dut.tuser.value = 0
    await FallingEdge(dut.clk)
    dut.tvalid.value = 1
    await ClockCycles(dut.clk, 1)
    # Sample mid-cycle so the clock edge's registered updates have settled --
    # reading immediately after ClockCycles races the NBA update and returns
    # the previous cycle's value. Same RisingEdge-then-FallingEdge pattern the
    # other testbenches in this directory use.
    await FallingEdge(dut.clk)

    # tvalid=1 was only just sampled into the first pipeline stage, so it
    # hasn't reached out_tvalid yet (this block is a 2-stage pipeline).
    assert dut.out_tkeep.value == 0xFF, f"Expected 0xFF, got {dut.out_tkeep.value}"
    assert dut.out_tvalid.value == 0, f"Expected 0, got {dut.out_tvalid.value}"
    assert dut.out_tlast.value == 0, f"Expected 0, got {dut.out_tlast.value}"
    assert dut.out_tuser.value == 0, f"Expected 0, got {dut.out_tuser.value}"

    # One more cycle for it to reach the output stage.
    await ClockCycles(dut.clk, 1)
    await FallingEdge(dut.clk)
    assert dut.out_tkeep.value == 0xFF, f"Expected 0xFF, got {dut.out_tkeep.value}"
    assert dut.out_tvalid.value == 1, f"Expected 1, got {dut.out_tvalid.value}"
    assert dut.out_tlast.value == 0, f"Expected 0, got {dut.out_tlast.value}"
    assert dut.out_tuser.value == 0, f"Expected 0, got {dut.out_tuser.value}"

    dut._log.info("tvalid Bubble Test completed successfully")