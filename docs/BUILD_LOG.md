# Build log

One entry per PR. I record what I built, what broke, and what I had to decide,
so that future-me (and anyone reading this repo) can reconstruct why the code
looks the way it does.

---

## 2026-10-29 — Day 1: toolchain

No RTL today. I set up and *verified* the toolchain before writing a line of
SystemVerilog, which turned out to be the right call — three separate things
would have bitten me on day 3 looking like RTL bugs.

### Versions I'm building against

| Tool | Version | Source |
|---|---|---|
| Yosys | 0.70+277 (git sha1 `77dddbd66`) | OSS CAD Suite `20261029` |
| nextpnr-ice40 | 0.11.1-83-g9691ce8c | same |
| nextpnr-ecp5 | 0.11.1-83-g9691ce8c | same |
| Verilator | 5.053 devel (rev v5.052-640-g8c14ab842) | same |
| Icarus Verilog | 14.0 devel (s20260301-776-g699144553) | same |
| GTKWave | 4.0.0-prealpha (06a0d44) | same |
| Python | 3.13.18 | Homebrew `python@3.13` (framework build) |
| cocotb | 2.1.0 | venv wheel, `cp313` |
| NumPy | 2.5.4 | venv |

OSS CAD Suite tarball, pinned for reproducibility:

- `oss-cad-suite-darwin-arm64-20261029.tgz`
- 525,007,575 bytes
- sha256 `5a431a6578c93bcf7cd05451cd556f549232f335051adc7cc85b802a5c51fb94`
- Installed to `~/oss-cad-suite` (outside this repo — it's a shared toolchain,
  not a project dependency)

Host: MacBook Air M4, macOS 26.6.2, arm64.

### Three traps, and why each one matters

**1. Anaconda's Python can't be used.** My default `python3` is Anaconda's
3.14.6. cocotb embeds libpython into the simulator process, and Anaconda's
build fails that with `Failed to import encodings module`. Setting `PYTHONHOME`
doesn't fix it. I rebuilt the venv from Homebrew's `python@3.13`, which is a
proper framework build, and it embeds cleanly.

Worth being precise about why I initially got this wrong: I checked that cocotb
publishes a `cp314` wheel and concluded 3.14 was fine. The wheel was never the
problem — *which* Python, not which version, is what matters for embedding.

**2. Everything in `~/oss-cad-suite/bin/` is a wrapper script that hijacks
Python.** `bin/vvp` is bash, not a binary, and it does this:

```bash
export PYTHONEXECUTABLE="$release_topdir_abs/bin/tabbypy3"
export PYTHONHOME="$release_topdir_abs"
```

So any cocotb run through `bin/vvp` is silently forced onto the suite's own
bundled Python 3.11 — which has **no numpy**. My entire verification strategy
is "check RTL against a NumPy golden model," so that would have quietly made
the golden models unreachable. The fix is `ICARUS_BIN_DIR=~/oss-cad-suite/libexec`,
pointing at the real executables instead of the wrappers.

Verilator's wrapper does *not* pin `PYTHONHOME`, and cocotb exposes
`VERILATOR_BIN_DIR` as the same escape hatch if I need it later. Icarus was the
only booby trap.

**3. `MODULE` is deprecated in cocotb 2.x.** It's `COCOTB_TEST_MODULES` now.
Also worth noting: cocotb 2.x is a major rewrite from 1.x, and nearly every
tutorial online is 1.x and will not run. `Timer(1, unit="ns")` — `unit`,
not `units`.

These three are now encoded in [`../env.sh`](../env.sh) and
[`../tb/sim.mk`](../tb/sim.mk) rather than living in my shell history.

### Smoke test

I didn't want to call the toolchain "installed" on the strength of version
output, so I proved the whole chain end to end on a throwaway 8-bit adder:
SystemVerilog -> Icarus -> cocotb -> NumPy golden comparison over 20 random
vectors, all passing. That's the exact pattern every benchmark in this project
depends on, so it needed to work before I trusted anything else.

### Not resolved

- **Surfer is not bundled** in OSS CAD Suite, contrary to what I assumed when I
  wrote the scope. Only GTKWave ships. I'm using GTKWave for now and will
  decide on installing Surfer separately before I need serious waveform work.
- cocotb's `libpython` resolves into the Homebrew Cellar path, so moving or
  upgrading that Python will break the venv. If simulations suddenly fail to
  start, rebuild `.venv` first.

---

## 2026-10-31 — Day 2: PR 1, repo scaffold

Set up the repository layout, README stub, LICENSE (MIT), `.gitignore`, and
this log.

### A correction to my own scope doc

The command sequence I wrote in the scope doesn't work. I had:

```bash
git init -b main
git checkout -b dev
git checkout -b test
git checkout dev      # error: pathspec 'dev' did not match any file(s) known to git
```

Before the first commit exists, `git checkout -b <name>` doesn't create a
branch — it just repoints unborn `HEAD`, so each call overwrites the last.
Running all four lines leaves one unborn branch called `test`, no commits, and
no `main` at all. I tested this in a throwaway repo to confirm rather than
guessing.

What I actually did: an **empty root commit** on `main`, then branched `dev`
from `main` and `test` from `dev`. This preserves the rule I care about —
`main` only ever receives code already promoted through `test`, and the
scaffold arrives on `dev` through PR 1 like every other feature, rather than
being committed straight to `main`.

### Layout

```
rtl/      pe.sv, systolic_4x4.sv            (empty, PR 2 and 3)
tb/       sim.mk + cocotb tests             (tests land in PR 2)
golden/   NumPy reference models            (empty, PR 4)
synth/    yosys/nextpnr scripts, reports/   (empty, PR 7)
docs/     this log, decisions/              ADRs land with PR 3 and 4
```

### Public vs local notes

This repo is public, so this log is public. I keep two files local and
gitignored: `CLAUDE.md`, and a private log for context that belongs to my other
projects rather than to this one. Everything needed to understand, build, and
verify the array is in the repo; nothing load-bearing lives outside it.

### The PE, and a latent bug in sim.mk

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
