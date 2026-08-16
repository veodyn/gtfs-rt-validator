"""Differential: our Java HashMap iteration order simulation against a real JVM.

Only `CrossFeedDescriptorValidator` observes Java hash order, through W003 and
E047, and it observes it in output bytes. The simulation sorts on
`(bucketIndexAtFinalCapacity, insertionIndex)`, which was reasoned off the
`HashMap` source rather than tested, red-black treeification most of all. This
settles it against a running JVM.

Run:

    python tools/diff_hashorder_against_java.py

It generates cases, runs `tools/DumpHashOrder.java` under JDK 17 through the
single-file source launcher, and compares. A disagreement is printed with the
index where the two orders first diverge; it is never smoothed over.

Findings as of 2026-08-14, OpenJDK 17.0.19 arm64:

  - The simulation is exact for every realistic id set, to 216 keys, unicode
    included.
  - `HashMap` and `HashSet` iteration order were identical in every case, so one
    simulation serves both containers.
  - It breaks only on a large full-hash-collision set, somewhere between 9 and
    16 colliding keys in one bucket. Bucket depth alone is not the trigger:
    depth 8 and depth 9 both matched.

The simulation itself now lives in `gtfs_rt_validator.rules._shared.javahash`,
which is what W003 and E047 call, and this imports it rather than keeping a
second copy: two implementations would let the thing measured and the thing
shipped drift apart silently. `tests/test_shared_javahash.py` asserts that this
module and the rule layer name the same function object.

The promoted version *detects* the treeify condition and raises rather than
emitting a plausible wrong order, so a refusal is counted here as a
disagreement. It refuses on exactly the seven cases that disagreed before it
learned to.
"""

from __future__ import annotations

import itertools
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from jarenv import java_home_17

from gtfs_rt_validator.rules._shared.javahash import iteration_order
from gtfs_rt_validator.rules.errors import RuleContractError

ORACLE = Path(__file__).parent / "DumpHashOrder.java"


def collision_blocks(length: int) -> list[str]:
    """Strings with identical `hashCode`.

    `"Aa"` and `"BB"` hash equal, so every string built by concatenating those
    two blocks collides with every other of the same length. This is the only
    practical way to reach treeification, which needs 8 entries in one bucket.
    """
    return ["".join(parts) for parts in itertools.product(["Aa", "BB"], repeat=length)]


def gen_cases() -> list[list[str]]:
    random.seed(20260814)
    cases: list[list[str]] = []
    # Realistic ids, at sizes crossing every resize threshold (12, 24, 48, 96).
    for count in (1, 2, 5, 11, 12, 13, 23, 24, 25, 47, 48, 49, 95, 96, 97, 200):
        cases.append([f"trip_{i}" for i in range(count)])
        cases.append([f"{random.randint(1, 99999)}.{random.randint(0, 9)}" for _ in range(count)])
    for count in (5, 20, 60):
        cases.append([f"veh{random.randint(100, 999)}" for _ in range(count)])
    # Full collisions, at and around the treeify threshold.
    for length in (3, 4):
        blocks = collision_blocks(length)
        for count in (7, 8, 9, 16):
            if count <= len(blocks):
                cases.append(blocks[:count])
    # Treeification also needs a table of at least 64, so pad to force capacity
    # up, with the colliding keys inserted both before and after the padding.
    blocks16 = collision_blocks(4)
    for pad in (40, 90, 200):
        cases.append(blocks16 + [f"pad_{i}" for i in range(pad)])
        cases.append([f"pad_{i}" for i in range(pad)] + blocks16)
    # String.hashCode is over UTF-16 code units, so cover non-BMP.
    cases.append(["café", "naïve", "日本語", "\U0001f600emoji", "trip_1"])
    return cases


def run_oracle(cases: list[list[str]]) -> tuple[list[list[str]], list[list[str]]]:
    java = Path(java_home_17()) / "bin" / "java"
    payload = "".join("\t".join(case) + "\n" for case in cases)
    done = subprocess.run(
        [str(java), str(ORACLE)],
        input=payload.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    rows = [line.split("\t") for line in done.stdout.decode("utf-8").splitlines() if line]
    return (
        [row[1:] for row in rows if row[0] == "MAP"],
        [row[1:] for row in rows if row[0] == "SET"],
    )


def main() -> int:
    cases = gen_cases()
    maps, sets = run_oracle(cases)
    if not (len(maps) == len(sets) == len(cases)):
        print(f"oracle returned {len(maps)} maps and {len(sets)} sets for {len(cases)} cases")
        return 2

    agree = 0
    failures: list[tuple[list[str], list[str], list[str], list[str] | None, str]] = []
    for keys, from_map, from_set in zip(cases, maps, sets, strict=True):
        # A HashMap keeps the first insertion of a repeated key.
        unique = list(dict.fromkeys(keys))
        try:
            got: list[str] | None = list(iteration_order(unique))
        except RuleContractError as refusal:
            # A refusal is a disagreement, not a pass: the simulation is saying
            # it cannot answer for this key set, which is the honest failure.
            failures.append((unique, from_map, from_set, None, str(refusal)))
            continue
        if got == from_map == from_set:
            agree += 1
        else:
            failures.append((unique, from_map, from_set, got, ""))

    print(f"cases {len(cases)}   agree {agree}   disagree {len(failures)}")
    print(f"HashMap and HashSet orders identical in every case: {maps == sets}")

    for unique, from_map, from_set, got, refusal in failures:
        print(f"\n  {len(unique)} keys")
        print(f"    map and set agree with each other: {from_map == from_set}")
        if got is None:
            print(f"    refused: {refusal}")
            continue
        for index, (theirs, ours) in enumerate(zip(from_map, got, strict=True)):
            if theirs != ours:
                print(f"    first divergence at index {index}: java {theirs!r}, simulated {ours!r}")
                break

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
