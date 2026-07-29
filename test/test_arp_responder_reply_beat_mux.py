# SPDX-FileCopyrightText: © 2026 UW-ASIC
# SPDX-License-Identifier: Apache-2.0

# Testbench for RTL/arp_responder_reply_beat_mux.v
# Run from the test/ directory with:
#   make -B UNIT=arp_responder_reply_beat_mux
# (If your Verilog module name differs from the file name, add TOPLEVEL=<module_name>)

import cocotb
from cocotb.types import Logic, LogicArray
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
import logging

class Image:
    """
    The deserialized reply image from the MUX.
    """
    # Field names

    # From Ethernet II:
    # Destination MAC address (6B)
    dest_mac: LogicArray
    # Source MAC address (6B)
    source_mac: LogicArray
    # EtherType (2B)
    ethertype: LogicArray

    # From ARP:
    # Hardware type (2B)
    hardware_type: LogicArray
    # Protocol type (2B)
    protocol_type: LogicArray
    # Hardware length (1B)
    hardware_length: int
    # Protocol Length (1B)
    protocol_length: int
    # Operation (2B)
    operation: LogicArray
    # Sender hardware address (6B)
    sha: LogicArray
    # Sender protocol address (4B)
    spa: LogicArray
    # Target hardware address (6B)
    tha: LogicArray
    # Target protocol address (4B)
    tpa: LogicArray

    # Unused padding bits, should be zeroes (6B)
    padding: LogicArray

    def __init__(self, bits: LogicArray) -> None:
        """
        Deserialize an array of bits into a reply image
        """
        # Keep track of the starting point
        start_point = 384
        # From Ethernet II:
        # Destination MAC address (6B)
        start_point -= 6*8
        self.dest_mac = bits[start_point+6*8-1:start_point]
        # Source MAC address (6B)
        start_point -= 6*8
        self.source_mac = bits[start_point+6*8-1:start_point]
        # EtherType (2B)
        start_point -= 2*8
        self.ethertype = bits[start_point+2*8-1:start_point]

        # From ARP:
        # Hardware type (2B)
        start_point -= 2*8
        self.hardware_type = bits[start_point+2*8-1:start_point]
        # Protocol type (2B)
        start_point -= 2*8
        self.protocol_type = bits[start_point+2*8-1:start_point]
        # Hardware length (1B)
        start_point -= 1*8
        self.hardware_length = bits[start_point+1*8-1:start_point].to_unsigned()
        # Protocol Length (1B)
        start_point -= 1*8
        self.protocol_length = bits[start_point+1*8-1:start_point].to_unsigned()
        # Operation (2B)
        start_point -= 2*8
        self.operation = bits[start_point+2*8-1:start_point]
        # Sender hardware address (6B)
        start_point -= 6*8
        self.sha = bits[start_point+6*8-1:start_point]
        # Sender protocol address (4B)
        start_point -= 4*8
        self.spa = bits[start_point+4*8-1:start_point]
        # Target hardware address (6B)
        start_point -= 6*8
        self.tha = bits[start_point+6*8-1:start_point]
        # Target protocol address (4B)
        start_point -= 4*8
        self.tpa = bits[start_point+4*8-1:start_point]
        # Padding (6B)
        start_point -= 6*8
        self.padding = bits[start_point+6*8-1:start_point]

    def check_integrity(self):
        """
        Check that the fields in the image that are supposed to be constant...
        have the correct constants.
        """
        assert self.ethertype == 0x0806, f"EtherType must always be 0x0806 for ARP, but found {self.ethertype}"
        assert self.hardware_type == 0x0001, f"Hardware type must always be 0x0001 to indicate Ethernet, but found {self.hardware_type}"
        assert self.protocol_type == 0x0800, f"Protocol type must always be 0x0800 to indicate IPv4, but found {self.protocol_type}"
        assert self.hardware_length == 0x06, f"The hardware length for Ethernet is 6, but found {self.hardware_length}"
        assert self.protocol_length == 0x04, f"The protocol length for IPv4 is 1, but found {self.protocol_length}"
        assert self.operation == 0x0002, f"This is the reply beat MUX, so the operation must be 2 for reply, but found {self.operation}"
        assert self.padding == 0, f"Padding must always be 0 so that the TX serializer doesn't transmit garbage, but found {self.padding}"

class Design:
    """
    A model of the Verilog component.
    """

    def __init__(self, dut, logger: logging.Logger) -> None:
        """
        Create a new model of the MUX.
        Remember to run reset() after this.
        """
        # Assign logger
        self._logger = logger
        # Assign DUT
        self._dut = dut
        # Set valid_packet to 0
        self._dut.valid_packet.value = 0
        
        # Start clock
        self._clock = Clock(dut.clk, 10, unit="us")
        cocotb.start_soon(self._clock.start())

    async def reset(self) -> None:
        """
        Reset the MUX.
        """
        # Pull the reset line low to trigger reset
        self._dut.rst_n.value = 0
        # Wait for 1 clock cycle
        await ClockCycles(self._dut.clk, 1)
        # Pull the reset line high to end reset
        self._dut.rst_n.value = 1

    async def deserialize_beats(self) -> Image:
        """
        Deserialize the beats outputted by the model
        """
        # Current bits collected from beats
        cur_beats: list[Logic] = []
        # For each of the 6 beats
        for i in range(6):
            # Set beat number in design
            self._dut.beat_idx.value = i
            # Wait for 1 clock cycle
            await ClockCycles(self._dut.clk, 1)
            # Copy the beat
            self._logger.info(f"Beat {i}: {self._dut.beat_data.value}")
            cur_beats += list(self._dut.beat_data.value)

        # Collect the bits together to form a logic array
        joined = LogicArray(cur_beats)

        # Return Image
        return Image(joined)

@cocotb.test
async def reset_behavior(dut):
    """
    Tests that the module resets to the correct values.
    """
    # Get logger
    logger = logging.getLogger("reset_behavior")
    logger.setLevel(logging.DEBUG)
    # Initialize design
    logger.debug("Initializing design")
    design = Design(dut, logger) 
    await design.reset()
    # Request and deserialize beats
    logger.debug("Requesting beats")
    image = await design.deserialize_beats()
    # Assertions
    logger.debug("Asserting")
    image.check_integrity() 
    assert image.dest_mac == 0
    assert image.source_mac == 0
    assert image.sha == 0
    assert image.spa == 0
    assert image.tha == 0
    assert image.tpa == 0
