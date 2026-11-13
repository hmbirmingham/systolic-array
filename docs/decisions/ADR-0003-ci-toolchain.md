# ADR-0003 — CI uses the pinned OSS CAD Suite, not distribution packages

**Status:** accepted
**Date:** 2026-11-11

## Context

Every PR into `dev` should gate on the cocotb suite, which needs a simulator on
the runner.

Synthesis is not a CI product: resource and Fmax numbers are generated locally
and committed to `synth/reports/`. So the runner needs Icarus and nothing else,
which makes the question narrower than it first looks.

## Decision

**CI installs the same dated OSS CAD Suite release I run locally, cached between
runs, and sources the same `env.sh`.**

## Why

- **A failure means what a local failure means.** This repo's claim is that the
  array is verified. A check running a different simulator than the one behind
  my results tables answers a different question than a reader assumes it does.
- **One toolchain path.** CI sources `env.sh` unchanged, so there is no second
  environment definition to drift out of step with the first.
- **The cache makes it cheap in steady state.** 712 MB on a miss, ~20s warm.

## The alternatives

**`apt install iverilog`.** Three lines of YAML, no caching. Ubuntu's
electronics packages lag: noble ships nextpnr 0.6 against my 0.11.1, with a
correspondingly old iverilog. The gap isn't purely a cost — a second, older
simulator catches assumptions tied to my specific build — but it means a CI
failure might be a simulator difference rather than an RTL bug. Defensible, and
I'd have taken it if synthesis were in CI and the download had to be paid every
job.

**A prebuilt HDL container.** Trades my pinned versions for the image
maintainer's and adds a third-party image to the supply chain. Little gained
over a warm cache.

**A self-hosted runner on my laptop.** Exact fidelity, zero install, and a real
security hole: on a public repo, a pull request from any fork executes code on
my development machine. Rejected outright.

## Consequences

- `OSS_CAD_TAG` and `OSS_CAD_STAMP` must move together when I bump the release.
- GitHub evicts caches unused for 7 days, so a quiet stretch pays the cold cost
  again.
- Python 3.13 is pinned. cocotb embeds libpython into the simulator process, so
  the interpreter is part of the toolchain rather than incidental.
- The gate parses `results.xml` and fails on any failure *or* on zero tests. A
  suite that silently ran nothing would pass an exit-status check. Tested
  against a passing run, an injected failure, and an empty file.
- CI covers `dev`, `test` and `main`, which makes "never test on `main`"
  enforceable rather than a convention.

## Amendment, 2026-11-13

I left one thing unverified: whether the Linux `bin/` wrappers pin `PYTHONHOME`
like the macOS ones. The first run answered it and the framing was too narrow.

`PYTHONHOME` came back unset, `cocotb-config` resolved to the venv, numpy was
reachable. The run failed on the library path instead:
`libvvp.so.1: cannot open shared object file`.

The Linux build ships its own glibc and runs `libexec` binaries through its own
dynamic loader with `--inhibit-cache --inhibit-rpath ""`. macOS doesn't need
that because `libexec/vvp` names its library as
`@executable_path/../lib/libvvp.1.14.0.dylib` and resolves relative to itself. I
had generalised the macOS case.

So the wrappers carry two responsibilities: the loader invocation, which I need,
and the `PYTHONHOME` export, which I don't. `tb/toolshim-linux/` is the suite's
own invocation minus that export, and `env.sh` selects per platform. Linux
`bin/iverilog` sets no `PYTHONHOME`, so only `vvp` required it.

`LD_LIBRARY_PATH` would have paired the system loader with the suite's bundled
libc, which is what `--inhibit-rpath` exists to prevent.

Cold cache measured ~20s, not the 2-4 minutes estimated above.
