# ADR-0006 — ECP5 as the v1 synthesis target

**Status:** accepted
**Date:** 2026-11-13

## Context

ADR-0001 recorded a constraint and deferred it: `synth_ice40` on one PE gave
238 LUT4 with no `SB_MAC16` inferred, so the 8x8 multiply became LUT logic.
Sixteen of those extrapolated to ~3,800 LUTs, comfortable on an HX8K at
DATA_W=8 and probably not at 16 — and the 3D transform benchmark needs 16. That
ADR said the question belonged to whichever ADR settled the target.

With the array built, it can be measured instead of estimated. Measured before
the benchmarks were written, deliberately: a target that cannot hold the array
is a constraint on the benchmarks, not a detail discovered afterwards.

## Decision

**ECP5 is the v1 synthesis target. iCE40 numbers are reported alongside for
contrast.**

## Why

Measured with Yosys 0.70+277 on `systolic_4x4`, ACC_W=32:

| Target | DATA_W=8 | DATA_W=16 | Hard multipliers |
|---|---|---|---|
| iCE40 | 3,782 LUT4, 704 DFFESR, 656 CARRY | **13,028 LUT4** | none inferred |
| ECP5 | 514 LUT4, 256 CCU2C, 704 FF | **515 LUT4**, 256 CCU2C, 896 FF | **16 MULT18X18D** |

- **iCE40 at 16 bits is 13,028 LUT4 against an HX8K's 7,680.** 170% of the
  device. Not a tuning problem.
- **ECP5 infers one MULT18X18D per PE**, all sixteen, and LUT usage drops 25x.
  An LFE5U-25F has 28 of those blocks and ~24k LUTs.
- **On ECP5, 16-bit costs the same as 8-bit**: 515 LUT4 against 514. The DSP
  block covers both widths, so the fixed-point benchmark stops being a
  resource decision.
- The extrapolation in ADR-0001 was good: 238 x 16 = 3,808 predicted against
  3,782 measured at DATA_W=8, within 1%.

## The alternatives

**iCE40 HX8K at DATA_W=8 only.** Fits at 3,782 LUT4, and gives up the 16-bit
transform, which is the workload the array exists for.

**iCE40 UP5K.** Has hard multipliers, unlike the HX8K, but fewer than the
sixteen this array wants, so some PEs would fall back to LUT logic. Its exact
DSP count is from the datasheet rather than measured here, so this would need
checking before being relied on. Not pursued, because ECP5 already fits.

**Report iCE40's 16-bit number as the result and stop.** Honest, and a weaker
artifact than one that fits a real part.

## Consequences

- Synthesis scripts and the committed report target ECP5. iCE40 is kept as a
  second data point, because the contrast between 13,028 LUT4 and 16 DSP blocks
  is the more interesting result than either number alone.
- The resume line's "[part]" resolves to an ECP5 device.
- v1 is still simulation only. Nothing here implies bring-up, and no board has
  been bought.
- `nextpnr-ecp5` has never been run here, only `yosys`. Placement, routing and
  Fmax remain unmeasured, and Fmax is the number most likely to surprise:
  sixteen DSP blocks with a carry chain into a 32-bit accumulator is where the
  critical path will be.
- The 8-bit iCE40 configuration still fits an HX8K, so that option stays open if
  bring-up ever starts on cheaper hardware.
