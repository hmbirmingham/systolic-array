# Architecture decision records

One file per decision, numbered in the order I made them. Each records the
context, the options I considered, what I chose, and what that choice costs me.

I write an ADR when a choice closes off alternatives that a reader might
reasonably expect me to have taken — not for every design detail.

| ADR | Decision | Status |
|---|---|---|
| [ADR-0001](ADR-0001-dataflow.md) | Output-stationary vs weight-stationary dataflow | accepted, PR 2 |
| ADR-0002 | Fixed-point format for the transform benchmark | planned, PR 4 |
| [ADR-0003](ADR-0003-ci-toolchain.md) | CI runs the pinned OSS CAD Suite, not distro packages | accepted, PR 3 |

Numbering follows the order I made the decisions, so a gap means a planned ADR
hasn't been written yet rather than that one was removed.
