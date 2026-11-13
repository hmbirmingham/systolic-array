# ADR-0002 — Two fixed-point formats, and a scaled homogeneous component

**Status:** accepted
**Date:** 2026-11-13

## Context

The transform benchmark runs at `DATA_W=16`. A 4x4 homogeneous transform
multiplies three quantities with different ranges:

- **Rotation entries**, all `<= 1`.
- **Translation**, metres, in the matrix's last column.
- **Coordinates**, metres, bounded by the working volume.

One 16-bit format cannot serve all three well. A format wide enough for metres
wastes its fraction on rotation entries that never exceed 1; a fraction-heavy
format cannot hold translation at all.

## Decision

**Matrix in Q1.14, points in Q7.8, translation carried through a power-of-two
scale on the homogeneous component.** Rounding is half-away-from-zero.
Rescaling happens in software, not in the RTL.

With `P[3] = w` and `M[:,3] = t/w`, the product `(t_i/w) * w` recovers `t_i` at
the matrix's own resolution. `w` is a power of two, so that scaling is exact.

## Why

Measured over 4,096 points with a rotation of (0.3, -0.7, 1.1) rad and a
translation of (10, -5, 2) m:

| Matrix / point format | extent +/-8 m | extent +/-64 m |
|---|---|---|
| Q7.8 / Q7.8 | 39.0 mm | 310.7 mm |
| Q1.14 / Q7.8 | 3.1 mm | **4.9 mm** |
| Q1.14 / Q4.11 | **0.66 mm** | saturates |
| Q3.12 / Q3.12 | saturates | saturates |

- **The matrix always wants Q1.14.** Rotation entries are `<= 1`, so every
  integer bit is waste. Forcing a shared format costs 39 mm where two formats
  cost 0.66 mm at the same extent — a factor of 59.
- **The point format tracks the working volume**, and that is the only free
  variable left. Q7.8 reaches +/-128 m at 3.9 mm resolution; Q4.11 reaches
  +/-16 m at 0.49 mm.
- **Half-away-from-zero, not truncation.** Truncation biases every coordinate
  toward zero, and a transform applied repeatedly would accumulate that drift.
- **Software rescales.** The accumulator holds Q(f_matrix + f_point) and the
  shift back to metres happens in `transform_ref.dequantize`. That keeps the
  array a pure integer MAC and leaves the rounding mode a documented software
  choice rather than something frozen into RTL.

## The alternatives

**One format for everything.** Simplest to describe and 59x worse at 8 m. The
error is not in the arithmetic but in spending bits on range the rotation matrix
never uses.

**Q1.14 / Q4.11.** Better at 0.66 mm, and limited to a +/-16 m envelope. The
right choice if the working volume is a room rather than a street. It also
leaves only one bit of accumulator headroom against Q7.8's two, because
`f_product` rises to 25.

**Widen the matrix for translation instead of scaling `w`.** Removes the `w`
bookkeeping at the cost of the fraction bits that make the matrix accurate,
which is the whole problem.

## Consequences

- **`ACC_W = 32` is sufficient for this envelope and not in general.** Four
  full-scale 16-bit products sum to `2^32`: `-32768 * -32768` is `2^30` and
  there are four terms. That does not fit a signed 32-bit accumulator. Measured
  headroom inside the envelope is 29 bits of 31 at Q7.8 and 30 of 31 at Q4.11.
  So the envelope below is a constraint, not a recommendation:

      K * max|m_q| * max|p_q| < 2^31

  With `K=4`, a rotation bounded by 1 (`2^14` in Q1.14) and coordinates bounded
  by 64 m (`2^14` in Q7.8), that is `2^30` — one bit of margin.

- **The error bound is derived, not observed.** For one output component,
  `P'_i = sum_k M[i][k] * P[k]`, so the error is at most
  `sum_k ( |dM| * |P_k| + |M[i][k]| * |dP| )` with `|dM| = 2^-15` and
  `|dP| = 2^-9`. That gives 28.2 mm at +/-64 m against 4.9 mm measured, so the
  bound is conservative by about 6x. The README quotes the bound, because a
  measurement over one cloud is not a guarantee.

- **Saturation raises rather than clips.** `quantize_points` rejects a cloud
  that exceeds the envelope instead of silently clamping it, which would make a
  benchmark meaningless.

- **The benchmark's own data never reaches the signed corner.** Rotation entries
  quantize to at most `2^14` and coordinates similarly, so `-32768 * -32768`
  never occurs naturally. Mutation testing found this: truncating the product by
  one bit survived every realistic test. `tb/transform` now drives that corner
  directly, with a single contributing term — four corner terms do not
  discriminate, because the product wrap and the accumulator wrap cancel exactly.

- **The working volume is still unconfirmed.** Q7.8 is the conservative default
  at +/-128 m representable. If the real volume is a room, Q4.11 is a 7x
  accuracy improvement for a one-line change and this ADR should be revised.
