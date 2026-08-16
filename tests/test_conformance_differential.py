"""Tier 1: this project's `--compat` output against the jar's, group by group.

`tests/test_compat_writer.py` compares against the eight output-contract
goldens. This is the wider comparison: 32 crafted inputs over three static
archives, aimed at making every one of the 56 batch-reachable rules fire, and
compared **byte for byte** including the absence of a file for an input the jar
skipped.

**Never weaken a comparison to make it pass.** A red diff is the deliverable.
There is no normalisation here, no whitespace tolerance, no substring match, no
file skipped for being awkward and no `except` that turns a mismatch into a
pass. The comparison itself is `tools/resultsdiff.py`'s, so this module cannot
soften it even by accident.

The checks that read committed bytes run anywhere. The two that run the jar skip
when there is none, because `jar-build/` and `*.jar` are gitignored and a clean
checkout will not have one:

    .venv/bin/python tools/build_jar.py

A skip here is not a pass, and the structural checks below are what keep it from
reading like one: they assert on the committed goldens the jar already wrote, so
a corpus that stopped exercising hash order, or the file loop, or both shapes
modes, fails on a machine with no JDK at all.
"""

from __future__ import annotations

import json

import pytest

import conformancecorpus as corpus
from conformancecorpus import GROUPS, MANIFEST, group_names, records
from jarcorpus import ROOT, digest, import_tool

jarenv = import_tool("jarenv")
run_jar = import_tool("run_jar")
resultsdiff = import_tool("resultsdiff")
conformancefeeds = import_tool("conformancefeeds")
conformancerun = import_tool("conformancerun")

#: The committed size budget for the whole tier 1 corpus.
SIZE_BUDGET = 5 * 1024 * 1024


def _unavailable() -> str:
    """Why the jar cannot be run here, or the empty string if it can.

    The same environment pin `tools/diff_compat_against_jar.py` applies, and for
    the same two measured reasons: `Float.toString` changed in JDK 19, and
    `String.format("%.2f", ...)` in `VehicleValidator` reads
    `Locale.Category.FORMAT`, which `-Duser.language.format` moves on its own.
    Checking only that a JDK 17 is *installed* leaves this comparison willing to
    run under a JVM whose floats and decimal separators are not the goldens'.
    """
    if not jarenv.jar_present():
        return f"no jar at {jarenv.JAR}; run .venv/bin/python tools/build_jar.py"
    try:
        jarenv.checked_java_17()
    except (jarenv.NoJdk17Error, jarenv.WrongLocaleError) as exc:
        return str(exc)
    return ""


REASON = _unavailable()
needs_jar = pytest.mark.skipif(bool(REASON), reason=REASON or "a jar is present")


def test_the_corpus_is_pinned_to_the_sha_the_rest_of_the_project_is():
    pins = json.loads((ROOT / "upstream" / "pins.json").read_text(encoding="utf-8"))
    assert MANIFEST["pin"] == pins["gtfs_realtime_validator"]["commit"]
    assert MANIFEST["generated_by"] == "tools/gen_golden.py --conformance"
    assert MANIFEST["mtime_base"] == run_jar.MTIME_BASE


def test_every_committed_file_has_the_bytes_and_the_mtime_the_manifest_records():
    """Both halves, because upstream reads the mtime as the clock and the sort
    key, so a corpus whose order moved is a different input."""
    for name in group_names():
        planned = run_jar.plan([record["name"] for record in corpus.group(name)["inputs"]])
        for record in corpus.group(name)["inputs"]:
            path = corpus.directory(name) / record["name"]
            assert digest(path.read_bytes()) == record["sha256"], f"{name}/{record['name']}"
            assert planned[record["name"]] == record["mtime"], f"{name}/{record['name']}"


def test_every_committed_golden_has_the_bytes_the_manifest_records():
    for name in group_names():
        for record in corpus.group(name)["inputs"]:
            if record["results"] is None:
                continue
            blob = (corpus.directory(name) / record["results"]).read_bytes()
            assert digest(blob) == record["results_sha256"], f"{name}/{record['name']}"


def test_the_directories_hold_nothing_the_manifest_does_not_list():
    """A stale golden left behind by a renamed feed would never be compared."""
    assert {path.name for path in corpus.CORPUS.iterdir() if path.is_dir()} == set(group_names())
    for name in group_names():
        listed = set()
        for record in corpus.group(name)["inputs"]:
            listed.add(record["name"])
            if record["results"]:
                listed.add(record["results"])
        assert {path.name for path in corpus.directory(name).iterdir()} == listed, name


def test_the_static_archives_the_corpus_was_produced_against_are_committed():
    """Without them the goldens could be read but never regenerated."""
    for section in GROUPS:
        assert digest(corpus.archive(section["name"]).read_bytes()) == section["gtfs_sha256"]
    assert set(MANIFEST["archives"]) == {section["gtfs"] for section in GROUPS}


