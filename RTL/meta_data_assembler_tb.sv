`timescale 1ns/1ps

module meta_data_assembler_tb;

    logic clk = 0;
    always #5 clk = !clk;

    logic eof = 0;
    logic [13:0] len = 0;
    logic fcs_ok = 0;

    logic [47:0] dst_mac = 0;
    logic [47:0] src_mac = 0;
    logic [15:0] ethertype = 0;
    logic [11:0] vlan_id = 0;
    logic [2:0]  pcp = 0;
    logic [1:0]  frame_type = 0;

    logic [144:0] meta_data_out;

    meta_data_assembler dut (
        .eof        (eof),
        .len        (len),
        .fcs_ok     (fcs_ok),
        .dst_mac    (dst_mac),
        .src_mac    (src_mac),
        .ethertype  (ethertype),
        .vlan_id    (vlan_id),
        .pcp        (pcp),
        .frame_type (frame_type),
        .meta_d_out (meta_data_out)
    );

    task automatic drive_input(
        input logic [15:0] ethertype_i,
        input logic [11:0] vlan_i,
        input logic [2:0]  pcp_i
    );
        @(posedge clk);

        eof = $urandom_range(1, 0);
        len = $urandom_range(1518, 0);
        fcs_ok = $urandom_range(1, 0);

        dst_mac = {$urandom(), $urandom()};
        src_mac = {$urandom(), $urandom()};
        ethertype = ethertype_i;
        vlan_id = vlan_i;
        pcp = pcp_i;
        frame_type = $urandom_range(3, 0);
    endtask


    task automatic out_monitor(
        input logic [15:0] ethertype_exp,
        input logic [11:0] vlan_exp,
        input logic [2:0]  pcp_exp
    );
        logic [11:0] vlan_actual;
        logic [2:0]  pcp_actual;

        @(posedge clk);

        vlan_actual = meta_data_out[123:112];
        pcp_actual  = meta_data_out[126:124];

        if (ethertype_exp == 16'h0000) begin
            assert(vlan_actual == 12'h000)
                else $fatal(1, "FAIL: ethertype=0, expected vlan=0, got vlan=%0h", vlan_actual);

            assert(pcp_actual == 3'h0)
                else $fatal(1, "FAIL: ethertype=0, expected pcp=0, got pcp=%0h", pcp_actual);
        end
        else begin
            assert(vlan_actual == vlan_exp)
                else $fatal(1, "FAIL: expected vlan=%0h, got vlan=%0h", vlan_exp, vlan_actual);

            assert(pcp_actual == pcp_exp)
                else $fatal(1, "FAIL: expected pcp=%0h, got pcp=%0h", pcp_exp, pcp_actual);
        end
    endtask


    initial begin
        logic [15:0] ethertype_rand;
        logic [11:0] vlan_rand;
        logic [2:0]  pcp_rand;

        repeat (100) begin
            // Force half the tests to ethertype == 0
            if ($urandom_range(1, 0))
                ethertype_rand = 16'h0000;
            else
                ethertype_rand = $urandom_range(16'hFFFF, 16'h0001);

            vlan_rand = $urandom_range(4095, 0);
            pcp_rand  = $urandom_range(7, 0);

            fork
                drive_input(ethertype_rand, vlan_rand, pcp_rand);
                out_monitor(ethertype_rand, vlan_rand, pcp_rand);
            join
        end

        $display("Pass");
        $finish;
    end

endmodule