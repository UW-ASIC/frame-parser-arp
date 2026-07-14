`default_nettype none

module frame_parser_header_datapath (
    input  wire        clk,
    input  wire        rst_n,
    input wire         ena,
    //input wire         offset, <-- in block diagram, not used.

     // inputs from frame input stage
    input wire [63:0] out_tdata,
    input wire [7:0]  out_tkeep,
    input wire        out_tvalid, // (*updated tvalid)
    input wire        out_tlast,
    input wire        out_tuser,
    
    input wire        tready,

    //inputs from Control FSM stage
    input wire         is_vlan_frame,   // do we even need this?
    input wire         en_dst_mac, 
    input wire         en_src_mac_part1, 
    input wire         en_src_mac_part2,
    input wire         en_ethertype, 
    input wire         en_data,
    
    //output to Control FSM
    output reg [15:0]    ethertype,

    //outputs to metadata assembler
    output reg [47:0]    dst_mac,
    output reg [47:0]    src_mac,
    output reg [15:0]    vlan_TCI,
    output reg [15:0]    final_ethertype, // (CHANGE THIS NAME LATER)

    output reg [5:0]     payload_bit_offset,
    output reg           payload_valid,

    output wire          tuser
    
);
    // fwding t user
    assign tuser = out_tuser;

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

            if (out_tvalid && tready) begin
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
