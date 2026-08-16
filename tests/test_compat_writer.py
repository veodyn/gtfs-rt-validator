"""The compat writer, byte-compared against a real jar's output.

Every assertion here is ultimately about bytes. Upstream's `.results.json` is
Jackson's `DefaultPrettyPrinter` over a bean tree, so the indent, the `" : "`
separator, the `[ {` and `}, {` array form, the absent trailing newline and the
declaration order of four beans are all part of what has to match, and so is the
order the entries themselves come in.

The five committed goldens in `tests/fixtures/jar/` are the contract. They were
written by a jar built from the pinned commit under JDK 17, and
`tests/test_jar_goldens.py` pins their provenance. Here they are the expected
bytes of this project's own run over the same eight inputs, staged the same way;
`tests/compatstage.py` owns the staging and the conditions it fixes.

**A red diff here is the deliverable.** Nothing in this module may be widened to
make a comparison pass: if the bytes differ, either this project is wrong or the
golden is, and both are worth stopping for.
"""

from __future__ import annotations

import json
import os

import pytest

from clifixtures import workspace
from compatstage import GOLDEN_GTFS, compat_run, first_difference
from gtfs_rt_validator import api
from gtfs_rt_validator.report import compat, manifest
from gtfs_rt_validator.report.occurrence import NoticeContainer, Occurrence
from gtfs_rt_validator.rules._shared.javahash import iteration_order
from gtfs_rt_validator.runner import Mode
from jarcorpus import GOLDEN_NAMES, INPUTS, golden_bytes, parsed
from runnerfixtures import CLEAN_HEADER_TIMESTAMP, written_feed


@pytest.fixture(scope="module")
def staged(tmp_path_factory):
    """One compat run over the whole corpus, shared by the module."""
    return compat_run(tmp_path_factory.mktemp("compat-corpus"))


def occurrences_of(name: str) -> list[Occurrence]:
    """One golden read back as the occurrences that produced it, in file order."""
    return [
        Occurrence(entry["errorMessage"]["validationRule"]["errorId"], found["prefix"])
        for entry in parsed(name)
        for found in entry["occurrenceList"]
    ]


def container_of(occurrences: list[Occurrence]) -> NoticeContainer:
    container = NoticeContainer()
    container.add_all(occurrences)
    return container


# --- the goldens, byte for byte -------------------------------------------


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_every_committed_golden_is_reproduced_byte_for_byte(name, staged):
    """The whole contract in one assertion, five times over.

    A failure names the first differing byte rather than printing two files.
    Never relax this to a parsed comparison: the parse is what the formatting
    contract exists to survive.
    """
    ours = staged.results_for(name)
    jars = golden_bytes(name)
    assert ours is not None, f"nothing was written for {name}"
    assert ours == jars, first_difference(ours, jars)


def test_a_file_the_jar_skipped_gets_no_results_file_at_all(staged):
    """The absence is part of parity. An empty list for a skipped file would be
    this project claiming it validated something upstream never read."""
    skipped = [entry["name"] for entry in INPUTS if entry["results"] is None]
    assert skipped == ["05-duplicate-of-04.pb", "06-truncated.pb", "07-empty.pb"]
    for name in skipped:
        assert staged.results_for(name) is None
        assert not (staged.directory / f"{name}{compat.RESULTS_SUFFIX}").exists()


def test_the_run_wrote_one_file_per_validated_message_and_nothing_else(staged):
    """Upstream's `writeResults` is unconditional per validated file
    (`BatchProcessor.java:284`), so the count of output files is the count of
    messages that got past the decode and duplicate gates."""
    written = sorted(name for name in staged.written)
    assert written == sorted(f"{name}{compat.RESULTS_SUFFIX}" for name in GOLDEN_NAMES)


