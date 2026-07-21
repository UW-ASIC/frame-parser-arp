module meta_data_assembler (
    // input logic clk,
    input logic eof,
    input logic [13:0] len,
    input fcs_ok,

    input logic [47:0] dst_mac,
    input logic [47:0] src_mac,
    input logic [15:0] ethertype,
    input logic [11:0] vlan_id,
    input logic [2:0] pcp,
    input logic [1:0]  frame_type,

    output logic [144:0] meta_d_out
);
    logic [11:0] out_vlan; 
    logic [2:0] out_pcp;

always_comb begin
    meta_d_out[144] = eof;
    //if frame_type  is eth II ('0) zero out pcp/vlan
    out_vlan = frame_type == '0 ? '0 : vlan_id; // 
    out_pcp = frame_type == '0 ? '0 : pcp;
    meta_d_out[143:0] = {len,fcs_ok,frame_type,
    out_pcp,out_vlan,ethertype,src_mac,dst_mac};
end

endmodule
