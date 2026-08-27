import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

CLK_PERIOD_NS = 10

async def reset_dut(dut):
    dut.rst_n.value = 0
    dut.p_tdata.value = 0
    dut.p_tkeep.value = 0
    dut.p_tvalid.value = 0
    dut.p_tlast.value = 0
    dut.orig_tlast.value = 0
    dut.orig_payload_valid.value = 0
    dut.w_final_ethertype.value = 0
    dut.tuser.value = 0

@cocotb.test()
async def test_byte_tkeep_reversal(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit = "ns").start())
    await reset_dut(dut)

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1


    p_tdata_val = 0x0102030405060708
    p_tkeep_val = 0b10110001

    dut.p_tdata.value = p_tdata_val
    dut.p_tkeep.value = p_tkeep_val

    await RisingEdge(dut.clk)

    bytes_in = [(p_tdata_val >> (8 * i)) & 0xFF for i in range(8)]
    expected_reversed_tdata = 0
    for i, b in enumerate(bytes_in):
        expected_reversed_tdata |= b << (8 *(7 - i))

    expected_reversed_tkeep = 0
    for i in range(8):
        bit = (p_tkeep_val >> i) & 0x1
        expected_reversed_tkeep |= bit << (7 - i)

    assert dut.s_tdata.value == expected_reversed_tdata, (
        f"tdata reversal wrong: got {int(dut.s_tdata.value):#018x}, expected {expected_reversed_tdata:#018x}"
    )
    assert dut.s_tkeep.value == expected_reversed_tkeep, (
        f"tkeep reversal wrong: got {int(dut.s_tkeep.value):#04x}, expected {expected_reversed_tkeep:#04x}"
    )





@cocotb.test()
async def test_ethertype_routing(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit = "ns").start())
    await reset_dut(dut)

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    dut.p_tvalid.value = 1
    dut.w_final_ethertype.value = 0x0806

    p_tdata_val = 0x0102030405060708
    p_tkeep_val = 0b10110001

    dut.p_tdata.value = p_tdata_val
    dut.p_tkeep.value = p_tkeep_val

    await RisingEdge(dut.clk)

    assert dut.s_tvalid.value == 1

    dut.p_tvalid.value = 1
    dut.w_final_ethertype.value = 0x0800

    p_tdata_val = 0x0102030405060708
    p_tkeep_val = 0b10110001

    dut.p_tdata.value = p_tdata_val
    dut.p_tkeep.value = p_tkeep_val

    await RisingEdge(dut.clk)

    assert dut.s_tvalid.value == 0





@cocotb.test()
async def test_tuser_latch(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit = "ns").start())
    await reset_dut(dut)

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1


    p_tdata_val = 0x0102030405060708
    p_tkeep_val = 0b10110001

    dut.p_tdata.value = p_tdata_val
    dut.p_tkeep.value = p_tkeep_val
    dut.orig_tlast.value = 1
    dut.orig_payload_valid.value = 1
    dut.tuser.value = 1

    await RisingEdge(dut.clk)

    dut.tuser.value = 0 
    dut.orig_payload_valid.value = 0
    dut.orig_tlast.value = 0

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    assert dut.s_tuser.value == 1