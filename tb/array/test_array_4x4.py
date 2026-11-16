"""cocotb suite for the 4x4 array.

Two oracles per test where it's possible. `matmul_reference` is the maths;
`ArrayModel` is a cycle-accurate mesh composed from the already-verified
`PEModel`, so a mismatch against one and not the other says whether the fault is
arithmetic or wiring.

Tile control is a single broadcast `clear` at t=0 with `en` high throughout
(ADR-0004). That is only correct because the feeder presents zeros outside each
cell's window, so `test_feed_schedule_pads_outside_every_window` checks the
contract directly rather than leaving it implied by the other tests passing.
"""

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from array_model import ArrayModel, feed_schedule, matmul_reference, total_cycles

DATA_W = 8
ACC_W = 32
N = 4
LO, HI = -(2 ** (DATA_W - 1)), 2 ** (DATA_W - 1) - 1


def pack(values, width: int) -> int:
    """Pack signed ints into one vector, element i at [i*width +: width]."""
    mask = (1 << width) - 1
    out = 0
    for idx, value in enumerate(values):
        out |= (int(value) & mask) << (idx * width)
    return out


def read_acc(dut) -> np.ndarray:
    """Unpack acc_flat into a 4x4 of signed ints. PE(i,j) is at i*N + j."""
    raw = dut.acc_flat.value.to_unsigned()
    mask = (1 << ACC_W) - 1
    sign = 1 << (ACC_W - 1)
    out = np.zeros((N, N), dtype=np.int64)
    for i in range(N):
        for j in range(N):
            word = (raw >> ((i * N + j) * ACC_W)) & mask
            out[i, j] = word - (1 << ACC_W) if word & sign else word
    return out


