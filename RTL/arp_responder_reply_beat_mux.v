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

    // Reset behavior (executed when reset line is LOW)
    always @(negedge rst_n) begin
        // Set constant fields in reply_img
        reply_img[287:272] <= 16'h0806; // Ethernet: EtherType
        reply_img[271:256] <= 16'h0001; // ARP: Hardware Type
        reply_img[255:240] <= 16'h0800; // ARP: Protocol Type
        reply_img[239:232] <= 8'h06; // ARP: Hardware Length
        reply_img[231:224] <= 8'h04; // ARP: Protocol Length
        reply_img[223:208] <= 16'h0002; // ARP: Operation
        reply_img[47:0] <= 48'h0; // Unused padding, set to 0

        // Set variable fields to 0 for now
        reply_img[383:336] <= 48'h0; // Ethernet: Destination MAC Address
        reply_img[335:288] <= 48'h0; // Ethernet: Source MAC Address
        reply_img[207:160] <= 48'h0; // ARP: Sender Hardware Address
        reply_img[159:128] <= 32'h0; // ARP: Sender Protocol Address
        reply_img[127:80] <= 48'h0; // ARP: Target Hardware Address
        reply_img[79:48] <= 32'h0; // ARP: Target Protocol Address
    end

    // Clock behavior (executed for every positive clock edge)
    always @(posedge clk) begin
        // When not being reset
        if (rst_n) begin
            // If packet is valid
            if (valid_packet) begin
                // Latch SHA and SPA from ARP request
                reply_img[383:336] <= sha; // Ethernet: Destination MAC Address
                reply_img[335:288] <= own_mac; // Ethernet: Source MAC Address
                reply_img[207:160] <= own_mac; // ARP: Sender Hardware Address
                reply_img[159:128] <= own_ip; // ARP: Sender Protocol Address
                reply_img[127:80] <= sha; // ARP: Target Hardware Address
                reply_img[79:48] <= spa; // ARP: Target Protocol Address
            end
        end
    end

    // Assign beat data:
    // - If the beat ID is valid (i.e. between 0 and 5 inclusive), then multiplex the desired segment
    // - Otherwise, output all zeroes to tell the TX serializer that they screwed up :/
    assign beat_data = (beat_idx <= 3'd5) ? reply_img[(383 - (beat_idx+1)*64 + 1) +: 64] : 64'h0;

endmodule
