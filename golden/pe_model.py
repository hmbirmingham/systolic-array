"""NumPy reference for the processing element.

The RTL is checked against this, never against hand-written expected values.
A MAC cell has an exact mathematical definition, so there is no reason to
approximate it in the testbench — and a golden model is the one kind of oracle
that cannot drift toward whatever the RTL happens to do.
"""

import numpy as np


def mac_width(data_w: int) -> int:
    """Bits needed for a signed DATA_W x DATA_W product, without truncation."""
    return 2 * data_w


def wrap_signed(value: int, width: int) -> int:
    """Two's-complement wrap into `width` bits.

    The accumulator is a fixed-width register, so it wraps. The model has to
    wrap identically or a long accumulation would diverge from the RTL for a
    reason that is not a bug.
    """
    mask = (1 << width) - 1
    value &= mask
    if value & (1 << (width - 1)):
        value -= 1 << width
    return value


class PEModel:
    """One output-stationary MAC cell, cycle for cycle with `rtl/pe.sv`."""

    def __init__(self, data_w: int = 8, acc_w: int = 32):
        self.data_w = data_w
        self.acc_w = acc_w
        self.acc = 0
        self.a_out = 0
        self.b_out = 0

    def reset(self) -> None:
        self.acc = 0
        self.a_out = 0
        self.b_out = 0

    def step(self, a_in: int, b_in: int, en: bool, clear: bool) -> None:
        """Advance one clock edge, matching the RTL's priority exactly."""
        prod = int(np.int64(a_in) * np.int64(b_in))
        if clear:
            self.acc = wrap_signed(prod, self.acc_w) if en else 0
        elif en:
            self.acc = wrap_signed(self.acc + prod, self.acc_w)
        if en:
            self.a_out = a_in
            self.b_out = b_in


def dot_reference(a: np.ndarray, b: np.ndarray, acc_w: int = 32) -> int:
    """What a PE should hold after streaming two vectors through it.

    This is the property the array ultimately rests on: a PE accumulating a row
    of A against a column of B is computing one element of A @ B.
    """
    total = int(np.dot(a.astype(np.int64), b.astype(np.int64)))
    return wrap_signed(total, acc_w)
