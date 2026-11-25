# Build log

One entry per PR: what I built, what broke, what I had to decide.

---

## 2026-10-29 — Day 1: toolchain

No RTL. Installed and verified the toolchain first.

### Versions

| Tool | Version | Source |
|---|---|---|
| Yosys | 0.70+277 (`77dddbd66`) | OSS CAD Suite `20261029` |
| nextpnr-ice40 / ecp5 | 0.11.1-83-g9691ce8c | same |
| Verilator | 5.053 devel | same |
| Icarus Verilog | 14.0 devel (s20260301-776-g699144553) | same |
| GTKWave | 4.0.0-prealpha | same |
| Python | 3.13.18 | Homebrew `python@3.13` |
| cocotb | 2.1.0 | venv wheel, `cp313` |
| NumPy | 2.5.4 | venv |

Tarball, pinned: `oss-cad-suite-darwin-arm64-20261029.tgz`, 525,007,575 bytes,
sha256 `5a431a6578c93bcf7cd05451cd556f549232f335051adc7cc85b802a5c51fb94`.
Installed to `~/oss-cad-suite`, outside the repo — it's a shared toolchain, not
a project dependency. Host: MacBook Air M4, macOS 26.6.2, arm64.

### Three things that had to be sorted before any RTL

**Anaconda's Python can't be used.** My default `python3` is Anaconda's 3.14.6.
cocotb embeds libpython into the simulator process and Anaconda's build fails
that with `Failed to import encodings module`. `PYTHONHOME` doesn't fix it. The
venv is built from Homebrew's `python@3.13`, a framework build, which embeds
cleanly. I'd checked that cocotb ships a `cp314` wheel and wrongly concluded 3.14
was fine; *which* Python matters for embedding, not which version.

**`~/oss-cad-suite/bin/*` are wrapper scripts, not binaries.** `bin/vvp` is bash
and exports `PYTHONEXECUTABLE` and `PYTHONHOME` at the suite, forcing cocotb
onto the suite's bundled Python 3.11. That interpreter has no numpy, and every
assertion I write compares against a NumPy model, so the oracle would have been
unreachable. `ICARUS_BIN_DIR` points at `libexec/` instead. (Revised on day 5 —
this is right on macOS only.)

**cocotb 2.x is not 1.x.** `COCOTB_TEST_MODULES`, not `MODULE`.
`Timer(1, unit="ns")`, not `units`. Most tutorials online are 1.x and won't run.

Encoded in [`../env.sh`](../env.sh) and [`../tb/sim.mk`](../tb/sim.mk).

### Smoke test

Version output isn't evidence the chain works, so I proved it on a throwaway
8-bit adder: SystemVerilog → Icarus → cocotb → NumPy comparison over 20 random
vectors. That's the pattern every benchmark here depends on.

### Open

Surfer is not bundled in OSS CAD Suite; only GTKWave ships. Using GTKWave for
now. cocotb's `libpython` resolves into the Homebrew Cellar path, so a
`brew upgrade python@3.13` breaks `.venv` until it's rebuilt.

---

## 2026-10-31 — Day 2: PR 1, repo scaffold

Layout, README stub, MIT license, `.gitignore`, this log.

### The branch sequence in my scope doc doesn't work

```bash
git init -b main
git checkout -b dev
git checkout -b test
git checkout dev      # error: pathspec 'dev' did not match any file(s)
```

Before the first commit exists, `git checkout -b` doesn't create a branch, it
repoints unborn `HEAD`, so each call overwrites the last. Those four lines leave
one unborn branch called `test`, no `main`, and no commits. Confirmed in a
throwaway repo.

`main` is now an empty root commit, `dev` branched from it, `test` from `dev`.
`main` only ever receives code already promoted through `test`, and the scaffold
arrived on `dev` via PR 1 like any other feature.

### Layout

```
rtl/      pe.sv, systolic_4x4.sv
tb/       sim.mk, per-block cocotb tests
golden/   NumPy reference models
synth/    yosys/nextpnr scripts, reports/
docs/     this log, decisions/
```

This repo is public, so this log is public. `CLAUDE.md` and a private log for
context belonging to my other projects are gitignored. Everything needed to
build and verify the array is in the repo.

---

## 2026-11-07 — PR 2: the PE, and a latent bug in sim.mk

