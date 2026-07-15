# SPDX-FileCopyrightText: © 2026 UW-ASIC
# SPDX-License-Identifier: Apache-2.0

# Testbench for RTL/arp_responder_validate_match.v
# Run from the test/ directory with:
#   make -B UNIT=arp_responder_validate_match TOPLEVEL=arp_responder_validate_match
# (If your Verilog module name differs from the file name, add TOPLEVEL=<module_name>)

import cocotb
from cocotb import log
from cocotb.triggers import Timer, ClockCycles
from cocotb.clock import Clock

async def generate_clock(dut):
    """Generate clock pulses."""
    for _ in range(10):
        dut.clk.value = 0
        await Timer(1, unit="ns")
        dut.clk.value = 1
        await Timer(1, unit="ns")

# Reset the Design Under Test
async def reset_dut(dut):
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)

# Reset test helper
def test_reset_get_err_string(var_name: str):
    return f"{var_name} is non-0 during reset"
# Reset test
@cocotb.test()
async def test_reset(dut):
    """
        Tests whether the module resets to the correct values
        within 2 clock cycles.
    """
    # Start clock
    cocotb.start_soon(generate_clock(dut))
    # Apply reset signal
    log.info("Apply reset signal")
    log.info(dut.rst_n.value)
    dut.rst_n.value = 0
    log.info(dut.rst_n.value)
    await ClockCycles(dut.clk, 2)
    log.info("2 cycles passed")
    # Check signals
    log.info("Checking output signals")
    assert dut.format_valid.value == 0, test_reset_get_err_string("format_valid")
    assert dut.target_match.value == 0, test_reset_get_err_string("target_match")
    assert dut.reply_required.value == 0, test_reset_get_err_string("reply_required")
    assert dut.fire_q.value == 0, test_reset_get_err_string("fire_q")
    assert dut.drop_q.value == 0, test_reset_get_err_string("drop_q")
    assert dut.requester_mac_q.value == 0, test_reset_get_err_string("requester_mac_q")
    assert dut.requester_ip_q.value == 0, test_reset_get_err_string("requester_ip_q")
