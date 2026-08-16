"""The jar as a negative oracle for the spec tier's declared overlaps.

The jar implements none of the 52 spec rules, so `tools/diff_compat_against_jar.py`
cannot confirm one. It can **refute a declared overlap**, which is the part of a
cited rule most likely to be wrong, because "no upstream rule covers this" is
a claim about 6,792 lines of somebody else's Java that nobody re-reads.

The method, which is the only one available with no oracle: build a fixture
whose only defect is the new rule's, run the jar over it, and a jar run that
says nothing is empirical proof that the boundary is real. `specshadow.py` holds the clean
pieces and `specshadowfeeds.py` the 21 fixtures, one per rule of cohorts A, B
and C.

Four assertions, in ascending cost:

1. the spec rule actually fires on its own fixture, without which the rest
   proves nothing about that rule;
2. `Registry.compat()` over the same bytes emits exactly what the fixture
   records, which runs everywhere and is this project's byte-for-byte
   reproduction of the jar being asked the same question;
3. the real jar emits exactly that too, which needs a jar and skips without one;
4. the id the fixture's `not_emitted` names is not among them.

**Never weaken these.** The rule that governs the compat differential applies
here as much: a red diff against the jar is the deliverable, not an obstacle. If
the jar disagrees, the rule's declared overlap is wrong, not the test.

Two of the recorded verdicts are not empty and both were measured rather than
excused. `specshadowfeeds.DESCRIPTOR_ARTIFACT` explains W009, which follows from
the 2015 enum lacking the member a post-2015 fixture states; S020's note
explains E003 and W003, which follow from a duplicate trip not being in
`trips.txt` and having no TripUpdate. Neither names the id its `not_emitted`
does, which is the claim under test.

**A fixture is a run rather than a message**, staged into a directory the way
`tests/test_practice_tier_does_not_shadow_the_jar.py` stages one, because S021
is the one spec rule whose defect is a change *between* two messages and it can
have no fixture at all otherwise. Almost every fixture is still one message and
states nothing: `Fixture.preceding` is empty and the run is one file whose
header timestamp and mtime are both `CLOCK`, exactly as before.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from gtfs_rt_validator import api
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.runner.mode import Mode
from gtfsfixtures import build_feed
from jarcorpus import import_tool
from specshadow import CLOCK, Fixture, tables
from specshadowfeeds import FIXTURES

jarenv = import_tool("jarenv")
run_jar = import_tool("run_jar")


def jar_ids(results: bytes) -> set[str]:
    """Every `errorId` in one `.results.json`, which is what the jar found.

    The file is a list of `ErrorListHelperModel` beans and the id sits at
    `errorMessage.validationRule.errorId`; `tests/jarcontract.py` is what pins
    that shape against the committed goldens, so this reads it rather than
    restating it.
    """
    return {
        entry["errorMessage"]["validationRule"]["errorId"]
        for entry in json.loads(results.decode("utf-8"))
    }


def _unavailable() -> str:
    """Why the jar cannot be run here, or the empty string if it can."""
    if not jarenv.jar_present():
        return f"no jar at {jarenv.JAR}; run .venv/bin/python tools/build_jar.py"
    try:
        jarenv.java_home_17()
    except jarenv.NoJdk17Error as exc:
        return str(exc)
    return ""


REASON = _unavailable()
needs_jar = pytest.mark.skipif(bool(REASON), reason=REASON or "a jar is present")

CASES = pytest.mark.parametrize("fixture", FIXTURES, ids=lambda fixture: fixture.rule_id)


def blobs(fixture: Fixture) -> dict[str, bytes]:
    """The fixture's run, one `FeedMessage` per file, under the current schema.

    Which is the point: the jar parses them with the 2015 bindings and puts
    every field it does not know into its unknown-field set, exactly as it would
    with a real modern feed.

    Message `n` carries header timestamp `CLOCK + n`, which is `CLOCK` for the
    one-message fixtures that are almost all of them. Two messages sharing a
    header timestamp are E017's shape, so a fixture that states a `preceding`
    message would otherwise measure that rule rather than its own.
    """
    return {
        f"{fixture.rule_id.lower()}-{index}.pb": encode(
            {
                "header": {
                    "gtfs_realtime_version": "2.0",
                    "incrementality": 0,
                    "timestamp": CLOCK + index,
                },
                "entity": entities,
            },
            SCHEMA,
        )
        for index, entities in enumerate(fixture.messages())
    }


def staged(fixture: Fixture, tmp_path: Path) -> tuple[Path, Path]:
    """The static archive and the run directory, on disk, with the clock stamped.

    The mtime is the clock: `BatchProcessor.java:223` reads it as "current" for
    every timestamp rule, so a message written now over a header stamped at
    `CLOCK` is W008's shape rather than a clean feed. File `n` is stamped
    `CLOCK + n`, matching the header its own message carries and the order
    `tools/run_jar.py` stamps a run in.

    The messages live in their own directory so the GTFS zip is not walked as a
    realtime input.
    """
    gtfs = build_feed(
        tmp_path,
        tables(
            fixture.exact_times,
            shape_points=fixture.shape_points,
            extra_stops=fixture.extra_stops,
        ),
    )
    directory = tmp_path / "rt"
    directory.mkdir()
    for index, (name, blob) in enumerate(blobs(fixture).items()):
        path = directory / name
        path.write_bytes(blob)
        os.utime(path, (CLOCK + index, CLOCK + index))
    return gtfs, directory


def ids_from(fixture: Fixture, tmp_path: Path, mode: Mode) -> set[str]:
    """Every rule id this project reports over the fixture's run, in one mode."""
    gtfs, directory = staged(fixture, tmp_path)
    result = api.validate(api.Request(mode=mode, gtfs=gtfs, inputs=api.resolve(str(directory))))
    return set(result.run.notices.grouped())


