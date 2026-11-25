# systolic-array

A parameterized 4x4 systolic array in SystemVerilog, verified with cocotb,
synthesized with Yosys and placed and routed with nextpnr for an ECP5. v1 is
simulation only; nothing has run on an FPGA, and no hardware bring-up until
summer 2027.

The 4x4 shape is deliberate. Point cloud transforms are 4x4 homogeneous matrix
multiplies, so the array maps onto a real workload rather than an arbitrary
benchmark size. It extends my spine, physical signal to decision, down to
silicon.

## Layout

| Path | Contents |
|---|---|
| `rtl/` | `pe.sv` (MAC cell), `systolic_4x4.sv` (the array), `systolic_4x4_top.sv` (readout wrapper) |
| `tb/` | cocotb testbenches per block, `sim.mk`, Linux tool shims |
| `golden/` | NumPy reference models |
| `synth/` | `run.sh` (Yosys, both targets, both widths) and the committed cell-count reports |
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

1. **4x4 homogeneous transform** over a synthetic point cloud, four points per
   tile, fixed-point at `DATA_W=16`. The matrix is Q1.14 and the points Q7.8,
   with translation carried through a power-of-two scale on the homogeneous
   component ([ADR-0002](docs/decisions/ADR-0002-fixed-point.md)).
2. **Linear image filter**, one convolution step from an image-processing
   pipeline, expressed as a matmul via im2col.

### Results

| Benchmark | Cycles/tile | Throughput | Accuracy | MCU baseline |
|---|---|---|---|---|
| 4x4 transform, `DATA_W=16` | 10 (4 points) | 2.50 cycles/point | 4.54 mm max, 1.50 mm rms | 90.0 cycles/point |
| Linear filter (im2col) | not yet measured | not yet measured | not yet measured | not yet measured |

Tile cycles include fill and drain and exclude the 16-cycle readout. Accuracy is
quantization error against a float reference; the RTL itself is **bit-exact**
against the fixed-point reference, with no tolerance on that comparison. The
derived error bound for this format is 28.2 mm, so the measured figures sit
about 6x inside it. The bound is what the format guarantees
([ADR-0002](docs/decisions/ADR-0002-fixed-point.md)).

Every figure in the transform row is printed by `tb/transform` on each CI run:
the bit-exact check over 64 points, the error over 256 points, and the cycle
count over 1024 points.

