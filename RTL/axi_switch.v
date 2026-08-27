`default_nettype none

module axi_switch(
    input wire clk,
    input wire rst_n,

    input wire [63:0] p_tdata,
    input wire [7:0] p_tkeep,
    input wire p_tvalid,
    input wire p_tlast,
    input wire orig_tlast,
    input wire orig_payload_valid,

    input wire [15:0] w_final_ethertype,
    input wire tuser,
    output wire [63:0] s_tdata,
    output wire [7:0] s_tkeep,
    output wire s_tvalid,
    output wire s_tlast,
    output wire [0:0] s_tuser
);

wire [63:0] reversed_tdata = {p_tdata[7:0], p_tdata[15:8], p_tdata[23:16], p_tdata[31:24],
                               p_tdata[39:32], p_tdata[47:40], p_tdata[55:48], p_tdata[63:56]};
wire [7:0] reversed_tkeep = {p_tkeep[0], p_tkeep[1], p_tkeep[2], p_tkeep[3],
                              p_tkeep[4], p_tkeep[5], p_tkeep[6], p_tkeep[7]};

assign s_tdata = reversed_tdata;
assign s_tkeep = reversed_tkeep;
assign s_tvalid = p_tvalid && (w_final_ethertype == 16'h0806);
assign s_tlast = p_tlast;

reg tuser_latched;

always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        tuser_latched <= 1'b0;
    else if (orig_tlast && orig_payload_valid)
        tuser_latched <= tuser;
end

assign s_tuser = tuser_latched;


endmodule