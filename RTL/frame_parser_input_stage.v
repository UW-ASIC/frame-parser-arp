`default_nettype none

module frame_parser_input (
    input wire        clk, 
    input wire        rst_n,

    // inputs from MAC
    input wire [63:0] tdata,
    input wire [7:0]  tkeep,
    input wire        tvalid,
    input wire        tlast,
    input wire        tuser,

    // outputs to MAC
    output reg       out_tready,
    
    // inputs from frame control + header datapath
    input wire        frame_ready,
    input wire        header_ready,

    // outputs to frame control + header datapath
    output reg [63:0] out_tdata,
    output reg [7:0]  out_tkeep,
    output reg        out_tvalid,
    output reg        out_tlast,
    output reg        out_tuser
);

  reg [63:0] reg_tdata;
  reg [7:0]  reg_tkeep;
  reg        reg_tvalid;
  reg        reg_tlast;
  reg        reg_tuser;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      reg_tdata <= 64'b0;
      reg_tkeep <= 8'b0;
      reg_tvalid <= 1'b0;
      reg_tlast <= 1'b0;
      reg_tuser <= 1'b0;

      out_tdata <= 64'b0;
      out_tkeep <= 8'b0;
      out_tvalid <= 1'b0;
      out_tlast <= 1'b0;
      out_tuser <= 1'b0;

      out_tready <= 1'b0;
    end else begin
      out_tready <= frame_ready && header_ready;
      if (frame_ready && header_ready) begin
        reg_tdata <= (tvalid) ? tdata : reg_tdata;
        reg_tkeep <= (tvalid) ? tkeep : reg_tkeep;
        reg_tvalid <= tvalid;
        reg_tlast <= (tvalid) ? tlast : reg_tlast;
        reg_tuser <= (tvalid) ? tuser : reg_tuser;

        out_tdata <= reg_tdata;
        out_tkeep <= reg_tkeep;
        out_tvalid <= reg_tvalid;
        out_tlast <= reg_tlast;
        out_tuser <= reg_tuser;
      end
  end

endmodule
