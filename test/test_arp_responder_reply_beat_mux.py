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
from typing import Optional

def mac_address(value: int) -> LogicArray:
    """
    Make a LogicArray representing a 6-byte MAC address.
    """
    return LogicArray(value, 6*8)

def hardware_address(value: int) -> LogicArray:
    """
    Make a LogicArray representing a 6-byte SHA or THA.
    """
    return LogicArray(value, 6*8)

def protocol_address(value: int) -> LogicArray:
    """
    Make a LogicArray representing a 4-byte SPA or TPA.
    """
    return LogicArray(value, 4*8)

class PackageAttributes:
    """
    Package attributes, containing own MAC, own IP, SHA, SPA, THA, and TPA.
    """
    # From Ethernet II:
    # Destination MAC address (6B)
    dest_mac: Optional[LogicArray]
    # Source MAC address (6B)
    source_mac: Optional[LogicArray]

    # From ARP:
    # Sender hardware address (6B)
    sha: Optional[LogicArray]
    # Sender protocol address (4B)
    spa: Optional[LogicArray]
    # Target hardware address (6B)
    tha: Optional[LogicArray]
    # Target protocol address (4B)
    tpa: Optional[LogicArray]

    @staticmethod
    def _get_assert_msg(property: str, expected: LogicArray, actual: Optional[LogicArray]) -> str:
        """
        Helper function to get an assertion message
        """
        return f"Expected {property} to be {expected}, but got {actual}"

    @staticmethod
    def _inspect(property: str, expected: Optional[LogicArray], actual: Optional[LogicArray], logger: logging.Logger):
        """
        Helper function to inspect between two attributes
        """
        # If there is a mismatch
        if expected is not None and expected != actual:
            # Print the mismatch
            logger.warning(f"Mismatch detected for {property}:")
            logger.warning(f"Expected:\t{expected}")
            logger.warning(f"Actual:\t\t{actual}")
            # Print difference if `actual` isn't `None`
            if actual is not None:
                logger.warning(f"Difference:\t{expected ^ actual}")

            raise AssertionError(PackageAttributes._get_assert_msg(property, expected, actual))


    def __init__(self, dest_mac: Optional[LogicArray], source_mac: Optional[LogicArray], sha: Optional[LogicArray], spa: Optional[LogicArray], tha: Optional[LogicArray], tpa: Optional[LogicArray]) -> None:
        """
        Create a new package attributes object. You may pass `None` to any of the parameters
        to indicate that it can take on any value.
        """
        self.dest_mac = dest_mac
        self.source_mac = source_mac
        self.sha = sha
        self.spa = spa
        self.tha = tha
        self.tpa = tpa

    def assert_attrs(self, other: object,logger: logging.Logger):
        """
        Assert the attributes of this class onto another
        """
        # Check type of other
        if type(other) != PackageAttributes:
            raise TypeError(f"Attempted to compare a PackageAttributes with {type(other)}")

        # Assertions
        self._inspect("destination MAC address", self.dest_mac, other.dest_mac, logger)
        self._inspect("source MAC address", self.source_mac, other.source_mac, logger)
        self._inspect("Sender Hardware Address (SHA)", self.sha, other.sha, logger)
        self._inspect("Sender Protocol Address (SPA)", self.spa, other.spa, logger)
        self._inspect("Target Hardware Address (THA)", self.tha, other.tha, logger)
        self._inspect("Target Protocol Address (TPA)", self.tpa, other.tpa, logger)

