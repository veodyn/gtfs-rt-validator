"""The jar as a negative oracle for the practice tier's declared overlaps.

The jar implements none of the practice rules, so
`tools/diff_compat_against_jar.py` cannot confirm one. It can **refute a
declared overlap**, which is the part of a cited rule most likely to be wrong,
and for the band rules it can do more than that: P004 and P005 exist on the
claim that there is a band of feed behaviour no upstream rule reaches, and a jar
run that says nothing over an in-band feed is the proof.

`tests/test_spec_tier_does_not_shadow_the_jar.py` is the spec tier's version of
this and the shape is deliberately the same. What is different is that a practice
fixture is a *run* rather than a message: P004 is about the interval between two
consecutive header timestamps, so the messages are staged into a replay
directory with their mtimes stamped one second apart, exactly as
`tools/run_jar.py` stages a corpus, and both this project and the jar read each
file's own mtime as its clock.

Five assertions, in ascending cost:

1. the practice rule fires on the fixtures that say it does, and is silent on
   the ones that say it is not, which is what makes a band two-sided;
2. `Registry.compat()` over the same bytes emits exactly what the fixture
   records, which runs everywhere and is this project's byte-for-byte
   reproduction of the jar being asked the same question;
3. the id the rule declares as its overlap is not among them;
4. the real jar emits exactly that too, which needs a jar and skips without one;
5. the in-band fixtures make the jar say nothing at all.

**Never weaken these.** The rule that governs the compat differential applies
here as much: a red diff against the jar is the deliverable, not an obstacle. If
the jar disagrees, the rule's declared overlap is wrong, not the test.
Assertion 5 has no exceptions in it and must not grow one, because a band claim
carrying an exemption proves nothing about the bands beside it. It has already
been the reason a rule was removed: a third band rule, P014, was proposed
for an `exact_times=0` trip whose `TripDescriptor.schedule_relationship` is
absent, and its in-band fixture made the jar emit W009. W009 fires on
`!hasScheduleRelationship()` for any TripDescriptor
(`TripDescriptorValidator.java:470-474`), and `_shared/walk_trip_descriptor.py`
`:141-142` calls it with none of the suppression its stop_time_update overload
has, so P014's trigger was a strict subset of W009's and no feed shape escaped
it. P014 was retired rather than exempted here; clause `143#2`'s verdict in
`upstream/practice-clause-verdicts.json` carries the measurement.

## Adding a fixture

A cohort adds `Fixture` entries to `practiceshadowfeeds.FIXTURES` and nothing
here changes. One entry carries:

- `rule_id` and a `case` string; together they are the test id, so the case says
  what distinguishes this fixture from the rule's others;
- `messages`, a tuple of `practiceshadow.Message`, one per file of the run, in
  the order they are stamped. One message is the common case;
- `fires`, whether the rule itself reports on the run. A rule needs at least one
  fixture with `fires=False`, or its test cannot catch a rule that fires on
  everything;
- `jar_ids`, **recorded from a real run and never predicted**. Run the case,
  read what came back, put it here with a note if it is not empty;
- `not_emitted`, the upstream id the rule declares as its overlap in
  `test_tier_overlap.OVERLAP`, or `None` where it declares none;
- `exact_times`, when the rule needs `frequencies.txt` in the static feed.

Build the entities from `practiceshadow`'s `as_trip_update` and `as_vehicle` so
the only defect in the run is the rule's. A fixture whose jar verdict is not
empty is not automatically wrong, but it needs a note saying which upstream rule
answered and why that is not the one the rule declares.
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
from practiceshadow import CLOCK, Fixture, tables
from practiceshadowfeeds import FIXTURES, IN_BAND

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

CASES = pytest.mark.parametrize("fixture", FIXTURES, ids=lambda fixture: fixture.name())

IN_BAND_CASES = pytest.mark.parametrize(
    "fixture",
    [fixture for fixture in FIXTURES if fixture.name() in IN_BAND],
    ids=lambda fixture: fixture.name(),
)


def blobs(fixture: Fixture) -> dict[str, bytes]:
    """The fixture's run, one file per message, encoded under the current schema.

    Which is the point: the jar parses them with the 2015 bindings and puts
    every field it does not know into its unknown-field set, exactly as it would
    with a real modern feed. The names sort in message order, because
    `tools/run_jar.py` stamps mtimes in the order it is given and this project's
    replay sorts by them.
    """
    return {
        f"{fixture.rule_id.lower()}-{index}.pb": encode(
            {
                "header": {
                    # The message's own version rather than a constant: P001's
                    # fixture is a `"1.0"` header and nothing else, and it could
                    # not be expressed here until `Message` carried the field.
                    "gtfs_realtime_version": message.gtfs_realtime_version,
                    "incrementality": 0,
                    "timestamp": message.header_timestamp,
                },
                "entity": message.entities,
            },
            SCHEMA,
        )
        for index, message in enumerate(fixture.messages)
    }


def staged(fixture: Fixture, tmp_path: Path) -> tuple[Path, Path]:
    """The static archive and the run directory, on disk, with mtimes stamped.

    The messages live in their own directory so the GTFS zip is not walked as a
    realtime input, and the mtimes are `CLOCK + index`: upstream reads a file's
    mtime as "current" for every timestamp rule (`BatchProcessor.java:223`) and
    `runner/clock.py:modern_reading` does the same on a directory replay, so the
    two see the same clock for the same file.
    """
    static = tmp_path / "static"
    static.mkdir()
    gtfs = build_feed(static, tables(fixture.exact_times))
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
def test_the_rule_says_what_the_fixture_says_it_says(fixture, tmp_path):
    """Both directions, and the second is the one that matters. Without a
    fixture the rule is silent on, every other assertion here would pass on a
    rule that reported nothing at all, and half of these fixtures exist
    precisely to stand just outside a band."""
    reported = fixture.rule_id in ids_from(fixture, tmp_path, Mode.MODERN)

    assert reported is fixture.fires, fixture.note


@CASES
def test_compat_over_the_same_bytes_emits_what_was_recorded(fixture, tmp_path):
    """This project's reproduction of the jar, asked the jar's question. It runs
    on a checkout with no jar, and `tools/diff_compat_against_jar.py` is what
    makes it worth anything: these ids are the jar's ids unless that
    differential is red."""
    assert ids_from(fixture, tmp_path, Mode.COMPAT) == set(fixture.jar_ids)


@CASES
def test_no_fixture_makes_the_jar_emit_the_id_its_fixture_forbids(fixture):
    """The rule's own claim, stated over the recorded verdict.

    A rule that declares an upstream overlap is claiming that this fixture is
    *not* that upstream rule's, and a recorded verdict naming it would be the
    refutation.
    """
    assert fixture.not_emitted not in fixture.jar_ids


@needs_jar
@CASES
def test_the_jar_emits_exactly_what_was_recorded(fixture, tmp_path):
    """The oracle itself. One invocation per fixture rather than one for all of
    them, because `BatchProcessor` carries the previous message across files in
    a run: two fixtures in one directory would compare one fixture's header
    against another's."""
    gtfs, directory = staged(fixture, tmp_path)
    names = sorted(path.name for path in directory.iterdir())
    outcome = run_jar.run({name: (directory / name).read_bytes() for name in names}, gtfs)

    assert outcome.skipped == [], outcome.summary()
    found = {rule_id for name in names for rule_id in jar_ids(outcome.results[name])}
    assert found == set(fixture.jar_ids), fixture.note


@needs_jar
@IN_BAND_CASES
def test_the_jar_says_nothing_at_all_inside_a_band(fixture, tmp_path):
    """The practice tier's strongest claim, and the reason the band rules were
    built first.

    A band split is a paragraph until a jar run over an in-band feed comes back
    empty. This is that run, and it takes no exceptions: a rule whose in-band
    fixture makes the jar say something has no band, and the module docstring
    names the one that has already been removed for it.
    """
    gtfs, directory = staged(fixture, tmp_path)
    names = sorted(path.name for path in directory.iterdir())
    outcome = run_jar.run({name: (directory / name).read_bytes() for name in names}, gtfs)

    assert outcome.skipped == [], outcome.summary()
    assert {rule_id for name in names for rule_id in jar_ids(outcome.results[name])} == set()