`rtl/pe.sv` plus its cocotb suite and NumPy golden model. Every assertion
compares the RTL against `golden/pe_model.py` rather than a number typed into
the testbench: a MAC has an exact definition, so there was no reason to accept a
weaker oracle than the real one.

**`tb/sim.mk` had a bug that would have bitten the first testbench either way.**

```make
RTL_DIR ?= $(realpath $(dir $(lastword $(MAKEFILE_LIST)))/../rtl)
```

`?=` defines a *recursive* variable, so `MAKEFILE_LIST` is read when `RTL_DIR`
is first used — not where it is written. By then cocotb's `Makefile.sim` and its
own includes have been pulled in, `lastword` points at a makefile inside
`site-packages`, there is no `../rtl` beside it, `realpath` returns empty, and
the build dies with ``No rule to make target `/pe.sv'``. The message names a
path that appears nowhere in the repo, which is what makes it slow to find.

Fixed by pinning the directory at parse time with `:=` and leaving `RTL_DIR`
itself overridable:

```make
SIM_MK_DIR := $(dir $(lastword $(MAKEFILE_LIST)))
RTL_DIR ?= $(realpath $(SIM_MK_DIR)/../rtl)
```

**The suite was mutation-tested rather than trusted for being green.** Four
deliberate breaks in `pe.sv`, all caught: truncating the product to
`2*DATA_W-1` bits (1 failure, the `-128 * -128` corner), letting `en` outrank
`clear` (1), forwarding operands while stalled (2), and overwriting the
accumulator instead of adding to it (4). Six tests passing says nothing about
whether they can fail; killing four mutants says they can.

**Synthesis, as a smoke check only** — the real synthesis work is still PR 7.
`synth_ice40` on the PE alone gives 238 LUT4, 48 DFFESR, 41 SB_CARRY, with no
`SB_MAC16` inferred: the 8x8 multiply became LUT logic. Sixteen PEs is ~3,800
LUTs, which is comfortable on an HX8K at 8 bits and likely does not fit at
`DATA_W=16`. The 3D-transform benchmark wants 16, so this is a constraint on the
array, noted in ADR-0001.

---

## 2026-11-11 — PR 3: continuous integration

Every PR into `dev`, `test` and `main` now runs the cocotb suite.

CI installs the same dated OSS CAD Suite release I run locally, cached between
runs, and sources the same `env.sh`. Ubuntu's packages would have been three
lines of YAML, but they lag: noble ships nextpnr 0.6 against my 0.11.1, with a
correspondingly old iverilog. A check running a different simulator than my
results tables answers a different question than a reader would assume.
[ADR-0003](decisions/ADR-0003-ci-toolchain.md) has the comparison, including why
I rejected a self-hosted runner: on a public repo it lets a fork's pull request
execute code on my laptop.

Synthesis is not a CI product. Resource and Fmax numbers are generated locally
and committed to `synth/reports/`, so the runner needs Icarus and nothing else.
That's what makes the 712 MB tarball affordable.

**The gate parses `results.xml` rather than checking `make`'s exit status.** A
suite that silently ran zero tests would pass an exit-status check. It fails on
any failure or on an empty run. Tested against three inputs before I trusted it:
a passing run, a run with an injected failure, and a file with no tests. My
first test appeared to fail on a passing suite — the `results.xml` on disk was
stale, left from a mutation run that had deliberately failed.

One thing I left unverified on purpose: whether the Linux `bin/` wrappers pin
`PYTHONHOME` like the macOS ones. The workflow prints the resolved interpreter
and `ICARUS_BIN_DIR` on every run so the first run would answer it.

---

## 2026-11-13 — PR 3 fix: the Linux loader

The first CI run failed. The question I'd left open came back clean:

```
PYTHONHOME=(unset)
cocotb-config -> .../systolic-array/.venv/bin/cocotb-config
numpy 2.5.4
```

It failed on something else:

```
libexec/vvp: error while loading shared libraries:
libvvp.so.1: cannot open shared object file
```

I'd taken a macOS fact and used it cross-platform. On macOS `libexec/vvp` names
its library as `@executable_path/../lib/libvvp.1.14.0.dylib`, resolving relative
to itself, which is why `ICARUS_BIN_DIR=libexec` works there. The Linux build
ships its own glibc and runs `libexec` binaries through its own dynamic loader:

```bash
exec .../lib/ld-linux-x86-64.so.2 --inhibit-cache --inhibit-rpath "" \
     --library-path .../lib .../libexec/vvp "$@"
