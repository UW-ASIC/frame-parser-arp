# SPDX-FileCopyrightText: © 2026 UW-ASIC
# SPDX-License-Identifier: Apache-2.0

# Testbench for RTL/frame_parser_metadata_assembler.v
# Run from the test/ directory with:
#   make -B UNIT=frame_parser_metadata_assembler
# (If your Verilog module name differs from the file name, add TOPLEVEL=<module_name>)
# `timescale 1ns/1ps

# module meta_data_assembler_tb;

#     logic clk = 0;
#     always #5 clk = !clk;

#     logic eof = 0;
#     logic [13:0] len = 0;
#     logic fcs_ok = 0;

#     logic [47:0] dst_mac = 0;
#     logic [47:0] src_mac = 0;
#     logic [15:0] ethertype = 0;
#     logic [11:0] vlan_id = 0;
#     logic [2:0]  pcp = 0;
#     logic [1:0]  frame_type = 0;

#     logic [144:0] meta_data_out;

#     meta_data_assembler dut (
#         .eof        (eof),
#         .len        (len),
#         .fcs_ok     (fcs_ok),
#         .dst_mac    (dst_mac),
#         .src_mac    (src_mac),
#         .ethertype  (ethertype),
#         .vlan_id    (vlan_id),
#         .pcp        (pcp),
#         .frame_type (frame_type),
#         .meta_d_out (meta_data_out)
#     );

#     task automatic drive_input(
#         input logic [15:0] ethertype_i,
#         input logic [11:0] vlan_i,
#         input logic [2:0]  pcp_i
#     );
#         @(posedge clk);

#         eof = $urandom_range(1, 0);
#         len = $urandom_range(1518, 0);
#         fcs_ok = $urandom_range(1, 0);

#         dst_mac = {$urandom(), $urandom()};
#         src_mac = {$urandom(), $urandom()};
#         ethertype = ethertype_i;
#         vlan_id = vlan_i;
#         pcp = pcp_i;
#         frame_type = $urandom_range(3, 0);
#     endtask


#     task automatic out_monitor(
#         input logic [15:0] ethertype_exp,
#         input logic [11:0] vlan_exp,
#         input logic [2:0]  pcp_exp
#     );
#         logic [11:0] vlan_actual;
#         logic [2:0]  pcp_actual;

#         @(posedge clk);

#         vlan_actual = meta_data_out[123:112];
#         pcp_actual  = meta_data_out[126:124];

#         if (ethertype_exp == 16'h0000) begin
#             assert(vlan_actual == 12'h000)
#                 else $fatal(1, "FAIL: ethertype=0, expected vlan=0, got vlan=%0h", vlan_actual);

#             assert(pcp_actual == 3'h0)
#                 else $fatal(1, "FAIL: ethertype=0, expected pcp=0, got pcp=%0h", pcp_actual);
#         end
#         else begin
#             assert(vlan_actual == vlan_exp)
#                 else $fatal(1, "FAIL: expected vlan=%0h, got vlan=%0h", vlan_exp, vlan_actual);

#             assert(pcp_actual == pcp_exp)
#                 else $fatal(1, "FAIL: expected pcp=%0h, got pcp=%0h", pcp_exp, pcp_actual);
#         end
#     endtask


#     initial begin
#         logic [15:0] ethertype_rand;
#         logic [11:0] vlan_rand;
#         logic [2:0]  pcp_rand;

#         repeat (100) begin
#             // Force half the tests to ethertype == 0
#             if ($urandom_range(1, 0))
#                 ethertype_rand = 16'h0000;
#             else
#                 ethertype_rand = $urandom_range(16'hFFFF, 16'h0001);

#             vlan_rand = $urandom_range(4095, 0);
#             pcp_rand  = $urandom_range(7, 0);

#             fork
#                 drive_input(ethertype_rand, vlan_rand, pcp_rand);
#                 out_monitor(ethertype_rand, vlan_rand, pcp_rand);
#             join
#         end

#         $display("Pass");
#         $finish;
#     end

# endmodule

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge


NUM_TESTS = 100


def mac_gen() -> int:
    return random.getrandbits(48)


async def input_driver(dut,eth_type: int,vlan_id: int,pcp: int,) -> None:

    await RisingEdge(dut.clk)
    dut.eof.value = random.randint(0, 1)
    dut.len.value = random.randint(0, 1518)
    dut.fcs_ok.value = random.randint(0, 1)

    dut.dst_mac.value = mac_gen()
    dut.src_mac.value = mac_gen()

    dut.ethertype.value = eth_type
    dut.vlan_id.value = vlan_id
    dut.pcp.value = pcp

    dut.frame_type.value = random.randint(0, 3)


async def output_monitor(dut, ethertype_expected: int, vlan_expected: int, pcp_expected: int,) -> None:

    await RisingEdge(dut.clk)
    await ReadOnly()

    metadata = int(dut.meta_d_out.value)

    # meta_d_out[123:112]
    vlan_actual = (metadata >> 112) & 0xFFF

    # meta_d_out[126:124]
    pcp_actual = (metadata >> 124) & 0x7

    if ethertype_expected == 0:
        assert vlan_actual == 0, ("FAIL: ethertype=0, expected vlan=0, "f"got vlan=0x{vlan_actual:03x}")
        assert pcp_actual == 0, ("FAIL: ethertype=0, expected pcp=0, "f"got pcp=0x{pcp_actual:x}")

    else:
        assert vlan_actual == vlan_expected, (f"FAIL: expected vlan=0x{vlan_expected:03x}, "f"got vlan=0x{vlan_actual:03x}")
        assert pcp_actual == pcp_expected, (f"FAIL: expected pcp=0x{pcp_expected:x}, "f"got pcp=0x{pcp_actual:x}")


@cocotb.test()
async def test_metadata_assembler(dut) -> None:
    """Randomized test equivalent to the SystemVerilog testbench."""

    # Initialize DUT inputs.
    dut.eof.value = 0
    dut.len.value = 0
    dut.fcs_ok.value = 0
    dut.dst_mac.value = 0
    dut.src_mac.value = 0
    dut.ethertype.value = 0
    dut.vlan_id.value = 0
    dut.pcp.value = 0
    dut.frame_type.value = 0

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await ClockCycles(dut.clk, 2)

    for test_number in range(NUM_TESTS):
        if random.randint(0, 1):
            ethertype_random = 0x0000
        else:
            ethertype_random = random.randint(0x0001, 0xFFFF)

        vlan_random = random.randint(0, 0xFFF)
        pcp_random = random.randint(0, 0x7)

        dut._log.debug("Test %d: ethertype=0x%04x vlan=0x%03x pcp=0x%x",test_number,ethertype_random,vlan_random,pcp_random,)

        driver_task = cocotb.start_soon(input_driver(dut,ethertype_random,vlan_random,pcp_random,))
        monitor_task = cocotb.start_soon(output_monitor(dut,ethertype_random,vlan_random,pcp_random,))

        await driver_task
        await monitor_task

    dut._log.info("Pass: all %d randomized tests completed", NUM_TESTS)
# @cocotb.test()
# async def test_placeholder(dut):
#     """Placeholder test — replace with real tests for this module."""
#     await Timer(1, unit="ns")
