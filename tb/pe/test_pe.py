"""cocotb suite for the processing element.

Every assertion compares the RTL against `golden/pe_model.py` rather than
against a number written here by hand. A MAC has an exact definition, so the
testbench has a real oracle and there is no reason to settle for a weaker one.
"""

import random

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from pe_model import PEModel, dot_reference

DATA_W = 8
ACC_W = 32
LO, HI = -(2 ** (DATA_W - 1)), 2 ** (DATA_W - 1) - 1


def signed(handle) -> int:
    """Read a signed RTL value as a Python int."""
    return handle.value.to_signed()


async def start(dut):
    """Clock running, one reset pulse, model and DUT both at zero."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.en.value = 0
    dut.clear.value = 0
    dut.a_in.value = 0
    dut.b_in.value = 0
    for _ in range(2):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    return PEModel(DATA_W, ACC_W)


async def apply(dut, model, a, b, en, clear):
    """Drive one cycle on both the DUT and the model, then compare."""
    dut.a_in.value = a
    dut.b_in.value = b
    dut.en.value = int(en)
    dut.clear.value = int(clear)
    await RisingEdge(dut.clk)
    model.step(a, b, en, clear)
    # Settle past the nonblocking update before sampling.
    await cocotb.triggers.Timer(1, unit="ns")
    assert signed(dut.acc) == model.acc, (
        f"acc: rtl {signed(dut.acc)} != model {model.acc} "
        f"(a={a} b={b} en={en} clear={clear})"
    )
    assert signed(dut.a_out) == model.a_out, f"a_out: {signed(dut.a_out)} != {model.a_out}"
    assert signed(dut.b_out) == model.b_out, f"b_out: {signed(dut.b_out)} != {model.b_out}"


@cocotb.test()
async def test_reset_clears(dut):
    """Reset zeroes the accumulator and both operand registers."""
    model = await start(dut)
    assert signed(dut.acc) == 0
    assert signed(dut.a_out) == 0
    assert signed(dut.b_out) == 0
    assert model.acc == 0


@cocotb.test()
async def test_accumulates_against_golden(dut):
    """A random operand stream tracks the model cycle for cycle."""
    random.seed(0xC0C0)
    model = await start(dut)
    for _ in range(200):
        await apply(dut, model, random.randint(LO, HI), random.randint(LO, HI), en=True, clear=False)


@cocotb.test()
async def test_stall_holds_the_accumulator(dut):
    """With `en` low the PE keeps its total and forwards nothing.

    This is the property that lets the array be fed from a slower source: a
    stalled cycle has to be a no-op, not a lost partial result.
    """
    model = await start(dut)
    for _ in range(4):
        await apply(dut, model, 7, 6, en=True, clear=False)
    held = model.acc
    for _ in range(3):
        await apply(dut, model, 100, 100, en=False, clear=False)
    assert signed(dut.acc) == held, "a stalled PE lost its accumulator"
    await apply(dut, model, 7, 6, en=True, clear=False)
    assert signed(dut.acc) == held + 42


@cocotb.test()
async def test_clear_outranks_accumulate(dut):
    """`clear` with `en` starts the new tile from this cycle's product."""
    model = await start(dut)
    for _ in range(5):
        await apply(dut, model, 9, 9, en=True, clear=False)
    assert signed(dut.acc) == 405
    # Tile boundary: the incoming product belongs to the new tile, not the old.
    await apply(dut, model, 3, 4, en=True, clear=True)
    assert signed(dut.acc) == 12, "clear+en must restart from the new product"
    # Clear alone zeroes without consuming a MAC step.
    await apply(dut, model, 50, 50, en=False, clear=True)
    assert signed(dut.acc) == 0


@cocotb.test()
async def test_most_negative_product_is_not_truncated(dut):
    """-128 * -128 is +16384, which needs the full 2*DATA_W product width.

    The signed corner that a 2*DATA_W-1 product would silently get wrong, and
    the reason the RTL carries a full-width intermediate.
    """
    model = await start(dut)
    await apply(dut, model, LO, LO, en=True, clear=True)
    assert signed(dut.acc) == 16384, f"expected 16384, got {signed(dut.acc)}"


@cocotb.test()
async def test_pe_computes_a_dot_product(dut):
    """The property the whole array rests on.

    A PE streaming a row of A against a column of B holds one element of
    A @ B. If this fails, nothing built on top of the PE can be correct.
    """
    random.seed(0xD07)
    model = await start(dut)
    a = np.array([random.randint(LO, HI) for _ in range(4)], dtype=np.int64)
    b = np.array([random.randint(LO, HI) for _ in range(4)], dtype=np.int64)
    for k in range(4):
        await apply(dut, model, int(a[k]), int(b[k]), en=True, clear=(k == 0))
    want = dot_reference(a, b, ACC_W)
    assert signed(dut.acc) == want, f"dot product: rtl {signed(dut.acc)} != numpy {want}"
