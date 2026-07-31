`default_nettype none

module frame_parser_header_datapath (
    input  wire        clk,
    input  wire        rst_n,
    input wire         ena,
    //input wire         offset, <-- in block diagram, not used in this implementation. Instead of the Frame Control block handling offset, this Header datapath block does it instead (and forwards to metadata assembler)

     // inputs from frame input stage
    input wire [63:0] out_tdata,
    input wire [7:0]  out_tkeep,
    input wire        out_tvalid, // (*updated tvalid)
    input wire        out_tlast,
    input wire        out_tuser,
    
    input wire        tready,

    //inputs from Control FSM stage
    input wire         is_vlan_frame,   // unused in this implementation
    input wire         en_dst_mac, 
    input wire         en_src_mac_part1, 
    input wire         en_src_mac_part2,
    input wire         en_ethertype, 
    input wire         en_data,
    
    //output to Control FSM
    output reg [15:0]    ethertype,  // this is tied DIRECTLY from the controlFSM's ethertype - effectively, it gives a "naive" ethertype before we know if its VLAN or not.

    //outputs to metadata assembler
    output reg [47:0]    dst_mac,
    output reg [47:0]    src_mac,
    output wire [11:0]   vlan_id,
    output wire [2:0]    vlan_pcp,
    output wire          vlan_dei,
    output reg [15:0]    final_ethertype, // ENSURE that final_ethertype is tied to ethertype field in METADATA ASSEMBLER

    output reg [5:0]     payload_bit_offset,
    output reg           payload_valid,

    output wire          tuser,
    output wire          fcs_ok    //only added so I can easily forward this line to metadata assembler, it's just the NOT of tuser, nothing more than that. It's perfectly OK to tie tuser to nothing on the top file, and feed through fcs_ok to metadata.
    
);
    // assigning vlan_id and vlan_pcp from vlan_TCI
    reg [15:0]    vlan_TCI;
    assign vlan_pcp = is_vlan_frame ? vlan_TCI[15:13] : 3'b0;
    assign vlan_dei = is_vlan_frame ? vlan_TCI[12] : 1'b0;
    assign vlan_id  = is_vlan_frame ? vlan_TCI[11:0]  : 12'b0;
    
    // fwding t user
    assign tuser = out_tuser;
    assign fcs_ok = ~out_tuser;

    //fwds ethertype (before realizing if it's VLAN or not)
    always @(*) begin
        ethertype = 16'b0;

        if (en_src_mac_part2) begin
            ethertype = {
                out_tdata[39:32],
                out_tdata[47:40]
            };
        end
    end

    // extracting data from beats
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            dst_mac   <= 48'b0;
            src_mac   <= 48'b0;
            final_ethertype <= 16'b0;
            vlan_TCI  <= 16'b0;
            payload_valid <=1'b0;
            payload_bit_offset <=6'b0;
            end
            
        else begin 
            payload_valid <= 1'b0;
            payload_bit_offset <=6'b0;

            if (out_tvalid) begin // (out_tvalid && tready) is used instead, if tready is not tied to 1. This block and Frame control block both assume tready is always 1 - if this changes, we must rememnber to update both blocks.
                if (en_dst_mac) begin 
                    dst_mac <= {
                        out_tdata[7:0],
                        out_tdata[15:8],
                        out_tdata[23:16],
                        out_tdata[31:24],
                        out_tdata[39:32],
                        out_tdata[47:40]  
                    };
                    payload_valid <=1'b0;
                end

                if (en_src_mac_part1) begin
                    src_mac[47:32] <= {
                        out_tdata[55:48],
                        out_tdata[63:56]
                    };
                    payload_valid <=1'b0;
                end

                if (en_src_mac_part2) begin
                    src_mac[31:0] <= {
                            out_tdata[7:0],
                            out_tdata[15:8],
                            out_tdata[23:16],
                            out_tdata[31:24]
                        };
                    
                    if (en_ethertype) begin //NON-VLAN
                        final_ethertype <= {
                            out_tdata[39:32],
                            out_tdata[47:40]
                            };
                        payload_valid <= 1'b1;        //there is data in this beat too!
                        payload_bit_offset <= 6'd48;  //data0 <= out_tdata[63 ... 48]; <-- payload starts on the 7th byte if out_tdata

                    end else begin //VLAN
                        vlan_TCI <= {
                            out_tdata[55:48],
                            out_tdata[63:56]
                            };
                        payload_valid <=1'b0;          // there is no data
                    end

                end else if (en_ethertype) begin
                    final_ethertype <= {
                            out_tdata[7:0],
                            out_tdata[15:8]
                            };
                    payload_valid <=1'b1;
                    payload_bit_offset <=6'd16; //data0 <= out_tdata[63 ... 16];

                end else if (en_data) begin
                    payload_valid <= 1'b1;
                    payload_bit_offset <=6'd0; //data0 <= out_tdata[63 ... 0];, full beat of data
                end
            end
        end
    end

wire _unused = &{
    ena,
    out_tkeep,
    out_tlast
};

endmodule
