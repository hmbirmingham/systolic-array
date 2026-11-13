# systolic-array

A parameterized 4x4 systolic array in SystemVerilog, verified with cocotb and
synthesized with Yosys and nextpnr. v1 is simulation only; no hardware bring-up
until summer 2027.

The 4x4 shape is deliberate. Point cloud transforms are 4x4 homogeneous matrix
multiplies, so the array maps onto a real workload rather than an arbitrary
benchmark size. It extends my spine — physical signal to decision — down to
silicon.

## Layout

| Path | Contents |
|---|---|
| `rtl/` | `pe.sv` (multiply-accumulate cell), `systolic_4x4.sv` |
| `tb/` | cocotb testbenches, `sim.mk`, Linux tool shims |
| `golden/` | NumPy reference models |
| `synth/` | Yosys + nextpnr scripts and committed reports |
| `docs/` | `BUILD_LOG.md`, architecture decision records |

## Design

The processing element does one multiply-accumulate, parameterized on `DATA_W`
(default 8) and `ACC_W` (default 32). The product is carried at full `2*DATA_W`
width: `-128 * -128 = +16384` overflows a `2*DATA_W-1` result.

Dataflow is output-stationary. Each PE owns one element of the result for the
whole tile, `a` flows west to east, `b` flows north to south, and each PE
forwards what it received one cycle later. That one-cycle hop in both directions
creates the diagonal wavefront, so skew is a property of the dataflow rather
than something the testbench arranges.
[ADR-0001](docs/decisions/ADR-0001-dataflow.md) covers the weight-stationary
alternative.

## Verification

Every RTL output is checked against a NumPy model in `golden/`, never against
expected values typed into a testbench. The models wrap at `ACC_W` to match the
hardware, since Python's unbounded integers would diverge on a long
accumulation.

New testbenches are mutation-tested: the RTL is broken on purpose and the suite
has to catch it. Six passing tests say nothing about whether they can fail.

CI runs the suite on the same pinned toolchain as my local setup, on every PR
into `dev`, `test` and `main`
([ADR-0003](docs/decisions/ADR-0003-ci-toolchain.md)).

## Benchmarks

Both run against the same RTL:

1. **4x4 homogeneous transform** over a synthetic point cloud, points batched as
   4xN tiles, fixed-point at `DATA_W=16`.
2. **Linear image filter**, one convolution step from an image-processing
   pipeline, expressed as a matmul via im2col.

### Results

Not yet measured.

| Benchmark | Cycles | Throughput | Pi 5 baseline | Speedup |
|---|---|---|---|---|
| 4x4 transform | — | — | — | — |
| Linear filter (im2col) | — | — | — | — |

### Synthesis

Not yet run. A smoke check on the PE alone gives 238 LUT4, 48 DFFESR and
41 SB_CARRY on iCE40 with no `SB_MAC16` inferred, so the 8x8 multiply maps to
LUT logic. Sixteen of those is roughly 3,800 LUTs, comfortable on an HX8K at 8
bits and probably not at `DATA_W=16`.

## Setup

Toolchain versions and the macOS and Linux traps are in
[`docs/BUILD_LOG.md`](docs/BUILD_LOG.md).

```bash
source env.sh          # venv ahead of OSS CAD Suite, platform-correct ICARUS_BIN_DIR
cd tb/pe && make
```

## Branch flow

`feat/*` → PR into `dev` → promote `dev` to `test` → full suite on `test` →
promote `test` to `main`. I never test on `main`; it only receives code that has
already passed on `test`.

## License

MIT, see [LICENSE](LICENSE).
