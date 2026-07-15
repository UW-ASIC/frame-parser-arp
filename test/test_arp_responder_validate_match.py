# SPDX-FileCopyrightText: © 2026 UW-ASIC
# SPDX-License-Identifier: Apache-2.0

"""Tests for RTL/arp_responder_validate_match.v.

Run from test/ with:
    make -B UNIT=arp_responder_validate_match
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge


LOCAL_IP = 0xC0A8_0164
SENDER_MAC = 0x0200_0000_0001
SENDER_IP = 0xC0A8_010A

VALID_REQUEST = {
    "input_valid": 1,
    "frame_error": 0,
    "tx_busy": 0,
    "hardware_type": 0x0001,
    "protocol_type": 0x0800,
    "hardware_addr_len": 6,
    "protocol_addr_len": 4,
    "opcode": 0x0001,
    "sender_mac": SENDER_MAC,
    "sender_ip": SENDER_IP,
    "target_ip": LOCAL_IP,
    "local_ip": LOCAL_IP,
}


def check_outputs(dut, expected):
    for name, value in expected.items():
        actual = int(getattr(dut, name).value)
        assert actual == value, f"{name}={actual}, expected {value}"


async def reset_dut(dut):
    for name, value in VALID_REQUEST.items():
        getattr(dut, name).value = value
    dut.input_valid.value = 0
    dut.rst_n.value = 0

    await ClockCycles(dut.clk, 2)
    await ReadOnly()
    check_outputs(
        dut,
        {
            "format_valid": 0,
            "target_match": 0,
            "reply_required": 0,
            "fire": 0,
            "drop": 0,
            "requester_mac": 0,
            "requester_ip": 0,
        },
    )

    await FallingEdge(dut.clk)
    dut.rst_n.value = 1


async def start_test(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)


async def apply_case(dut, expected, **overrides):
    await FallingEdge(dut.clk)
    inputs = VALID_REQUEST.copy()
    inputs.update(overrides)
    for name, value in inputs.items():
        getattr(dut, name).value = value

    await RisingEdge(dut.clk)
    await ReadOnly()
    check_outputs(dut, expected)
    check_outputs(
        dut,
        {
            "requester_mac": SENDER_MAC if expected["fire"] else 0,
            "requester_ip": SENDER_IP if expected["fire"] else 0,
        },
    )


@cocotb.test()
async def test_valid_request_and_output_pulse(dut):
    """A clean local request fires once and forwards the requester address."""
    await start_test(dut)

    accepted = {
        "format_valid": 1,
        "target_match": 1,
        "reply_required": 1,
        "fire": 1,
        "drop": 0,
    }
    await apply_case(dut, accepted)
    await apply_case(dut, accepted)  # Back-to-back requests are both accepted.
    await apply_case(
        dut,
        {
            "format_valid": 0,
            "target_match": 0,
            "reply_required": 0,
            "fire": 0,
            "drop": 0,
        },
        input_valid=0,
    )


@cocotb.test()
async def test_rejects_each_bad_arp_field(dut):
    """Every required Ethernet/IPv4 ARP request field is checked."""
    await start_test(dut)

    rejected = {
        "format_valid": 0,
        "target_match": 1,
        "reply_required": 0,
        "fire": 0,
        "drop": 1,
    }
    bad_fields = {
        "hardware_type": 0x0006,
        "protocol_type": 0x86DD,
        "hardware_addr_len": 8,
        "protocol_addr_len": 16,
        "opcode": 0x0002,
    }

    for name, value in bad_fields.items():
        await apply_case(dut, rejected, **{name: value})


@cocotb.test()
async def test_nonreply_conditions(dut):
    """Wrong targets, damaged frames, and a busy transmitter are dropped."""
    await start_test(dut)

    await apply_case(
        dut,
        {
            "format_valid": 1,
            "target_match": 0,
            "reply_required": 0,
            "fire": 0,
            "drop": 1,
        },
        target_ip=LOCAL_IP + 1,
    )
    await apply_case(
        dut,
        {
            "format_valid": 1,
            "target_match": 1,
            "reply_required": 0,
            "fire": 0,
            "drop": 1,
        },
        frame_error=1,
    )
    await apply_case(
        dut,
        {
            "format_valid": 1,
            "target_match": 1,
            "reply_required": 1,
            "fire": 0,
            "drop": 1,
        },
        tx_busy=1,
    )