```

Read off the Linux tarball by streaming the archive and stopping at the first
match, rather than downloading all 712 MB to inspect one 485-byte file.

So the wrappers do two jobs: the loader invocation, which I need, and the
`PYTHONHOME` export, which hides numpy. Bypassing `bin/` on day 1 escaped the
second and silently dropped the first, which costs nothing on macOS.

`LD_LIBRARY_PATH` was my first instinct and would have been wrong: it pairs the
system loader with the suite's bundled libc, which is what
`--inhibit-cache --inhibit-rpath` exists to prevent, and it might not have
failed loudly.

[`../tb/toolshim-linux/`](../tb/toolshim-linux/) is the suite's own invocation
with the `PYTHONHOME` export removed. `env.sh` selects per platform. Linux
`bin/iverilog` sets no `PYTHONHOME` at all, so only `vvp` needed the treatment;
CI compiled through raw `libexec/iverilog` by luck and the shim covers both.

Cold cache is ~20s on a runner, not the 2-4 minutes I estimated in ADR-0003.

---

## 2026-11-13 — PR 6: the 4x4 array

`rtl/systolic_4x4.sv`, a synthesizable wrapper, and the synthesis number that
decides the target part.

### Tile control

The array's cells work on different windows: PE(i,j) has real operands only for
t = i+j .. K-1+i+j, offsets running 0 to 6. A broadcast `clear` at t=0 would
zero PE(3,3) six cycles before its first product arrives.

Solved by zero-padding the feed instead of adding control: out-of-window
operands are zero, the product is zero, the accumulator is unchanged, so every
cell can run with `en` high for the whole tile. The array is sixteen cells and
wires, no counters, no per-cell start. [ADR-0004](decisions/ADR-0004-tile-control.md).

`clear` outranking `en` — chosen in PR 2 for tile boundaries — is what makes
t=0 correct: PE(0,0) already has its real first product then, and
`acc <= en ? prod : 0` with both asserted gives the product rather than zero.

A tile is K + 2*(N-1) cycles, so K+6. Fill and drain are in that number and
have to stay in it.

### The stall test was wrong, not the RTL

Wrote a stall test that held `clear` through the stall and watched an
accumulator go from -5590 to 0. `clear` is deliberately not gated by `en`, so
holding it zeroes the array — which makes `clear` a single-cycle pulse rather
than a mode. That is now a documented contract in ADR-0004 and in the wrapper
header, and the stall test checks it is survivable.

### Readout

Sixteen accumulators at ACC_W=32 is 512 bits, which places on nothing. But
readout logic inside the array sits in the middle of the module whose arithmetic
is being verified.

Split: `systolic_4x4` exposes the flat vector and `systolic_4x4_top` wraps it
with a shift-chain readout, one word per cycle, row-major.
[ADR-0005](decisions/ADR-0005-readout.md). The top is ~101 I/O at DATA_W=8 and
~165 at 16, inside an HX8K's ~206. `read_start` snapshots all sixteen on one
edge, so the array can stream the next tile while the previous result shifts
out.

### Synthesis, measured before the benchmarks

ADR-0001 left the 16-bit question to whichever ADR settled the target. Measured
it now rather than in PR 7, because a target that cannot hold the array is a
constraint on the benchmarks:

| Target | DATA_W=8 | DATA_W=16 | Hard multipliers |
|---|---|---|---|
| iCE40 | 3,782 LUT4 | 13,028 LUT4 | none inferred |
| ECP5 | 514 LUT4 | 515 LUT4 | 16 MULT18X18D |

iCE40 at 16 bits is 170% of an HX8K's 7,680 LUTs. ECP5 infers one MULT18X18D
per PE and 16-bit costs the same as 8-bit. Target is ECP5
([ADR-0006](decisions/ADR-0006-synthesis-target.md)).

The extrapolation in ADR-0001 held: 238 x 16 predicted 3,808 against 3,782
measured.

`nextpnr-ecp5` still has not run. Fmax is unmeasured, and sixteen DSP blocks
feeding a 32-bit accumulator is where the critical path will be.

### Verification

16 tests across three suites: 6 PE, 7 array, 3 wrapper.

The array has two oracles. `matmul_reference` is the maths; `ArrayModel` is a
cycle-accurate mesh composed from the already-verified `PEModel`, so a mismatch
against one and not the other says whether the fault is arithmetic or wiring.
`test_cycle_accurate_against_model` compares all sixteen accumulators on every
edge, because an end-of-tile check can pass while the wavefront is wrong in a
way that cancels.

Mutation-tested, six breaks, all caught: transposing the accumulator index,
swapping the west and north edges, removing the horizontal skew, removing the
vertical skew, pinning the north edge to column 0, and leaving the eastward
operand unconnected.

### CI

It was running `tb/pe` only, so the two new suites would not have been checked.
It now loops every directory under `tb/` with a Makefile and requires a
`results.xml` from each — a suite that never ran was otherwise
indistinguishable from one that passed. Tested against a passing set, a missing
suite, and an injected failure.

Also added `main` to the push triggers. It was absent, so a direct push to
`main` would have had no CI at all, which contradicted ADR-0003.

---

## 2026-11-13 — PR 7: the transform benchmark

The workload the array exists for. A 4x4 homogeneous transform over a point
cloud, four points per tile.

### Fixed point, measured rather than chosen

Three quantities with different ranges share one 16-bit word: rotation entries
(all <= 1), translation (metres), and coordinates (metres). One format for all
three costs 39 mm of error at an 8 m extent where two formats cost 0.66 mm, a
factor of 59, because a shared format spends its fraction on range the rotation
matrix never uses.

Matrix in Q1.14, points in Q7.8, translation carried through a power-of-two
scale on the homogeneous component: with `P[3] = w` and `M[:,3] = t/w`, the
product recovers `t` at the matrix's own resolution.
[ADR-0002](decisions/ADR-0002-fixed-point.md).

| Matrix / point | +/-8 m | +/-64 m |
|---|---|---|
| Q7.8 / Q7.8 | 39.0 mm | 310.7 mm |
| Q1.14 / Q7.8 | 3.1 mm | 4.9 mm |
| Q1.14 / Q4.11 | 0.66 mm | saturates |

### ACC_W=32 is not enough in general

Four full-scale 16-bit products sum to 2^32 — `-32768 * -32768` is 2^30 and
there are four terms — which does not fit a signed 32-bit accumulator. Inside
the transform's envelope the measured headroom is 29 bits of 31, so it is
sufficient *there*. That makes the envelope a constraint rather than a
recommendation:

    K * max|m_q| * max|p_q| < 2^31

I found this by writing the corner test and watching it fail against an
unbounded Python reference. The RTL was wrapping correctly; the reference was
not wrapping at all.

### Results

- Bit-exact against the integer reference over 64 points. No tolerance on that
  comparison: the RTL must equal the fixed-point answer exactly.
- Quantization error 4.54 mm max, 1.50 mm rms against a derived bound of
  28.2 mm, so the bound is conservative by about 6x. The bound is what gets
  quoted, because a measurement over one cloud is not a guarantee.
- 10 cycles per 4-point tile, **2.50 cycles/point**, fill and drain included,
  readout excluded.

### Mutation testing found a real gap

The benchmark's own data never reaches the signed corner: rotation entries
quantize to at most 2^14 and coordinates similarly, so `-32768 * -32768` never
occurs naturally. Truncating the product by one bit survived every realistic
test.

Driving the corner directly took working out. Four corner terms do **not**
discriminate: a 2*DATA_W-1 product wraps 2^30 to -2^30, four of those sum to
-2^32, and the accumulator wraps that back to 0 — the same answer the correct
version gives. The product wrap and the accumulator wrap cancel. One
contributing term leaves the sum at 2^30, which fits, so the truncation shows.
Only `-32768 * -32768` reaches 2^30 at all; `32767 * 32767` is 1073676289 and
stays inside a 31-bit product.

One mutation still survives and is provably a no-op here: at `DATA_W=16`,
`2*DATA_W` equals `ACC_W`, so `ACC_W'(prod)` leaves the bits untouched and the
product's signedness cannot matter. Sign extension exists only at narrower
widths, and `tb/pe` at `DATA_W=8` does catch it.

