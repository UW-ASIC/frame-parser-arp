module frame_parser_payload_aligner (
    input wire clk,
    input wire rst_n,
    input wire ena,
    input wire payload_valid,
    input wire [5:0] payload_bit_offset,
    input wire is_vlan_frame,
    input wire [63:0] tdata,
    input wire [7:0] tkeep,
    input wire tvalid,
    input wire tlast,

    output wire [63:0] p_tdata,
    output wire [7:0] p_tkeep,
    output wire p_tvalid,
    output wire p_tlast
);

    reg[47:0] carry_reg;
    reg flush_reg;

    wire [79:0] combined_nonvlan = {tdata, carry_reg[15:0]}; // 2 byte carry
    wire [111:0] combined_vlan = {tdata, carry_reg[47:0]}; // 6 byte carry

    assign p_tdata = flush_reg ? {16'd0, carry_reg} : (is_vlan_frame ? combined_vlan[63:0] : combined_nonvlan[63:0]);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            carry_reg <= 48'd0;
        end else if (payload_valid) begin
            if (is_vlan_frame)
                carry_reg <= combined_vlan[111:64];
            else
                carry_reg <= {32'd0, combined_nonvlan[79:64]};
        end
    end

    reg have_carry;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            have_carry <= 1'b0;
        else
            have_carry <= payload_valid;
    end

    assign p_tvalid = (payload_valid && have_carry) || flush_reg;

    // How many bytes of *this* beat are real, per tkeep (only the frame's
    // true last beat should ever be less than a full 8 -- same convention
    // frame_control.v's bytes_kept table uses).
    reg [3:0] beat_valid_bytes;
    always @(*) begin
        case (tkeep)
            8'b00000000: beat_valid_bytes = 4'd0;
            8'b00000001: beat_valid_bytes = 4'd1;
            8'b00000011: beat_valid_bytes = 4'd2;
            8'b00000111: beat_valid_bytes = 4'd3;
            8'b00001111: beat_valid_bytes = 4'd4;
            8'b00011111: beat_valid_bytes = 4'd5;
            8'b00111111: beat_valid_bytes = 4'd6;
            8'b01111111: beat_valid_bytes = 4'd7;
            default:      beat_valid_bytes = 4'd8;
        endcase
    end

    // carry_size_now: how many bytes of the current output come from the
    // carry (always real); slot_size: how many come fresh from this beat.
    wire [3:0] carry_size_now = is_vlan_frame ? 4'd6 : 4'd2;
    wire [3:0] slot_size      = 4'd8 - carry_size_now;

    // How many of THIS cycle's output bytes are real (carry is always fully
    // real; only the fresh slot from this beat can be partial).
    wire [3:0] this_output_valid = carry_size_now +
        ((beat_valid_bytes < slot_size) ? beat_valid_bytes : slot_size);

    // How many bytes of the NEW carry (visible next cycle / at flush) are
    // real -- whatever's left of this beat's valid bytes beyond the slot.
    wire [3:0] new_carry_valid_w = (beat_valid_bytes > slot_size) ?
        (beat_valid_bytes - slot_size) : 4'd0;

    reg [3:0] carry_valid_bytes;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            carry_valid_bytes <= 4'd0;
        else if (payload_valid)
            carry_valid_bytes <= new_carry_valid_w;
    end

    function [7:0] tkeep_for_count;
        input [3:0] count;
        begin
            case (count)
                4'd0: tkeep_for_count = 8'h00;
                4'd1: tkeep_for_count = 8'h01;
                4'd2: tkeep_for_count = 8'h03;
                4'd3: tkeep_for_count = 8'h07;
                4'd4: tkeep_for_count = 8'h0F;
                4'd5: tkeep_for_count = 8'h1F;
                4'd6: tkeep_for_count = 8'h3F;
                4'd7: tkeep_for_count = 8'h7F;
                default: tkeep_for_count = 8'hFF;
            endcase
        end
    endfunction

    assign p_tkeep = flush_reg ? tkeep_for_count(carry_valid_bytes) : tkeep_for_count(this_output_valid);



    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
        flush_reg <= 1'b0;
        else
        flush_reg <= (tlast && payload_valid); // was this the frame's real last beat
    end

    assign p_tlast = flush_reg;



endmodule