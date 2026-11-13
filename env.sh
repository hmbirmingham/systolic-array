#!/usr/bin/env bash
# Source this, don't execute it:   source env.sh
#
# cocotb needs my venv's Python, not the one bundled in OSS CAD Suite, which has
# no numpy. That means PATH order, PYTHONHOME unset, and an ICARUS_BIN_DIR that
# avoids the bin/ wrappers. See docs/BUILD_LOG.md.

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

# Platform-specific. macOS libexec binaries resolve their libraries relative to
# themselves; Linux ones need the suite's bundled loader, which only the bin/
# wrappers invoke, and bin/vvp also sets PYTHONHOME. tb/toolshim-linux/README.md
# has the detail.
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