def test_the_committed_feeds_are_the_ones_the_generator_builds():
    """The generator is the corpus's source. A `.pb` edited on disk, or a feed
    added without regenerating, would otherwise compare green against a golden
    that was never produced from it."""
    built = {
        group.name: [(feed.name, feed.why, digest(feed.blob), feed.skip) for feed in group.feeds]
        for group in conformancefeeds.GROUPS
    }
    committed = {
        section["name"]: [
            (record["name"], record["why"], record["sha256"], record["skip"])
            for record in section["inputs"]
        ]
        for section in GROUPS
    }
    assert committed == built


def test_the_files_the_jar_skipped_have_no_golden_committed():
    """Upstream writes nothing at all for a file it skips, and an empty results
    file is a different claim: it means the jar read the feed and found nothing."""
    for name, record in records():
        path = corpus.directory(name) / (record["name"] + corpus.RESULTS_SUFFIX)
        assert path.exists() == (record["skip"] is None), f"{name}/{record['name']}"


def test_the_corpus_fits_the_budget():
    assert corpus.total_bytes() <= SIZE_BUDGET, f"{corpus.total_bytes()} bytes"


def test_the_sequence_interleaves_dedupe_skips_with_decode_failures():
    """The structural property a single feed cannot have. Cross-file state
    survives a skip, and `15-after-skips.pb` firing E017 against the header
    timestamp of `11-out-of-range-times.pb` is the proof: three files were
    skipped between them and `prevMessage` was still the eleventh."""
    inputs = corpus.group("bullrunner")["inputs"]
    skips = [record["skip"] for record in inputs if record["skip"]]
    assert skips.count("duplicate") == 2
    assert skips.count("decode") == 2
    after = next(record for record in inputs if record["name"] == "15-after-skips.pb")
    assert after["rules"] == ["E017"]
    assert [record["name"] for record in inputs[11:14]] == [
        "12-duplicate-of-11.pb",
        "13-truncated.pb",
        "14-empty-file.pb",
    ]


def test_both_shapes_modes_are_recorded_over_the_same_geometry():
    """E028 reads the buffered `shapes.txt` coverage area by default and falls
    back to the `stops.txt` bounds under `-ignoreShapes`, and E029 is not
    evaluated at all in the second mode. Both strings are in the goldens, so a
    writer that hard-coded either would fail."""
    with_shapes = corpus.goldens("bullrunner")["19-outside-coverage.pb"]
    without = corpus.goldens("bullrunner-ignoring-shapes")["01-outside-coverage.pb"]
    assert with_shapes is not None and without is not None
    assert b"shapes.txt coverage area" in with_shapes
    assert b"stops.txt coverage area" in without
    assert corpus.group("bullrunner-ignoring-shapes")["ignore_shapes"] is True
    assert corpus.group("bullrunner")["ignore_shapes"] is False
    off_shape = corpus.goldens("bullrunner-ignoring-shapes")["02-off-shape.pb"]
    assert off_shape == b"[ ]", "E029 must not be evaluated when shapes are ignored"


def test_no_rule_in_the_corpus_comes_near_this_project_s_retention_cap():
    """The cap is 100,000 occurrences per rule, it is this project's rather than
    upstream's, and the jar has none. A golden that exceeded it would be a real
    divergence; a golden anywhere near it would be several megabytes, which the
    5 MB budget above forbids. So the cap is a recorded divergence rather than
    an exercised one, and this asserts the corpus is nowhere near it."""
    from gtfs_rt_validator.report.occurrence import MAX_OCCURRENCES_PER_RULE

    for name in group_names():
        for rule_id, count in corpus.occurrence_counts(name).items():
            assert count < MAX_OCCURRENCES_PER_RULE, f"{name} {rule_id}"


@needs_jar
@pytest.mark.parametrize("name", group_names())
def test_this_project_reproduces_the_jar_byte_for_byte(name, tmp_path):
    """One group, staged twice with the same names and the same mtimes."""
    section = corpus.group(name)
    inputs = corpus.inputs(name)
    gtfs = conformancerun.archive(conformancefeeds.group(name))

    jar_directory, our_directory = tmp_path / "jar", tmp_path / "ours"
    jar_directory.mkdir()
    our_directory.mkdir()
    jars = conformancerun.jar_side(
        inputs, gtfs, jar_directory, ignore_shapes=section["ignore_shapes"]
    )
    ours = conformancerun.compat_side(
        inputs, gtfs, our_directory, ignore_shapes=section["ignore_shapes"]
    )

    divergences = resultsdiff.compare(ours, jars)
    assert divergences == [], "\n".join(each.render() for each in divergences)


@needs_jar
@pytest.mark.parametrize("name", group_names())
def test_the_committed_goldens_are_what_the_jar_writes_today(name, tmp_path):
    """The recording against the jar itself. A committed golden cannot notice
    that the jar was rebuilt, that the JDK moved, or that a feed was edited."""
    section = corpus.group(name)
    gtfs = conformancerun.archive(conformancefeeds.group(name))
    directory = tmp_path / "run"
    directory.mkdir()

    produced = conformancerun.jar_side(
        corpus.inputs(name), gtfs, directory, ignore_shapes=section["ignore_shapes"]
    )

    assert produced == corpus.goldens(name)
