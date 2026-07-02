`default_nettype none
`timescale 1ns / 1ps

module arp_responder_validate_match_tb;

    localparam [15:0] HTYPE_ETHERNET = 16'h0001;
    localparam [15:0] PTYPE_IPV4     = 16'h0800;
    localparam [7:0]  HLEN_MAC       = 8'd6;
    localparam [7:0]  PLEN_IPV4      = 8'd4;
    localparam [15:0] OPER_REQUEST   = 16'h0001;
    localparam [15:0] OPER_REPLY     = 16'h0002;
    localparam [31:0] LOCAL_IP       = 32'hc0a8_0164;
    localparam [31:0] OTHER_IP       = 32'hc0a8_0165;

    reg clk;
    reg rst_n;
    reg input_valid;
    reg frame_error;
    reg tx_busy;
    reg [15:0] hardware_type;
    reg [15:0] protocol_type;
    reg [7:0] hardware_addr_len;
    reg [7:0] protocol_addr_len;
    reg [15:0] opcode;
    reg [47:0] sender_mac;
    reg [31:0] sender_ip;
    reg [31:0] target_ip;
    reg [31:0] local_ip;

    wire format_valid;
    wire target_match;
    wire reply_required;
    wire fire;
    wire drop;
    wire [47:0] requester_mac;
    wire [31:0] requester_ip;

    integer checks;
    integer failures;

    // Unit-level DUT instance. The Tiny Tapeout top does not instantiate this block yet.
    arp_responder_validate_match dut (
        .clk(clk),
        .rst_n(rst_n),
        .input_valid(input_valid),
        .frame_error(frame_error),
        .tx_busy(tx_busy),
        .hardware_type(hardware_type),
        .protocol_type(protocol_type),
        .hardware_addr_len(hardware_addr_len),
        .protocol_addr_len(protocol_addr_len),
        .opcode(opcode),
        .sender_mac(sender_mac),
        .sender_ip(sender_ip),
        .target_ip(target_ip),
        .local_ip(local_ip),
        .format_valid(format_valid),
        .target_match(target_match),
        .reply_required(reply_required),
        .fire(fire),
        .drop(drop),
        .requester_mac(requester_mac),
        .requester_ip(requester_ip)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    task expect_outputs;
        input [8*48-1:0] name;
        input exp_format_valid;
        input exp_target_match;
        input exp_reply_required;
        input exp_fire;
        input exp_drop;
        begin
            checks = checks + 1;

            if (format_valid !== exp_format_valid) begin
                failures = failures + 1;
                $display("FAIL %0s: format_valid=%b expected=%b",
                         name, format_valid, exp_format_valid);
            end
            if (target_match !== exp_target_match) begin
                failures = failures + 1;
                $display("FAIL %0s: target_match=%b expected=%b",
                         name, target_match, exp_target_match);
            end
            if (reply_required !== exp_reply_required) begin
                failures = failures + 1;
                $display("FAIL %0s: reply_required=%b expected=%b",
                         name, reply_required, exp_reply_required);
            end
            if (fire !== exp_fire) begin
                failures = failures + 1;
                $display("FAIL %0s: fire=%b expected=%b", name, fire, exp_fire);
            end
            if (drop !== exp_drop) begin
                failures = failures + 1;
                $display("FAIL %0s: drop=%b expected=%b", name, drop, exp_drop);
            end
        end
    endtask

    task apply_case;
        input [8*48-1:0] name;
        input in_valid_i;
        input frame_error_i;
        input tx_busy_i;
        input [15:0] hardware_type_i;
        input [15:0] protocol_type_i;
        input [7:0] hardware_addr_len_i;
        input [7:0] protocol_addr_len_i;
        input [15:0] opcode_i;
        input [31:0] target_ip_i;
        input exp_format_valid;
        input exp_target_match;
        input exp_reply_required;
        input exp_fire;
        input exp_drop;
        begin
            // Drive inputs on the falling edge so the DUT samples stable values
            // on the next rising edge.
            @(negedge clk);
            input_valid       = in_valid_i;
            frame_error       = frame_error_i;
            tx_busy           = tx_busy_i;
            hardware_type     = hardware_type_i;
            protocol_type     = protocol_type_i;
            hardware_addr_len = hardware_addr_len_i;
            protocol_addr_len = protocol_addr_len_i;
            opcode            = opcode_i;
            sender_mac        = 48'h0200_0000_0001;
            sender_ip         = 32'hc0a8_010a;
            target_ip         = target_ip_i;
            local_ip          = LOCAL_IP;

            @(posedge clk);
            #1;
            expect_outputs(name, exp_format_valid, exp_target_match,
                           exp_reply_required, exp_fire, exp_drop);

            // SHA/SPA should only be meaningful when this block fires a reply.
            if (fire && requester_mac !== sender_mac) begin
                failures = failures + 1;
                $display("FAIL %0s: requester_mac was not forwarded", name);
            end
            if (fire && requester_ip !== sender_ip) begin
                failures = failures + 1;
                $display("FAIL %0s: requester_ip was not forwarded", name);
            end
        end
    endtask

    task apply_unknown_case;
        begin
            // Unknown format bits must not become a definite reply.
            @(negedge clk);
            input_valid       = 1'b1;
            frame_error       = 1'b0;
            tx_busy           = 1'b0;
            hardware_type     = 16'hxxxx;
            protocol_type     = PTYPE_IPV4;
            hardware_addr_len = HLEN_MAC;
            protocol_addr_len = PLEN_IPV4;
            opcode            = OPER_REQUEST;
            sender_mac        = 48'h0200_0000_0001;
            sender_ip         = 32'hc0a8_010a;
            target_ip         = LOCAL_IP;
            local_ip          = LOCAL_IP;

            @(posedge clk);
            #1;
            checks = checks + 1;
            if (format_valid === 1'b1 || reply_required === 1'b1) begin
                failures = failures + 1;
                $display("FAIL unknown field: unknown hardware_type looked valid");
            end
        end
    endtask

    initial begin
        checks = 0;
        failures = 0;
        rst_n = 1'b0;
        input_valid = 1'b0;
        frame_error = 1'b0;
        tx_busy = 1'b0;
        hardware_type = HTYPE_ETHERNET;
        protocol_type = PTYPE_IPV4;
        hardware_addr_len = HLEN_MAC;
        protocol_addr_len = PLEN_IPV4;
        opcode = OPER_REQUEST;
        sender_mac = 48'h0200_0000_0001;
        sender_ip = 32'hc0a8_010a;
        target_ip = LOCAL_IP;
        local_ip = LOCAL_IP;

        repeat (2) @(posedge clk);
        #1;
        expect_outputs("reset clears outputs", 1'b0, 1'b0, 1'b0, 1'b0, 1'b0);
        rst_n = 1'b1;

        // Good request: exactly the packet that should launch a reply.
        apply_case("valid local request", 1'b1, 1'b0, 1'b0,
                   HTYPE_ETHERNET, PTYPE_IPV4, HLEN_MAC, PLEN_IPV4,
                   OPER_REQUEST, LOCAL_IP, 1'b1, 1'b1, 1'b1, 1'b1, 1'b0);

        // Valid ARP shape, but not our IP.
        apply_case("valid request other ip", 1'b1, 1'b0, 1'b0,
                   HTYPE_ETHERNET, PTYPE_IPV4, HLEN_MAC, PLEN_IPV4,
                   OPER_REQUEST, OTHER_IP, 1'b1, 1'b0, 1'b0, 1'b0, 1'b1);

        // Format rejects every unsupported ARP field independently.
        apply_case("reply opcode", 1'b1, 1'b0, 1'b0,
                   HTYPE_ETHERNET, PTYPE_IPV4, HLEN_MAC, PLEN_IPV4,
                   OPER_REPLY, LOCAL_IP, 1'b0, 1'b1, 1'b0, 1'b0, 1'b1);
        apply_case("wrong hardware type", 1'b1, 1'b0, 1'b0,
                   16'h0006, PTYPE_IPV4, HLEN_MAC, PLEN_IPV4,
                   OPER_REQUEST, LOCAL_IP, 1'b0, 1'b1, 1'b0, 1'b0, 1'b1);
        apply_case("wrong protocol type", 1'b1, 1'b0, 1'b0,
                   HTYPE_ETHERNET, 16'h86dd, HLEN_MAC, PLEN_IPV4,
                   OPER_REQUEST, LOCAL_IP, 1'b0, 1'b1, 1'b0, 1'b0, 1'b1);
        apply_case("wrong hardware length", 1'b1, 1'b0, 1'b0,
                   HTYPE_ETHERNET, PTYPE_IPV4, 8'd8, PLEN_IPV4,
                   OPER_REQUEST, LOCAL_IP, 1'b0, 1'b1, 1'b0, 1'b0, 1'b1);
        apply_case("wrong protocol length", 1'b1, 1'b0, 1'b0,
                   HTYPE_ETHERNET, PTYPE_IPV4, HLEN_MAC, 8'd16,
                   OPER_REQUEST, LOCAL_IP, 1'b0, 1'b1, 1'b0, 1'b0, 1'b1);

        // Control cases: invalid pulse, bad frame, and busy TX.
        apply_case("input valid low", 1'b0, 1'b0, 1'b0,
                   HTYPE_ETHERNET, PTYPE_IPV4, HLEN_MAC, PLEN_IPV4,
                   OPER_REQUEST, LOCAL_IP, 1'b0, 1'b0, 1'b0, 1'b0, 1'b0);
        apply_case("frame error blocks reply", 1'b1, 1'b1, 1'b0,
                   HTYPE_ETHERNET, PTYPE_IPV4, HLEN_MAC, PLEN_IPV4,
                   OPER_REQUEST, LOCAL_IP, 1'b1, 1'b1, 1'b0, 1'b0, 1'b1);
        apply_case("tx busy drops reply", 1'b1, 1'b0, 1'b1,
                   HTYPE_ETHERNET, PTYPE_IPV4, HLEN_MAC, PLEN_IPV4,
                   OPER_REQUEST, LOCAL_IP, 1'b1, 1'b1, 1'b1, 1'b0, 1'b1);

        // Consecutive requests prove there is no stale state between pulses.
        apply_case("back-to-back valid 1", 1'b1, 1'b0, 1'b0,
                   HTYPE_ETHERNET, PTYPE_IPV4, HLEN_MAC, PLEN_IPV4,
                   OPER_REQUEST, LOCAL_IP, 1'b1, 1'b1, 1'b1, 1'b1, 1'b0);
        apply_case("back-to-back valid 2", 1'b1, 1'b0, 1'b0,
                   HTYPE_ETHERNET, PTYPE_IPV4, HLEN_MAC, PLEN_IPV4,
                   OPER_REQUEST, LOCAL_IP, 1'b1, 1'b1, 1'b1, 1'b1, 1'b0);
        apply_case("mixed valid request", 1'b1, 1'b0, 1'b0,
                   HTYPE_ETHERNET, PTYPE_IPV4, HLEN_MAC, PLEN_IPV4,
                   OPER_REQUEST, LOCAL_IP, 1'b1, 1'b1, 1'b1, 1'b1, 1'b0);
        apply_case("mixed invalid request", 1'b1, 1'b0, 1'b0,
                   HTYPE_ETHERNET, PTYPE_IPV4, HLEN_MAC, PLEN_IPV4,
                   OPER_REPLY, LOCAL_IP, 1'b0, 1'b1, 1'b0, 1'b0, 1'b1);
        apply_unknown_case();

        if (failures == 0) begin
            $display("PASS arp_responder_validate_match: %0d checks", checks);
            $finish;
        end

        $display("FAIL arp_responder_validate_match: %0d failures in %0d checks",
                 failures, checks);
        $fatal;
    end

endmodule
