"""The corpus `tests/test_tier_overlap.py` runs the modern registry over.

Split out of the test module for the file-size hook, and because this is one of
the two parts a reader has to trust before the assertions mean anything: which
messages were actually looked at. The other is what "the same thing" means when
a cited rule and an upstream rule both report, and it is `tests/tiersubjects.py`
next door.

## The corpus, in ascending cost

1. **The conformance corpus**, `tests/fixtures/conformance/`, 32 committed `.pb`
   inputs in four groups. Three of the four groups are here; `testagency2` is
   not, and the reason is measured rather than a preference. Modern mode reads
   the static feed through the canonical, typed path (`runner/gate.py:206`,
   `load_static if mode is not COMPAT`) and `testagency2.zip` carries a
   `trips.txt` cell that path will not type, so `prepare_static` raises
   `StaticLoadError: trips.txt is in the archive but did not load`. Compat reads
   the same archive fine, through onebusaway. Two inputs are lost; the other
   30 are here.
2. **Every committed shadow fixture**, from `specshadowfeeds.FIXTURES` and
   `practiceshadowfeeds.FIXTURES`. These are the single-defect crafted feeds,
   one per cited rule, and they matter here for a reason the conformance corpus
   cannot cover: a rule that fires only on a real feed, where
   a dozen unrelated rules fire beside it, has no evidence of ever firing
   *alone*. They are also cheap, one or two entities each.
3. **The agency feeds** under `corpus/agencies/`, which are gitignored. Present
   locally or not; `agency_runs` yields nothing and `agencies_missing()` says
   why when they are absent, the way the jar-gated modules skip.

## The clock

The two `.pb` corpora are replays and take each file's clock from its mtime, as
compat does. So are the shadow fixtures, staged one directory each: without a
replay modern's clock would be `now` and every one of them would draw W008,
P008 and E050 for being months old. A spec fixture used to be a single file
pinned with `at=` for that reason, and became a directory when S021 arrived,
which is one message longer than the rest and the only rule here that compares
two.

**The agency corpus is staged by `tools/agencycorpus.py` and this module must
not stage a second time.** Every message goes under a name whose last twenty
characters encode its own `header.timestamp`, the run is one `-sort name`
replay, and each message is therefore validated at the instant its producer
stamped it. That module carries the measurement of why: a single fixed instant
for the whole recording, `recorded_at` being the last round's, judges every
earlier round stale for having been recorded first and takes P005 from 92
occurrences to 985 over the MBTA corpus. One `Request` per round is wrong for a
second reason, which no count would show: a round with no previous message
leaves P002, P003 and P004 unable to fire at all, so three of the rules this
module exists to check would be silently outside it.

The join key an occurrence is reduced to, and why it is read out of the
occurrence prefix, is `tests/tiersubjects.py`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import conformancecorpus as conformance
import practiceshadow
import specshadow
from gtfs_rt_validator import api
from gtfs_rt_validator.inputs import Inputs
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.report.occurrence import NoticeContainer
from gtfs_rt_validator.runner import Mode, SortBy
from gtfsfixtures import build_feed
from jarcorpus import import_tool
from practiceshadowfeeds import FIXTURES as PRACTICE_FIXTURES
from specshadowfeeds import FIXTURES as SPEC_FIXTURES

run_jar = import_tool("run_jar")

#: The agency corpus's staging, verification and clock, owned by `tools/` and
#: shared with `tools/tier_counts.py`. Imported the way every other tool is here
#: rather than reimplemented: two stagings would be two clocks.
agencycorpus = import_tool("agencycorpus")

#: The one conformance group modern mode cannot load. See the module docstring.
UNTYPEABLE_GROUP = "testagency2"


def conformance_runs(tmp: Path) -> Iterator[tuple[str, NoticeContainer]]:
    """The three groups modern mode can load, each one replay."""
    for name in conformance.group_names():
        if name == UNTYPEABLE_GROUP:
            continue
        directory = tmp / name
        directory.mkdir(parents=True)
        run_jar.stage(conformance.inputs(name), directory)
        result = api.validate(
            api.Request(
                mode=Mode.MODERN,
                gtfs=conformance.archive(name),
                inputs=api.resolve_walk(str(directory), SortBy.DATE_MODIFIED),
                sort_by=SortBy.DATE_MODIFIED,
                ignore_shapes="ignoring-shapes" in name,
            )
        )
        yield f"conformance/{name}", result.run.notices


def _spec_run(fixture, directory: Path) -> tuple[str, NoticeContainer]:
    """One `specshadow.Fixture`: its run, over the tables it asks for.

    A run of one message for all but S021's fixture, which is the only spec rule
    whose defect is a change between two of them. The messages go into a
    directory rather than in as a single file, so this is a replay and modern
    mode's clock is each file's own mtime; a single file would leave the clock
    at `now` and draw W008, P008 and E050 on every fixture for being months old.
    """
    gtfs = build_feed(
        directory,
        specshadow.tables(
            fixture.exact_times,
            shape_points=fixture.shape_points,
            extra_stops=fixture.extra_stops,
        ),
    )
    messages = directory / "rt"
    messages.mkdir()
    for index, entities in enumerate(fixture.messages()):
        message = messages / f"{fixture.rule_id.lower()}-{index}.pb"
        message.write_bytes(
            encode(
                {
                    "header": {
                        "gtfs_realtime_version": "2.0",
                        "incrementality": 0,
                        "timestamp": specshadow.CLOCK + index,
                    },
                    "entity": entities,
                },
                SCHEMA,
            )
        )
        os.utime(message, (specshadow.CLOCK + index, specshadow.CLOCK + index))
    result = api.validate(
        api.Request(mode=Mode.MODERN, gtfs=gtfs, inputs=api.resolve(str(messages)))
    )
    return f"spec-fixture/{fixture.rule_id}", result.run.notices


def _practice_run(fixture, directory: Path, blobs) -> tuple[str, NoticeContainer]:
    """One `practiceshadow.Fixture`: a run of one or more messages, replayed."""
    gtfs = build_feed(directory, practiceshadow.tables(fixture.exact_times))
    messages = directory / "rt"
    messages.mkdir()
    for index, (name, blob) in enumerate(blobs(fixture).items()):
        path = messages / name
        path.write_bytes(blob)
        os.utime(path, (practiceshadow.CLOCK + index, practiceshadow.CLOCK + index))
    result = api.validate(
        api.Request(mode=Mode.MODERN, gtfs=gtfs, inputs=api.resolve(str(messages)))
    )
    return f"practice-fixture/{fixture.name()}", result.run.notices


def fixture_runs(tmp: Path, blobs) -> Iterator[tuple[str, NoticeContainer]]:
    """Every committed shadow fixture of both cited tiers, one run each.

    `blobs` is `test_practice_tier_does_not_shadow_the_jar.blobs`, passed in
    rather than imported, so the encoding of a practice fixture has exactly one
    definition and this module cannot drift from the one the jar is asked about.
    """
    for index, fixture in enumerate(SPEC_FIXTURES):
        directory = tmp / f"spec-{index}"
        directory.mkdir(parents=True)
        yield _spec_run(fixture, directory)
    for index, fixture in enumerate(PRACTICE_FIXTURES):
        directory = tmp / f"practice-{index}"
        directory.mkdir(parents=True)
        yield _practice_run(fixture, directory, blobs)


def agencies_missing() -> str:
    """Why the agency corpus cannot be read here, or the empty string if it can.

    `agencycorpus.verified_bytes` raises `CorpusMissing` for a file that is not
    there and for one whose SHA-256 is not the manifest's, and both are the same
    answer to a caller: these are not the bytes anything was measured over.
    """
    for agency in agencycorpus.manifest()["agencies"]:
        for record in _recorded_files(agency):
            try:
                agencycorpus.verified_bytes(record)
            except agencycorpus.CorpusMissing as missing:
                return str(missing)
    return ""


def _recorded_files(agency: dict) -> Iterator[dict]:
    """Every file one agency's recording pins, static archive included.

    The roles come from `agencycorpus.roles_of` and never from `ROLES`, which is
    an order and not a census: an agency publishing no alerts feed is recorded
    with two roles and one publishing one is recorded with three. That is the
    shape `runner/context.py` already works in, where a cycle holds the roles
    that decoded and a missing one is a smaller cycle rather than an error.
    """
    yield agency["static"]
    roles = agencycorpus.roles_of(agency)
    for entry in agency["rounds"]:
        for role in roles:
            yield entry["files"][role]


def agency_runs(tmp: Path) -> Iterator[tuple[str, NoticeContainer]]:
    """One `-sort name` replay per agency, staged by `tools/agencycorpus.py`.

    Nothing about the staging is decided here. The clock is in each file name
    and a cycle keeps an agency's roles together, however many it publishes,
    which is what makes P002, P003 and P004 reachable; the module docstring says
    what happens when either is done differently.
    """
    if agencies_missing():
        return
    for index, agency in enumerate(agencycorpus.manifest()["agencies"]):
        directory = tmp / f"agency-{index}"
        directory.mkdir(parents=True)
        staged = agencycorpus.stage(agency, directory)
        result = api.validate(
            api.Request(
                mode=Mode.MODERN,
                gtfs=staged.archive,
                inputs=Inputs(staged.cycles, directory_replay=True),
                sort_by=SortBy.NAME,
            )
        )
        yield f"agency/{agency['static_mdb_id']}", result.run.notices


def message_count() -> int:
    """How many messages the whole available corpus is, for the report."""
    manifest = agencycorpus.manifest()
    agency = (
        0
        if agencies_missing()
        else sum(
            len(agencycorpus.roles_of(entry)) * len(entry["rounds"])
            for entry in manifest["agencies"]
        )
    )
    conformance_inputs = sum(
        len(conformance.group(name)["inputs"])
        for name in conformance.group_names()
        if name != UNTYPEABLE_GROUP
    )
    practice = sum(len(fixture.messages) for fixture in PRACTICE_FIXTURES)
    spec = sum(len(fixture.messages()) for fixture in SPEC_FIXTURES)
    return conformance_inputs + spec + practice + agency