The baseline is the same transform in C on a Cortex-M4 (STM32F411RE), which is
the class of processor this array would offload. Cycles per point is the
architectural comparison; the wall-clock conversion is under
[Wall-clock](#wall-clock) below, now that there is an Fmax.

| | Cycles/point | Cycles/MAC | vs array |
|---|---|---|---|
| Naive C, rolled `k` loop | 202.0 | 12.63 | 81x |
| Optimised C, unrolled | 90.0 | 5.63 | **36x** |
| Array, compute only | 2.50 | | |
| Array, steady state with readout | 4.0 | | 22x |

36x against optimised C is the figure I stand behind; against the naive C it
would be 81x, which flatters the array. Readout is 16 cycles against a 10-cycle
tile, so a pipelined array is readout-bound at 4.0 cycles/point rather than
2.50 — `read_start` snapshots the accumulators so the next tile overlaps
(ADR-0005). On that basis it is 22x.

Unlike the rows above, this one is **not** a CI figure: there is no board on the
runner. It is a board run recorded in
[`bench/mcu/reports/f411re_hsi16.txt`](bench/mcu/reports/f411re_hsi16.txt) with
the raw results block, the toolchain, and the flags, reproducible with
`cd bench/mcu && make flash read`.

The C is also a second implementation of the fixed-point format, held to
`golden/transform_ref.py` bit-for-bit over realistic tiles and the signed
corners (`.venv/bin/python bench/mcu/crosscheck.py`). The Python model was
trusted for being short; now something checks it.

### Synthesis

Measured on `systolic_4x4` with `ACC_W=32`:

| Target | `DATA_W=8` | `DATA_W=16` | Hard multipliers |
|---|---|---|---|
| iCE40 | 3,782 LUT4 | 13,028 LUT4 | none inferred |
| ECP5 | 514 LUT4 | 515 LUT4 | 16 × MULT18X18D |

iCE40 at 16 bits is 170% of an HX8K's 7,680 LUTs. ECP5 infers one `MULT18X18D`
per PE, and 16-bit costs the same as 8-bit because the DSP block covers both.
The target is ECP5 ([ADR-0006](docs/decisions/ADR-0006-synthesis-target.md)).

Each cell of that table is a Yosys `stat` report in
[`synth/reports/`](synth/reports/), one file per target and width, and
`synth/run.sh` regenerates all four.

### Place and route

`systolic_4x4_top` on an LFE5U-25F, CABGA381. The bare array cannot be routed —
644 port bits — so Fmax belongs to the wrapper with its shift-chain readout
(ADR-0005).

| Speed grade | `DATA_W=8` | `DATA_W=16` |
|---|---|---|
| 6 | 87.56 MHz | **83.68 MHz** |
| 7 | 96.00 MHz | 89.29 MHz |
| 8 | 112.99 MHz | 107.26 MHz |

Widening to 16 bits costs 4.4% of Fmax, because the DSP block absorbs it. At
`DATA_W=16`, speed grade 6:

| Resource | Used | Available | |
|---|---|---|---|
| MULT18X18D | 16 | 28 | 57.1% |
| TRELLIS_COMB | 1,622 | 24,288 | 6.7% |
| TRELLIS_FF | 1,413 | 24,288 | 5.8% |
| TRELLIS_IO | **167** | 197 | **84.8%** |

**The design is pin-bound, not logic-bound.** It uses 6.7% of the logic and 85%
of the I/O. Anything that widens the interface hits the package before it hits
the fabric.

The 11.951 ns critical path runs from a PE's accumulator through its
`MULT18X18D` and back: 50.0% logic, 45.6% routing, with the multiplier alone
3.927 ns and the carry chain only 0.923 ns over 13 steps. The product is
combinational into the accumulator, so registering it would pipeline the one
term that dominates — at the cost of a cycle of latency per PE
([ADR-0006](docs/decisions/ADR-0006-synthesis-target.md)).

`synth/pnr.sh` regenerates all six reports.

### Wall-clock

With an Fmax the cycle comparison can be converted. Array at `DATA_W=16`, speed
grade 6, against the Cortex-M4 at the F411RE's maximum 100 MHz:

| | Throughput | vs MCU |
|---|---|---|
| Cortex-M4, 90 cycles/point @ 100 MHz | 1.11 Mpoint/s | |
| Array, readout-bound, 4.0 cycles/point @ 83.68 MHz | 20.9 Mpoint/s | **18.8x** |
| Array, compute only, 2.50 cycles/point @ 83.68 MHz | 33.5 Mpoint/s | 30.1x |

Worth being clear about where that comes from: **the array is clocked slower
than the MCU**, 83.68 MHz against 100 MHz. The advantage is entirely work per
cycle, not clock speed.

Two caveats. The MCU figure scales a cycle count measured at 16 MHz with zero
flash wait states up to 100 MHz, where the F411 needs three and would depend on
the ART accelerator to sustain it — so 1.11 Mpoint/s is generous to the MCU.
And nothing here has run on an FPGA; these are nextpnr's post-route timing
estimates, not measurements on a board.

## Setup

Toolchain versions and the macOS and Linux traps are in
[`docs/BUILD_LOG.md`](docs/BUILD_LOG.md).

```bash
source env.sh          # venv ahead of OSS CAD Suite, platform-correct ICARUS_BIN_DIR
cd tb/array && make    # or tb/pe, tb/top, tb/transform
bash synth/run.sh      # from the repo root: Yosys cell counts into synth/reports/
```

## Branch flow

`feat/*` → PR into `dev` → promote `dev` to `test` → full suite on `test` →
promote `test` to `main`. I never test on `main`; it only receives code that has
already passed on `test`.

## License

MIT, see [LICENSE](LICENSE).
