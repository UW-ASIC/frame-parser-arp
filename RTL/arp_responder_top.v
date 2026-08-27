`default_nettype none

module arp_responder_top #(
    parameter PAD_TO_MIN = 1
)(
    input wire clk,
    input wire rst_n,

    input wire [63:0] s_tdata,
    input wire [7:0] s_tkeep,
    input wire s_tvalid,
    input wire s_tlast,
    input wire [0:0] s_tuser,
    output wire s_tready,

    input wire [47:0] own_mac,
    input wire [31:0] own_ip,

    output wire [63:0] m_tdata,
    output wire [7:0] m_tkeep,
    output wire m_tvalid,
    input wire m_tready,
    output wire m_tlast
);

wire [15:0] w_opcode;
wire [47:0] w_sha;
wire [31:0] w_spa;
wire [31:0] w_tpa;
wire w_req_tuser;
wire w_capture_done;
wire [15:0] w_htype;
wire [15:0] w_ptype;
wire [7:0] w_hlen;
wire [7:0] w_plen;
wire w_fire;
wire [47:0] w_requester_mac;
wire [31:0] w_requester_ip;
wire w_busy;
wire [2:0] w_beat_idx;
wire [63:0] w_beat_data;
wire [7:0] w_beat_tkeep;

arp_responder_request_capture u_request_capture (
    .clk(clk),
    .rst_n(rst_n),
    .s_axis_tdata(s_tdata),
    .s_axis_tkeep(s_tkeep),
    .s_axis_tvalid(s_tvalid),
    .s_axis_tlast(s_tlast),
    .s_axis_tuser(s_tuser),

    .s_axis_tready(s_tready),
    .ext_opcode(w_opcode),
    .ext_sha(w_sha),
    .ext_spa(w_spa),
    .ext_tpa(w_tpa),
    .ext_tuser(w_req_tuser),
    .capture_done(w_capture_done),
    .ext_htype(w_htype),
    .ext_ptype(w_ptype),
    .ext_hlen(w_hlen),
    .ext_plen(w_plen)
);

arp_responder_validate_match u_validate_match (
    .clk(clk),
    .rst_n(rst_n),
    .input_valid(w_capture_done),
    .frame_error(w_req_tuser),
    .tx_busy(w_busy),
    .hardware_type(w_htype),
    .protocol_type(w_ptype),
    .hardware_addr_len(w_hlen),
    .protocol_addr_len(w_plen),
    .opcode(w_opcode),
    .sender_mac(w_sha),
    .sender_ip(w_spa),
    .target_ip(w_tpa),

    .local_ip(own_ip),
    .format_valid(),
    .target_match(),
    .reply_required(),
    .fire(w_fire),
    .drop(),
    .requester_mac(w_requester_mac),
    .requester_ip(w_requester_ip)
);

arp_responder_reply_beat_mux #(
    .PAD_TO_MIN(PAD_TO_MIN)
) u_reply_beat_mux (
    .clk(clk),
    .rst_n(rst_n),
    .own_mac(own_mac),
    .own_ip(own_ip),
    .valid_packet(w_fire),
    .sha(w_requester_mac),
    .spa(w_requester_ip),
    .beat_idx(w_beat_idx),
    .beat_data(w_beat_data),
    .tkeep(w_beat_tkeep)
);

arp_responder_tx_serializer #(
    .PAD_TO_MIN(PAD_TO_MIN)
) u_tx_serializer (
    .clk(clk),
    .rst_n(rst_n),
    .fire(w_fire),
    .busy(w_busy),
    .beat_idx(w_beat_idx),
    .mux_tdata(w_beat_data),
    .mux_tkeep(w_beat_tkeep),
    .m_tdata(m_tdata),
    .m_tkeep(m_tkeep),
    .m_tvalid(m_tvalid),
    .m_tready(m_tready),
    .m_tlast(m_tlast)
);


endmodule