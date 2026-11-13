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
| `rtl/` | `pe.sv` (MAC cell), `systolic_4x4.sv` (the array), `systolic_4x4_top.sv` (readout wrapper) |
| `tb/` | cocotb testbenches per block, `sim.mk`, Linux tool shims |
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

Because the operands are skewed, each cell works on a different window of the
tile. Rather than add per-cell start logic, the feed is zero-padded outside each
window: an out-of-window product is zero, so every cell can run with `en` high
for the whole tile under a single broadcast `clear`
([ADR-0004](docs/decisions/ADR-0004-tile-control.md)). A tile is `K + 2*(N-1)`
cycles, fill and drain included.

`systolic_4x4` exposes all sixteen accumulators flat, which is right for
verification and unplaceable on a device at 512 bits. `systolic_4x4_top` adds a
shift-chain readout, one word per cycle
([ADR-0005](docs/decisions/ADR-0005-readout.md)).

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

Yosys only so far; `nextpnr` has not run, so Fmax is unmeasured. Measured on
`systolic_4x4` with `ACC_W=32`:

| Target | `DATA_W=8` | `DATA_W=16` | Hard multipliers |
|---|---|---|---|
| iCE40 | 3,782 LUT4 | 13,028 LUT4 | none inferred |
| ECP5 | 514 LUT4 | 515 LUT4 | 16 × MULT18X18D |

iCE40 at 16 bits is 170% of an HX8K's 7,680 LUTs. ECP5 infers one `MULT18X18D`
per PE, and 16-bit costs the same as 8-bit because the DSP block covers both.
The target is ECP5 ([ADR-0006](docs/decisions/ADR-0006-synthesis-target.md)).

## Setup

Toolchain versions and the macOS and Linux traps are in
[`docs/BUILD_LOG.md`](docs/BUILD_LOG.md).

```bash
source env.sh          # venv ahead of OSS CAD Suite, platform-correct ICARUS_BIN_DIR
cd tb/array && make    # or tb/pe, tb/top
```

## Branch flow

`feat/*` → PR into `dev` → promote `dev` to `test` → full suite on `test` →
promote `test` to `main`. I never test on `main`; it only receives code that has
already passed on `test`.

## License

MIT, see [LICENSE](LICENSE).
