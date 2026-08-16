"""The recorded agency corpus, compared against the jar's committed goldens.

`tests/test_agency_differential.py` runs the same corpus against a *running*
jar. That is the stronger check and this does not replace it: it re-derives the
jar's side from the artefact itself, so it notices a rebuilt jar, a moved JDK and
a changed locale, none of which a recording can. What it cannot do is run in a
checkout, because it needs a built jar and a JDK 17 as well as the recorded
bytes. **Neither module is redundant. Do not delete one for duplicating the
other.** This one is what a machine with no JVM gets.

**What is committed is a digest and a census, not the jar's bytes.**
`tools/agencygoldens.py` explains why: MBTA alone is 3.5 MB of `.results.json`
per sort regime, against 56 KB of committed goldens for the entire crafted
corpus, and `corpus/` was gitignored to keep this repository small in the first
place. The SHA-256 makes the check exact; the rule census makes a failure
readable, because the common failure is that a rule started or stopped firing
and a bare digest reports that as sixty-four different hex characters.

**Ten regimes.** Four agencies under `--sort name` and `--sort date`, plus
MBTA's two `--drop-static-file areas.txt` runs. Those two are a diagnostic and
say so in every record, and they exist because the jar refuses MBTA's archive
outright: without them the corpus's largest agency would pin no jar output at
all, and 13,177 occurrences under the file-name clock and 22,169 under the
date-modified one would go unchecked in a checkout.

**The refusal is a recorded outcome, not an absence.** `jar_refusal` names the
exception, the file, the line and the missing field, so a jar or an archive that
one day reads `areas.txt` regenerates into something visibly different rather
than quietly filling in eighteen files that looked merely missing.

**Skips loudly.** `corpus/` is gitignored, so a fresh checkout cannot recompute
this project's side. `-ra` in `addopts` prints the reason, the convention
`test_agency_tier_counts.py` and `test_manifest_drift.py` already follow.
Everything that can be asserted about the committed file without the bytes is
asserted above the recount rather than skipped with it.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from agencygolden import (
    GOLDEN,
    IDS,
    MBTA,
    ROOT,
    RUNS,
    OurSides,
    agencycorpus,
    agencygoldens,
    jarenv,
    no_corpus,
    run_id,
    tool,
)

#: Every rule id this project can report, as a shape. The census keys are the
#: only feed-derived strings in the whole file, so what they may look like is
#: asserted rather than assumed.
RULE_ID = re.compile(r"^[EWSP]\d{3}$")

NO_CORPUS = no_corpus()
needs_corpus = pytest.mark.skipif(bool(NO_CORPUS), reason=NO_CORPUS or "the corpus is here")


@pytest.fixture(scope="session")
def ours(tmp_path_factory) -> OurSides:
    """This project's `--compat` output by regime name, with no jar and no JDK.

    Session scoped so each regime is staged once for the whole module, and lazy
    so a `-k` filtered run stages only the regimes it names. `OurSides` says
    why both matter.
    """
    if NO_CORPUS:
        pytest.skip(NO_CORPUS)
    return OurSides(tmp_path_factory)


def test_the_golden_says_how_it_was_made():
    """A generated file names its generator, or the next reader hand-edits it."""
    assert GOLDEN["generated_by"] == "tools/gen_agency_goldens.py"
    assert "tools/gen_agency_goldens.py" in GOLDEN["do_not_edit"]
    assert GOLDEN["what_this_is"]


def test_the_golden_is_pinned_to_the_jar_and_jdk_the_rest_of_the_project_is():
    """A golden from a different jar than the project pins proves nothing.

    The JDK is pinned for the same reason `tools/jarenv.py` refuses anything but
    17: `Float.toString` was rewritten in JDK 19 (JDK-4511638), so E026, E027,
    E028, E029 and W004 render differently there. The FORMAT locale is pinned
    because `VehicleValidator` calls `String.format("%.2f", ...)` with no
    `Locale`.
    """
    pins = json.loads((ROOT / "upstream" / "pins.json").read_text(encoding="utf-8"))
    assert GOLDEN["jar"]["pin"] == pins["gtfs_realtime_validator"]["commit"]
    assert GOLDEN["jar"]["sha256"], "a golden that cannot name the jar it came from"
    assert GOLDEN["jdk"]["java_version"].startswith("17.")
    assert GOLDEN["jdk"]["format_locale"] == jarenv.GOLDEN_LOCALE


def test_the_golden_pins_the_corpus_it_was_taken_over():
    """Different bytes under the same provenance is worse than no golden at all.

    The manifest holds every recorded file's SHA-256 and `agencycorpus` verifies
    each one before staging it, so pinning the manifest pins the corpus. Runs
    without the corpus, which is the point: a manifest re-recorded and committed
    without regenerating this file fails here rather than as a mysterious red
    diff in a rule nobody touched.
    """
    committed = agencygoldens.digest(agencycorpus.MANIFEST.read_bytes())
    assert GOLDEN["corpus"]["manifest_sha256"] == committed, (
        "tests/fixtures/agencies/manifest.json has moved since this golden was taken. "
        "Re-record deliberately, then .venv/bin/python tools/gen_agency_goldens.py"
    )
    assert GOLDEN["corpus"]["recorded_at"] == agencycorpus.manifest()["recorded_at"]


def test_every_agency_is_covered_in_both_sort_regimes():
    """Both clocks, because they are different runs and only one had been compared.

    `--sort name` reads each message's own `header.timestamp` out of its file
    name (`BatchProcessor.java:220-232`); `--sort date` reads the mtime, which
    `run_jar.plan` stamps from a fixed 2023 base, so a 2026 recording is
    uniformly in the future and E050 fires on most of the feed.
    """
    expected = {
        (entry["static_mdb_id"], sort)
        for entry in agencycorpus.manifest()["agencies"]
        for sort in sorted(tool.SORTS)
    }
    covered = {(run["static_mdb_id"], run["sort"]) for run in RUNS if not run["diagnostic"]}
    assert covered == expected
    assert len(IDS) == len(set(IDS)), "two runs share an id, so one of them is unreachable"


def test_the_golden_carries_no_feed_content():
    """A digest, a length, a count and rule ids. No trip id, no stop, no coordinate.

    This is the property that made committing a golden for a real production
    feed acceptable at all, so it is asserted on the file rather than promised
    in a docstring. A future record that carried occurrence text would fail here
    before anybody had to notice it in a diff.
    """
    for run in RUNS:
        for name, held in run["inputs"].items():
            if held is None:
                continue
            assert tuple(held) == agencygoldens.RECORD_KEYS, f"{run_id(run)} {name}"
            assert isinstance(held["sha256"], str)
            assert len(held["sha256"]) == 64
            for rule_id, count in held["census"].items():
                assert RULE_ID.match(rule_id), f"{run_id(run)} {name}: {rule_id!r}"
                assert isinstance(count, int)


def test_no_run_pins_nothing():
    """A golden that recorded an empty run would agree with everything forever.

    Every regime the jar validated has a results file for every message and a
    nonzero occurrence total; the two it refused have neither, and say so.
    """
    for run in RUNS:
        assert len(run["inputs"]) == run["messages"] > 0, run_id(run)
        if run["jar_outcome"] == "validated":
            assert run["jar_results_files"] == run["messages"], run_id(run)
            assert run["jar_occurrences"] > 0, run_id(run)
        else:
            assert run["jar_results_files"] == 0
            assert run["jar_occurrences"] == 0


def test_the_mbta_refusal_is_a_recorded_outcome_and_not_an_absence():
    """The most interesting fact in the corpus, and the one easiest to lose.

    `onebusaway-gtfs-1.3.87`'s `Area` declares `wkt` with no `@CsvField`, which
    csv-entities reads as required, and MBTA publishes the current spec's
    `area_id,area_name`. `GtfsReader.run` throws before `BatchProcessor` reaches
    its file loop and `Main.main:62` does not catch it, so the JVM exits 1
    having written nothing for any of the eighteen inputs.

    Recorded as an outcome so that a jar or an archive that *does* read the file
    regenerates into something visibly different. Eighteen nulls alone would
    read as "the jar happened to write nothing", which is the shape of a harness
    bug rather than of a refusal.
    """
    refused = [run for run in RUNS if run["static_mdb_id"] == MBTA and not run["diagnostic"]]
    assert len(refused) == len(tool.SORTS)
    for run in refused:
        refusal = run["jar_refusal"]
        assert run["jar_outcome"] == "refused-the-archive"
        assert refusal["exit_code"] == 1
        assert refusal["path"] == "areas.txt"
        assert refusal["missing_field"] == "wkt"
        assert refusal["entity_type"] == "org.onebusaway.gtfs.model.Area"
        assert refusal["caused_by"].endswith("MissingRequiredFieldException")
        assert "at edu.usf.cutr.gtfsrtvalidator.lib.Main.main(Main.java:62)" in refusal["frames"]
        assert all(blob is None for blob in run["inputs"].values())
        # The parity gap itself: this project validates all eighteen anyway.
        assert [one["kind"] for one in run["expected_divergences"]] == ["only-ours"] * 18


def test_the_diagnostic_runs_are_labelled_and_are_the_only_mbta_jar_bytes():
    """A diagnostic must never be read as a parity result, and says so per record.

    They earn their place regardless: they are the only thing in this file that
    pins what the jar writes over MBTA's six-thousand-entity surface, which the
    refusal above otherwise hides entirely.
    """
    diagnostics = [run for run in RUNS if run["diagnostic"]]
    assert {run["static_mdb_id"] for run in diagnostics} == {MBTA}
    assert len(diagnostics) == len(tool.SORTS)
    for run in diagnostics:
        assert run["dropped_static_files"] == ["areas.txt"]
        assert "not a parity result" in run["diagnostic_note"]
        assert run["jar_outcome"] == "validated"
    assert sum(run["jar_occurrences"] for run in diagnostics) > 0
    for run in RUNS:
        if not run["diagnostic"]:
            assert run["diagnostic_note"] is None


@needs_corpus
@pytest.mark.parametrize("run", RUNS, ids=IDS)
def test_recomputing_our_side_reproduces_the_committed_golden(run: dict[str, Any], ours: OurSides):
    """The ratchet, and the whole reason this file exists.

    A red here is not a flake and is never fixed by regenerating: it means this
    project's `--compat` output stopped matching what upstream's jar wrote for a
    real agency's feed. Read the census in the message, decide which side is
    right (under `--compat` the answer is almost always the jar), and only then
    re-run `.venv/bin/python tools/gen_agency_goldens.py` against a real jar.

    The expected divergences are compared as a list rather than asserted empty,
    because MBTA's two parity runs legitimately have eighteen of them. Comparing
    the list means the gap closing goes red here too, which is the correct
    outcome: it wants inverting, not deleting.
    """
    divergences = agencygoldens.compare(ours(run_id(run)), run["inputs"])
    found = [{"name": one.name, "kind": one.kind} for one in divergences]
    assert found == run["expected_divergences"], (
        f"{run_id(run)} no longer agrees with the jar's committed golden\n"
        + "\n".join(one.render() for one in divergences)
    )


@needs_corpus
def test_our_mbta_output_does_not_depend_on_areas_txt(ours: OurSides):
    """What makes the diagnostic run evidence about the parity run as well.

    The jar refuses MBTA's archive over `areas.txt`, so the golden holds no jar
    bytes for the parity regimes and the check there can only be "we still write
    eighteen files". It is stronger than that because this project's compat
    static loader reads seven tables and never opens `areas.txt`: the bytes it
    produces with the entry dropped are the bytes it produces with it present,
    and those *are* pinned against real jar output. Asserted rather than
    reasoned, because the day the loader learns to read `areas.txt` this
    equality is the first thing that breaks.
    """
    for sort in sorted(tool.SORTS):
        parity = f"{MBTA} --sort {sort}"
        assert ours(parity) == ours(f"{parity} --drop-static-file areas.txt"), (
            f"under --sort {sort} this project's MBTA output now depends on areas.txt, so the "
            "diagnostic run no longer stands in for the parity run it cannot pin"
        )
