"""The recorded agency corpus, compared against a running jar.

`tests/test_jar_differential.py` re-derives the committed goldens from the jar
over eight crafted fixtures. This is the same comparison over real production
feeds: `tools/diff_agency_against_jar.py` stages four agencies' recorded rounds
and hands them to `diff_compat_against_jar`'s own two sides, so there is one
comparison in this repository and not two.

**Skips loudly, twice over.** The jar and a JDK 17 are gitignored build output,
and `corpus/` is gitignored recorded bytes, so a clean checkout has neither.
`-ra` in `addopts` prints which one was missing, the convention
`test_agency_tier_counts.py` and `test_jar_differential.py` already follow.

**`tests/test_agency_goldens.py` is the half that needs no JVM, and neither
module replaces the other.** That one compares this project's side against
`tests/fixtures/agencies/jar-goldens.json`, a committed digest and rule census
of what the jar wrote, so a checkout with the recorded bytes and no Java can
still detect drift. This module is the stronger check and is the only one that
can notice a rebuilt jar, a moved JDK or a changed FORMAT locale, because it
re-derives the jar's side from the artefact instead of reading a recording of
it. Do not delete either for duplicating the other.

**One test here is expected to be red about the product and green as a test.**
`test_the_jar_cannot_read_the_mbta_archive_at_all` pins a measured parity gap:
the jar dies reading MBTA's `areas.txt` and validates nothing, and this project
validates all eighteen messages. Asserting the gap rather than skipping it is
deliberate. Nobody has to remember it, and the day the compat static loader
learns to refuse what `GtfsReader` refuses, this goes red and says so. Do not
delete it then, invert it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from jarcorpus import import_tool

jarenv = import_tool("jarenv")
agencycorpus = import_tool("agencycorpus")
diff = import_tool("diff_compat_against_jar")
tool = import_tool("diff_agency_against_jar")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from gtfs_rt_validator.runner import SortBy  # noqa: E402

#: The agency whose archive the jar cannot read. See the module docstring and
#: `tools/diff_agency_against_jar.py` for the Java that settles why.
MBTA = "mdb-437"

#: The cheapest agency to run both sides over: two roles, six rounds, a 53 KB
#: archive. Used where the assertion is about the harness rather than the feed.
SMALLEST = "tld-820"


def _no_jar() -> str:
    if not jarenv.jar_present():
        return f"no jar at {jarenv.JAR}; run .venv/bin/python tools/build_jar.py"
    try:
        jarenv.java_home_17()
    except jarenv.NoJdk17Error as exc:
        return str(exc)
    return ""


def _no_corpus() -> str:
    try:
        for entry in agencycorpus.manifest()["agencies"]:
            agencycorpus.verified_bytes(entry["static"])
            for record in entry["rounds"]:
                for held in record["files"].values():
                    agencycorpus.verified_bytes(held)
    except agencycorpus.CorpusMissing as absent:
        return f"the recorded agency corpus is not available: {absent}"
    return ""


NO_JAR, NO_CORPUS = _no_jar(), _no_corpus()
needs_corpus = pytest.mark.skipif(bool(NO_CORPUS), reason=NO_CORPUS or "the corpus is here")
needs_both = pytest.mark.skipif(
    bool(NO_JAR or NO_CORPUS), reason=NO_JAR or NO_CORPUS or "both are here"
)

#: Every agency whose archive the jar can actually read, which is the set the
#: byte-for-byte assertion applies to. Never empty: an empty parametrize list
#: makes pytest skip with "got empty parameter set", which hides the reason the
#: gate above went to the trouble of computing.
READABLE = [
    entry["static_mdb_id"]
    for entry in agencycorpus.manifest()["agencies"]
    if entry["static_mdb_id"] != MBTA
] or ["<the manifest lists no agency>"]


@pytest.mark.parametrize("sort", sorted(tool.SORTS))
def test_the_flag_names_upstreams_own_sort_vocabulary(sort: str):
    """`--sort name` has to reach the jar as `-sort name` or it is decoration.

    The mapping is what makes the file-name clock reachable at all
    (`BatchProcessor.java:220-232`), and `DATE_MODIFIED` maps to `None` on
    purpose: every committed golden was generated with no `-sort` on the command
    line, and `Main.getSortBy:158-177` treats absent and `date` identically.
    """
    assert diff.JAR_SORT[tool.SORTS[sort]] == (None if sort == "date" else sort)


@needs_corpus
def test_every_recorded_message_is_staged_under_its_own_clock():
    """The names are the clock under `--sort name`, so they are asserted, not assumed.

    One input per role per round, and each name's last twenty characters parse
    back to that message's own `header.timestamp`. A name that did not parse
    would not fail: upstream catches the parse error and falls back to the mtime
    (`BatchProcessor.java:226-231`), so the run would quietly become a
    date-modified run against a 2023 base.
    """
    for entry in agencycorpus.manifest()["agencies"]:
        roles = agencycorpus.roles_of(entry)
        inputs = tool.inputs_for(entry)
        assert len(inputs) == len(roles) * len(entry["rounds"])
        for name, blob in inputs.items():
            stamp = agencycorpus.header_timestamp(blob)
            assert name.endswith(agencycorpus.staged_name("", 0, stamp)[4:]), name


@needs_both
def test_a_single_flipped_byte_is_reported_with_its_offset(tmp_path, monkeypatch):
    """The teeth. A harness that compares nothing agrees about everything.

    `tests/test_compat_differential.py` already proves `resultsdiff.compare`
    rejects a moved byte over committed bytes. This proves the rejection
    survives the whole path this module actually runs: real corpus, real jar,
    real staging, one byte changed on the way out of this project's side.
    """
    corrupted: dict[str, int] = {}
    real = diff.compat_side

    def flip_one_byte(inputs, gtfs, directory, sort_by):
        side = real(inputs, gtfs, directory, sort_by)
        name = max((held for held in side if side[held]), key=lambda held: len(side[held]))
        blob = bytearray(side[name])
        offset = len(blob) // 2
        blob[offset] ^= 0x20
        corrupted[name] = offset
        side[name] = bytes(blob)
        return side

    monkeypatch.setattr(diff, "compat_side", flip_one_byte)
    result = tool.run_one(tool.agency(SMALLEST), tmp_path, SortBy.NAME, ())

    assert corrupted, "the hook never ran, so nothing was corrupted and nothing was proved"
    [name] = list(corrupted)
    assert result.exit_code == 1
    assert [(one.name, one.kind) for one in result.report.divergences] == [(name, "bytes")]
    assert f"first difference at byte {corrupted[name]}" in result.report.divergences[0].detail


@needs_both
@pytest.mark.parametrize("mdb_id", READABLE)
def test_the_recorded_rounds_agree_byte_for_byte(mdb_id: str, tmp_path):
    """A red here is the deliverable. Never widen the comparison to pass it.

    Under `--sort name`, so each message is validated at the instant its own
    producer stamped it and both sides read that instant out of the same name.
    """
    result = tool.run_one(tool.agency(mdb_id), tmp_path, SortBy.NAME, ())
    assert result.report.divergences == [], result.render()
    assert result.messages == len(result.report.jars)
    assert all(blob for blob in result.report.jars.values()), (
        "the jar wrote no results for some input, so the agreement above is an "
        "agreement about nothing"
    )


@needs_both
def test_the_jar_cannot_read_the_mbta_archive_at_all(tmp_path):
    """The measured parity gap, pinned. Read the module docstring before touching it.

    `onebusaway-gtfs-1.3.87`'s `Area` declares `wkt` with no `@CsvField`, which
    csv-entities reads as required, and MBTA publishes the current spec's
    `area_id,area_name`. `GtfsReader.run` therefore throws before
    `BatchProcessor` reaches its file loop, and nothing in the validator lib
    reads `Area` at all, so upstream refuses an archive whose failure could not
    have changed a single occurrence.

    This project reads seven tables and never opens `areas.txt`, so it validates
    everything. Both halves are asserted: an implementation that started
    aborting on this archive would be the fix, and one that stopped writing
    results for another reason would not.
    """
    result = tool.run_one(tool.agency(MBTA), tmp_path, SortBy.NAME, ())
    kinds = {one.kind for one in result.report.divergences}
    assert kinds == {"jar-aborted", "only-ours"}
    aborted = next(one for one in result.report.divergences if one.kind == "jar-aborted")
    assert "missing required field: wkt" in aborted.detail
    assert "areas.txt" in aborted.detail
    assert all(blob is None for blob in result.report.jars.values())
    assert all(blob for blob in result.report.ours.values())
    assert len(result.report.ours) == result.messages == 18
