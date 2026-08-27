`default_nettype none

module frame_parser_arp_top (
    input wire clk,
    input wire rst_n,
    input wire ena,

    //AXI_Stream slave in, from MAC
    input wire [63:0] s_tdata,
    input wire [7:0] s_tkeep,
    input wire s_tvalid,
    input wire s_tlast,
    input wire s_tuser,
    output wire s_tready,

    output wire [144:0] metadata,
    output wire drop,


    //AXI_STREAM master out
    output wire [63:0] arp_tdata,
    output wire [7:0] arp_tkeep,
    output wire arp_tvalid,
    output wire arp_tlast,
    output wire [0:0] arp_tuser,

    // AXI-Stream master out -- the ARP reply, from arp_responder_top
    output wire [63:0] reply_tdata,
    output wire [7:0] reply_tkeep,
    output wire reply_tvalid,
    input wire reply_tready,
    output wire reply_tlast
);

    //  hardcoded
    // fallback option until something loadable replaces this.
    localparam [47:0] OWN_MAC = 48'hDABCAB123456;
    localparam [31:0] OWN_IP  = 32'hC0A80101;
    // frame_parse_input to frame_control / header_datapath
    wire [63:0] w_tdata;
    wire [7:0] w_tkeep;
    wire w_tvalid;
    wire w_tlast;
    wire w_tuser;
    wire w_tready;

    // frame_control -> metadata_assembler
    wire [13:0] w_final_frame_len;
    wire w_drop;
  
    // header_datapath -> metadata_assembler
    wire [47:0] w_dst_mac;
    wire [47:0] w_src_mac;
    wire [11:0] w_vlan_id;
    wire [2:0]  w_vlan_pcp;
    wire  w_vlan_dei;
    wire [15:0] w_final_ethertype;
    wire  w_fcs_ok;

    assign drop = w_drop;

    frame_parser_input_stage u_input_stage (
        .clk (clk),
        .rst_n (rst_n),

        .tdata (s_tdata),
        .tkeep (s_tkeep),
        .tvalid (s_tvalid),
        .tlast (s_tlast),
        .tuser (s_tuser),

        .out_tready (s_tready),

        .frame_ready (w_tready),
        .header_ready (1'b1),

        .out_tdata (w_tdata),
        .out_tkeep (w_tkeep),
        .out_tvalid (w_tvalid),
        .out_tlast (w_tlast),
        .out_tuser (w_tuser)
    );
    // frame_control to and from header_datapath 
    wire [15:0] w_ethertype;
    wire w_is_vlan_frame;
    wire w_en_dst_mac;
    wire w_en_src_mac_part1;
    wire w_en_src_mac_part2;
    wire w_en_ethertype;
    wire w_en_data;


    wire w_payload_valid;
    wire w_header_tuser;
    wire wp_tvalid;
    wire [63:0] wp_tdata;
    wire [7:0] wp_tkeep;
    wire wp_tlast;
    wire [5:0] w_payload_bit_offset;

    frame_parser_frame_control u_frame_control (
        .tdata (w_tdata),
        .tkeep (w_tkeep),
        .tvalid (w_tvalid),
        .tready (w_tready),
        .tlast (w_tlast),
        .tuser_0 (w_tuser),

        .ena (ena),
        .clk (clk),
        .rst_n (rst_n),

        .ethertype (w_ethertype),

        .is_vlan_frame (w_is_vlan_frame),
        .en_dst_mac (w_en_dst_mac),
        .en_src_mac_part1 (w_en_src_mac_part1),
        .en_src_mac_part2 (w_en_src_mac_part2),
        .en_ethertype (w_en_ethertype),
        .en_data (w_en_data),

        .final_frame_len (w_final_frame_len),
        .drop (w_drop)
     );

    frame_parser_header_datapath u_header_datapath (
        .clk (clk),
        .rst_n (rst_n),
        .ena (ena),

        .out_tdata (w_tdata),
        .out_tkeep (w_tkeep),
        .out_tvalid (w_tvalid),
        .out_tlast (w_tlast),
        .out_tuser (w_tuser),

        .tready (w_tready),

        .is_vlan_frame (w_is_vlan_frame),
        .en_dst_mac (w_en_dst_mac),
        .en_src_mac_part1 (w_en_src_mac_part1),
        .en_src_mac_part2 (w_en_src_mac_part2),
        .en_ethertype (w_en_ethertype),
        .en_data (w_en_data),

        .ethertype (w_ethertype),

        .dst_mac (w_dst_mac),
        .src_mac (w_src_mac),
        .vlan_id (w_vlan_id),
        .vlan_pcp (w_vlan_pcp),
        .vlan_dei (w_vlan_dei),
        .final_ethertype (w_final_ethertype),

        .payload_bit_offset (w_payload_bit_offset),
        .payload_valid (w_payload_valid),

        .tuser (w_header_tuser),
        .fcs_ok (w_fcs_ok)


    );

    wire [1:0] w_frame_type;
    assign w_frame_type = w_is_vlan_frame ? 2'b01 : 2'b00;
    wire w_eof;
    assign w_eof = w_tlast && w_tvalid && !w_drop;

    frame_parser_metadata_assembler u_metadata_assembler(
        .clk (clk),
        .rst_n (rst_n),

        .dst_mac (w_dst_mac),
        .src_mac (w_src_mac),
        .ethertype (w_final_ethertype),
        .vlan_id (w_vlan_id),
        .pcp (w_vlan_pcp),
        .frame_type (w_frame_type),
        .eof (w_eof),
        .frame_len (w_final_frame_len),
        .fcs_ok (w_fcs_ok),

        .metadata (metadata)
        
    );



    axi_switch u_axi_switch(
        .clk (clk),
        .rst_n (rst_n),
        .p_tdata(wp_tdata),
        .p_tkeep(wp_tkeep),
        .p_tvalid(wp_tvalid),
        .p_tlast(wp_tlast),
        .orig_tlast(w_tlast),
        .orig_payload_valid(w_payload_valid),
        .w_final_ethertype(w_final_ethertype),
        .tuser(w_header_tuser),

        .s_tdata(arp_tdata),
        .s_tkeep(arp_tkeep),
        .s_tvalid(arp_tvalid),
        .s_tlast(arp_tlast),
        .s_tuser(arp_tuser)
    );

    frame_parser_payload_aligner u_payload_aligner (
        .clk (clk),
        .rst_n (rst_n),
        .ena(ena),
        .payload_valid(w_payload_valid),
        .payload_bit_offset(w_payload_bit_offset),
        .is_vlan_frame(w_is_vlan_frame),
        .tdata(w_tdata),
        .tkeep(w_tkeep),
        .tvalid(w_tvalid),
        .tlast(w_tlast),
        .p_tdata(wp_tdata),
        .p_tkeep(wp_tkeep),
        .p_tvalid(wp_tvalid),
        .p_tlast(wp_tlast)
    );

    // The ARP chain works internally in network/big-endian lane order (byte 0
    // in bits [63:56]) that's the convention axi_switch swapped into on the
    // request path. Swap back here so this module's reply port matches its own
    // MAC-facing input convention (byte 0 in bits [7:0], standard AXI-Stream).
    // Without this, every 8-byte group reaches MAC_TX reversed.
    wire [63:0] w_reply_tdata;
    wire [7:0]  w_reply_tkeep;

    assign reply_tdata = {w_reply_tdata[7:0],   w_reply_tdata[15:8],
                          w_reply_tdata[23:16], w_reply_tdata[31:24],
                          w_reply_tdata[39:32], w_reply_tdata[47:40],
                          w_reply_tdata[55:48], w_reply_tdata[63:56]};
    assign reply_tkeep = {w_reply_tkeep[0], w_reply_tkeep[1],
                          w_reply_tkeep[2], w_reply_tkeep[3],
                          w_reply_tkeep[4], w_reply_tkeep[5],
                          w_reply_tkeep[6], w_reply_tkeep[7]};

    arp_responder_top u_arp_responder (
        .clk(clk),
        .rst_n(rst_n),

        .s_tdata(arp_tdata),
        .s_tkeep(arp_tkeep),
        .s_tvalid(arp_tvalid),
        .s_tlast(arp_tlast),
        .s_tuser(arp_tuser),
        .s_tready(),

        .own_mac(OWN_MAC),
        .own_ip(OWN_IP),

        .m_tdata(w_reply_tdata),
        .m_tkeep(w_reply_tkeep),
        .m_tvalid(reply_tvalid),
        .m_tready(reply_tready),
        .m_tlast(reply_tlast)
    );

endmodule