class Image:
    """
    The deserialized reply image from the MUX.
    """
    # Field names

    # From Ethernet II:
    # Destination MAC address (6B, packaged)
    # Source MAC address (6B, packaged)
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
    # Sender hardware address (6B, packaged)
    # Sender protocol address (4B, packaged)
    # Target hardware address (6B, packaged)
    # Target protocol address (4B, packaged)

    # Package attributes
    package_attr: PackageAttributes

    # Unused padding bits, should be zeroes (6B)
    padding: LogicArray

    def __init__(self, bits: LogicArray, logger: logging.Logger) -> None:
        """
        Deserialize an array of bits into a reply image
        """
        # Assign logger
        self._logger = logger
        # Keep track of the starting point
        start_point = 384
        # From Ethernet II:
        # Destination MAC address (6B)
        start_point -= 6*8
        dest_mac = bits[start_point+6*8-1:start_point]
        # Source MAC address (6B)
        start_point -= 6*8
        source_mac = bits[start_point+6*8-1:start_point]
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
        sha = bits[start_point+6*8-1:start_point]
        # Sender protocol address (4B)
        start_point -= 4*8
        spa = bits[start_point+4*8-1:start_point]
        # Target hardware address (6B)
        start_point -= 6*8
        tha = bits[start_point+6*8-1:start_point]
        # Target protocol address (4B)
        start_point -= 4*8
        tpa = bits[start_point+4*8-1:start_point]
        # Padding (6B)
        start_point -= 6*8
        self.padding = bits[start_point+6*8-1:start_point]

        # Set package attributes
        self.package_attr = PackageAttributes(
            dest_mac=dest_mac,
            source_mac=source_mac,
            sha=sha,
            spa=spa,
            tha=tha,
            tpa=tpa
        )

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

    def check_attrs(self, criteria: PackageAttributes):
        """
        Check that the non-constant fields in the image match `criteria`. 
        """
        criteria.assert_attrs(self.package_attr, self._logger)

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
        # Pull the reset line high to end reset
        self._dut.rst_n.value = 1
        # Wait for 1 clock cycle
        await ClockCycles(self._dut.clk, 1)

    async def get_beat(self, beat_number: int) -> LogicArray:
        """
        Manually get a beat by beat number
        """
        # Set beat number in design
        self._dut.beat_idx.value = beat_number
        # Wait for 1 clock cycle
        await ClockCycles(self._dut.clk, 1)
        # Return the beat
        return self._dut.beat_data.value

    async def deserialize_beats(self) -> Image:
        """
        Deserialize the beats outputted by the model
        """
        # Current bits collected from beats
        cur_beats: list[Logic] = []
        # For each of the 6 beats
        for i in range(6):
            # Get beat
            cur_beat = await self.get_beat(i)
            # Copy the beat
            self._logger.info(f"Beat {i}: {cur_beat}")
            cur_beats += list(cur_beat)

        # Collect the bits together to form a logic array
        joined = LogicArray(cur_beats)

        # Return Image
        return Image(joined, self._logger)

    async def set_attrs(self, own_mac: Optional[LogicArray], own_ip: Optional[LogicArray], sha: Optional[LogicArray], spa: Optional[LogicArray], commit: bool = True) -> None:
        """
        Set some package attributes into the design.
        If `commit` is true, `valid_packet` will be asserted to latch the packet.
        Otherwise, `valid_packet` will not be asserted, and the packet will not be latched.
        """
        # Set attribute values
        if own_mac is not None:
            self._dut.own_mac.value = own_mac
        if own_ip is not None:
            self._dut.own_ip.value = own_ip
        if sha is not None:
            self._dut.sha.value = sha
        if spa is not None:
            self._dut.spa.value = spa

        # Commit changes if requested
        if commit:
            self._dut.valid_packet.value = True
            await ClockCycles(self._dut.clk, 1)
            self._dut.valid_packet.value = False
            await ClockCycles(self._dut.clk, 1)

@cocotb.test
async def reset_behavior(dut):
    """
    Tests that the module resets to the correct values.
    """
    # Get logger
    logger = logging.getLogger("reset_behavior")
    # logger.setLevel(logging.DEBUG)
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
    image.check_attrs(PackageAttributes(
        dest_mac=mac_address(0),
        source_mac=mac_address(0),
        sha=hardware_address(0),
        spa=protocol_address(0),
        tha=hardware_address(0),
        tpa=protocol_address(0)
    ))

@cocotb.test
async def invalid_packet_after_reset(dut):
    """
    Tests that immediately after resetting, the module does not latch attributes from invalid packets
    """
    # Get logger
    logger = logging.getLogger("invalid_packet_after_reset")
    # logger.setLevel(logging.DEBUG)
    # Initialize design
    logger.debug("Initializing design")
    design = Design(dut, logger) 
    await design.reset()
    # Set package values without committing
    await design.set_attrs(
        own_mac=mac_address(0xFFFFFFFFFFFF),
        own_ip=protocol_address(0xFFFFFFFF),
        sha=hardware_address(0xFFFFFFFFFFFF),
        spa=protocol_address(0xFFFFFFFF),
        commit=False
    )
    # Request and deserialize beats
    logger.debug("Requesting beats")
    image = await design.deserialize_beats()
    # Assertions
    logger.debug("Asserting")
    image.check_integrity() 
    image.check_attrs(PackageAttributes(
        dest_mac=mac_address(0),
        source_mac=mac_address(0),
        sha=hardware_address(0),
        spa=protocol_address(0),
        tha=hardware_address(0),
        tpa=protocol_address(0)
    ))

@cocotb.test
async def first_packet(dut):
    """
    Tests that immediately after resetting, the module can latch its first packet
    """
    # Get logger
    logger = logging.getLogger("first_packet")
    logger.setLevel(logging.DEBUG)
    # Initialize design
    logger.debug("Initializing design")
    design = Design(dut, logger) 
    await design.reset()
    # Set package values and commit
    await design.set_attrs(
        own_mac=mac_address(0xDABCAB123456),
        own_ip=protocol_address(0xB0BACAFE),
        sha=hardware_address(0x9876543210CC),
        spa=protocol_address(0xDEADBEEF)
    )
    # Request and deserialize beats
    logger.debug("Requesting beats")
    image = await design.deserialize_beats()
    # Assertions
    logger.debug("Asserting")
    image.check_integrity() 
    image.check_attrs(PackageAttributes(
        dest_mac=hardware_address(0x9876543210CC),
        source_mac=mac_address(0xDABCAB123456),
        sha=mac_address(0xDABCAB123456),
        spa=protocol_address(0xB0BACAFE),
        tha=hardware_address(0x9876543210CC),
        tpa=protocol_address(0xDEADBEEF)
    ))