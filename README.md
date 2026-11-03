# systolic-array

A parameterized 4x4 systolic array in SystemVerilog, verified with cocotb and
synthesized against a real FPGA target. v1 is simulation only — no hardware
bring-up until summer 2027.

I chose the 4x4 shape deliberately. Point cloud transforms are 4x4 homogeneous
matrix multiplies, so the array maps directly onto a real workload rather than
an arbitrary benchmark size. It's built and verified as a standalone component.

## Why this exists

- It extends my spine — physical signal to decision — down to silicon.
- It gives me an RTL and verification artifact next to my firmware work.
- The benchmarks run on real workloads from my own systems, not toy matrices.

## What's here

| Path | Contents |
|---|---|
| `rtl/` | `pe.sv` (multiply-accumulate cell), `systolic_4x4.sv` (the array) |
| `tb/` | cocotb testbenches and the simulation Makefile |
| `golden/` | NumPy reference models every RTL output is checked against |
| `synth/` | Yosys + nextpnr scripts and committed reports |
| `docs/` | `BUILD_LOG.md` and architecture decision records |

## Design

- **Processing element** — multiply-accumulate, parameterized `DATA_W`
  (default 8) and `ACC_W` (default 32).
- **Dataflow** — output-stationary. It's the simplest correct dataflow for v1;
  I document the tradeoff against weight-stationary in
  [ADR-0001](docs/decisions/ADR-0001-dataflow.md).

## Benchmarks

Both run against the same RTL:

1. **3D transform** — a 4x4 homogeneous transform over a synthetic point cloud,
   points batched as 4xN tiles, fixed-point with `DATA_W=16`.
2. **Linear image filter** — one convolution step from an image-processing
   pipeline, expressed as a matmul via im2col.

## Results

<!-- Filled in by PR 8. -->
_Not yet measured._

| Benchmark | Cycles | Throughput | Pi 5 baseline | Speedup |
|---|---|---|---|---|
| 4x4 transform | TBD | TBD | TBD | TBD |
| Linear filter (im2col) | TBD | TBD | TBD | TBD |

## Synthesis

<!-- Filled in by PR 7. -->
_Not yet run._

## Getting set up

The toolchain is all free and all local. See
[`docs/BUILD_LOG.md`](docs/BUILD_LOG.md) for the exact versions I'm building
against and the macOS-specific traps I hit getting cocotb to talk to Icarus.

```bash
source env.sh          # puts the venv ahead of OSS CAD Suite on PATH
cd tb && make          # run the cocotb suite
```

## Branch flow

Every feature goes `feat/*` -> PR into `dev` -> promote `dev` to `test` -> run
the full suite on `test` -> promote `test` to `main`. I never test on `main`;
it only ever receives code that has already passed on `test`.

## License

MIT — see [LICENSE](LICENSE).
