
module frame_parser_metadata_assembler (
    input  wire          clk,
    input  wire          rst_n,

    input  wire  [47:0]  dst_mac,
    input  wire  [47:0]  src_mac,
    input  wire  [15:0]  ethertype,
    input  wire  [11:0]  vlan_id,
    input  wire  [2:0]   pcp,
    input  wire  [1:0]   frame_type,
    input  wire          eof,        
    input  wire  [13:0]  frame_len,  
    input  wire          fcs_ok,     
    output wire  [144:0] metadata
);

    reg [144:0] metadata_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            metadata_q <= 145'b0;
        end else begin
            if (eof) begin
                metadata_q[144]     <= 1'b1;        
                metadata_q[143:130] <= frame_len;
                metadata_q[129]     <= fcs_ok;
                metadata_q[128:127] <= frame_type;
                if (frame_type == 2'b00) begin
                    metadata_q[126:124] <= 3'b000;  
                    metadata_q[123:112] <= 12'b000; 
                end else begin
                    metadata_q[126:124] <= pcp;
                    metadata_q[123:112] <= vlan_id;
                end
                
                metadata_q[111:96]  <= ethertype;
                metadata_q[95:48]   <= src_mac;
                metadata_q[47:0]    <= dst_mac;

            end else begin
                metadata_q[144]     <= 1'b0; 
            end
        end
    end
    assign metadata = metadata_q;

endmodule
