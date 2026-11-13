# ADR-0001 — Output-stationary dataflow for v1

**Status:** accepted
**Date:** 2026-11-07

## Context

A systolic array has to choose which operand stays put. The choice decides what
each PE stores, how operands move, and what the host has to do between tiles.
v1 is simulation-only, and the first real workload is a 4x4 homogeneous
transform over a point cloud batched as 4xN tiles.

## Decision

**Output-stationary.** Each PE owns one element of the result for the whole
tile. `a` flows west to east, `b` flows north to south, and every PE forwards
what it received one cycle later.

## Why

- **The accumulator never moves.** A partial sum stays in the PE that owns it,
  so there is no partial-sum bus and no adder tree to drain the array. For a 4x4
  array the result is read out of 16 registers, which is the simplest possible
  readout.
- **It matches the workload.** A 4xN point-cloud tile reuses the same 4x4
  transform across every tile. Output-stationary makes the result the thing that
  stays, and the transform is re-streamed per tile — which is the cheap
  direction when N is large and the matrix is fixed.
- **One hop, one cycle, in both directions.** That is what creates the diagonal
  wavefront: PE(i,j) sees `A[i][k]` and `B[k][j]` in the same cycle because each
  has travelled the same number of register stages. The skew is a property of the
  dataflow rather than something the testbench has to arrange.

## The alternative

**Weight-stationary** holds one operand of the matrix in each PE and streams
activations through, accumulating along a column. It is the better choice when
one matrix is reused across many invocations and the other is a stream — which
is the inference case, and why it is what most NPUs do.

It is the wrong choice *here* for two reasons. It needs a partial-sum path down
each column plus somewhere to land the result, which is more plumbing than v1
should carry before the PE is verified. And loading weights is a separate phase
with its own control, so the first thing I would be debugging is sequencing
rather than arithmetic.

## Consequences

- The PE needs `clear` as well as `en`, so a tile boundary can zero the
  accumulator without spending a MAC step. `clear` outranks `en` for the case
  where both arrive together and the incoming product belongs to the new tile.
- The accumulator is a fixed-width register and therefore wraps. The golden
  model wraps identically, on purpose: a model that used Python's unbounded ints
  would diverge from correct RTL on a long accumulation.
- **Revisit when hardware bring-up starts.** Measured on this PE at `DATA_W=8`,
  `synth_ice40` maps the multiply to LUT logic rather than inferring an
  `SB_MAC16`: 238 LUT4, 48 DFFESR, 41 CARRY per PE. Sixteen of those is roughly
  3,800 LUTs, which fits an HX8K's 7,680 with room to spare at 8 bits and
  probably does not at `DATA_W=16` unless the multiplier maps to a hard block.
  The 3D-transform benchmark wants 16 bits, so that is a real constraint on the
  array rather than a detail of the cell — and it belongs to whichever ADR
  settles the synthesis target.
