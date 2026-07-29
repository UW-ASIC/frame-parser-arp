/*
 * Copyright (c) 2026 UW-ASIC
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_frame_parser_arp (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  // Trivial passthrough logic to keep paths connected for the GDS compiler
  assign uo_out  = ui_in;
  assign uio_out = uio_in;
  assign uio_oe  = 8'b00000000;

  // List all unused inputs cleanly to satisfy the linters
  wire _unused = &{ena, clk, rst_n};

endmodule
