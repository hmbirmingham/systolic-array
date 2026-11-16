# Architecture decision records

One file per decision, numbered in the order I made them. Each records the
context, what I chose, the alternative, and what the choice costs.

I write one when a choice closes off an alternative a reader might reasonably
expect me to have taken.

| ADR | Decision | Status |
|---|---|---|
| [ADR-0001](ADR-0001-dataflow.md) | Output-stationary dataflow for v1 | accepted, PR 2 |
| [ADR-0002](ADR-0002-fixed-point.md) | Two fixed-point formats, scaled homogeneous component | accepted, PR 7 |
| [ADR-0003](ADR-0003-ci-toolchain.md) | CI uses the pinned OSS CAD Suite | accepted, PR 3 |
| [ADR-0004](ADR-0004-tile-control.md) | Zero-padded feed and a single broadcast clear | accepted, PR 6 |
| [ADR-0005](ADR-0005-readout.md) | Flat accumulators, shift-chain readout in a wrapper | accepted, PR 6 |
| [ADR-0006](ADR-0006-synthesis-target.md) | ECP5 as the v1 synthesis target | accepted, PR 6 |

A gap in the numbering means a planned ADR isn't written yet, not that one was
removed.
