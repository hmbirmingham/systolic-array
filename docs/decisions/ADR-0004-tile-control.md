# ADR-0004 — Zero-padded feed and a single broadcast clear

**Status:** accepted
**Date:** 2026-11-13

## Context

The array's operands are skewed by construction (ADR-0001). With
PE(i,j).a_in(t) = a_in[i](t-j) and PE(i,j).b_in(t) = b_in[j](t-i), a feeder that
delays row i by i cycles and column j by j gives PE(i,j) the pair
(A[i][k], B[k][j]) with k = t-i-j.

That alignment is the point, and it means each cell works on a different window:
PE(i,j) has real operands only for t = i+j .. K-1+i+j. The offsets run 0 to 6
on a 4x4. A broadcast `clear` at t=0 would zero PE(3,3) six cycles before its
first product arrives, and a broadcast `clear` timed for PE(3,3) would wipe six
cycles of PE(0,0)'s work.

So the array needs per-cell start behaviour, or something that makes per-cell
start unnecessary.

## Decision

**Zero-pad the feed outside each cell's window, pulse `clear` once at t=0, and
hold `en` high for the whole tile.**

## Why

- **Out-of-window products are zero, so running a cell early or late is free.**
  A PE whose operands are zero computes a zero product and its accumulator is
  unchanged. There is nothing to protect it from.
- **It needs no RTL beyond the PE as already built.** No control path, no
  counters, no per-cell comparators. The array is sixteen cells and wires.
- **`clear` outranking `en` makes t=0 land correctly.** PE(0,0) has its real
  first product at t=0, and `acc <= en ? prod : 0` with both asserted gives
  `acc = prod` rather than zero. That priority was chosen in PR 2 for tile
  boundaries and happens to be exactly what this needs.
- **The complexity moves to Python.** The feeder is `feed_schedule` in
  `golden/array_model.py`, next to the model it is checked against, where it is
  cheap to test exhaustively.

## The alternatives

**Propagate a "first element" tag with the operands.** A control bit travelling
the same path as the data, so each cell clears when its first real operand
arrives. Self-contained — the array would not depend on a feeder contract — at
the cost of an extra register and wire per cell. The better choice if the array
ever has to accept an unpadded stream.

**Global counter plus a per-cell comparator on i+j.** Sixteen comparators and a
counter to get what padding gives for nothing.

## Consequences

- **The feed contract is load-bearing.** Array correctness now depends on the
  feeder zeroing out-of-window operands.
  `test_feed_schedule_pads_outside_every_window` checks that property directly
  on the schedule, rather than leaving it implied by the other tests passing.
- **A tile is K + 2*(N-1) cycles**, so K+6 on a 4x4. Fill and drain are in that
  number and must stay in it: a throughput figure that counts only K would be
  wrong by six cycles per tile, which matters at small K.
- **`clear` is a single-cycle pulse, not a mode.** It is deliberately not gated
  by `en`, so holding it through a stall zeroes the array. Found by writing a
  stall test that left `clear` asserted and watching an accumulator go from
  -5590 to 0 — the RTL was right and the testbench was wrong. The wrapper
  documents the same contract.
- An unpadded or misaligned feed produces plausible wrong answers rather than an
  error. The cycle-accurate model is what catches that, by comparing all sixteen
  accumulators every cycle instead of only at the end of a tile.
