"""NumPy and cycle-accurate references for the 4x4 array.

Two oracles, deliberately. `matmul_reference` is the mathematical answer.
`ArrayModel` is a cycle-accurate model built by composing the already-verified
`PEModel` into a 4x4 mesh, so it checks the wiring and the feed schedule rather
than the arithmetic. A test that passes against both is being held to the maths
and to the dataflow at the same time.

The feed schedule is the contract the array depends on. Tile control is a single
broadcast clear with `en` held high (ADR-0004), which is only correct because
out-of-window operands are zero. So the padding here is load-bearing, not
cosmetic, and `test_array_4x4.py` asserts it rather than assuming it.
"""

import numpy as np

from pe_model import PEModel, wrap_signed

N = 4


def total_cycles(k: int, n: int = N) -> int:
    """Cycles until every accumulator is valid.

    PE(i,j) takes its last product at t = k-1+i+j, and the worst cell is
    (n-1, n-1), so the final accumulator settles on the edge at t = k-1+2*(n-1)
    and is readable one cycle later.
    """
    return k + 2 * (n - 1)


def feed_schedule(a: np.ndarray, b: np.ndarray, n: int = N):
    """Per-cycle edge operands for A @ B, skewed and zero-padded.

    `a` is (n, k) and `b` is (k, n). Yields `(a_vec, b_vec)` per cycle, where
    `a_vec[i]` enters row i at the west edge and `b_vec[j]` enters column j at
    the north edge.

    Row i is delayed by i cycles and column j by j, which is what makes
    PE(i,j) see k = t-i-j. Everything outside a cell's window is zero.
    """
    k = a.shape[1]
    assert a.shape == (n, k), f"a must be ({n}, k), got {a.shape}"
    assert b.shape == (k, n), f"b must be (k, {n}), got {b.shape}"

    for t in range(total_cycles(k, n)):
        a_vec = np.zeros(n, dtype=np.int64)
        b_vec = np.zeros(n, dtype=np.int64)
        for i in range(n):
            if 0 <= t - i < k:
                a_vec[i] = a[i, t - i]
        for j in range(n):
            if 0 <= t - j < k:
                b_vec[j] = b[t - j, j]
        yield a_vec, b_vec


def matmul_reference(a: np.ndarray, b: np.ndarray, acc_w: int = 32) -> np.ndarray:
    """A @ B with each element wrapped to the accumulator width."""
    product = a.astype(np.int64) @ b.astype(np.int64)
    return np.array(
        [[wrap_signed(int(v), acc_w) for v in row] for row in product],
        dtype=np.int64,
    )


class ArrayModel:
    """4x4 mesh of PEModel, stepped cycle for cycle with `rtl/systolic_4x4.sv`."""

    def __init__(self, data_w: int = 8, acc_w: int = 32, n: int = N):
        self.n = n
        self.cells = [[PEModel(data_w, acc_w) for _ in range(n)] for _ in range(n)]

    def reset(self) -> None:
        for row in self.cells:
            for cell in row:
                cell.reset()

    def step(self, a_vec, b_vec, en: bool, clear: bool) -> None:
        """Advance one clock edge.

        Neighbour outputs are snapshotted before any cell is stepped, because
        every cell updates on the same edge. Stepping in place without the
        snapshot would let a cell see this cycle's output from its neighbour
        instead of last cycle's, which is the bug this method exists to avoid.
        """
        n = self.n
        a_at = [[0] * n for _ in range(n)]
        b_at = [[0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                a_at[i][j] = int(a_vec[i]) if j == 0 else self.cells[i][j - 1].a_out
                b_at[i][j] = int(b_vec[j]) if i == 0 else self.cells[i - 1][j].b_out

        for i in range(n):
            for j in range(n):
                self.cells[i][j].step(a_at[i][j], b_at[i][j], en, clear)

    def acc(self) -> np.ndarray:
        return np.array(
            [[cell.acc for cell in row] for row in self.cells], dtype=np.int64
        )

    def run_tile(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Stream one tile and return the accumulators. `clear` fires at t=0."""
        self.reset()
        for t, (a_vec, b_vec) in enumerate(feed_schedule(a, b, self.n)):
            self.step(a_vec, b_vec, en=True, clear=(t == 0))
        return self.acc()
