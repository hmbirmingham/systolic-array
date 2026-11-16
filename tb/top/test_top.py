"""cocotb suite for the synthesizable wrapper.

The array is verified in `tb/array`. This covers only what the wrapper adds:
that the readout emits every accumulator, in the order `acc_flat` packs them,
and that the snapshot is a snapshot.

Readout order is the part worth testing properly. Row-major PE(i,j) at i*N+j is
a convention, and a wrapper that shifted the other way, or started a word late,
would still produce sixteen plausible numbers.
"""

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from array_model import feed_schedule, matmul_reference

DATA_W = 8
ACC_W = 32
N = 4
WORDS = N * N
LO, HI = -(2 ** (DATA_W - 1)), 2 ** (DATA_W - 1) - 1


def pack(values, width: int) -> int:
    mask = (1 << width) - 1
    out = 0
    for idx, value in enumerate(values):
        out |= (int(value) & mask) << (idx * width)
    return out


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.en.value = 0
    dut.clear.value = 0
    dut.read_start.value = 0
    dut.a_in_flat.value = 0
    dut.b_in_flat.value = 0
    for _ in range(2):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def stream(dut, a, b):
    """Push one tile through. Leaves `en` low and the accumulators settled."""
    for t, (a_vec, b_vec) in enumerate(feed_schedule(a, b, N)):
        dut.a_in_flat.value = pack(a_vec, DATA_W)
        dut.b_in_flat.value = pack(b_vec, DATA_W)
        dut.en.value = 1
        dut.clear.value = int(t == 0)
        await RisingEdge(dut.clk)
    dut.en.value = 0
    dut.clear.value = 0
    await Timer(1, unit="ns")


async def read_out(dut, expect_words=WORDS):
    """Pulse read_start and collect words while result_valid is high."""
    dut.read_start.value = 1
    await RisingEdge(dut.clk)
    dut.read_start.value = 0
    await Timer(1, unit="ns")

    words = []
    guard = 0
    while dut.result_valid.value and guard < expect_words * 4:
        words.append(dut.result.value.to_signed())
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        guard += 1
    return words


@cocotb.test()
async def test_readout_order_matches_row_major(dut):
    """Every accumulator comes out once, PE(i,j) at position i*N+j."""
    await start(dut)
    rng = np.random.default_rng(67)
    k = 5
    a = rng.integers(LO, HI + 1, size=(N, k), dtype=np.int64)
    b = rng.integers(LO, HI + 1, size=(k, N), dtype=np.int64)

    await stream(dut, a, b)
    words = await read_out(dut)

    want = matmul_reference(a, b, ACC_W).reshape(-1).tolist()
    assert len(words) == WORDS, f"expected {WORDS} words, got {len(words)}"
    assert words == want, f"readout order wrong\ngot  {words}\nwant {want}"
    dut._log.info(f"all {WORDS} accumulators read out in row-major order")


@cocotb.test()
async def test_readout_is_exactly_sixteen_words_then_done(dut):
    """Not fifteen, not seventeen, and `read_done` asserts after the last."""
    await start(dut)
    k = 2
    a = np.ones((N, k), dtype=np.int64)
    b = np.ones((k, N), dtype=np.int64)
    await stream(dut, a, b)

    assert dut.read_done.value == 1, "read_done should be high while idle"

    dut.read_start.value = 1
    await RisingEdge(dut.clk)
    dut.read_start.value = 0
    await Timer(1, unit="ns")

    valid_cycles = 0
    for _ in range(WORDS * 3):
        if dut.result_valid.value:
            valid_cycles += 1
        else:
            break
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

    assert valid_cycles == WORDS, f"result_valid held for {valid_cycles}, want {WORDS}"
    assert dut.read_done.value == 1, "read_done should reassert after the last word"


@cocotb.test()
async def test_snapshot_is_not_disturbed_by_the_next_tile(dut):
    """The capture is a snapshot, so the array can run on during readout.

    This is the property that lets a host read tile n while tile n+1 streams.
    """
    await start(dut)
    rng = np.random.default_rng(71)
    k = 4
    a1 = rng.integers(LO, HI + 1, size=(N, k), dtype=np.int64)
    b1 = rng.integers(LO, HI + 1, size=(k, N), dtype=np.int64)
    a2 = rng.integers(LO, HI + 1, size=(N, k), dtype=np.int64)
    b2 = rng.integers(LO, HI + 1, size=(k, N), dtype=np.int64)

    await stream(dut, a1, b1)

    # Latch tile 1, then immediately start tile 2 while shifting tile 1 out.
    dut.read_start.value = 1
    await RisingEdge(dut.clk)
    dut.read_start.value = 0
    await Timer(1, unit="ns")

    words = []
    schedule = list(feed_schedule(a2, b2, N))
    for idx in range(WORDS):
        words.append(dut.result.value.to_signed())
        if idx < len(schedule):
            a_vec, b_vec = schedule[idx]
            dut.a_in_flat.value = pack(a_vec, DATA_W)
            dut.b_in_flat.value = pack(b_vec, DATA_W)
            dut.en.value = 1
            dut.clear.value = int(idx == 0)
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
    dut.en.value = 0
    dut.clear.value = 0

    want = matmul_reference(a1, b1, ACC_W).reshape(-1).tolist()
    assert words == want, (
        "tile 2 streaming corrupted tile 1's readout\n"
        f"got  {words}\nwant {want}"
    )
    dut._log.info("snapshot survived a concurrent tile")
