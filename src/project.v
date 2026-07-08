/*
 * Ethernet Header Extractor for UW-ASIC frame-parser-arp Tiny Tapeout project.
 *
 * This file uses the Tiny Tapeout / UW-ASIC top-level module skeleton:
 *   module tt_um_frame_parser_arp(ui_in, uo_out, uio_in, uio_out, uio_oe, ena, clk, rst_n)
 *
 * Input protocol, one byte per accepted clock:
 *   ui_in[7:0] = Ethernet frame byte in wire order
 *   uio_in[0]  = byte_valid
 *   uio_in[1]  = start_of_frame, asserted with byte 0
 *   uio_in[2]  = end_of_frame, asserted with final byte
 *
 * Output protocol:
 *   uio_out[3] = byte_ready
 *   uio_out[4] = header_done pulse
 *   uio_out[5] = frame_error, latched for current/last frame
 *   uio_out[6] = VLAN present for current/last parsed header
 *   uio_out[7] = metadata output byte valid
 *   uo_out     = serialized metadata byte while uio_out[7] is high
 *
 * Serialized metadata order:
 *   0..5   destination MAC, most-significant byte first
 *   6..11  source MAC, most-significant byte first
 *   12..13 EtherType, network byte order
 *   14..15 VLAN TCI, network byte order; zero when untagged
 *   16     status = {1'b0, frame_error, vlan_present, header_length[4:0]}
 *
 * Supported headers:
 *   - Ethernet II, 14-byte header
 *   - One IEEE 802.1Q VLAN tag with TPID 16'h8100, 18-byte header
 */

