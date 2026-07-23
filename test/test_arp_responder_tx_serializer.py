# SPDX-FileCopyrightText: © 2026 UW-ASIC
# SPDX-License-Identifier: Apache-2.0

# Testbench for RTL/arp_responder_tx_serializer.v
# NOTE: the module inside this file is currently named arp_tx_serializer (not the
# file name), so pass the toplevel override:
#   make -B UNIT=arp_responder_tx_serializer TOPLEVEL=arp_tx_serializer

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge, Timer
import random

async def reset_dut(dut):
    dut.fire.value = 0
    dut.m_tready.value = 0
    dut.mux_tdata.value = 0
    dut.mux_tkeep.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)

@cocotb.test()
async def test_basic_frame(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.m_tready.value = 1
    dut.fire.value = 1
    await ClockCycles(dut.clk, 1)
    dut.fire.value = 0

    for expected_beat in range(6):
        await RisingEdge(dut.clk)   # sample just after the edge
        assert dut.m_tvalid.value == 1
        assert dut.beat_idx.value == expected_beat
        if expected_beat == 5:
            assert dut.m_tlast.value == 1

    await ClockCycles(dut.clk, 1)
    assert dut.busy.value == 0 and dut.m_tvalid.value == 0

@cocotb.test()
async def test_stall_midframe(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.m_tready.value = 1
    dut.fire.value = 1
    await ClockCycles(dut.clk, 1)
    dut.fire.value = 0

    for expected_beat in range(2):
        await FallingEdge(dut.clk)
        assert dut.m_tvalid.value == 1
        assert dut.beat_idx.value == expected_beat
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    assert dut.m_tvalid.value == 1
    assert dut.beat_idx.value == 2
    dut.m_tready.value = 0

    for _ in range(4):
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        assert dut.m_tvalid.value == 1
        assert dut.beat_idx.value == 2

    dut.m_tready.value = 1
    await RisingEdge(dut.clk)

    for expected_beat in range(3, 6):
        await FallingEdge(dut.clk)
        assert dut.m_tvalid.value == 1
        assert dut.beat_idx.value == expected_beat
        if expected_beat == 5:
            assert dut.m_tlast.value == 1
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    assert dut.busy.value == 0 and dut.m_tvalid.value == 0

@cocotb.test()
async def test_stall_at_start(dut):
    cocotb.start_soon(Clock(dut.clk, 10 , unit="ns").start())
    await reset_dut(dut)

    dut.m_tready.value = 0
    dut.fire.value = 1
    await ClockCycles(dut.clk, 1)
    dut.fire.value = 0

    for _ in range(3):
        await FallingEdge(dut.clk)
        assert dut.m_tvalid.value == 1
        assert dut.beat_idx.value == 0
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    assert dut.m_tvalid.value == 1
    assert dut.beat_idx.value == 0
    dut.m_tready.value = 1
    await RisingEdge(dut.clk)

    for expected_beat in range(1, 6):
        await FallingEdge(dut.clk)
        assert dut.m_tvalid.value == 1
        assert dut.beat_idx.value == expected_beat
        if expected_beat == 5:
            assert dut.m_tlast.value == 1
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    assert dut.busy.value == 0 and dut.m_tvalid.value == 0

@cocotb.test()
async def test_stall_on_last_beat(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.m_tready.value = 1
    dut.fire.value = 1
    await ClockCycles(dut.clk, 1)
    dut.fire.value = 0

    for expected_beat in range(5):
        await FallingEdge(dut.clk)
        assert dut.m_tvalid.value == 1
        assert dut.beat_idx.value == expected_beat
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    assert dut.m_tvalid.value == 1
    assert dut.beat_idx.value == 5
    assert dut.m_tlast.value == 1
    dut.m_tready.value = 0

    for _ in range(3):
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        assert dut.m_tvalid.value == 1
        assert dut.beat_idx.value == 5
        assert dut.m_tlast.value == 1
        assert dut.busy.value == 1

    dut.m_tready.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    assert dut.busy.value == 0 and dut.m_tvalid.value == 0

@cocotb.test()
async def test_random_backpressure(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.m_tready.value = 1
    dut.fire.value = 1
    await ClockCycles(dut.clk, 1)
    dut.fire.value = 0

    handshake_beats = []

    rng = random.Random(0)
    prev_valid = 0

    for _ in range(100):
        await FallingEdge(dut.clk)
        ready_before = rng.randint(0, 1)
        dut.m_tready.value = ready_before
        valid_before = int(dut.m_tvalid.value)
        beat_before = int(dut.beat_idx.value)
        last_before = int(dut.m_tlast.value)

        await RisingEdge(dut.clk)
        await ReadOnly()
        valid_after = int(dut.m_tvalid.value)

        if valid_before == 1 and ready_before == 1:
            handshake_beats.append(beat_before)
            if beat_before == 5:
                assert last_before == 1
            else:
                assert last_before == 0

        if prev_valid == 1 and valid_after == 0:
            assert handshake_beats == [0, 1, 2, 3, 4, 5]
        prev_valid = valid_after

        if handshake_beats == [0, 1, 2, 3, 4, 5]:
            assert dut.m_tvalid.value == 0
            assert dut.busy.value == 0
            break

    assert handshake_beats == [0, 1, 2, 3, 4, 5]

@cocotb.test()
async def test_fire_ignored_while_busy(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit = "ns").start())
    await reset_dut(dut)

    dut.m_tready.value = 1
    dut.fire.value = 1
    await ClockCycles(dut.clk, 1)
    dut.fire.value = 0

    handshake_beats = []

    for _ in range(6):
        await FallingEdge(dut.clk)
        assert dut.m_tvalid.value == 1
        
        beat_before = int(dut.beat_idx.value)
        handshake_beats.append(beat_before)

        if beat_before == 2:
            dut.fire.value = 1
            await RisingEdge(dut.clk)
            dut.fire.value = 0
        else:
            await RisingEdge(dut.clk)

        
    await FallingEdge(dut.clk)
    assert dut.m_tvalid.value == 0
    assert dut.busy.value == 0
    await ClockCycles(dut.clk, 1)
    await ClockCycles(dut.clk, 1)
    assert handshake_beats == [0,1,2,3,4,5]
    assert dut.m_tvalid.value == 0
    assert dut.busy.value == 0
    
@cocotb.test()
async def test_fire_during_reset(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.fire.value = 0
    dut.rst_n.value = 0
    dut.m_tready.value = 1
    dut.mux_tdata.value = 0
    dut.mux_tkeep.value = 0

    await RisingEdge(dut.clk)

    for _ in range (2):
        await RisingEdge(dut.clk)
        assert dut.busy.value == 0
        assert dut.m_tvalid.value == 0
        assert dut.beat_idx.value == 0

    dut.fire.value = 1

    await ClockCycles(dut.clk, 1)
    dut.fire.value = 0

    await ClockCycles(dut.clk,1)
    dut.rst_n.value = 1

    for _ in range (3):
        await FallingEdge(dut.clk)
        assert dut.busy.value == 0
        assert dut.m_tvalid.value == 0
        assert dut.beat_idx.value == 0
        await RisingEdge(dut.clk)

@cocotb.test()
async def test_fire_held_high(dut):
       
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.fire.value = 0
    dut.rst_n.value = 0
    dut.m_tready.value = 1
    dut.mux_tdata.value = 0
    dut.mux_tkeep.value = 0

    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    
    assert dut.busy.value == 0

    dut.fire.value = 1

    await RisingEdge(dut.clk)

    for expected_beat in range(6): # 0, 1, 2, 3, 4, 5
        await FallingEdge(dut.clk) # Read safely on falling edge
        
        assert dut.busy.value == 1, f"Expected busy=1 on beat {expected_beat}"
        assert dut.m_tvalid.value == 1
        assert dut.beat_idx.value == expected_beat
        
        if expected_beat == 5:
            assert dut.m_tlast.value == 1
        else:
            assert dut.m_tlast.value == 0
            
        await RisingEdge(dut.clk) # Step to the next clock cycle

    await FallingEdge(dut.clk)
    assert dut.busy.value == 0, "Expected a 1-cycle IDLE gap based on current RTL!"
    assert dut.m_tvalid.value == 0
    await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    assert dut.busy.value == 1, "RTL failed to re-fire a new frame after the idle cycle"
    assert dut.beat_idx.value == 0
    await RisingEdge(dut.clk)

    # Let the second frame process beats 1 and 2
    for expected_beat in range(1, 3):
        await FallingEdge(dut.clk)
        assert dut.busy.value == 1
        assert dut.beat_idx.value == expected_beat
        await RisingEdge(dut.clk)
    
    # Drop fire mid-frame. The current frame must still finish gracefully!
    dut.fire.value = 0 

    # Track remaining beats of the second frame (beats 3, 4, 5) step-by-step
    for expected_beat in range(3, 6):
        await FallingEdge(dut.clk)
        assert dut.busy.value == 1
        assert dut.m_tvalid.value == 1
        assert dut.beat_idx.value == expected_beat
        if expected_beat == 5:
            assert dut.m_tlast.value == 1
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    assert dut.busy.value == 0, "Design failed to return to idle after fire was released!"
    assert dut.m_tvalid.value == 0
    
@cocotb.test()
async def test_reset_midframe(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.m_tready.value = 1
    dut.fire.value = 1
    await RisingEdge(dut.clk) # Trigger the start of the frame
    dut.fire.value = 0

    # Let beats 0, 1, and 2 process normally
    for expected_beat in range(3):
        await FallingEdge(dut.clk) # Safe reading phase
        assert dut.busy.value == 1
        assert dut.m_tvalid.value == 1
        assert dut.beat_idx.value == expected_beat
        await RisingEdge(dut.clk) # Move to the next cycle

    dut.rst_n.value = 0
    
    # Hold reset low for a couple of cycles to simulate an asynchronous or synchronous reset hit
    await ClockCycles(dut.clk, 2) 

    await FallingEdge(dut.clk)
    assert dut.busy.value == 0, "busy did not drop to 0 during mid-frame reset!"
    assert dut.m_tvalid.value == 0, "m_tvalid did not drop to 0 during mid-frame reset!"

    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1) # Give the design a cycle to stabilize in IDLE

    dut.fire.value = 1
    await RisingEdge(dut.clk)
    dut.fire.value = 0

    for expected_beat in range(3):
        await FallingEdge(dut.clk)
        assert dut.busy.value == 1, f"Failed: Expected busy=1 on fresh frame beat {expected_beat}"
        assert dut.m_tvalid.value == 1, f"Failed: Expected m_tvalid=1 on fresh frame beat {expected_beat}"
        assert dut.beat_idx.value == expected_beat, f"Failed: Expected beat_idx={expected_beat}, got {int(dut.beat_idx.value)}"
        await RisingEdge(dut.clk)

@cocotb.test()
async def test_data_passthrough(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.m_tready.value = 1
    dut.fire.value = 1
    await ClockCycles(dut.clk, 1)
    dut.fire.value = 0

    for expected_beat in range(6):
        await FallingEdge(dut.clk)
        assert dut.m_tvalid.value == 1
        assert dut.beat_idx.value == expected_beat

        # Emulate the reply beat mux: unique data per beat. An ARP reply is
        data = 0xA5A5_0000_0000_0000 | (expected_beat << 8) | expected_beat
        keep = 0x03 if expected_beat == 5 else 0xFF
        dut.mux_tdata.value = data
        dut.mux_tkeep.value = keep

        await ReadOnly()
        assert dut.m_tdata.value == data, f"beat {expected_beat}: m_tdata did not follow mux_tdata"
        assert dut.m_tkeep.value == keep, f"beat {expected_beat}: m_tkeep did not follow mux_tkeep"

        if expected_beat == 2:
            # The passthrough is combinational: a mid-cycle change on the mux
            # inputs must appear on the outputs without waiting for a clock edge
            await Timer(1, unit="ns")
            data = 0x1234_5678_9ABC_DEF0
            dut.mux_tdata.value = data
            await ReadOnly()
            assert dut.m_tdata.value == data, "m_tdata is not combinationally following mux_tdata"

        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    assert dut.busy.value == 0 and dut.m_tvalid.value == 0

@cocotb.test()
async def test_back_to_back_frames(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.m_tready.value = 1
    dut.fire.value = 1
    await ClockCycles(dut.clk, 1)
    dut.fire.value = 0

    for expected_beat in range(6):
        await FallingEdge(dut.clk)
        assert dut.m_tvalid.value == 1
        assert dut.beat_idx.value == expected_beat
        await RisingEdge(dut.clk)

    dut.fire.value = 1
    await FallingEdge(dut.clk)
    assert dut.busy.value == 0 and dut.m_tvalid.value == 0, "expected the 1-cycle idle gap between frames"
    await RisingEdge(dut.clk)
    dut.fire.value = 0

    for expected_beat in range(6):
        await FallingEdge(dut.clk)
        assert dut.m_tvalid.value == 1, f"frame 2 beat {expected_beat}: m_tvalid dropped"
        assert dut.beat_idx.value == expected_beat, f"frame 2: beat counter did not restart cleanly"
        if expected_beat == 5:
            assert dut.m_tlast.value == 1
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    assert dut.busy.value == 0 and dut.m_tvalid.value == 0

@cocotb.test()
async def test_soak(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    rng = random.Random(2)

    for frame in range(10):
        # random idle gap before firing
        for _ in range(rng.randint(0, 4)):
            await RisingEdge(dut.clk)

        await FallingEdge(dut.clk)
        assert dut.busy.value == 0, f"frame {frame}: not idle before fire"
        dut.fire.value = 1
        dut.m_tready.value = rng.randint(0, 1)
        await RisingEdge(dut.clk)
        dut.fire.value = 0

        # Random backpressure until all 6 beats are delivered. Sampling on the
        handshakes = []
        cycles = 0
        while len(handshakes) < 6:
            cycles += 1
            assert cycles < 100, f"frame {frame}: timed out waiting for 6 handshakes"
            await FallingEdge(dut.clk)
            assert dut.m_tvalid.value == 1, f"frame {frame}: m_tvalid dropped mid-frame"
            beat = int(dut.beat_idx.value)
            if beat == 5:
                assert dut.m_tlast.value == 1
            else:
                assert dut.m_tlast.value == 0
            ready = rng.randint(0, 1)
            dut.m_tready.value = ready
            if ready:
                handshakes.append(beat)
            await RisingEdge(dut.clk)

        assert handshakes == [0, 1, 2, 3, 4, 5], f"frame {frame}: handshake beats were {handshakes}"

        await FallingEdge(dut.clk)
        dut.m_tready.value = 0
        assert dut.m_tvalid.value == 0 and dut.busy.value == 0, f"frame {frame}: did not return to idle"