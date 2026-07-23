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
    output wire       out_tready,
    
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
  reg [7:0]  out_tkeep;
  reg        out_tvalid;
  reg        out_tlast;
  reg        out_tuser;

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
    end else if (tvalid) begin
      reg_tdata <= tdata;
      reg_tkeep <= tkeep;
      reg_tvalid <= tvalid;
      reg_tlast <= tlast;
      reg_tuser <= tuser;

      out_tdata <= reg_tdata;
      out_tkeep <= reg_tkeep;
      out_tvalid <= reg_tvalid;
      out_tlast <= reg_tlast;
      out_tuser <= reg_tuser;

      out_tready <= frame_ready && header_ready;
    end else begin
      reg_tdata <= 64'b0;
      reg_tkeep <= 8'b0;
      reg_tvalid <= 1'b0;
      reg_tlast <= 1'b0;
      reg_tuser <= 1'b0;
  end

endmodule
