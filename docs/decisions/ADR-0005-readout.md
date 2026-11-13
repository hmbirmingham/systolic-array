# ADR-0005 — Flat accumulators in the array, shift-chain readout in a wrapper

**Status:** accepted
**Date:** 2026-11-13

## Context

Output-stationary means the result lands in sixteen accumulators and stays
there. Something has to get it out.

Sixteen accumulators at ACC_W=32 is 512 bits. An iCE40 HX8K has about 206 I/O
and an LFE5U-25F a few hundred; a flat result bus cannot be placed on either.
But readout logic inside the array would sit in the middle of the module whose
arithmetic I am trying to verify.

## Decision

**`systolic_4x4` exposes all sixteen accumulators as one flat vector.
`systolic_4x4_top` wraps it with a shift-chain readout, one ACC_W word per
cycle, row-major, PE(i,j) at i*N+j.**

The array does arithmetic. The wrapper does interface.

## Why

- **The flat array is the right shape for verification.** `tb/array` reads all
  sixteen accumulators on every cycle and compares them against a cycle-accurate
  model. Through a 16-cycle readout that test would be far harder to write and
  would conflate two kinds of bug.
- **Cycle counts stay honest.** Readout costs 16 cycles. Measuring it separately
  from the K+6 tile means the throughput number says what it claims, instead of
  smearing interface cost into arithmetic cost.
- **It places.** With readout, the top is ~101 I/O at DATA_W=8 and ~165 at 16,
  both inside an HX8K's budget. Flat is 580 port bits and places nowhere.
- **The readout boundary is where a host link goes.** `read_start` /
  `result_valid` is already close to what an SPI or UART slave would drive, so
  the deferred link work has somewhere to attach without reopening the array.

## The alternatives

**Flat only.** Simplest, and makes the synthesis report meaningless, since
nextpnr cannot place 512 output pins. Not an option once synthesis is in scope.

**Row-parallel, 4 x ACC_W.** 128 bits out, 4 cycles. Fewer readout cycles, and
~229 I/O at DATA_W=16 — over an HX8K's budget, so it trades the thing the
wrapper exists to fix.

**Readout inside the array.** One module, no wrapper, and the verification
problem above.

## Consequences

- Readout is 16 cycles and must be reported separately from tile throughput.
- **`read_start` latches all sixteen accumulators on one edge**, so the array can
  stream the next tile while the previous result shifts out.
  `test_snapshot_is_not_disturbed_by_the_next_tile` checks that, because a
  readout that sampled the live accumulators one at a time would silently mix two
  tiles.
- Row-major order is a convention, so it is tested rather than assumed: a
  wrapper shifting the other way, or starting a word late, would still emit
  sixteen plausible numbers.
- `systolic_4x4` is not synthesizable onto a device on its own. That is
  intentional and is stated in the module header, so nobody tries.