### Still outstanding

- The **working volume** is unconfirmed. Q7.8 is the conservative default. If
  the real volume is a room, Q4.11 is a 7x accuracy improvement for a one-line
  change.
- The **MCU baseline** is unmeasured. It needs the same transform in C on a
  Cortex-M4 (STM32F411RE) and a board to run it on. Cycles per point is the
  comparison that means something architecturally; wall-clock waits on Fmax.
- `nextpnr` still has not run, so Fmax is unmeasured.

---

## 2026-11-16: consolidation, v0.1

No RTL, no testbench changes, no new measurements. This entry is about getting
what already existed onto `main`, and making every number in the README trace
to something in the repo.

### Where the branches were

`dev` was 4 commits ahead of `main` and 2 behind, and `test` was 1 behind.

The 4 ahead were PRs 6 and 7, the array and the transform benchmark. They had
merged into `dev` and never been promoted. The 2 behind were the merge commits
from PRs 4 and 5. Those exist only on `test` and `main` because I promote with
merge commits, and they carry no content: diffing the branches showed nothing
on `main` that `dev` lacked.

So there was nothing to reconcile by hand. Being behind by merge commits is
what this flow looks like. It is not drift.

### A commit that missed its PR

`28ab73b`, the Cortex-M4 baseline correction, was pushed to
`feat/bench-transform` after PR 7 had already merged, so `dev` never received
it. PR 8 landed it.

