"""Benchmark: 4x4 homogeneous transform over a point cloud.

The workload this array exists for. The matrix is a rotation plus translation,
the points are homogeneous, and one tile transforms four of them.

Checked at two levels, kept separate on purpose. `transform_fixed` is the
integer-exact fixed-point answer, computed in Python ints so it cannot overflow
where the RTL would: the RTL must match it **bit for bit**. `transform_exact` is
the float answer, and the gap between the two is quantization error, which is
held to a *derived* bound rather than an observed one. Comparing RTL against
float directly would conflate the two and make neither claim meaningful.
"""

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from array_model import feed_schedule
from pe_model import wrap_signed
from transform_ref import (
    ACC_W,
    Format,
    accumulator_headroom,
    dequantize,
    error_bound_m,
    quantize_points,
    quantize_transform,
    tile_cycles,
    tiles,
    transform_exact,
    transform_fixed,
    w_scale_for,
)

DATA_W = 16
N = 4

# Point format tracks the working volume; the matrix is always fraction-heavy
# because rotation entries are <= 1 (ADR-0002).
FMT = Format(f_matrix=14, f_point=8)
EXTENT_M = 64.0


def rotation(rx: float, ry: float, rz: float) -> np.ndarray:
    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)
    r_x = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    r_y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    r_z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return r_z @ r_y @ r_x


def pose(rx=0.3, ry=-0.7, rz=1.1, t=(10.0, -5.0, 2.0)) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = rotation(rx, ry, rz)
    m[:3, 3] = t
    return m


