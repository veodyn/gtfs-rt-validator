"""Float comparison at ulp resolution, and the divergence tally built on it.

Both halves of `tools/diff_geometry_against_java.py` compare doubles Java
produced against doubles Python produced, and both hit the same wall: Java's
`Math` on this JDK is fdlibm and CPython's is the platform libm, so a handful of
results differ in the last bit or two.

That is a real difference and it is not swallowed by a tolerance. It is counted,
named and reported apart from everything else, precisely so that an algorithmic
regression cannot hide behind it. Both categories are divergences and both make
the harness exit non-zero; the split says which kind, not whether it counts.

`ULP_NOISE_LIMIT` is where the two categories part. The recorded gaps are one
and two ulps: `tests/test_bbox.py` pins a buffered longitude two ulps outside
the jar's, and the raw offset curves differ by one ulp at latitudes near zero.
Four leaves headroom for a libm that rounds differently again while staying many
orders of magnitude below anything an algorithm error produces, since a wrong
arc angle or a missed simplifier pass moves a coordinate in a decimal place a
human can read, which is upwards of 1e11 ulps.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

ULP_NOISE_LIMIT = 4


def _lex(x: float) -> int:
    """Doubles reordered as integers, so adjacent doubles are adjacent ints."""
    bits = struct.unpack("<Q", struct.pack("<d", x))[0]
    return -(bits & ((1 << 63) - 1)) if bits >> 63 else bits


def ulp_gap(java: float, py: float) -> int | None:
    """Representable doubles between two values; `None` means not comparable.

    Two NaNs are equal here, because an empty spatial4j rectangle is NaN in all
    four bounds and reproducing that is the point. A NaN facing a number, or a
    disagreeing infinity, has no ulp distance and is always a hard divergence.
    """
    if math.isnan(java) or math.isnan(py):
        return 0 if math.isnan(java) and math.isnan(py) else None
    if math.isinf(java) or math.isinf(py):
        return 0 if java == py else None
    return abs(_lex(java) - _lex(py))


@dataclass
class Tally:
    """One comparison run: what was compared, and how it diverged."""

    label: str
    unit: str = "values"
    compared: int = 0
    hard: list[str] = field(default_factory=list)
    ulp: list[str] = field(default_factory=list)
    worst: int = 0

    def value(self, case: str, what: str, java: float, py: float) -> None:
        """One double against the jar's double, compared exactly."""
        self.compared += 1
        gap = ulp_gap(java, py)
        if gap == 0:
            return
        row = f"{case} {what}: java={java!r} python={py!r} gap={gap} ulps"
        if gap is None or gap > ULP_NOISE_LIMIT:
            self.hard.append(row)
        else:
            self.worst = max(self.worst, gap)
            self.ulp.append(row)

    def answer(
        self, case: str, what: str, java: bool, py: bool, on_ulp_bound: bool = False
    ) -> None:
        """One boolean against the jar's boolean.

        `on_ulp_bound` says the probe sits exactly on a bound that already
        diverged at ulp level, so the flip is that same libm gap seen through
        containment rather than a second, independent finding. Any other
        disagreement is a hard failure.
        """
        self.compared += 1
        if java == py:
            return
        row = f"{case} {what}: java={java} python={py}"
        if on_ulp_bound:
            self.ulp.append(f"{row} (probe lies on a bound that differs by ulps)")
        else:
            self.hard.append(row)

    def fail(self, case: str, why: str) -> None:
        """The oracle gave no usable answer. Never silently skipped."""
        self.hard.append(f"{case}: {why}")

    def status(self) -> int:
        """Fail closed: a run that compared nothing is a failure, not a MATCH."""
        return 1 if self.hard or self.ulp or self.compared == 0 else 0

    def summary(self) -> str:
        verdict = "DIFF" if self.hard or self.ulp else "MATCH"
        if self.compared == 0 and not self.hard:
            verdict = "EMPTY, nothing was compared"
        tail = f"{len(self.hard)} hard, {len(self.ulp)} ulp-level"
        # `worst` stays 0 when every ulp row is a flipped containment answer
        # rather than a compared value, and reporting "worst 0 ulps" would read
        # as a measurement instead of as the absence of one.
        if self.worst:
            tail += f", worst {self.worst} ulp{'s' if self.worst > 1 else ''}"
        return f"{self.label}: {self.compared} {self.unit} compared, {tail} -> {verdict}"

    def report(self, limit: int = 12) -> None:
        print(self.summary())
        for kind, rows in (("HARD", self.hard), ("ULP ", self.ulp)):
            for row in rows[:limit]:
                print(f"  {kind} {row}")
            if len(rows) > limit:
                print(f"  {kind} ... {len(rows) - limit} more")
