/*
 * Copyright (c) 2026 UW-ASIC
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module frame_parser_frame_control (
    input  wire [63:0] tdata,
    input  wire [7:0]  tkeep,   
    input  wire        tvalid,   
    output reg         tready,  
    input  wire        tlast,   
    input  wire        tuser_0,

    input  wire        ena,      // always 1 when the design is powered
    input  wire        clk,      // clock
    input  wire        rst_n,    // reset_n - low to reset

    input  wire [15:0] ethertype,
    output reg         is_vlan_frame,
    output reg         en_dst_mac, 
    output reg         en_src_mac_part1, 
    output reg         en_src_mac_part2,
    output reg         en_ethertype, 
    output reg         en_data,

    output reg  [13:0] final_frame_len,
    output reg         drop
);


  // List all unused inputs cleanly to satisfy the linters
  wire _unused = &tdata & ena;

  // States
  localparam IDLE         = 3'd0;
  localparam BEAT_1       = 3'd1;
  localparam BEAT_2       = 3'd2;
  localparam BEAT_3_VLAN  = 3'd3;
  localparam WAIT_EOF     = 3'd4;
  localparam LAST_FRAME   = 3'd5;

  reg [2:0] present_state;
  reg [2:0] next_state;

  reg [13:0] frame_len;
  reg [4:0]  bytes_kept;

  wire vlan_detected = (ethertype == 16'h8100) && (next_state == BEAT_2);
  reg vlan_remembered;






  // Frame Length Counting =====================================================
  // check if you do  * or posedge clk since usually case statements you should do posedge clock but i'm not sure i think u might be right 
  always@(*) begin
    case (tkeep) 
      8'b00000001 : bytes_kept = 4'd1;
      8'b00000011 : bytes_kept = 4'd2;
      8'b00000111 : bytes_kept = 4'd3;
      8'b00001111 : bytes_kept = 4'd4;
      8'b00011111 : bytes_kept = 4'd5;
      8'b00111111 : bytes_kept = 4'd6;
      8'b01111111 : bytes_kept = 4'd7;
      8'b11111111 : bytes_kept = 4'd8;
      default     : bytes_kept = 4'd0;
    endcase
  end
  
  always@(posedge clk, negedge rst_n) begin
    if (!rst_n) begin
      frame_len <= 14'd0;
    end else if (tvalid) begin
      if ((next_state != IDLE)) begin
        frame_len <= frame_len + bytes_kept;
      end else begin
        frame_len <= 14'd0;
      end
    end else begin
      frame_len <= frame_len;
    end
  end


  // VLAN Rememberance =====================================================
  always@(posedge clk, negedge rst_n) begin
    if (!rst_n) begin
      vlan_remembered <= 1'b0;
    end else if (next_state == BEAT_2) begin
      vlan_remembered <= vlan_detected;
    end else if (present_state == IDLE) begin
      vlan_remembered <= 1'b0;
    end else begin
      vlan_remembered <= vlan_remembered;
    end
  end



  // FSM =======================================================================

  // State Assignment
  always@(posedge clk, negedge rst_n) begin
    if (!rst_n) begin
      present_state <= IDLE;
    end else begin
      present_state <= next_state;
    end
  end

  // Next State Logic
  always@(*) begin
    if (tvalid) begin
      case (present_state) 

        IDLE        : begin
          next_state = BEAT_1;
        end
        BEAT_1      : begin
          next_state = BEAT_2;
        end
        BEAT_2      : begin
          if (is_vlan_frame) begin  // checks directly, since is_vlan_frame updates next cycle
            next_state = BEAT_3_VLAN;
          end else begin
            next_state = WAIT_EOF;
          end
        end
        BEAT_3_VLAN : begin
          next_state = WAIT_EOF;
        end
        WAIT_EOF    : begin
          if (tlast) begin
            next_state = LAST_FRAME;
          end else begin
            next_state = WAIT_EOF;
          end
        end
        LAST_FRAME  : begin
          next_state = IDLE;
        end
        default : next_state = present_state;

      endcase
    end else begin
      next_state = present_state;
    end
  end


  // Output Logic
  always@(*) begin

      // Enable and Frame Validation Handling
      case (next_state) 
      
        IDLE        : begin
          en_dst_mac        = 1'b0;
          en_src_mac_part1  = 1'b0;
          en_src_mac_part2  = 1'b0;
          en_ethertype      = 1'b0; 
          en_data           = 1'b0;
        end

        BEAT_1      : begin
          en_dst_mac        = 1'b1;
          en_src_mac_part1  = 1'b1;
          en_src_mac_part2  = 1'b0;
          en_ethertype      = 1'b0; 
          en_data           = 1'b0;
        end

        BEAT_2      : begin
          en_dst_mac        = 1'b0;
          en_src_mac_part1  = 1'b0;
          en_src_mac_part2  = 1'b1;
          
          if (vlan_detected) begin
            en_ethertype      = 1'b0; 
            en_data           = 1'b0;
          end else begin
            en_ethertype      = 1'b1; 
            en_data           = 1'b1;
          end
          
        end

        BEAT_3_VLAN : begin
          en_dst_mac        = 1'b0;
          en_src_mac_part1  = 1'b0;
          en_src_mac_part2  = 1'b0;
          en_ethertype      = 1'b1; 
          en_data           = 1'b1;
          // is_vlan_frame remains as determined in BEAT_2; latched
        end

        WAIT_EOF    : begin
          en_dst_mac        = 1'b0;
          en_src_mac_part1  = 1'b0;
          en_src_mac_part2  = 1'b0;
          en_ethertype      = 1'b0; 
          en_data           = 1'b1;
          // is_vlan_frame remains as determined in BEAT_2; 
        end

        LAST_FRAME    : begin
          en_dst_mac        = 1'b0;
          en_src_mac_part1  = 1'b0;
          en_src_mac_part2  = 1'b0;
          en_ethertype      = 1'b0; 
          en_data           = 1'b1;
          // is_vlan_frame remains as determined in BEAT_2; 
        end

        default : begin
          en_dst_mac        = 1'b0;
          en_src_mac_part1  = 1'b0;
          en_src_mac_part2  = 1'b0;
          en_ethertype      = 1'b0; 
          en_data           = 1'b0;
        end

    endcase

    // Drop Handling
    if (tlast && tvalid) begin
      // Drop is high if: FCS failed || frame is too long || frame is a runt (less than 64 bytes)
      drop = ((tuser_0 == 1'b1) || ((frame_len + bytes_kept) > (is_vlan_frame ? 14'd1522 : 14'd1518)) || ((frame_len + bytes_kept) < 14'd64));
      // output the frame length on the final beat
      final_frame_len <= frame_len;
    end else begin
      drop = 1'b0;
      final_frame_len <= 14'b0;
    end

    // VLAN_Frame En Handling
    is_vlan_frame = vlan_remembered || vlan_detected;

    // Ready Signal: Always high
    tready = 1'b1;
    
  end


endmodule