def cloud(n: int, extent: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    points = np.ones((4, n))
    points[:3] = rng.uniform(-extent, extent, size=(3, n))
    return points


def pack(values, width: int) -> int:
    mask = (1 << width) - 1
    out = 0
    for idx, value in enumerate(values):
        out |= (int(value) & mask) << (idx * width)
    return out


def read_acc(dut) -> np.ndarray:
    raw = dut.acc_flat.value.to_unsigned()
    mask = (1 << ACC_W) - 1
    sign = 1 << (ACC_W - 1)
    out = np.zeros((N, N), dtype=object)
    for i in range(N):
        for j in range(N):
            word = (raw >> ((i * N + j) * ACC_W)) & mask
            out[i, j] = word - (1 << ACC_W) if word & sign else word
    return out


async def start(dut):
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


async def run_tile(dut, matrix_i, block_i) -> np.ndarray:
    """Stream one 4-point tile. Returns the accumulators."""
    for t, (a_vec, b_vec) in enumerate(feed_schedule(matrix_i, block_i, N)):
        dut.a_in_flat.value = pack(a_vec, DATA_W)
        dut.b_in_flat.value = pack(b_vec, DATA_W)
        dut.en.value = 1
        dut.clear.value = int(t == 0)
        await RisingEdge(dut.clk)
    dut.en.value = 0
    dut.clear.value = 0
    await Timer(1, unit="ns")
    return read_acc(dut)


@cocotb.test()
async def test_identity_leaves_points_unmoved(dut):
    """An identity transform returns each point within one LSB."""
    await start(dut)
    points = cloud(16, EXTENT_M, seed=3)
    matrix = np.eye(4)
    matrix_i, w = quantize_transform(matrix, FMT)

    for block, valid in tiles(points, N):
        block_i = quantize_points(block, FMT, w)
        acc = await run_tile(dut, matrix_i, block_i)
        got = dequantize(acc.astype(np.float64), FMT)
        want = block[:3, :valid]
        assert np.allclose(got[:3, :valid], want, atol=FMT.point_resolution), (
            f"identity moved points\ngot\n{got[:3, :valid]}\nwant\n{want}"
        )


@cocotb.test()
async def test_rtl_matches_fixed_point_reference_bit_for_bit(dut):
    """The RTL must equal the integer reference exactly. No tolerance here."""
    await start(dut)
    matrix = pose()
    points = cloud(64, EXTENT_M, seed=9)
    matrix_i, w = quantize_transform(matrix, FMT)

    worst_bits = 0
    for idx, (block, _) in enumerate(tiles(points, N)):
        block_i = quantize_points(block, FMT, w)
        acc = await run_tile(dut, matrix_i, block_i)
        want = matrix_i.astype(object) @ block_i.astype(object)
        assert np.array_equal(acc, want), (
            f"tile {idx} differs from the integer reference\n"
            f"rtl\n{acc}\nref\n{want}"
        )
        worst_bits = max(worst_bits, accumulator_headroom(acc))

    assert worst_bits <= ACC_W - 1, f"accumulator needed {worst_bits} bits"
    dut._log.info(
        f"bit-exact over {points.shape[1]} points; "
        f"widest accumulator {worst_bits} of {ACC_W - 1} bits"
    )


@cocotb.test()
async def test_quantization_error_is_inside_the_derived_bound(dut):
    """Quantization error, held to a bound derived from the format.

    An observed maximum is a measurement. A derived bound is a guarantee, and
    the difference is what makes the README's tolerance claim meaningful.
    """
    await start(dut)
    matrix = pose()
    points = cloud(256, EXTENT_M, seed=17)
    matrix_i, w = quantize_transform(matrix, FMT)
    bound = error_bound_m(matrix, EXTENT_M, FMT)

    worst = 0.0
    squares, count = 0.0, 0
    for block, valid in tiles(points, N):
        block_i = quantize_points(block, FMT, w)
        acc = await run_tile(dut, matrix_i, block_i)
        got = dequantize(acc.astype(np.float64), FMT)[:3, :valid]
        exact = transform_exact(matrix, block)[:3, :valid]
        err = np.abs(got - exact)
        worst = max(worst, float(err.max()))
        squares += float((err ** 2).sum())
        count += err.size

    rms = (squares / count) ** 0.5
    assert worst <= bound, f"max error {worst*1000:.3f} mm exceeds bound {bound*1000:.3f} mm"
    dut._log.info(
        f"{FMT} over {points.shape[1]} points, w={w:g}: "
        f"max {worst*1000:.3f} mm, rms {rms*1000:.3f} mm, "
        f"derived bound {bound*1000:.3f} mm"
    )


@cocotb.test()
async def test_signed_corner_at_sixteen_bits(dut):
    """Drive the full-scale signed corner, which real point data never reaches.

    A rotation entry quantizes to at most 2^14 and a coordinate similarly, so
    the benchmark's own data stays far from full scale and never exercises
    -32768 * -32768 = +2^30 — the product that needs the whole 2*DATA_W width.
    Mutation testing found that: truncating the product by one bit survived
    every other test in this file. So the corner is driven directly here rather
    than left to chance.
    """
    await start(dut)
    lo = -(2 ** (DATA_W - 1))          # -32768
    hi = 2 ** (DATA_W - 1) - 1

    # A single corner term, with the other three k-contributions zero.
    #
    # This is the case that actually discriminates, and it took working out.
    # Filling all four terms with -32768 does not: a 2*DATA_W-1 product wraps
    # 2^30 to -2^30, four of those sum to -2^32, and the accumulator wraps that
    # back to 0 — exactly what the correct version produces. The product wrap
    # and the accumulator wrap cancel. With one term the sum is 2^30, which fits
    # ACC_W, so a truncated product shows up as -2^30 instead.
    #
    # Only -32768 * -32768 reaches 2^30 at all; 32767 * 32767 is 1073676289 and
    # stays inside a 31-bit product. So this is the single case that exercises
    # the full 2*DATA_W width.
    matrix_i = np.zeros((N, N), dtype=np.int64)
    block_i = np.zeros((N, N), dtype=np.int64)
    matrix_i[:, 0] = lo
    block_i[0, :] = lo
    acc = await run_tile(dut, matrix_i, block_i)
    want_single = lo * lo
    assert int(acc[0][0]) == want_single, (
        f"single-term corner: rtl {int(acc[0][0])} != {want_single}. "
        "A product narrower than 2*DATA_W wraps 2^30 to -2^30 here."
    )
    assert np.all(np.asarray(acc, dtype=object) == want_single)
    dut._log.info(f"single-term corner: {lo} * {lo} = {int(acc[0][0])} = 2^30")

    for matrix_fill, block_fill in ((lo, lo), (lo, hi)):
        matrix_i = np.full((N, N), matrix_fill, dtype=np.int64)
        block_i = np.full((N, N), block_fill, dtype=np.int64)
        acc = await run_tile(dut, matrix_i, block_i)

        # The reference has to wrap. Four full-scale products sum to 2^32, which
        # does not fit a signed 32-bit accumulator: -32768 * -32768 is 2^30 and
        # there are four of them. ACC_W=32 is sufficient for the transform's
        # representable envelope (29 bits measured) and NOT for arbitrary 16-bit
        # operands, which is why that envelope is a constraint in ADR-0002
        # rather than a recommendation. The RTL wrapping here is correct.
        exact = matrix_i.astype(object) @ block_i.astype(object)
        want = np.array(
            [[wrap_signed(int(v), ACC_W) for v in row] for row in exact],
            dtype=object,
        )
        assert np.array_equal(acc, want), (
            f"full-scale {matrix_fill} x {block_fill} differs\n"
            f"rtl\n{acc}\nref\n{want}"
        )
        overflowed = not np.array_equal(
            np.asarray(exact, dtype=object), np.asarray(want, dtype=object)
        )
        dut._log.info(
            f"{matrix_fill} x {block_fill} x {N} = {int(exact[0][0])} -> "
            f"wrapped to {int(acc[0][0])}"
            if overflowed
            else f"{matrix_fill} x {block_fill} x {N} = {int(acc[0][0])}, no wrap"
        )


@cocotb.test()
async def test_throughput(dut):
    """Cycles per tile and per point, fill and drain included."""
    await start(dut)
    matrix = pose()
    n_points = 1024
    points = cloud(n_points, EXTENT_M, seed=23)
    matrix_i, w = quantize_transform(matrix, FMT)

    per_tile = tile_cycles(k=N, n=N)
    n_tiles = 0
    start_ns = cocotb.utils.get_sim_time(unit="ns")
    for block, _ in tiles(points, N):
        await run_tile(dut, matrix_i, quantize_points(block, FMT, w))
        n_tiles += 1
    elapsed_ns = cocotb.utils.get_sim_time(unit="ns") - start_ns

    total_cycles = n_tiles * per_tile
    dut._log.info(
        f"{n_points} points -> {n_tiles} tiles x {per_tile} cycles "
        f"= {total_cycles} cycles, {total_cycles / n_points:.2f} cycles/point "
        f"({N} points per tile, readout excluded)"
    )
    assert n_tiles == (n_points + N - 1) // N