def test_the_run_validated_the_committed_archive_and_not_a_copy_of_it(staged):
    """The goldens were produced against `tests/fixtures/gtfs/testagency.zip`,
    so anything else here would be comparing against a feed the jar never saw.
    This used to assert instead that a two-cell patch had stayed two cells."""
    assert staged.gtfs.read_bytes() == GOLDEN_GTFS.read_bytes()


# --- what the writer puts in a file ----------------------------------------
#
# The layout itself is `tests/test_jackson_printer.py`, which asserts about the
# printer and about the goldens' own bytes. What is here is the bean tree this
# writer builds and hands it.


def test_w003_writes_an_empty_occurrence_suffix_rather_than_omitting_it(staged):
    """W003 is the only rule whose suffix is the empty string, and Jackson emits
    the key regardless."""
    blob = staged.results_for("04-combined-feed.pb")
    assert b'"errorId" : "W003"' in blob
    assert b'"occurrenceSuffix" : ""' in blob


def test_the_dead_fields_are_null_and_the_occurrence_id_is_zero(staged):
    """`messageId` is a boxed `Integer` nothing sets; `occurrenceId` is an
    unboxed `int`. The webapp's three models are null in a batch run."""
    entry = json.loads(staged.results_for("01-no-timestamps.pb"))[0]
    assert entry["errorMessage"]["messageId"] is None
    assert entry["errorMessage"]["gtfsRtFeedIterationModel"] is None
    assert entry["errorMessage"]["errorDetails"] is None
    assert entry["occurrenceList"][0] == {
        "occurrenceId": 0,
        "messageLogModel": None,
        "prefix": "trip_id 1.1",
    }


def test_the_four_bean_key_orders_are_the_ones_jackson_emits(staged):
    """Key order is part of the bytes, so it is asserted as order rather than as
    membership. Jackson emits bean properties in declaration order."""
    entry = json.loads(staged.results_for("01-no-timestamps.pb"))[0]
    assert list(entry) == ["errorMessage", "occurrenceList"]
    assert list(entry["errorMessage"]) == [
        "messageId",
        "gtfsRtFeedIterationModel",
        "validationRule",
        "errorDetails",
    ]
    assert list(entry["errorMessage"]["validationRule"]) == [
        "errorId",
        "severity",
        "title",
        "errorDescription",
        "occurrenceSuffix",
    ]
    assert list(entry["occurrenceList"][0]) == ["occurrenceId", "messageLogModel", "prefix"]


def test_the_five_rule_strings_are_the_manifests_own(staged):
    """Not hardcoded here and not hardcoded there: the writer reads the packed
    manifest, which is generated from the same commit the jar was built from."""
    rule = json.loads(staged.results_for("01-no-timestamps.pb"))[0]["errorMessage"][
        "validationRule"
    ]
    packed = manifest.rule("W002")
    assert rule["severity"] == packed.severity
    assert rule["title"] == packed.title
    assert rule["errorDescription"] == packed.error_description
    assert rule["occurrenceSuffix"] == packed.occurrence_suffix


# --- the ordering contract -------------------------------------------------


def test_the_output_order_is_every_batch_reachable_rule_exactly_once():
    """Registration order across validators, `errors.add` order within one. The
    56 that `BatchProcessor` can reach, and no id twice."""
    order = compat.output_order()
    assert sorted(order) == sorted(manifest.batch_reachable_ids())
    assert len(order) == len(set(order)) == 56
    assert order[:2] == ("W003", "E047")
    grouped = [rule_id for ids in manifest.group_order().values() for rule_id in ids]
    assert list(order) == grouped


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_a_permuted_run_produces_the_golden_order_anyway(name):
    """The ordering contract, isolated from the run that produced it.

    The occurrences go in reversed, so the entry order the writer emits cannot
    have come from the order it was handed. Occurrences *within* a rule keep the
    order they arrived in, so they are reversed back before the comparison: that
    half is the walk's, and the writer may not sort it either.
    """
    found = occurrences_of(name)
    scrambled = list(reversed(found))
    per_rule: dict[str, list[Occurrence]] = {}
    for occurrence in scrambled:
        per_rule.setdefault(occurrence.rule_id, []).insert(0, occurrence)
    container = container_of([one for group in per_rule.values() for one in group])
    assert compat.dumps(container).encode("utf-8") == golden_bytes(name)