@CASES
def test_the_rule_fires_on_its_own_fixture(fixture, tmp_path):
    """Without this the other three assertions are about a feed with no defect
    in it, and every one of them would pass on an empty message."""
    assert fixture.rule_id in ids_from(fixture, tmp_path, Mode.MODERN)


@CASES
def test_compat_over_the_same_bytes_emits_what_was_recorded(fixture, tmp_path):
    """This project's reproduction of the jar, asked the jar's question. It runs
    on a checkout with no jar, and `tools/diff_compat_against_jar.py` is what
    makes it worth anything: these ids are the jar's ids unless that
    differential is red."""
    assert ids_from(fixture, tmp_path, Mode.COMPAT) == set(fixture.jar_ids)


@CASES
def test_no_fixture_makes_the_jar_emit_the_id_its_fixture_forbids(fixture):
    """The rule's declared overlap, stated over the recorded verdict.

    A rule that declares an upstream neighbour is claiming that this fixture is
    *not* that neighbour's, and a recorded verdict naming it would be the
    refutation. `OVERLAP` in `tests/test_tier_overlap.py` is where each
    declaration is kept.
    """
    assert fixture.not_emitted not in fixture.jar_ids


@needs_jar
@CASES
def test_the_jar_emits_exactly_what_was_recorded(fixture, tmp_path):
    """The oracle itself. One invocation per fixture rather than one for all of
    them, because `BatchProcessor` carries the previous message across files in
    a run, so two fixtures in one directory would compare one fixture's header
    against another's and E017 would fire on the second file onwards."""
    gtfs, directory = staged(fixture, tmp_path)
    names = sorted(path.name for path in directory.iterdir())
    outcome = run_jar.run({name: (directory / name).read_bytes() for name in names}, gtfs)

    assert outcome.skipped == [], outcome.summary()
    found = {rule_id for name in names for rule_id in jar_ids(outcome.results[name])}
    assert found == set(fixture.jar_ids), fixture.note
