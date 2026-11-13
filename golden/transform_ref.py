"""Fixed-point 4x4 homogeneous transform: the reference and the quantizer.

The array multiplies a 4x4 matrix by a 4x4 block of homogeneous points, so one
tile transforms four points. `K=4`, and a tile costs `K + 2*(N-1)` = 10 cycles.

Two formats, not one, and the reason is measured rather than assumed. A rotation
matrix's entries are all <= 1, so integer bits in the matrix are wasted; points
are metres and need them. Forcing one format on both costs 39 mm of error at an
8 m extent where two formats cost 0.66 mm.

Translation is the awkward part: it lives in the matrix's last column but is
metres, not <= 1. Rather than widen the whole matrix for it, the homogeneous
component carries a scale. With `P[3] = w` and `M[:,3] = t/w`, the product
`(t_i/w) * w` recovers `t_i` at the matrix's own resolution. `w` is a power of
two so the scaling is exact.

The RTL does not rescale. The accumulator holds Q(f_m + f_p) and the shift back
happens here, in software, which keeps the array a pure integer MAC and leaves
the rounding mode a documented software choice rather than a hardware one.
"""

from dataclasses import dataclass

import numpy as np

DATA_W = 16
ACC_W = 32
INT_MAX = 2 ** (DATA_W - 1) - 1
INT_MIN = -(2 ** (DATA_W - 1))
ACC_MAX = 2 ** (ACC_W - 1) - 1


@dataclass(frozen=True)
class Format:
    """Fractional bit counts for the matrix and the points.

    `f_matrix` is the fraction width of the transform's entries, `f_point` of
    the coordinates. The product carries `f_matrix + f_point` fractional bits.
    """

    f_matrix: int = 14
    f_point: int = 8

    @property
    def f_product(self) -> int:
        return self.f_matrix + self.f_point

    @property
    def point_extent(self) -> float:
        """Largest representable coordinate magnitude, in metres."""
        return (INT_MAX + 1) / (1 << self.f_point)

    @property
    def point_resolution(self) -> float:
        return 1.0 / (1 << self.f_point)

    def __str__(self) -> str:
        return (f"Q{DATA_W - 1 - self.f_matrix}.{self.f_matrix}"
                f"/Q{DATA_W - 1 - self.f_point}.{self.f_point}")


def quantize(values, frac_bits: int) -> np.ndarray:
    """Round-half-away-from-zero to a fixed-point integer, then saturate.

    Half-away rather than truncation: truncation biases every coordinate toward
    zero, and a transform applied repeatedly would accumulate that drift.
    Saturation is checked by the caller via `saturates`; silently clipping a
    point would make a benchmark meaningless.
    """
    scaled = np.asarray(values, dtype=np.float64) * (1 << frac_bits)
    rounded = np.trunc(scaled + np.copysign(0.5, scaled))
    return np.clip(rounded, INT_MIN, INT_MAX).astype(np.int64)


def saturates(values, frac_bits: int) -> bool:
    """True if any value is at or beyond the representable magnitude."""
    scaled = np.abs(np.asarray(values, dtype=np.float64)) * (1 << frac_bits)
    return bool(np.any(scaled >= INT_MAX))


def w_scale_for(matrix: np.ndarray, fmt: Format) -> float:
    """Smallest power of two making the translation representable in the matrix.

    The matrix format is fraction-heavy, so a translation of several metres does
    not fit directly. Dividing the last column by `w` does fit, and setting the
    points' homogeneous component to `w` recovers it exactly.
    """
    reach = (INT_MAX + 1) / (1 << fmt.f_matrix)
    worst = float(np.max(np.abs(matrix[:3, 3])))
    if worst < reach:
        return 1.0
    return float(2.0 ** np.ceil(np.log2(worst / reach)))