def test_occurrences_within_a_rule_are_neither_sorted_nor_deduplicated():
    """Upstream's `addOccurrence` does neither, so two identical prefixes report
    twice and a descending pair stays descending."""
    prefixes = ["trip_id z", "trip_id a", "trip_id z"]
    container = container_of([Occurrence("E041", prefix) for prefix in prefixes])
    entries = compat.entries(container)
    assert [one["prefix"] for one in entries[0]["occurrenceList"]] == prefixes


def test_java_hash_iteration_order_reaches_the_written_bytes():
    """W003's occurrence order is a `HashMap`'s, reproduced in `javahash.py`.

    The writer's whole job here is not to touch it, so the check is that an
    order which is neither the insertion order nor a sorted one survives.
    """
    ids = ["v10", "v2", "v33", "v4", "v5"]
    ordered = iteration_order(ids)
    assert list(ordered) != ids
    assert list(ordered) != sorted(ids)
    container = container_of([Occurrence("W003", f"vehicle_id {one}") for one in ordered])
    written = [one["prefix"] for one in compat.entries(container)[0]["occurrenceList"]]
    assert written == [f"vehicle_id {one}" for one in ordered]


def test_an_id_the_compat_order_does_not_carry_is_refused():
    """A modern container handed to this writer would silently lose its `S` and
    `P` rules, and E010, which `BatchProcessor` cannot reach. It raises instead."""
    container = container_of([Occurrence("S001", "trip_id 1.1")])
    with pytest.raises(ValueError, match="S001"):
        compat.dumps(container)


# --- the entry point -------------------------------------------------------


def test_a_validated_message_with_no_findings_writes_an_empty_list(tmp_path):
    """`writeResults` is unconditional, and Jackson writes an empty list as
    `[ ]`. A clean feed produces a file, unlike a skipped one.

    The mtime is the header's own timestamp because that is the compat clock: a
    feed is only clean against a run that happened when it was published.
    """
    space = workspace(tmp_path)
    path = written_feed(tmp_path, "clean.pb", "a")
    os.utime(path, (CLEAN_HEADER_TIMESTAMP, CLEAN_HEADER_TIMESTAMP))
    writer = compat.ResultsWriter()
    request = api.Request(mode=Mode.COMPAT, gtfs=space.gtfs, inputs=api.resolve(str(path)))

    api.validate(request, sink=writer)

    assert writer.written == [tmp_path / f"clean.pb{compat.RESULTS_SUFFIX}"]
    assert writer.written[0].read_bytes() == b"[ ]"


def test_the_results_file_is_the_input_path_with_the_suffix_appended(tmp_path):
    """Whatever the extension, and beside the input rather than under an output
    directory: upstream writes `path.toAbsolutePath() + ".results.json"`."""
    (tmp_path / "feed.bin").write_bytes(b"")
    source = api.resolve(str(tmp_path / "feed.bin")).cycles[0][0]
    assert compat.results_path(source) == tmp_path / f"feed.bin{compat.RESULTS_SUFFIX}"


def test_a_compat_result_has_no_directory_shaped_write(tmp_path):
    """The unit of work is the message, not the run, so there is nothing left to
    write when the run ends. `Result.write` says so rather than inventing a
    directory layout upstream has no counterpart for."""
    space = workspace(tmp_path)
    result = api.validate(
        api.Request(mode=Mode.COMPAT, gtfs=space.gtfs, inputs=api.resolve(str(space.rt)))
    )
    with pytest.raises(api.UsageError, match="beside each input"):
        result.write(space.out)
