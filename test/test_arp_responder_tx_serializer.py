# SPDX-FileCopyrightText: © 2026 UW-ASIC
# SPDX-License-Identifier: Apache-2.0

# Testbench for RTL/arp_responder_tx_serializer.v
# NOTE: the module inside this file is currently named arp_tx_serializer (not the
# file name), so pass the toplevel override:
#   make -B UNIT=arp_responder_tx_serializer TOPLEVEL=arp_tx_serializer

import cocotb
from cocotb.triggers import Timer


@cocotb.test()
async def test_placeholder(dut):
    """Placeholder test — replace with real tests for this module."""
    await Timer(1, unit="ns")
