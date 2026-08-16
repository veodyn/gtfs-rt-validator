"""Differential: `rules/_shared/javafmt.py` against a running JDK 17.

Nine Java renderings reach compat occurrence bytes. This runs every one of them
through `tools/DumpJavaFormat.java`
over the corpus in `tools/javafmtcorpus.py` and compares string against string.
Nothing is normalised, no tolerance is applied, and a divergence prints the exact
bit pattern needed to reproduce it. A red diff is the deliverable, not an
obstacle.

JDK 17 is not incidental. `Float.toString` and `Double.toString` were rewritten
in JDK 19 (JDK-4511638) to emit the shortest round-tripping decimal, and this
compares against the older algorithm because that is what upstream's pom
targets. `tools/jarenv.py` finds a 17 and raises rather than settle for another
release, which is deliberate: a green run under JDK 21 would prove nothing about
the jar.

The enum row is compared too, against `proto/schema_2015.py` rather than against
a second copy of the names, because upstream's pom pins the same
gtfs-realtime-bindings 0.0.4 that compat's schema was generated from.

Run:
    .venv/bin/python tools/diff_javafmt_against_java.py
    .venv/bin/python tools/diff_javafmt_against_java.py --quick
"""

from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import jarenv  # noqa: E402
import javafmtcorpus  # noqa: E402
from javafmtcorpus import NULL_ITEM, SEPARATOR, Case  # noqa: E402

from gtfs_rt_validator.proto import schema_2015  # noqa: E402
from gtfs_rt_validator.rules._shared import javafmt  # noqa: E402

DUMPER = ROOT / "tools" / "DumpJavaFormat.java"
BINDINGS = ROOT / "tools" / ".jars" / "gtfs-realtime-bindings-0.0.4.jar"
PROTOBUF = ROOT / "tools" / ".jars" / "protobuf-java-2.6.1.jar"

LABELS = {
    "F32": "Float.toString",
    "F64": "Double.toString",
    "FMT2F": 'String.format("%.2f", float)',
    "FMT2D": 'String.format("%.2f", double)',
    "LIST": "List<String>.toString",
    "LISTI": "List<Integer>.toString",
    "BOOL": "boolean concatenation",
    "NULL": "null concatenation",
}


class Tally:
    """Cases compared, and every one that diverged, with the input that did it."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.count = 0
        self.bad: list[str] = []

    def check(self, where: str, java: str, python: str) -> None:
        self.count += 1
        if java != python:
            self.bad.append(f"  {where}\n    java   {java!r}\n    python {python!r}")

    def report(self) -> None:
        print(f"{self.label}: {self.count} cases, {len(self.bad)} divergent")
        for row in self.bad[:40]:
            print(row)
        if len(self.bad) > 40:
            print(f"  ... and {len(self.bad) - 40} more")


def run_oracle(cases: list[Case]) -> list[list[str]]:
    """One JVM for the whole corpus, under the JDK 17 upstream's pom targets."""
    command = [str(jarenv.java_17())]
    if BINDINGS.exists() and PROTOBUF.exists():
        command += ["-cp", f"{BINDINGS}:{PROTOBUF}"]
    command.append(str(DUMPER))
    stdin = "".join(f"{name}\t{op}\t{arg}\n" for name, op, arg in cases)
    done = subprocess.run(command, input=stdin, check=True, capture_output=True, text=True)
    return [line.split("\t") for line in done.stdout.splitlines() if line.strip()]


def python_side(op: str, arg: str) -> str:
    """What `javafmt` renders for the same case, by the same op name."""
    if op in ("F32", "FMT2F"):
        value = struct.unpack("<f", struct.pack("<I", int(arg, 16)))[0]
        return javafmt.float32_str(value) if op == "F32" else javafmt.fmt2(value)
    if op in ("F64", "FMT2D"):
        value = struct.unpack("<d", struct.pack("<Q", int(arg, 16)))[0]
        return javafmt.double_str(value) if op == "F64" else javafmt.fmt2(value)
    if op == "LIST":
        items = arg.split(SEPARATOR) if arg else []
        return javafmt.java_list([None if v == NULL_ITEM else v for v in items])
    if op == "LISTI":
        return javafmt.java_list([int(v) for v in arg.split(",")] if arg else [])
    if op == "BOOL":
        return javafmt.java_bool(arg == "1")
    return arg + javafmt.java_str(None)


def compare(cases: list[Case], rows: list[list[str]]) -> list[Tally]:
    args = {name: arg for name, _op, arg in cases}
    tallies = {op: Tally(label) for op, label in LABELS.items()}
    errors = Tally("the JVM refused a case")
    enums: dict[str, dict[str, int]] = {}
    for row in rows:
        name, op = row[0], row[1]
        if op == "LOCALE":
            print(f"measured against JDK {row[3]}, default locale {row[2]}")
        elif op == "ENUM":
            enums.setdefault(row[2], {})[row[3]] = int(row[4])
        elif op == "ENUMS":
            print(f"enum comparison skipped: {' '.join(row[2:])}")
        elif op == "ERROR":
            errors.bad.append(f"  {name}: {' '.join(row[2:])}")
        else:
            arg = args[name]
            where = f"{name} {op} {arg}"
            if op == "FMT2D" and row[2] != row[3]:
                # Upstream passes no Locale, so its separator is the default
                # one. This machine's writing a comma would not be a Python bug
                # and must not be reported as one.
                tallies[op].bad.append(
                    f"  {where}\n    the default locale gave {row[2]!r}, Locale.ROOT {row[3]!r}"
                )
            tallies[op].check(where, row[2], python_side(op, arg))
    return [*tallies.values(), compare_enums(enums), errors]


def compare_enums(java: dict[str, dict[str, int]]) -> Tally:
    """Every constant the 2015 bindings declare, against `proto/schema_2015.py`.

    Compat decodes with the 2015 schema and upstream's pom pins the same
    gtfs-realtime-bindings 0.0.4, so the two tables have to agree name for name
    and number for number, or an enum renders bytes upstream never wrote.
    """
    tally = Tally("enum constant names")
    ours = schema_2015.SCHEMA.enums
    for type_name in sorted(set(java) | set(ours)):
        theirs = java.get(type_name, {})
        mine = ours.get(type_name, {})
        for number in sorted(set(theirs.values()) | set(mine.values())):
            java_name = next((n for n, v in theirs.items() if v == number), "<absent>")
            try:
                python_name = javafmt.java_enum(number, mine)
            except ValueError:
                python_name = "<absent>"
            tally.check(f"{type_name} = {number}", java_name, python_name)
    return tally


def main() -> None:
    quick = "--quick" in sys.argv[1:]
    cases = javafmtcorpus.build_cases(quick=quick)
    print(f"cases: {len(cases)}")
    tallies = compare(cases, run_oracle(cases))
    print("\n=== summary ===")
    for tally in tallies:
        tally.report()
    bad = sum(len(tally.bad) for tally in tallies)
    print(f"\nexit status {1 if bad else 0}; non-zero means javafmt.py and the JVM disagree.")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
