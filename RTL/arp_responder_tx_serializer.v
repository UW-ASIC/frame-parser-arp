module arp_responder_tx_serializer #(
    parameter TDATA_W = 64,
    parameter TKEEP_W = TDATA_W / 8,
    parameter PAD_TO_MIN = 1
)(
    input wire clk,
    input wire rst_n, // Active_low synchronous reset

    // from Validate + Match
    input wire fire, //1 cycle pulse: ignored unless idle
    output wire busy,

    //to or from Reply Beat Mux
    output wire [2:0] beat_idx,
    input  wire [TDATA_W-1:0]  mux_tdata,
    input  wire [TKEEP_W-1:0]  mux_tkeep,
 
    // AXI-Stream master to MAC_TX
    output wire [TDATA_W-1:0]  m_tdata,
    output wire [TKEEP_W-1:0]  m_tkeep,
    output wire                m_tvalid,
    input  wire                m_tready,
    output wire                m_tlast
);

    localparam [2:0] LAST_BEAT = PAD_TO_MIN ? 3'd7 : 3'd5;

    localparam S_IDLE = 1'b0,
               S_SEND = 1'b1;
 
    reg state_q;
    reg [2:0] beat_q;

    //beat moves on this cycle, and only on this cycle
    wire transfer  = m_tvalid && m_tready;
    wire last_xfer = transfer && (beat_q == LAST_BEAT);

    always @(posedge clk) begin
        if (!rst_n) begin
            state_q <= S_IDLE;
            beat_q <= 3'b0;
        end else begin
            case (state_q) 
            S_IDLE: begin
                if(fire) begin
                    state_q <= S_SEND;
                    beat_q <= 3'b0;
                end
            end
            S_SEND: begin
                state_q <= S_SEND;
                if (last_xfer) begin
                    state_q <= S_IDLE;
                end else if (transfer) begin
                    beat_q <= beat_q + 1;
                end
            end
            default: begin
                state_q <= S_IDLE;
            end
            endcase
    end
end

assign m_tvalid = state_q == S_SEND;
assign busy = state_q == S_SEND;
assign beat_idx = beat_q;
assign m_tlast = beat_q == LAST_BEAT;
assign m_tdata = mux_tdata;
assign m_tkeep = mux_tkeep;
endmodule
