#!/usr/bin/env bash
# Source this, don't execute it:   source env.sh
#
# Three things have to be true before cocotb can drive Icarus on this machine.
# I learned each of them the hard way on day 1 — see docs/BUILD_LOG.md.
#
#   1. The venv's Python must win over the one bundled in OSS CAD Suite.
#      The bundled interpreter has no numpy, so my golden models can't run there.
#   2. PYTHONHOME must be unset.
#   3. ICARUS_BIN_DIR must avoid the bin/ wrappers, which force PYTHONHOME to
#      the suite. How to avoid them differs per platform — see the case
#      statement below. Getting this wrong on Linux cost me a CI run.

_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export OSS_CAD_SUITE="${OSS_CAD_SUITE:-$HOME/oss-cad-suite}"

if [ ! -d "$_REPO/.venv" ]; then
  echo "env.sh: no .venv in $_REPO — create it with:" >&2
  echo "  /opt/homebrew/opt/python@3.13/bin/python3.13 -m venv .venv" >&2
  echo "  .venv/bin/pip install cocotb==2.1.0 numpy" >&2
  return 1 2>/dev/null || exit 1
fi

if [ ! -d "$OSS_CAD_SUITE" ]; then
  echo "env.sh: OSS CAD Suite not found at $OSS_CAD_SUITE" >&2
  return 1 2>/dev/null || exit 1
fi

# Order matters: venv first so `cocotb-config` resolves to mine, not the suite's.
export PATH="$_REPO/.venv/bin:$OSS_CAD_SUITE/bin:$PATH"
unset PYTHONHOME

# Where cocotb should find iverilog and vvp. The answer is platform-specific,
# because the suite's wrappers carry different responsibilities on each.
#
#   macOS: libexec/vvp references its library as
#          @executable_path/../lib/libvvp.1.14.0.dylib, so it resolves relative
#          to itself and libexec can be used directly.
#
#   Linux: the suite ships its own glibc and runs libexec binaries through its
#          own dynamic loader with --inhibit-cache --inhibit-rpath. Used
#          directly, libexec/vvp dies with
#          "libvvp.so.1: cannot open shared object file". But bin/vvp, which
#          does the loader invocation correctly, also exports PYTHONHOME to the
#          suite and so hides numpy from cocotb. tb/toolshim-linux is that same
#          invocation with the PYTHONHOME export removed.
case "$(uname -s)" in
  Linux)  export ICARUS_BIN_DIR="$_REPO/tb/toolshim-linux" ;;
  Darwin) export ICARUS_BIN_DIR="$OSS_CAD_SUITE/libexec" ;;
  *)      echo "env.sh: unrecognised platform $(uname -s); assuming libexec works" >&2
          export ICARUS_BIN_DIR="$OSS_CAD_SUITE/libexec" ;;
esac

echo "systolic-array env ready"
echo "  python       $(python3 --version 2>&1)"
echo "  cocotb       $(cocotb-config --version 2>&1)"
echo "  iverilog     $("$ICARUS_BIN_DIR/iverilog" -V 2>&1 | head -1)"
unset _REPO