def quantize_transform(matrix: np.ndarray, fmt: Format):
    """Quantize a 4x4 transform. Returns (int matrix, w_scale)."""
    assert matrix.shape == (4, 4), matrix.shape
    w = w_scale_for(matrix, fmt)
    scaled = matrix.astype(np.float64).copy()
    scaled[:, 3] = scaled[:, 3] / w
    if saturates(scaled, fmt.f_matrix):
        raise ValueError(f"transform does not fit {fmt} even with w={w}")
    return quantize(scaled, fmt.f_matrix), w


def quantize_points(points: np.ndarray, fmt: Format, w_scale: float) -> np.ndarray:
    """Quantize homogeneous points (4, N). Row 3 becomes the w scale."""
    assert points.shape[0] == 4, points.shape
    coords = points[:3]
    if saturates(coords, fmt.f_point):
        extent = fmt.point_extent
        raise ValueError(
            f"a coordinate exceeds {fmt}'s +/-{extent:g} m envelope; "
            "widen f_point's integer bits or scale the cloud"
        )
    out = np.empty(points.shape, dtype=np.int64)
    out[:3] = quantize(coords, fmt.f_point)
    out[3] = quantize(np.full(points.shape[1], w_scale), fmt.f_point)
    return out


def dequantize(acc: np.ndarray, fmt: Format) -> np.ndarray:
    """Accumulator integers back to metres."""
    return np.asarray(acc, dtype=np.float64) / (1 << fmt.f_product)


def transform_exact(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Float reference. What the fixed-point pipeline is approximating."""
    return matrix.astype(np.float64) @ points.astype(np.float64)


def transform_fixed(matrix: np.ndarray, points: np.ndarray, fmt: Format) -> np.ndarray:
    """Integer-exact fixed-point transform, in accumulator units.

    Uses Python ints so the model never overflows where the RTL would. Pair it
    with `accumulator_headroom` to assert the RTL's 32 bits were enough.
    """
    mi, w = quantize_transform(matrix, fmt)
    pi = quantize_points(points, fmt, w)
    return mi.astype(object) @ pi.astype(object)


def accumulator_headroom(acc) -> int:
    """Bits actually used by the widest accumulator value."""
    flat = np.asarray(acc).reshape(-1)
    return max(int(abs(int(v))).bit_length() for v in flat)


def error_bound_m(matrix: np.ndarray, extent_m: float, fmt: Format) -> float:
    """Derived worst-case error in metres, not an observed one.

    Each quantization is at most half an LSB. For one output component,
    P'_i = sum_k M[i][k] * P[k], so the error is bounded by

        sum_k ( |dM| * |P_k| + |M[i][k]| * |dP| )

    with |dM| = 2^-(f_matrix+1) and |dP| = 2^-(f_point+1). The w-scaled
    translation term contributes |dM| * w rather than |dM| * extent.
    """
    d_m = 2.0 ** -(fmt.f_matrix + 1)
    d_p = 2.0 ** -(fmt.f_point + 1)
    w = w_scale_for(matrix, fmt)
    rows = []
    for i in range(3):
        total = 0.0
        for k in range(3):
            total += d_m * extent_m + abs(matrix[i, k]) * d_p
        total += d_m * w + abs(matrix[i, 3] / w) * d_p * w
        rows.append(total)
    return max(rows)


def tiles(points: np.ndarray, n: int = 4):
    """Split (4, N) points into (4, n) blocks, zero-padding the last one.

    Yields (block, valid_count). A short final block is padded with zeros rather
    than dropped, so a cloud whose size is not a multiple of four still produces
    a full tile and the padding is accounted for in the cycle count.
    """
    total = points.shape[1]
    for start in range(0, total, n):
        stop = min(start + n, total)
        block = np.zeros((4, n), dtype=points.dtype)
        block[:, : stop - start] = points[:, start:stop]
        yield block, stop - start


def tile_cycles(k: int = 4, n: int = 4) -> int:
    """Cycles per tile, fill and drain included. Matches ADR-0004."""
    return k + 2 * (n - 1)