async def start(dut):
    """Clock running, one reset pulse, DUT idle."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.en.value = 0
    dut.clear.value = 0
    dut.a_in_flat.value = 0
    dut.b_in_flat.value = 0
    for _ in range(2):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def run_tile(dut, a: np.ndarray, b: np.ndarray, *, check_each_cycle=False):
    """Stream one tile through the DUT and a model in lockstep.

    Returns (rtl_acc, model_acc). With check_each_cycle the full 4x4 is compared
    on every edge, which localises a wiring fault to the cycle it appears.
    """
    model = ArrayModel(DATA_W, ACC_W, N)
    model.reset()

    for t, (a_vec, b_vec) in enumerate(feed_schedule(a, b, N)):
        dut.a_in_flat.value = pack(a_vec, DATA_W)
        dut.b_in_flat.value = pack(b_vec, DATA_W)
        dut.en.value = 1
        dut.clear.value = int(t == 0)
        await RisingEdge(dut.clk)
        model.step(a_vec, b_vec, en=True, clear=(t == 0))
        await Timer(1, unit="ns")
        if check_each_cycle:
            rtl = read_acc(dut)
            assert np.array_equal(rtl, model.acc()), (
                f"cycle {t}: accumulators diverged\nrtl\n{rtl}\nmodel\n{model.acc()}"
            )

    dut.en.value = 0
    dut.clear.value = 0
    return read_acc(dut), model.acc()


@cocotb.test()
async def test_reset_clears_every_accumulator(dut):
    """Reset zeroes all sixteen accumulators, not just the ones on the edges."""
    await start(dut)
    acc = read_acc(dut)
    assert np.array_equal(acc, np.zeros((N, N), dtype=np.int64)), f"after reset:\n{acc}"


@cocotb.test()
async def test_identity_returns_the_matrix(dut):
    """M @ I == M. The first result that distinguishes a wired array from noise."""
    await start(dut)
    rng = np.random.default_rng(11)
    m = rng.integers(LO, HI + 1, size=(N, N), dtype=np.int64)
    identity = np.eye(N, dtype=np.int64)

    rtl, model = await run_tile(dut, m, identity)
    assert np.array_equal(rtl, m), f"M @ I should be M\nrtl\n{rtl}\nM\n{m}"
    assert np.array_equal(rtl, model), "rtl and cycle-accurate model disagree"


@cocotb.test()
async def test_random_tiles_against_golden(dut):
    """Random A @ B at several tile depths, against both oracles."""
    await start(dut)
    rng = np.random.default_rng(23)

    for k in (1, 2, 4, 9, 16):
        a = rng.integers(LO, HI + 1, size=(N, k), dtype=np.int64)
        b = rng.integers(LO, HI + 1, size=(k, N), dtype=np.int64)

        rtl, model = await run_tile(dut, a, b)
        want = matmul_reference(a, b, ACC_W)

        assert np.array_equal(rtl, want), f"K={k} vs numpy\nrtl\n{rtl}\nwant\n{want}"
        assert np.array_equal(rtl, model), f"K={k} vs cycle model\nrtl\n{rtl}\n{model}"
        dut._log.info(f"K={k}: {total_cycles(k)} cycles, 16/16 accumulators match")


@cocotb.test()
async def test_cycle_accurate_against_model(dut):
    """Compare all sixteen accumulators on every edge, not just at the end.

    An end-of-tile check can pass while the wavefront is wrong in a way that
    cancels. This one fails on the cycle the divergence appears.
    """
    await start(dut)
    rng = np.random.default_rng(31)
    k = 8
    a = rng.integers(LO, HI + 1, size=(N, k), dtype=np.int64)
    b = rng.integers(LO, HI + 1, size=(k, N), dtype=np.int64)

    rtl, model = await run_tile(dut, a, b, check_each_cycle=True)
    assert np.array_equal(rtl, matmul_reference(a, b, ACC_W))


@cocotb.test()
async def test_feed_schedule_pads_outside_every_window(dut):
    """The contract that makes a broadcast clear correct.

    PE(i,j) has real operands only for t = i+j .. k-1+i+j. Outside that the
    feeder must present zero to at least one of its operands, or a cell running
    with `en` high for the whole tile would accumulate values that don't belong
    to it. Checked on the schedule itself, since it is what the array trusts.
    """
    await start(dut)
    k = 5
    rng = np.random.default_rng(41)
    a = rng.integers(1, HI + 1, size=(N, k), dtype=np.int64)   # no zeros, so a
    b = rng.integers(1, HI + 1, size=(k, N), dtype=np.int64)   # zero means padding

    schedule = list(feed_schedule(a, b, N))
    assert len(schedule) == total_cycles(k, N)

    for i in range(N):
        for j in range(N):
            for t, _ in enumerate(schedule):
                in_window = 0 <= t - i - j < k
                # An operand reaching PE(i,j) at cycle t was injected j (or i)
                # cycles earlier, so index the schedule back by the hop count.
                a_seen = schedule[t - j][0][i] if t - j >= 0 else 0
                b_seen = schedule[t - i][1][j] if t - i >= 0 else 0
                if not in_window:
                    assert a_seen == 0 or b_seen == 0, (
                        f"PE({i},{j}) at t={t} is outside its window but sees "
                        f"a={a_seen} b={b_seen}; the product would be nonzero"
                    )
    dut._log.info("feed schedule pads every cell's out-of-window cycles")


@cocotb.test()
async def test_stall_holds_every_accumulator(dut):
    """`en` low freezes the whole array, so it can be fed from a slower source."""
    await start(dut)
    rng = np.random.default_rng(53)
    k = 6
    a = rng.integers(LO, HI + 1, size=(N, k), dtype=np.int64)
    b = rng.integers(LO, HI + 1, size=(k, N), dtype=np.int64)

    schedule = list(feed_schedule(a, b, N))
    model = ArrayModel(DATA_W, ACC_W, N)
    model.reset()

    for t, (a_vec, b_vec) in enumerate(schedule):
        dut.a_in_flat.value = pack(a_vec, DATA_W)
        dut.b_in_flat.value = pack(b_vec, DATA_W)
        dut.en.value = 1
        dut.clear.value = int(t == 0)
        await RisingEdge(dut.clk)
        model.step(a_vec, b_vec, en=True, clear=(t == 0))
        await Timer(1, unit="ns")

        # Stall for three cycles mid-tile with garbage on the inputs. Nothing
        # may move: not the accumulators, not the operand pipeline.
        #
        # `clear` has to be deasserted here. It is not gated by `en` — a tile
        # boundary should not have to spend a MAC step to zero — so holding it
        # through a stall would zero the array. That makes `clear` a
        # single-cycle pulse coincident with the first enabled cycle, which is
        # the contract this loop checks is survivable.
        frozen = read_acc(dut)
        garbage = pack([HI] * N, DATA_W)
        for _ in range(3):
            dut.a_in_flat.value = garbage
            dut.b_in_flat.value = garbage
            dut.en.value = 0
            dut.clear.value = 0
            await RisingEdge(dut.clk)
            model.step([HI] * N, [HI] * N, en=False, clear=False)
            await Timer(1, unit="ns")
            assert np.array_equal(read_acc(dut), frozen), f"stall at t={t} moved the array"
            assert np.array_equal(read_acc(dut), model.acc()), (
                f"stall at t={t}: rtl and model diverged"
            )

    assert np.array_equal(read_acc(dut), matmul_reference(a, b, ACC_W))
    assert np.array_equal(read_acc(dut), model.acc())


@cocotb.test()
async def test_most_negative_product_across_the_array(dut):
    """-128 * -128 = +16384 in every cell at once.

    The signed corner that a 2*DATA_W-1 intermediate gets wrong, checked on all
    sixteen cells rather than one, since a sign bug could be wired per-column.
    """
    await start(dut)
    k = 3
    a = np.full((N, k), LO, dtype=np.int64)
    b = np.full((k, N), LO, dtype=np.int64)

    rtl, model = await run_tile(dut, a, b)
    want = matmul_reference(a, b, ACC_W)
    assert np.all(want == k * (LO * LO)), f"reference itself is wrong: {want}"
    assert np.array_equal(rtl, want), f"rtl\n{rtl}\nwant\n{want}"
    assert np.array_equal(rtl, model)
    dut._log.info(f"all 16 cells hold {k} * ({LO} * {LO}) = {k * LO * LO}")
