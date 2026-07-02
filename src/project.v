/*
 * Copyright (c) 2026 UW-ASIC
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_frame_parser_arp (
    input  wire [63:0]  tdata,
    input  wire [7:0]   tkeep,   
    input  wire         tvalid,   // IOs: Input path
    output wire         tready,  // IOs: Output path
    input  wire         tlast,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire         tuser_0,

    input  wire       ena,      // always 1 when the design is powered
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset

    input  wire [15:0] ethertype;
    output reg        is_vlan_frame;
    output wire       en_dst_mac, 
    output wire       en_src_mac_part1, 
    output wire       en_src_mac_part2,
    output wire       en_ethertype, 
    output wire       en_data,

    output reg      drop
);


  // List all unused inputs cleanly to satisfy the linters
  wire _unused = &ena;

  // States
  localparam IDLE         = 3'd0;
  localparam BEAT_1       = 3'd1;
  localparam BEAT_2       = 3'd2;
  localparam BEAT_3_VLAN  = 3'd3;
  localparam WAIT_EOF     = 3'd4;

  reg [2:0] present_state;
  reg [2:0] next_state;

  reg [13:0] frame_len;
  reg [4:0]  bytes_kept;

  wire vlan_detected = (ethertype == 16'h8100) && (present_state == BEAT_2);
  reg vlan_remembered;






  // Frame Length Counting =====================================================
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
      if ((present_state != IDLE)) begin
        frame_len <= frame_len + bytes_kept;
      end else begin
        frame_len <= 14'd0;
      end
    end else begin
      frame_len <= frame_len;
    end
  end





  // FSM =======================================================================
  // Next State Logic
  always@(*) begin
    case (present_state) 

      IDLE        : begin
        next_state = tvalid ? BEAT_1 : IDLE;
      end
      BEAT_1      : begin
        next_state = tvalid ? BEAT_2 : BEAT_1;
      end
      BEAT_2      : begin
        if (vlan_detected) begin  // checks directly, since is_vlan_frame updates next cycle
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
          next_state = IDLE;
        end else begin
          next_state = WAIT_EOF;
        end
      end
      default : next_state = present_state;

    endcase
  end


  // State Assignment
  always@(posedge clk, negedge rst_n) begin
    if (!rst_n) begin
      present_state <= IDLE;
    end else begin
      present_state <= next_state;
    end
  end


  // VLAN Frame Rememberance
  always@(posedge clk, negedge rst_n) begin
    if (!rst_n) begin
      vlan_remembered <= 1'b0;
    end else if (present_state == BEAT_2) begin
      vlan_remembered <= (vlan_detected) ? 1'b1 : 1'b0;
    end else if (present_state == IDLE) begin
      vlan_remembered <= 1'b0;
    end else begin
      vlan_remembered <= vlan_remembered;
    end
  end


  // Output Logic
  always@(*) begin

      // Enable and Frame Validation Handling
      case (present_state) 
      
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
    end else begin
      drop = 1'b0;
    end

    // VLAN_Frame En Handling
    is_vlan_frame = vlan_remembered || vlan_detected;
    
  end


endmodule
