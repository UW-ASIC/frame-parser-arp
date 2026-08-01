import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge
import random


def slice_metadata(raw):
    return {
        "valid"      : (raw >> 144) & 0x1,
        "frame_len"  : (raw >> 130) & 0x3FFF,
        "fcs_ok"     : (raw >> 129) & 0x1,
        "frame_type" : (raw >> 127) & 0x3,
        "pcp"        : (raw >> 124) & 0x7,
        "vlan_id"    : (raw >> 112) & 0xFFF,
        "ethertype"  : (raw >>  96) & 0xFFFF,
        "src_mac"    : (raw >>  48) & 0xFFFFFFFFFFFF,
        "dst_mac"    :  raw         & 0xFFFFFFFFFFFF,
    }


async def reset_dut(dut):
    dut.eof.value        = 0
    dut.dst_mac.value    = 0
    dut.src_mac.value    = 0
    dut.ethertype.value  = 0
    dut.vlan_id.value    = 0
    dut.pcp.value        = 0
    dut.frame_type.value = 0
    dut.frame_len.value  = 0
    dut.fcs_ok.value     = 0
    dut.rst_n.value      = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)


@cocotb.test()
async def test_basic_ethernet_ii(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    DST_MAC    = 0xAABBCCDDEEFF
    SRC_MAC    = 0x112233445566
    ETHERTYPE  = 0x0800
    FRAME_LEN  = 64
    FCS_OK     = 1
    FRAME_TYPE = 0b00

    dut.dst_mac.value    = DST_MAC
    dut.src_mac.value    = SRC_MAC
    dut.ethertype.value  = ETHERTYPE
    dut.vlan_id.value    = 0
    dut.pcp.value        = 0
    dut.frame_type.value = FRAME_TYPE
    dut.frame_len.value  = FRAME_LEN
    dut.fcs_ok.value     = FCS_OK
    dut.eof.value        = 1

    await ClockCycles(dut.clk, 1)
    dut.eof.value = 0

    await FallingEdge(dut.clk)
    f = slice_metadata(int(dut.metadata.value))

    assert f["valid"]      == 1,          "valid not set"
    assert f["dst_mac"]    == DST_MAC,    f"dst_mac: got {hex(f['dst_mac'])}"
    assert f["src_mac"]    == SRC_MAC,    f"src_mac: got {hex(f['src_mac'])}"
    assert f["ethertype"]  == ETHERTYPE,  f"ethertype: got {hex(f['ethertype'])}"
    assert f["frame_type"] == FRAME_TYPE, f"frame_type: got {f['frame_type']}"
    assert f["frame_len"]  == FRAME_LEN,  f"frame_len: got {f['frame_len']}"
    assert f["fcs_ok"]     == FCS_OK,     f"fcs_ok: got {f['fcs_ok']}"
    assert f["vlan_id"]    == 0,          f"vlan_id must be 0 for ETH II, got {f['vlan_id']}"
    assert f["pcp"]        == 0,          f"pcp must be 0 for ETH II, got {f['pcp']}"


@cocotb.test()
async def test_vlan_frame(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    DST_MAC    = 0x010203040506
    SRC_MAC    = 0x0A0B0C0D0E0F
    ETHERTYPE  = 0x0800
    VLAN_ID    = 0xABC
    PCP        = 0b101
    FRAME_TYPE = 0b01
    FRAME_LEN  = 100
    FCS_OK     = 1

    dut.dst_mac.value    = DST_MAC
    dut.src_mac.value    = SRC_MAC
    dut.ethertype.value  = ETHERTYPE
    dut.vlan_id.value    = VLAN_ID
    dut.pcp.value        = PCP
    dut.frame_type.value = FRAME_TYPE
    dut.frame_len.value  = FRAME_LEN
    dut.fcs_ok.value     = FCS_OK
    dut.eof.value        = 1

    await ClockCycles(dut.clk, 1)
    dut.eof.value = 0

    await FallingEdge(dut.clk)
    f = slice_metadata(int(dut.metadata.value))

    assert f["valid"]      == 1,          "valid not set"
    assert f["vlan_id"]    == VLAN_ID,    f"vlan_id: got {hex(f['vlan_id'])}, expected {hex(VLAN_ID)}"
    assert f["pcp"]        == PCP,        f"pcp: got {f['pcp']}, expected {PCP}"
    assert f["ethertype"]  == ETHERTYPE,  f"ethertype: got {hex(f['ethertype'])}"
    assert f["frame_type"] == FRAME_TYPE, f"frame_type: got {f['frame_type']}"


@cocotb.test()
async def test_vlan_fields_zeroed_for_eth_ii(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.dst_mac.value    = 0xDEADBEEFCAFE
    dut.src_mac.value    = 0xCAFEBABE1234
    dut.ethertype.value  = 0x0800
    dut.vlan_id.value    = 0xFFF
    dut.pcp.value        = 0b111
    dut.frame_type.value = 0b00
    dut.frame_len.value  = 64
    dut.fcs_ok.value     = 1
    dut.eof.value        = 1

    await ClockCycles(dut.clk, 1)
    dut.eof.value = 0

    await FallingEdge(dut.clk)
    f = slice_metadata(int(dut.metadata.value))

    assert f["vlan_id"] == 0, f"vlan_id must be zeroed for ETH II even if upstream drove 0xFFF, got {hex(f['vlan_id'])}"
    assert f["pcp"]     == 0, f"pcp must be zeroed for ETH II even if upstream drove 0b111, got {f['pcp']}"


@cocotb.test()
async def test_fcs_error(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.dst_mac.value    = 0xFFFFFFFFFFFF
    dut.src_mac.value    = 0x001122334455
    dut.ethertype.value  = 0x0800
    dut.vlan_id.value    = 0
    dut.pcp.value        = 0
    dut.frame_type.value = 0b00
    dut.frame_len.value  = 64
    dut.fcs_ok.value     = 0
    dut.eof.value        = 1

    await ClockCycles(dut.clk, 1)
    dut.eof.value = 0

    await FallingEdge(dut.clk)
    f = slice_metadata(int(dut.metadata.value))

    assert f["fcs_ok"] == 0, f"fcs_ok: got {f['fcs_ok']}, expected 0"
    assert f["valid"]  == 1, "valid should still be 1"


@cocotb.test()
async def test_valid_pulse_width(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.dst_mac.value    = 0x010101010101
    dut.src_mac.value    = 0x020202020202
    dut.ethertype.value  = 0x0800
    dut.vlan_id.value    = 0
    dut.pcp.value        = 0
    dut.frame_type.value = 0b00
    dut.frame_len.value  = 128
    dut.fcs_ok.value     = 1
    dut.eof.value        = 1

    await ClockCycles(dut.clk, 1)
    dut.eof.value = 0

    await FallingEdge(dut.clk)
    assert (int(dut.metadata.value) >> 144) & 0x1 == 1, "valid should be 1 on the cycle after eof"

    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    assert (int(dut.metadata.value) >> 144) & 0x1 == 0, "valid should deassert after exactly 1 cycle"


@cocotb.test()
async def test_no_eof_no_valid(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.dst_mac.value    = 0xAABBCCDDEEFF
    dut.src_mac.value    = 0x112233445566
    dut.ethertype.value  = 0x0800
    dut.frame_type.value = 0b00
    dut.frame_len.value  = 64
    dut.fcs_ok.value     = 1
    dut.eof.value        = 0

    for _ in range(5):
        await FallingEdge(dut.clk)
        assert (int(dut.metadata.value) >> 144) & 0x1 == 0, \
            "valid must stay 0 when eof has never been asserted"
        await RisingEdge(dut.clk)


@cocotb.test()
async def test_reset_clears_metadata(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.dst_mac.value    = 0xDEADBEEFCAFE
    dut.src_mac.value    = 0xCAFEBABE1234
    dut.ethertype.value  = 0x0806
    dut.vlan_id.value    = 0
    dut.pcp.value        = 0
    dut.frame_type.value = 0b00
    dut.frame_len.value  = 64
    dut.fcs_ok.value     = 1
    dut.eof.value        = 1

    await ClockCycles(dut.clk, 1)
    dut.eof.value = 0

    await FallingEdge(dut.clk)
    assert (int(dut.metadata.value) >> 144) & 0x1 == 1, "Setup: expected valid=1 before reset"

    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)

    await FallingEdge(dut.clk)
    assert int(dut.metadata.value) == 0, \
        f"metadata should be all-zero during reset, got {hex(int(dut.metadata.value))}"

    dut.rst_n.value = 1


@cocotb.test()
async def test_reset_mid_latch(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.dst_mac.value    = 0xAABBCCDDEEFF
    dut.src_mac.value    = 0x112233445566
    dut.ethertype.value  = 0x0800
    dut.frame_type.value = 0b00
    dut.frame_len.value  = 64
    dut.fcs_ok.value     = 1
    dut.eof.value        = 1
    dut.rst_n.value      = 0

    await ClockCycles(dut.clk, 2)

    await FallingEdge(dut.clk)
    assert int(dut.metadata.value) == 0, \
        "Reset must take priority over eof — metadata must remain 0"

    dut.rst_n.value = 1
    dut.eof.value   = 0


@cocotb.test()
async def test_back_to_back_frames(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    F1_DST = 0xAAAAAAAAAAAA
    F1_SRC = 0xBBBBBBBBBBBB
    F1_LEN = 64

    dut.dst_mac.value    = F1_DST
    dut.src_mac.value    = F1_SRC
    dut.ethertype.value  = 0x0800
    dut.vlan_id.value    = 0
    dut.pcp.value        = 0
    dut.frame_type.value = 0b00
    dut.frame_len.value  = F1_LEN
    dut.fcs_ok.value     = 1
    dut.eof.value        = 1

    await ClockCycles(dut.clk, 1)

    await FallingEdge(dut.clk)
    f1 = slice_metadata(int(dut.metadata.value))
    assert f1["valid"]     == 1,     "Frame 1: valid not asserted"
    assert f1["dst_mac"]   == F1_DST,"Frame 1: dst_mac mismatch"
    assert f1["src_mac"]   == F1_SRC,"Frame 1: src_mac mismatch"
    assert f1["frame_len"] == F1_LEN,"Frame 1: frame_len mismatch"

    F2_DST = 0xCCCCCCCCCCCC
    F2_SRC = 0xDDDDDDDDDDDD
    F2_LEN = 1500

    dut.dst_mac.value   = F2_DST
    dut.src_mac.value   = F2_SRC
    dut.ethertype.value = 0x0806
    dut.frame_len.value = F2_LEN

    await RisingEdge(dut.clk)
    dut.eof.value = 0

    await FallingEdge(dut.clk)
    f2 = slice_metadata(int(dut.metadata.value))
    assert f2["valid"]     == 1,     "Frame 2: valid not asserted"
    assert f2["dst_mac"]   == F2_DST,"Frame 2: dst_mac mismatch"
    assert f2["src_mac"]   == F2_SRC,"Frame 2: src_mac mismatch"
    assert f2["frame_len"] == F2_LEN, f"Frame 2: frame_len {f2['frame_len']}, expected {F2_LEN}"


@cocotb.test()
async def test_soak(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    rng = random.Random(42)

    for frame_num in range(50):
        for _ in range(rng.randint(0, 3)):
            await RisingEdge(dut.clk)

        ft   = rng.randint(0, 1)
        dst  = rng.randint(0, (1 << 48) - 1)
        src  = rng.randint(0, (1 << 48) - 1)
        eth  = rng.randint(0, 0xFFFF)
        vid  = rng.randint(0, 0xFFF)
        pcp  = rng.randint(0, 7)
        flen = rng.randint(64, 1522)
        fcs  = rng.randint(0, 1)

        dut.dst_mac.value    = dst
        dut.src_mac.value    = src
        dut.ethertype.value  = eth
        dut.vlan_id.value    = vid
        dut.pcp.value        = pcp
        dut.frame_type.value = ft
        dut.frame_len.value  = flen
        dut.fcs_ok.value     = fcs
        dut.eof.value        = 1

        await ClockCycles(dut.clk, 1)
        dut.eof.value = 0

        await FallingEdge(dut.clk)
        f = slice_metadata(int(dut.metadata.value))

        assert f["valid"]      == 1,    f"Frame {frame_num}: valid not set"
        assert f["dst_mac"]    == dst,  f"Frame {frame_num}: dst_mac mismatch"
        assert f["src_mac"]    == src,  f"Frame {frame_num}: src_mac mismatch"
        assert f["ethertype"]  == eth,  f"Frame {frame_num}: ethertype mismatch"
        assert f["frame_type"] == ft,   f"Frame {frame_num}: frame_type mismatch"
        assert f["frame_len"]  == flen, f"Frame {frame_num}: frame_len mismatch"
        assert f["fcs_ok"]     == fcs,  f"Frame {frame_num}: fcs_ok mismatch"

        if ft == 0b00:
            assert f["vlan_id"] == 0,   f"Frame {frame_num}: vlan_id not zeroed for ETH II"
            assert f["pcp"]     == 0,   f"Frame {frame_num}: pcp not zeroed for ETH II"
        else:
            assert f["vlan_id"] == vid, f"Frame {frame_num}: vlan_id mismatch"
            assert f["pcp"]     == pcp, f"Frame {frame_num}: pcp mismatch"
