`default_nettype none
module arp_responder_request_capture (
    input  wire        clk,
    input  wire        rst_n,

    // AXI-Stream Input (From Arbiter, L2 stripped)
    input  wire [63:0] s_axis_tdata,
    input  wire [7:0]  s_axis_tkeep,
    input  wire        s_axis_tvalid,
    input  wire        s_axis_tlast,
    input  wire [0:0]  s_axis_tuser,
    output wire        s_axis_tready,

    // Extracted fields to Block 2 (Validate + Match)
    output reg  [15:0] ext_opcode,
    output reg  [47:0] ext_sha,
    output reg  [31:0] ext_spa,
    output reg  [31:0] ext_tpa,
    output reg         ext_tuser,
    output reg         capture_done,
    output reg [15:0] ext_htype,
    output reg [15:0] ext_ptype,
    output reg [7:0] ext_hlen,
    output reg [7:0] ext_plen
);

// tready is always 1 - this block never stalls upstream
assign s_axis_tready = 1'b1;

// State definitions
localparam IDLE  = 3'd0;
localparam BEAT0 = 3'd1;
localparam BEAT1 = 3'd2;
localparam BEAT2 = 3'd3;
localparam WAIT_TLAST = 3'd4; //Absorbs padding

reg [2:0] state;

always @(posedge clk) begin 
    if (!rst_n) begin
            state        <= IDLE;
            ext_opcode   <= 16'd0;
            ext_sha      <= 48'd0;
            ext_spa      <= 32'd0;
            ext_tpa      <= 32'd0;
            ext_tuser    <= 1'b0;
            capture_done <= 1'b0;
            ext_htype <= 16'd0;
            ext_ptype <= 16'd0;
            ext_hlen <= 8'd0;
            ext_plen <= 8'd0;
        end else begin
            capture_done <= 1'b0;

            if (s_axis_tvalid) begin
                
                if (s_axis_tlast) begin
                    ext_tuser    <= s_axis_tuser[0];
                    capture_done <= 1'b1;
                    state        <= IDLE;
                end

                case (state)
                        IDLE: begin
                            ext_opcode <= s_axis_tdata[15:0];
                            ext_htype <= s_axis_tdata[63:48];
                            ext_ptype <= s_axis_tdata[47:32];
                            ext_hlen <= s_axis_tdata[31:24];
                            ext_plen <= s_axis_tdata[23:16];
                            if (!s_axis_tlast) state <= BEAT0;
                        end

                        BEAT0: begin
                            ext_sha <= s_axis_tdata[63:16];
                            ext_spa[31:16] <= s_axis_tdata[15:0];
                            if (!s_axis_tlast) state <= BEAT1;
                        end

                        BEAT1: begin
                            ext_spa[15:0] <= s_axis_tdata[63:48];
                            if (!s_axis_tlast) state <= BEAT2;
                        end

                        BEAT2: begin
                            ext_tpa <= s_axis_tdata[63:32];
                            if (!s_axis_tlast) state <= WAIT_TLAST;
                        end

                        WAIT_TLAST: begin
                            //absorbs padding
                        end

                        default: begin
                            state <= IDLE;
                        end
                endcase
            end
        end
    end 
endmodule