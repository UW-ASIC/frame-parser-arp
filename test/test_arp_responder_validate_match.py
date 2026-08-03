# SPDX-FileCopyrightText: © 2026 UW-ASIC
# SPDX-License-Identifier: Apache-2.0

# Testbench for RTL/arp_responder_validate_match.v
# Run from the test/ directory with:
#   make -B UNIT=arp_responder_validate_match
# (If your Verilog module name differs from the file name, add TOPLEVEL=<module_name>)

import cocotb
from cocotb.triggers import Timer


@cocotb.test()
async def test_placeholder(dut):
    """Placeholder test — replace with real tests for this module."""
    await Timer(1, unit="ns")
