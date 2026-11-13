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
