# ADR-0003: CI runs the pinned OSS CAD Suite, not distribution packages

**Status:** accepted
**Date:** 2026-11-08

## Context

Every PR into `dev` should gate on the cocotb suite. That needs a simulator on
the runner, and there's more than one way to get one.

A constraint that narrows this: **synthesis is not a CI product.** The resource
and Fmax numbers are generated locally and committed to `synth/reports/`, so CI
needs Icarus and nothing else. That removes Yosys and nextpnr from the
requirement and makes the question narrower than it first looks.

The thing I actually care about is what a green check *means*. This repo's value
rests on the word "verified." If CI runs a different simulator than the one that
produced my results tables, a green check answers a different question than the
one a reader assumes it answers.

## Options

**A. `apt install iverilog` on an Ubuntu runner.** Three lines of YAML, ~30s,
no caching. But Ubuntu's electronics packages lag badly: noble ships nextpnr
0.6 against the 0.11.1 I run locally, and iverilog is correspondingly old.

The version gap isn't purely a cost — a second, older simulator catches
assumptions that depend on my specific build, which is real value. But it also
means a CI failure might be a simulator difference rather than an RTL bug, and
"passes locally, fails CI" is the most expensive kind of confusion to debug when
I'm the only person on this.

**B. The pinned OSS CAD Suite tarball with `actions/cache`.** 712 MB on a cache
miss, roughly 2-4 minutes to download and extract; ~20-40s to restore once
warm. Byte-identical to my local toolchain, pinned to the same dated release.

**C. A prebuilt HDL container.** Fast and reproducible, but it trades my pinned
versions for the image maintainer's choices and adds a third-party image to the
supply chain. Little gained over B with a warm cache.

**D. A self-hosted runner on my laptop.** Exact fidelity, zero install. Also a
real security hole: on a public repo, a pull request from any fork can execute
arbitrary code on the runner. That's my development machine. Not worth it for a
version-matching benefit I can get another way.

## Decision

**Option B.** CI installs the same dated OSS CAD Suite release I run locally,
cached between runs.

The deciding factor is that it makes a CI failure mean exactly what a local
failure means. It also lets CI `source env.sh` — the same file I use locally —
so there is one toolchain code path instead of two that can drift apart.

I rejected D outright on security grounds and C for adding an external
dependency without a matching benefit. A is a defensible choice and I'd have
taken it if synthesis were in CI and the download cost had to be paid on every
job; as it stands the cache makes B cheap in steady state.

## Consequences

- First run on a new release tag costs a 712 MB download. `OSS_CAD_TAG` and
  `OSS_CAD_STAMP` in the workflow must move together when I bump it.
- GitHub evicts cache entries unused for 7 days, so after a quiet stretch I pay
  the cold cost again. Acceptable.
- The Python version is part of the toolchain, not incidental: cocotb embeds
  libpython into the simulator process. The workflow pins 3.13 to match my venv.
- Whether the Linux build's `bin/` wrappers pin `PYTHONHOME` the way the macOS
  ones do is **unverified**. The workflow has a step that prints the resolved
  interpreter and `ICARUS_BIN_DIR` so the first run answers it rather than
  hiding it. If they do, `env.sh` already handles it.
- The gate doesn't rely on `make` returning non-zero. It parses `results.xml`
  and fails on any failure *or* on zero tests, because a suite that silently
  runs nothing would otherwise report success. I tested that checker against a
  passing run, a failing run, and an empty file before trusting it.
- CI covers `dev`, `test`, and `main`, which is what makes "never test on
  `main`" enforceable rather than a convention I have to remember.

## Later

Verilator as a second matrix job. Two simulators disagreeing is a signal worth
having, and it's nearly free once the install works. Not in the first workflow.
