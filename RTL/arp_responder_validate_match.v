/*
 * Copyright (c) 2026 UW-ASIC
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module arp_responder_validate_match (
    input  wire        clk,
    input  wire        rst_n,

    // One-cycle pulse from request_capture when all parsed fields below are valid.
    input  wire        input_valid,
    // Set when the upstream parser/capture block saw a bad frame, for example bad FCS.
    input  wire        frame_error,
    // TX serializer is already sending a reply, so this request cannot be accepted.
    input  wire        tx_busy,

    // ARP header fields, already parsed into network-order integer values.
    input  wire [15:0] hardware_type,
    input  wire [15:0] protocol_type,
    input  wire [7:0]  hardware_addr_len,
    input  wire [7:0]  protocol_addr_len,
    input  wire [15:0] opcode,

    // Requester address fields forwarded to the reply image builder on fire.
    input  wire [47:0] sender_mac,
    input  wire [31:0] sender_ip,

    // TPA from the request and configured local IPv4 address.
    input  wire [31:0] target_ip,
    input  wire [31:0] local_ip,

    // Registered one-cycle results for the same request.
    output wire        format_valid,
    output wire        target_match,
    output wire        reply_required,
    output wire        fire,
    output wire        drop,
    output wire [47:0] requester_mac,
    output wire [31:0] requester_ip
);

    localparam [15:0] ARP_HTYPE_ETHERNET = 16'h0001;
    localparam [15:0] ARP_PTYPE_IPV4     = 16'h0800;
    localparam [7:0]  ARP_HLEN_MAC       = 8'd6;
    localparam [7:0]  ARP_PLEN_IPV4      = 8'd4;
    localparam [15:0] ARP_OPER_REQUEST   = 16'h0001;

    // Format means "Ethernet/IPv4 ARP request"; it does not mean "for us".
    wire hw_type_ok    = (hardware_type == ARP_HTYPE_ETHERNET);
    wire proto_type_ok = (protocol_type == ARP_PTYPE_IPV4);
    wire hw_len_ok     = (hardware_addr_len == ARP_HLEN_MAC);
    wire proto_len_ok  = (protocol_addr_len == ARP_PLEN_IPV4);
    wire opcode_ok     = (opcode == ARP_OPER_REQUEST);

    wire format_valid_w = input_valid &&
                          hw_type_ok &&
                          proto_type_ok &&
                          hw_len_ok &&
                          proto_len_ok &&
                          opcode_ok;

    // Match is intentionally separate: an ARP reply can target us but is not replyable.
    wire target_match_w = input_valid && (target_ip == local_ip);

    // A reply is useful only for a clean request aimed at this local IP.
    wire reply_required_w = format_valid_w && target_match_w && !frame_error;

    // No queue here: accept when TX is idle, otherwise drop the captured request.
    wire fire_w = reply_required_w && !tx_busy;
    wire drop_w = input_valid && !fire_w;

    reg format_valid_q;
    reg target_match_q;
    reg reply_required_q;
    reg fire_q;
    reg drop_q;
    reg [47:0] requester_mac_q;
    reg [31:0] requester_ip_q;

    // Register the decision so downstream blocks see a clean one-cycle pulse.
    always @(posedge clk) begin
        if (!rst_n) begin
            format_valid_q   <= 1'b0;
            target_match_q   <= 1'b0;
            reply_required_q <= 1'b0;
            fire_q           <= 1'b0;
            drop_q           <= 1'b0;
            requester_mac_q  <= 48'd0;
            requester_ip_q   <= 32'd0;
        end else begin
            format_valid_q   <= format_valid_w;
            target_match_q   <= target_match_w;
            reply_required_q <= reply_required_w;
            fire_q           <= fire_w;
            drop_q           <= drop_w;
            requester_mac_q  <= fire_w ? sender_mac : 48'd0;
            requester_ip_q   <= fire_w ? sender_ip : 32'd0;
        end
    end

    assign format_valid   = format_valid_q;
    assign target_match   = target_match_q;
    assign reply_required = reply_required_q;
    assign fire           = fire_q;
    assign drop           = drop_q;
    assign requester_mac  = requester_mac_q;
    assign requester_ip   = requester_ip_q;

endmodule
