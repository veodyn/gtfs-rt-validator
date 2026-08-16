"""The corpus `tools/diff_javafmt_against_java.py` measures over.

Split out of the differential the way `tools/geocorpus.py` is split out of
`tools/diff_geometry_against_java.py`: what is compared lives there, what is
compared *over* lives here, and neither file runs a JVM.

Every case is a raw bit pattern rather than a decimal literal. That is the only
way to put -0.0, a NaN with a payload and a subnormal in front of both languages
and know they saw the same value with no parse step in between.

What it covers, and why each part is here:

- every decimal literal in upstream's own Java, main and test sources alike,
  which is where the coordinates and speeds in `VehicleValidatorTest` come from;
- both neighbours of every power of ten, which brackets the 1e-3 and 1e7
  notation thresholds from each side;
- the boundary bit patterns: both zeros, both infinities, a quiet NaN and one
  with a payload, the smallest and largest subnormals, the smallest normal;
- integral values above 2^25 for floats and 2^54 for doubles, which is where
  `dtoa`'s fast path starts dropping decimal digits and stops producing the
  shortest representation;
- both `%.2f` tie directions, generated rather than listed: every `n / 1000` and
  `n / 200` across a range, so `x.xx5` is hit thousands of times over thousands
  of different binary neighbourhoods;
- a seeded random sweep over raw bit patterns, floats and doubles alike.
"""

from __future__ import annotations

import random
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "jar-build" / "upstream"

#: How `DumpJavaFormat.java` separates list items, and what stands for a null
#: one. Two control characters no Java source literal or list element uses.
SEPARATOR = "\x1f"
NULL_ITEM = "\x1e"

LITERAL = re.compile(r"-?\d+\.\d+(?:[eE][-+]?\d+)?[fFdD]?")

Case = tuple[str, str, str]


def f32_bits(value: float) -> int:
    """The bits of the float32 nearest `value`, saturating like a Java cast."""
    try:
        return struct.unpack("<I", struct.pack("<f", value))[0]
    except OverflowError:
        return 0xFF800000 if value < 0 else 0x7F800000


