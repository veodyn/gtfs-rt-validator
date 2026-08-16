"""The committed goldens, re-derived from a real jar.

This is the expensive half of the set. `tests/test_jar_goldens.py` and
`tests/test_jar_output_contract.py` read committed bytes and run anywhere; this
module rebuilds those bytes from upstream's jar and skips cleanly when there is
none, because `jar-build/` and `*.jar` are gitignored and a clean checkout will
not have one.

    .venv/bin/python tools/build_jar.py

is what makes these run. The isolation checks below need no jar and always run:
they are the guard on a real trap, where a second run over a directory ingests
the first run's `.results.json` files as feeds.
"""

from __future__ import annotations

import subprocess

import pytest

from jarcorpus import CORPUS, fingerprint, import_tool
from jarcorpus import INPUTS as RECORDS

# The tools own the jar's location, the JDK lookup and the run protocol.
# Importing them keeps this module from restating any of it, the way
# test_schema_2015.py imports its generator rather than the jar coordinates.
jarenv = import_tool("jarenv")
run_jar = import_tool("run_jar")
FEEDS = import_tool("goldenfeeds").FEEDS


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

INPUTS = {feed.name: feed.blob for feed in FEEDS}


@pytest.fixture(scope="module")
def outcome():
    """One jar run for the whole module. It is the slowest thing in the suite."""
    return run_jar.run(INPUTS, jarenv.GOLDEN_GTFS)


def test_staging_refuses_a_results_file_as_an_input():
    """The trap, closed at the only door into a run directory.

    Filtering it out quietly would hide the caller's mistake, so `plan` raises.
    """
    with pytest.raises(ValueError, match="second-run trap"):
        run_jar.plan(["01-no-timestamps.pb", "01-no-timestamps.pb.results.json"])


def test_reading_the_committed_corpus_yields_inputs_only():
    """`read_corpus` walks a directory that holds goldens beside their inputs."""
    read = run_jar.read_corpus(CORPUS)
    assert set(read) == set(INPUTS)
    assert not any(name.endswith(".results.json") for name in read)
    assert "manifest.json" not in read


def _fake_jar(tmp_path, monkeypatch) -> None:
    """Enough of an environment for `invoke` to reach `subprocess.run`.

    No jar and no JDK are needed to test what happens around the call, and
    requiring either would make these two skip on exactly the machines where the
    bound matters most.
    """
    jar = tmp_path / "fake.jar"
    jar.write_bytes(b"")
    monkeypatch.setattr(run_jar, "JAR", jar)
    # `invoke` pins the JVM release and FORMAT locale through `checked_java_17`,
    # which needs a real JDK; these two tests are about what happens around the
    # call, so the pin is stood in for rather than satisfied.
    monkeypatch.setattr(run_jar, "checked_java_17", lambda: (tmp_path / "java", "17.0.19", "en-US"))


def test_a_jar_that_never_returns_is_killed_rather_than_waited_on(tmp_path, monkeypatch):
    """The spin is upstream's, so the bound has to be ours.

    `FrequencyTypeOneValidator` never leaves its loop for an `exact_times = 1`
    row with `headway_secs = 0` that a realtime entity names, measured with
    `jstack` in the output-contract reference. Without a timeout one such file
    in a corpus hangs the differential forever.

    Raising rather than sleeping: waiting out a real timeout to test the timeout
    would put `RUN_TIMEOUT` seconds into every suite run.
    """
    _fake_jar(tmp_path, monkeypatch)

    def never_returns(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", never_returns)
    with pytest.raises(RuntimeError, match="timed out"):
        run_jar.invoke(tmp_path, jarenv.GOLDEN_GTFS, timeout=0.25)


def test_every_invocation_carries_the_bound(tmp_path, monkeypatch):
    """A timeout the caller has to remember to pass is a timeout that goes missing."""
    _fake_jar(tmp_path, monkeypatch)
    seen: dict = {}

    def record_call(command, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", record_call)
    run_jar.invoke(tmp_path, jarenv.GOLDEN_GTFS)
    assert seen["timeout"] == run_jar.RUN_TIMEOUT
    assert run_jar.RUN_TIMEOUT > 0


def test_the_mtimes_a_run_stamps_are_the_ones_the_manifest_records():
    """Needs no jar: the stamping is ours, and it is what makes a run repeatable."""
    assert run_jar.plan(list(INPUTS)) == {entry["name"]: entry["mtime"] for entry in RECORDS}


@needs_jar
def test_the_jar_reproduces_every_golden_byte_for_byte(outcome):
    """A red diff here is the deliverable. Never widen the comparison to pass it."""
    for entry in RECORDS:
        if entry["results"] is None:
            continue
        golden = (CORPUS / entry["results"]).read_bytes()
        assert outcome.results[entry["name"]] == golden, entry["name"]


@needs_jar
def test_the_files_the_jar_skips_are_the_files_the_manifest_says_it_skips(outcome):
    assert set(outcome.skipped) == {entry["name"] for entry in RECORDS if entry["results"] is None}


@needs_jar
def test_the_run_leaves_the_committed_corpus_untouched():
    """The corpus is read into memory and never handed to the jar as a directory.

    Its own run rather than the module fixture's, so the snapshot is taken
    before the jar has been anywhere near the filesystem.
    """
    before = fingerprint(CORPUS)
    run_jar.run(INPUTS, jarenv.GOLDEN_GTFS)
    after = fingerprint(CORPUS)
    assert after == before
    assert not any(name.endswith(".results.json.results.json") for name in after)


@needs_jar
def test_two_runs_of_the_same_corpus_agree(outcome):
    """Byte identity across runs is what makes a golden a contract.

    Java `HashSet` iteration decides the order of W003's four occurrences, and
    if that order were not stable within a JVM version this would catch it.
    """
    again = run_jar.run(INPUTS, jarenv.GOLDEN_GTFS)
    assert again.results == outcome.results
    assert again.skipped == outcome.skipped


@needs_jar
def test_reusing_a_directory_makes_the_jar_ingest_its_own_output(tmp_path):
    """The trap itself, demonstrated rather than asserted from the Java.

    `BatchProcessor` walks every regular file with no extension filter
    (`:168`) and writes results beside their input (`:321`), so the second run
    reads the first run's JSON as if it were a protobuf. This is the reason
    `run_jar.run` stages into a throwaway directory every time.
    """
    run_jar.stage({name: INPUTS[name] for name in ["01-no-timestamps.pb"]}, tmp_path)
    first = run_jar.invoke(tmp_path, jarenv.GOLDEN_GTFS)
    assert "01-no-timestamps.pb.results.json" not in first
    assert (tmp_path / "01-no-timestamps.pb.results.json").exists()

    second = run_jar.invoke(tmp_path, jarenv.GOLDEN_GTFS)
    assert "Read 01-no-timestamps.pb.results.json to byte array" in second


@needs_jar
def test_the_golden_generator_would_write_the_committed_bytes():
    """Regenerating must be a no-op, the way it is for every other generated file."""
    gen_golden = import_tool("gen_golden")
    before = fingerprint(CORPUS)
    assert gen_golden.main() == 0
    assert fingerprint(CORPUS) == before
