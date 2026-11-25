"""Hold the C baseline against golden/transform_ref.py, bit for bit.

The C is the measured baseline, so it has to compute the same arithmetic as the
model the RTL is checked against. It is also a second independent
implementation: the Python model is short enough to read, but nothing else
checks it, and two implementations agreeing is stronger than one being plausible.

Run from the repo root:
    .venv/bin/python bench/mcu/crosscheck.py
"""

import pathlib
import subprocess
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "golden"))

from pe_model import wrap_signed                      # noqa: E402
from transform_ref import (                           # noqa: E402
    Format,
    quantize_points,
    quantize_transform,
    tiles,
)

MCU = ROOT / "bench" / "mcu"
LO, HI = -32768, 32767


def rotation(rx, ry, rz):
    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)
    r_x = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    r_y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    r_z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return r_z @ r_y @ r_x


def build_host_harness() -> pathlib.Path:
    out = MCU / "host_check"
    subprocess.run(
        ["cc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(out),
         str(MCU / "transform_fx.c"), str(MCU / "host_check.c")],
        check=True,
    )
    return out


def cases():
    """Realistic tiles, the signed corners, and random full-range tiles.

    The corners matter most. Realistic transform data never reaches full scale,
    so a reference that is wrong only at -32768 * -32768 would look correct
    across any amount of plausible input.
    """
    fmt = Format(14, 8)
    rng = np.random.default_rng(101)

    matrix = np.eye(4)
    matrix[:3, :3] = rotation(0.3, -0.7, 1.1)
    matrix[:3, 3] = [10.0, -5.0, 2.0]
    mi, w = quantize_transform(matrix, fmt)

    points = np.ones((4, 64))
    points[:3] = rng.uniform(-64, 64, size=(3, 64))
    for idx, (block, _) in enumerate(tiles(points, 4)):
        yield f"realistic[{idx}]", mi, quantize_points(block, fmt, w)

    yield "full-scale lo*lo", np.full((4, 4), LO, np.int64), np.full((4, 4), LO, np.int64)
    yield "full-scale lo*hi", np.full((4, 4), LO, np.int64), np.full((4, 4), HI, np.int64)
    yield "full-scale hi*hi", np.full((4, 4), HI, np.int64), np.full((4, 4), HI, np.int64)

    single_m = np.zeros((4, 4), np.int64)
    single_p = np.zeros((4, 4), np.int64)
    single_m[:, 0] = LO
    single_p[0, :] = LO
    yield "single-term corner", single_m, single_p

    for t in range(12):
        yield (f"random[{t}]",
               rng.integers(LO, HI + 1, size=(4, 4), dtype=np.int64),
               rng.integers(LO, HI + 1, size=(4, 4), dtype=np.int64))


def main() -> int:
    harness = build_host_harness()
    all_cases = list(cases())

    stdin = "\n".join(
        " ".join(str(int(v)) for v in list(m.reshape(-1)) + list(p.reshape(-1)))
        for _, m, p in all_cases
    )
    run = subprocess.run([str(harness)], input=stdin, capture_output=True, text=True)
    if run.returncode == 2:
        print("the two C implementations disagree with each other:")
        print(run.stderr)
        return 1

    lines = [line for line in run.stdout.strip().splitlines() if line.strip()]
    if len(lines) != len(all_cases):
        print(f"got {len(lines)} outputs for {len(all_cases)} tiles")
        return 1

    bad = 0
    for (name, m, p), line in zip(all_cases, lines):
        got = [int(x) for x in line.split()]
        exact = m.astype(object) @ p.astype(object)
        want = [wrap_signed(int(v), 32) for v in np.asarray(exact).reshape(-1)]
        if got != want:
            bad += 1
            print(f"MISMATCH {name}\n  c      {got}\n  python {want}")

    print(f"{len(all_cases)} tiles compared, {bad} mismatches")
    if bad:
        return 1
    print("both C variants agree with each other and with the Python model")
    return 0


if __name__ == "__main__":
    sys.exit(main())