def f64_bits(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def upstream_literals() -> list[float]:
    """Every decimal literal in upstream's Java, so the corpus is theirs first.

    Scraped rather than transcribed. `VehicleValidatorTest.java` alone carries
    the coordinates E026 to E029 report, and hand-copying them is how a digit
    goes missing.
    """
    if not UPSTREAM.is_dir():
        print(f"no checkout at {UPSTREAM}; using the generated corpus only")
        return []
    found: set[float] = set()
    for path in UPSTREAM.rglob("*.java"):
        for match in LITERAL.finditer(path.read_text(encoding="utf-8", errors="replace")):
            found.add(float(match.group().rstrip("fFdD")))
    print(f"decimal literals scraped from {UPSTREAM}: {len(found)}")
    return sorted(found)


def float_bits_corpus(literals: list[float], *, quick: bool) -> list[tuple[str, int]]:
    cases: list[tuple[str, int]] = [
        ("f.zero", 0x00000000),
        ("f.negzero", 0x80000000),
        ("f.minsub", 0x00000001),
        ("f.maxsub", 0x007FFFFF),
        ("f.minnorm", 0x00800000),
        ("f.max", 0x7F7FFFFF),
        ("f.inf", 0x7F800000),
        ("f.neginf", 0xFF800000),
        ("f.nan", 0x7FC00000),
        ("f.nanpayload", 0x7F800001),
    ]
    cases += [(f"f.upstream{i}", f32_bits(v)) for i, v in enumerate(literals)]
    for power in range(-45, 39):
        base = f32_bits(float(f"1e{power}"))
        for tag, step in (("lo", -1), ("at", 0), ("hi", 1)):
            cases.append((f"f.pow{power}.{tag}", (base + step) & 0xFFFFFFFF))
    rng = random.Random(20260814)
    for i in range(200 if quick else 4000):
        exponent = rng.randint(25, 127)
        cases.append((f"f.integral{i}", f32_bits(float(rng.getrandbits(24) << (exponent - 24)))))
    cases += [(f"f.random{i}", rng.getrandbits(32)) for i in range(500 if quick else 30000)]
    return cases


def double_corpus(literals: list[float], *, quick: bool) -> list[tuple[str, int]]:
    named = (1609.0, 200.0, 2.675, -2.675, 0.125, -0.125, 0.135, 99.995, 0.005)
    cases: list[tuple[str, int]] = [
        ("d.zero", 0x0000000000000000),
        ("d.negzero", 0x8000000000000000),
        ("d.minsub", 0x0000000000000001),
        ("d.minnorm", 0x0010000000000000),
        ("d.max", 0x7FEFFFFFFFFFFFFF),
        ("d.inf", 0x7FF0000000000000),
        ("d.neginf", 0xFFF0000000000000),
        ("d.nan", 0x7FF8000000000000),
    ]
    cases += [(f"d.named{v}", f64_bits(v)) for v in named]
    cases += [(f"d.upstream{i}", f64_bits(v)) for i, v in enumerate(literals)]
    for power in range(-320, 309):
        base = f64_bits(float(f"1e{power}"))
        for tag, step in (("lo", -1), ("at", 0), ("hi", 1)):
            cases.append((f"d.pow{power}.{tag}", base + step))
    step = 7 if quick else 1
    cases += [(f"d.milli{n}", f64_bits(n / 1000)) for n in range(-2000, 20001, step)]
    cases += [(f"d.two{n}", f64_bits(n / 200)) for n in range(-400, 4001, step)]
    rng = random.Random(20260815)
    for i in range(200 if quick else 3000):
        exponent = rng.randint(54, 400)
        cases.append((f"d.huge{i}", f64_bits(float(rng.getrandbits(53) << (exponent - 53)))))
    cases += [(f"d.random{i}", rng.getrandbits(64)) for i in range(500 if quick else 20000)]
    cases += [
        (f"d.small{i}", f64_bits(rng.uniform(-1000.0, 1000.0)))
        for i in range(500 if quick else 20000)
    ]
    return cases


def string_cases() -> list[Case]:
    """The list, boolean and null rows, which are small and finite."""
    lists: list[list[str | None]] = [
        [],
        ["only"],
        ["a", "b", "c"],
        ["stop_id", None, "trip_id"],
        ["", ""],
        ["with space", "with,comma"],
        [None],
    ]
    cases: list[Case] = [
        (f"list{i}", "LIST", SEPARATOR.join(NULL_ITEM if v is None else v for v in items))
        for i, items in enumerate(lists)
    ]
    cases += [
        ("listi0", "LISTI", ""),
        ("listi1", "LISTI", "1"),
        ("listi2", "LISTI", "1,2,3"),
        ("listi3", "LISTI", "-1,0,2147483647,-2147483648"),
        ("bool0", "BOOL", "0"),
        ("bool1", "BOOL", "1"),
        ("null0", "NULL", ""),
        ("null1", "NULL", "trip_id "),
    ]
    return cases


def build_cases(*, quick: bool) -> list[Case]:
    """Every case, in the tab-separated shape `DumpJavaFormat.java` reads."""
    literals = upstream_literals()
    floats = float_bits_corpus(literals, quick=quick)
    doubles = double_corpus(literals, quick=quick)
    cases: list[Case] = [("env", "LOCALE", ""), ("enum", "ENUMS", "")]
    cases += [(name, "F32", format(bits, "08x")) for name, bits in floats]
    cases += [(f"{name}.p", "FMT2F", format(bits, "08x")) for name, bits in floats]
    cases += [(name, "F64", format(bits, "016x")) for name, bits in doubles]
    cases += [(f"{name}.p", "FMT2D", format(bits, "016x")) for name, bits in doubles]
    cases += string_cases()
    return cases