I found it by listing what each feature branch had that `dev` did not. That is
now the first thing I check before a promotion.

### The synthesis numbers had no source in the repo

The README said `synth/` held scripts and committed reports. It held a
`.gitkeep`. The LUT and multiplier counts in the README, this log and ADR-0006
were figures I had typed in after running Yosys by hand.

PR 9 added `synth/run.sh` and the four `stat` reports it writes. Re-run on
Yosys 0.70+277, every figure matched what I had written down.

The README also said the design was synthesized with nextpnr. It has not been.
Fixed in the same PR.

### Where each README number comes from

| Number | Source |
|---|---|
| 2.50 cycles/point | `tb/transform`, `test_throughput`: 1024 points, 256 tiles x 10 cycles |
| 4.54 mm max, 1.50 mm rms | `tb/transform`, `test_quantization_error_is_inside_the_derived_bound`: 256 points, prints 4.541 and 1.498 |
| Bit-exact | `tb/transform`, `test_rtl_matches_fixed_point_reference_bit_for_bit`: 64 points, exact equality, no tolerance |
| iCE40 3,782 / 13,028 LUT4 | `synth/reports/ice40_dw8.txt`, `synth/reports/ice40_dw16.txt` |
| ECP5 514 / 515 LUT4, 16 MULT18X18D | `synth/reports/ecp5_dw8.txt`, `synth/reports/ecp5_dw16.txt` |

The cycle count is the feed schedule, 10 clock edges per tile, times the 256
tiles the test drives through the RTL. It is not read from a counter in the
design. `test_cycle_accurate_against_model` in `tb/array` is what checks that
the hardware follows that schedule edge by edge.

The error figures are one synthetic cloud at a +/-64 m extent. The number the
format guarantees is the 28.2 mm bound, not the 4.54 mm measurement.

21 tests across four suites, green in CI on every PR in this promotion.

### Still not measured

- The linear filter benchmark.
- The Cortex-M4 baseline.
- Fmax. `nextpnr` has not run.

None of these were measured for v0.1, and the README says "not yet measured" in
each place.

### v0.1

`v0.1` is the `main` commit this promotion produces: the PE, the 4x4 array, the
readout wrapper, the transform benchmark, the synthesis reports, and CI on the
cocotb suite. Simulation only.

---

## 2026-11-25 — the Cortex-M4 baseline

The comparison the README had been promising. Same fixed-point transform in C on
an STM32F411RE, measured with `DWT->CYCCNT`.

| | Cycles/point | Cycles/MAC |
|---|---|---|
| Naive C, rolled `k` | 202.0 | 12.63 |
| Optimised C, unrolled | 90.0 | 5.63 |
| Array, compute only | 2.50 | |
| Array, readout-bound steady state | 4.0 | |

36x against optimised C, 22x once readout is counted. Readout is 16 cycles
against a 10-cycle tile, so a pipelined array is readout-bound rather than
compute-bound — which makes 2.50 the wrong number to quote for end-to-end
throughput even though it is the right one for the arithmetic.

### Two measurements I threw away

The first run reported 220.8 cycles/point. The timed region was also building
the input tiles, with a multiply and a modulo per element, and a modulo on this
core is a division. 13.8 cycles per multiply-accumulate on a core whose `SMLABB`
is one cycle was the tell. Inputs are now built before timing, and a pass over
the same tiles with no transform is timed separately and subtracted.

