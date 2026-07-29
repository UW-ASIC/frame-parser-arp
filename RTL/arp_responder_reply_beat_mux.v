// Disable implicit nets
`default_nettype none

module arp_responder_reply_beat_mux (
    // From Tiny Tapeout connections
    input wire clk, // Clock
    input wire rst_n, // Active-low reset line

    // From block: config
    // The device's own MAC address
    input wire [47:0] own_mac,
    // The device's own IPv4 address
    input wire [31:0] own_ip,

    // From block 2: validate & match
    // Whether the packet is valid. If it is, then this MUX will latch the SHA and SPA supplied into its inputs
    input wire valid_packet,
    // The Sender Hardware Address (e.g. MAC) from incoming ARP request
    input wire [47:0] sha,
    // The Sender Protocol Address (e.g. IPv4) from incoming ARP request
    input wire [31:0] spa,

    // From/to block 4: TX serializer
    // 3-bit index tracking the current beat (0 to 5)
    input wire [2:0] beat_idx,
    // 64-bit slice of the Ethernet frame handed to the AXI-S master to transmit serially.
    // Transmission is done in big-endian, sending [335:272] first and padding the last beat with 0s at the end
    output wire [63:0] beat_data
);
    // Register for reply image. Output is combinationally wired to select the correct 64-bit segment
    reg [383:0] reply_img;
    /*
        Layout for reply image, according to Ethernet II frame + ARP frame (CRC is ignored):
        - 6B [383:336]: Destination MAC address (=sha)
        - 6B [335:288]: Source MAC address (=own_mac)
        - 2B [287:272]: EtherType (=0x0806)
        - 28B [271:48]: ARP Payload
            + 2B [271:256]: Hardware Type (=0x0001)
            + 2B [255:240]: Protocol Type (=0x0800)
            + 1B [239:232]: Hardware Length (=0x06)
            + 1B [231:224]: Protocol Length (=0x04)
            + 2B [223:208]: Operation (=0x0002, since this is the REPLY beat MUX)
            + 6B [207:160]: Sender Hardware Address (SHA) (=own_mac)
            + 4B [159:128]: Sender Protocol Address (SPA) (=own_ip)
            + 6B [127:80]: Target Hardware Address (=sha)
            + 4B [79:48]: Target Protocol Address (=spa)
        - 6B [47:0]: unused padding (=0x0)
    */

    // Constants defined within the Ethernet II and ARP standards
    localparam logic[15:0] Ethertype = 16'h0806;
    localparam logic[15:0] HardwareType = 16'h0001;
    localparam logic[15:0] ProtocolType = 16'h0800;
    localparam logic[7:0] HardwareLength = 8'h06;
    localparam logic[7:0] ProtocolLength = 8'h04;
    localparam logic[15:0] Operation = 16'h0002;

    // Sequential behavior
    always @(posedge clk or negedge rst_n) begin
        // When being reset
        if (!rst_n) begin
            // Initialize reply image
            reply_img <= {
                48'h0,          // Ethernet: Destination MAC Address
                48'h0,          // Ethernet: Source MAC Address
                Ethertype,      // Ethernet: EtherType
                HardwareType,   // ARP: Hardware Type
                ProtocolType,   // ARP: Protocol Type
                HardwareLength, // ARP: Hardware Length
                ProtocolLength, // ARP: Protocol Length
                Operation,      // ARP: Operation
                48'h0,          // ARP: Sender Hardware Address
                32'h0,          // ARP: Sender Protocol Address
                48'h0,          // ARP: Target Hardware Address
                32'h0,          // ARP: Target Protocol Address
                48'h0           // Unused padding
            };
        end else if (valid_packet) begin
            // Latch SHA and SPA from ARP request
            reply_img <= {
                sha,            // Ethernet: Destination MAC Address
                own_mac,        // Ethernet: Source MAC Address
                Ethertype,      // Ethernet: EtherType
                HardwareType,   // ARP: Hardware Type
                ProtocolType,   // ARP: Protocol Type
                HardwareLength, // ARP: Hardware Length
                ProtocolLength, // ARP: Protocol Length
                Operation,      // ARP: Operation
                own_mac,        // ARP: Sender Hardware Address
                own_ip,         // ARP: Sender Protocol Address
                sha,            // ARP: Target Hardware Address
                spa,            // ARP: Target Protocol Address
                48'h0           // Unused padding
            };
        end
    end

    // Assign beat data:
    // - If the beat ID is valid (i.e. between 0 and 5 inclusive), then multiplex the desired segment
    // - Otherwise, output all zeroes to tell the TX serializer that they screwed up :/
    assign beat_data = (beat_idx <= 3'd5) ? reply_img[(383 - beat_idx*64) -: 64] : 64'h0;
endmodule
