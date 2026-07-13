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
    output wire       tready,
    
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

  reg processing;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n || tlast) processing <= 1'b0;
    else if (tvalid) processing <= 1'b1;
  end

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      out_tdata <= 64'b0;
      out_tkeep <= 8'b0;
      out_tvalid <= 1'b0;
      out_tlast <= 1'b0;
      out_tuser <= 1'b0;
    end else if (tvalid || processing) begin
      out_tdata <= tdata;
      out_tkeep <= tkeep;
      out_tvalid <= tvalid || processing;
      out_tlast <= tlast;
      out_tuser <= tuser;
    end
  end

  assign tready = processing || (frame_ready && header_ready);

endmodule