That got it to 202.0, which is still 12.63 cycles per MAC. Disassembling showed
why, and it was not a bad compile: gcc does emit `SMLABB`, but the rolled `k`
loop makes each MAC pay two loads, a compare and a taken branch, and the M4 has
no branch predictor. Unrolling `k` and hoisting the point's components into
locals gives 90.0.

Both figures are in the report. Quoting only the naive one would have inflated
the array's advantage by 2.24x.

### The C is also a second implementation

Both variants agree with `golden/transform_ref.py` bit for bit over 32 tiles:
realistic data, the full-scale signed corners, the single-term 2^30 corner, and
random full-range tiles. `bench/mcu/crosscheck.py` runs it.

The Python model was trusted because it is short. Nothing checked it until now.

### Provenance

Not a CI figure — there is no board on the runner, so this is the one number in
the README that a workflow cannot regenerate.
[`bench/mcu/reports/f411re_hsi16.txt`](../bench/mcu/reports/f411re_hsi16.txt)
holds the raw results block, the part, the probe, the clock, the compiler
version and the flags. `cd bench/mcu && make flash read` reproduces it.

### Independence

`bench/mcu/` carries its own startup, linker script and Makefile. Nothing comes
from my STM32 project; using an STM32 as a measurement platform is not a
dependency on that repo.

### One thing that cost a flash attempt

`.results` needs `(NOLOAD)` in the linker script. Without it the section gets a
load address up in SRAM and `objcopy` pads the flat binary from `0x08000000` to
`0x2001F018` — a 402 MB `.bin`. Nothing initialises the section now, so `main`
clears the guard word before measuring.

---

## 2026-11-25 — nextpnr, and an Fmax

The last unmeasured number in the README. `systolic_4x4_top` placed and routed
on an LFE5U-25F, CABGA381.

| Speed grade | DATA_W=8 | DATA_W=16 |
|---|---|---|
| 6 | 87.56 MHz | 83.68 MHz |
| 7 | 96.00 MHz | 89.29 MHz |
| 8 | 112.99 MHz | 107.26 MHz |

`synth/pnr.sh` regenerates all six reports. It routes the wrapper, not the bare
array: 644 port bits places on nothing, so Fmax has only ever been a property of
the design with its readout.

### 16 bits costs 4.4%

Against 170% of an HX8K's LUTs on iCE40. The DSP block absorbs the width, which
is what ADR-0006 predicted when it picked ECP5 on cell counts alone.

### Pin-bound, not logic-bound

At DATA_W=16: 6.7% of the logic, 5.8% of the registers, 57% of the
multipliers — and **84.8% of the I/O**, 167 of 197. The fabric is nearly empty
and the package is nearly full.

That inverts what I expected to worry about. Fitting a larger array on this part
is not the constraint; getting data in and out of it is. ADR-0005's shift-chain
readout is the only reason this fits a package at all, and it was chosen for
verification reasons rather than this one.

### The critical path, and what I got wrong

11.951 ns, from a PE's accumulator through its `MULT18X18D` and back.

    logic      5.976 ns   50.0%
    routing    5.450 ns   45.6%
    clk-to-q   0.525 ns    4.4%

I had written that the carry chain into a 32-bit accumulator would be where the
path went. The multiplier is indeed the largest single term at 3.927 ns, but the
carry chain is only 0.923 ns over 13 steps, and routing is 45.6% — nearly all of
logic. Routing that heavy is a placement artifact rather than a property of the
design, so a floorplan or another seed may move it.

If Fmax ever needs to be higher: the product is combinational into the
accumulator, so registering it pipelines the term that dominates. That costs a
cycle of latency per PE and changes the skew the dataflow relies on, so it is
not free, and at 83.68 MHz it is not needed.

### Wall-clock, finally

Array at DATA_W=16, speed grade 6, against the M4 at the F411RE's maximum:

    Cortex-M4, 90 cycles/point @ 100 MHz     1.11 Mpoint/s
    array, readout-bound, 4.0 @ 83.68 MHz   20.9 Mpoint/s   18.8x
    array, compute only,  2.50 @ 83.68 MHz  33.5 Mpoint/s   30.1x

The array is clocked **slower** than the MCU, 83.68 against 100 MHz. The whole
advantage is work per cycle.

Two things that make 18.8x the honest figure rather than a floor. The MCU number
scales a cycle count measured at 16 MHz and zero flash wait states up to
100 MHz, where the F411 needs three and would lean on the ART accelerator to
hold 90 cycles/point — generous to the MCU. And nothing here has run on an
FPGA; these are post-route estimates.