`default_nettype none

module tt_um_frame_parser_arp (
    input  wire [7:0] ui_in,    // Dedicated inputs: Ethernet byte stream
    output wire [7:0] uo_out,   // Dedicated outputs: serialized metadata byte
    input  wire [7:0] uio_in,   // IO input path: valid/SOF/EOF controls
    output wire [7:0] uio_out,  // IO output path: ready/status controls
    output wire [7:0] uio_oe,   // IO enable path, active high: 0=input, 1=output
    input  wire       ena,      // High when this design is selected
    input  wire       clk,      // Clock
    input  wire       rst_n     // Active-low reset
);

    localparam [1:0] ST_IDLE  = 2'd0;
    localparam [1:0] ST_PARSE = 2'd1;
    localparam [1:0] ST_DRAIN = 2'd2;

    localparam [15:0] VLAN_TPID = 16'h8100;

    wire        byte_valid;
    wire        start_of_frame;
    wire        end_of_frame;
    wire        byte_ready;
    wire        accept_byte;
    wire [15:0] completed_outer_type;
    wire [15:0] completed_inner_type;
    wire        header_completes_untagged;
    wire        header_completes_tagged;

    reg [1:0]  state;
    reg [4:0]  byte_index;
    reg [7:0]  outer_type_hi;

    reg [47:0] dst_mac_reg;
    reg [47:0] src_mac_reg;
    reg [15:0] ethertype_reg;
    reg [15:0] vlan_tci_reg;
    reg        vlan_present_reg;
    reg [4:0]  header_length_reg;
    reg        header_done_reg;
    reg        frame_error_reg;

    reg [47:0] out_dst_mac;
    reg [47:0] out_src_mac;
    reg [15:0] out_ethertype;
    reg [15:0] out_vlan_tci;
    reg        out_vlan_present;
    reg [4:0]  out_header_length;
    reg        out_frame_error;
    reg [4:0]  out_index;
    reg        out_active;
    reg [7:0]  out_byte;

    assign byte_valid     = uio_in[0];
    assign start_of_frame = uio_in[1];
    assign end_of_frame   = uio_in[2];

    // Hold input bytes while the 17-byte metadata result is being serialized.
    assign byte_ready  = ena && !out_active;
    assign accept_byte = byte_valid && byte_ready;

    assign completed_outer_type = {outer_type_hi, ui_in};
    assign completed_inner_type = {ethertype_reg[15:8], ui_in};

    assign header_completes_untagged =
        (state == ST_PARSE) &&
        (byte_index == 5'd13) &&
        (completed_outer_type != VLAN_TPID);

    assign header_completes_tagged =
        (state == ST_PARSE) &&
        (byte_index == 5'd17) &&
        vlan_present_reg;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state             <= ST_IDLE;
            byte_index        <= 5'd0;
            outer_type_hi     <= 8'd0;
            dst_mac_reg       <= 48'd0;
            src_mac_reg       <= 48'd0;
            ethertype_reg     <= 16'd0;
            vlan_tci_reg      <= 16'd0;
            vlan_present_reg  <= 1'b0;
            header_length_reg <= 5'd0;
            header_done_reg   <= 1'b0;
            frame_error_reg   <= 1'b0;
            out_dst_mac       <= 48'd0;
            out_src_mac       <= 48'd0;
            out_ethertype     <= 16'd0;
            out_vlan_tci      <= 16'd0;
            out_vlan_present  <= 1'b0;
            out_header_length <= 5'd0;
            out_frame_error   <= 1'b0;
            out_index         <= 5'd0;
            out_active        <= 1'b0;
        end else begin
            header_done_reg <= 1'b0;

            if (!ena) begin
                state      <= ST_IDLE;
                byte_index <= 5'd0;
                out_index  <= 5'd0;
                out_active <= 1'b0;
            end else begin
                // Serialize one metadata byte per clock when a header has completed.
                if (out_active) begin
                    if (out_index == 5'd16) begin
                        out_index  <= 5'd0;
                        out_active <= 1'b0;
                    end else begin
                        out_index <= out_index + 5'd1;
                    end
                end

                if (accept_byte) begin
                    case (state)
                        ST_IDLE: begin
                            if (start_of_frame) begin
                                dst_mac_reg       <= 48'd0;
                                src_mac_reg       <= 48'd0;
                                ethertype_reg     <= 16'd0;
                                vlan_tci_reg      <= 16'd0;
                                vlan_present_reg  <= 1'b0;
                                header_length_reg <= 5'd0;
                                outer_type_hi     <= 8'd0;
                                frame_error_reg   <= 1'b0;

                                // Byte 0 is the first destination-MAC byte.
                                dst_mac_reg[47:40] <= ui_in;
                                byte_index         <= 5'd1;

                                if (end_of_frame) begin
                                    // A one-byte frame cannot contain a valid Ethernet header.
                                    frame_error_reg <= 1'b1;
                                    state           <= ST_IDLE;
                                    byte_index      <= 5'd0;
                                end else begin
                                    state <= ST_PARSE;
                                end
                            end else begin
                                // A valid byte without SOF while idle is malformed.
                                frame_error_reg <= 1'b1;
                            end
                        end

                        ST_PARSE: begin
                            byte_index <= byte_index + 5'd1;

                            case (byte_index)
                                5'd1:  dst_mac_reg[39:32] <= ui_in;
                                5'd2:  dst_mac_reg[31:24] <= ui_in;
                                5'd3:  dst_mac_reg[23:16] <= ui_in;
                                5'd4:  dst_mac_reg[15:8]  <= ui_in;
                                5'd5:  dst_mac_reg[7:0]   <= ui_in;

                                5'd6:  src_mac_reg[47:40] <= ui_in;
                                5'd7:  src_mac_reg[39:32] <= ui_in;
                                5'd8:  src_mac_reg[31:24] <= ui_in;
                                5'd9:  src_mac_reg[23:16] <= ui_in;
                                5'd10: src_mac_reg[15:8]  <= ui_in;
                                5'd11: src_mac_reg[7:0]   <= ui_in;

                                5'd12: outer_type_hi <= ui_in;

                                5'd13: begin
                                    if (completed_outer_type == VLAN_TPID) begin
                                        vlan_present_reg <= 1'b1;
                                    end else begin
                                        // Untagged Ethernet II header is complete.
                                        ethertype_reg     <= completed_outer_type;
                                        vlan_tci_reg      <= 16'd0;
                                        header_length_reg <= 5'd14;
                                        header_done_reg   <= 1'b1;

                                        out_dst_mac       <= dst_mac_reg;
                                        out_src_mac       <= src_mac_reg;
                                        out_ethertype     <= completed_outer_type;
                                        out_vlan_tci      <= 16'd0;
                                        out_vlan_present  <= 1'b0;
                                        out_header_length <= 5'd14;
                                        out_frame_error   <= 1'b0;
                                        out_index         <= 5'd0;
                                        out_active        <= 1'b1;

                                        byte_index <= 5'd0;
                                        if (end_of_frame) begin
                                            state <= ST_IDLE;
                                        end else begin
                                            state <= ST_DRAIN;
                                        end
                                    end
                                end

                                5'd14: vlan_tci_reg[15:8]  <= ui_in;
                                5'd15: vlan_tci_reg[7:0]   <= ui_in;
                                5'd16: ethertype_reg[15:8] <= ui_in;

                                5'd17: begin
                                    // VLAN-tagged Ethernet II header is complete.
                                    ethertype_reg     <= completed_inner_type;
                                    header_length_reg <= 5'd18;
                                    header_done_reg   <= 1'b1;

                                    out_dst_mac       <= dst_mac_reg;
                                    out_src_mac       <= src_mac_reg;
                                    out_ethertype     <= completed_inner_type;
                                    out_vlan_tci      <= vlan_tci_reg;
                                    out_vlan_present  <= 1'b1;
                                    out_header_length <= 5'd18;
                                    out_frame_error   <= 1'b0;
                                    out_index         <= 5'd0;
                                    out_active        <= 1'b1;

                                    byte_index <= 5'd0;
                                    if (end_of_frame) begin
                                        state <= ST_IDLE;
                                    end else begin
                                        state <= ST_DRAIN;
                                    end
                                end

                                default: begin
                                    frame_error_reg <= 1'b1;
                                    state           <= ST_DRAIN;
                                    byte_index      <= 5'd0;
                                end
                            endcase

                            // EOF before byte 13/17 means the Ethernet header was truncated.
                            if (end_of_frame &&
                                !header_completes_untagged &&
                                !header_completes_tagged) begin
                                frame_error_reg <= 1'b1;
                                state           <= ST_IDLE;
                                byte_index      <= 5'd0;
                            end
                        end

                        ST_DRAIN: begin
                            // Header is already extracted; consume payload until EOF.
                            if (end_of_frame) begin
                                state      <= ST_IDLE;
                                byte_index <= 5'd0;
                            end
                        end

                        default: begin
                            state           <= ST_IDLE;
                            byte_index      <= 5'd0;
                            frame_error_reg <= 1'b1;
                        end
                    endcase
                end
            end
        end
    end

    always @(*) begin
        out_byte = 8'h00;
        case (out_index)
            5'd0:  out_byte = out_dst_mac[47:40];
            5'd1:  out_byte = out_dst_mac[39:32];
            5'd2:  out_byte = out_dst_mac[31:24];
            5'd3:  out_byte = out_dst_mac[23:16];
            5'd4:  out_byte = out_dst_mac[15:8];
            5'd5:  out_byte = out_dst_mac[7:0];
            5'd6:  out_byte = out_src_mac[47:40];
            5'd7:  out_byte = out_src_mac[39:32];
            5'd8:  out_byte = out_src_mac[31:24];
            5'd9:  out_byte = out_src_mac[23:16];
            5'd10: out_byte = out_src_mac[15:8];
            5'd11: out_byte = out_src_mac[7:0];
            5'd12: out_byte = out_ethertype[15:8];
            5'd13: out_byte = out_ethertype[7:0];
            5'd14: out_byte = out_vlan_tci[15:8];
            5'd15: out_byte = out_vlan_tci[7:0];
            5'd16: out_byte = {1'b0, out_frame_error, out_vlan_present, out_header_length};
            default: out_byte = 8'h00;
        endcase
    end

    assign uo_out = out_active ? out_byte : 8'h00;

    // uio[2:0] are inputs; uio[7:3] are outputs.
    assign uio_oe  = 8'b11111000;
    assign uio_out = {
        out_active,       // bit 7: serialized metadata byte is valid
        vlan_present_reg, // bit 6: current/last parsed header had one 0x8100 VLAN tag
        frame_error_reg,  // bit 5: current/last frame error
        header_done_reg,  // bit 4: one-cycle header-complete pulse
        byte_ready,       // bit 3: input byte may be accepted
        3'b000            // bits 2:0 are configured as inputs
    };

    // These bidirectional pins are configured as outputs, so their input path is unused.
    wire _unused = &{1'b0, uio_in[7:3]};

endmodule

`default_nettype wire
