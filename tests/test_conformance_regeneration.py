"""Regenerating the tier 1 corpus is a no-op, checked without regenerating it.

`tools/gen_golden.py --conformance` is the corpus's source, so the committed
bytes have to be exactly what it writes today: a `.pb` edited on disk, or a feed
added without regenerating, would otherwise compare green against a golden that
was never produced from it. This is also the only check that covers the manifest
itself.

**The regeneration never runs over `tests/fixtures/`.** `conformance_main`
overwrites every input and golden, unlinks files no feed claims, deletes whole
group directories and rewrites the manifest. Aimed at the committed corpus it
would make the fixtures the thing under test rather than the thing being
checked, and a run that differed, or that failed partway, would leave the
working tree modified with the bytes it was meant to be compared against
already gone. `--out` exists for that reason and both checks below use it.

Split out of `tests/test_conformance_differential.py`, which is the byte
comparison against the jar; this is the comparison against the generator.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

import conformancecorpus as corpus
from jarcorpus import digest, import_tool

jarenv = import_tool("jarenv")
conformancefeeds = import_tool("conformancefeeds")


def _unavailable() -> str:
    """Why the jar cannot be run here, or the empty string if it can."""
    if not jarenv.jar_present():
        return f"no jar at {jarenv.JAR}; run .venv/bin/python tools/build_jar.py"
    try:
        jarenv.checked_java_17()
    except (jarenv.NoJdk17Error, jarenv.WrongLocaleError) as exc:
        return str(exc)
    return ""


REASON = _unavailable()
needs_jar = pytest.mark.skipif(bool(REASON), reason=REASON or "a jar is present")


def _fingerprint(root: Path) -> dict[str, str]:
    """Every file under a corpus tree, by relative path, with its digest."""
    return {
        path.relative_to(root).as_posix(): digest(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@needs_jar
def test_regenerating_the_corpus_would_write_the_committed_bytes(tmp_path):
    """Regenerating must be a no-op, the way it is for every other generated
    file here. It is also the only check that covers the manifest itself.

    The regeneration runs into `tmp_path`, never over `tests/fixtures/`.
    `conformance_main` overwrites every input and golden, unlinks files no feed
    claims, deletes whole group directories and rewrites the manifest, so
    pointing it at the committed corpus would make the fixtures the thing under
    test: a run that differed, or that failed partway, would leave the working
    tree modified and the bytes it was meant to be compared against already
    gone. Two trees compared say the same thing and risk nothing.
    """
    gen_golden = import_tool("gen_golden")
    destination = tmp_path / "conformance"
    before = _fingerprint(corpus.CORPUS)

    assert gen_golden.main(["--conformance", "--out", str(destination)]) == 0

    assert _fingerprint(destination) == before
    assert _fingerprint(corpus.CORPUS) == before, "the committed corpus was written to"


@needs_jar
def test_a_regeneration_that_differs_goes_red_and_leaves_the_fixtures_alone(tmp_path, monkeypatch):
    """The teeth of the check above, and the demonstration of why it writes elsewhere.

    One group is regenerated from a deliberately shortened feed list, which is
    what a corpus edit that changed the output looks like. Three things have to
    hold at once: the run writes a corpus, that corpus does not match the
    committed one, and the committed one comes through untouched.

    The seeded `ghost/` directory is the rest of the demonstration. A group the
    current `GROUPS` does not name is deleted outright, so this same run aimed
    at `tests/fixtures/conformance/` would have removed three of the four
    committed groups before anything was compared.
    """
    gen_golden = import_tool("gen_golden")
    shortened = dataclasses.replace(
        conformancefeeds.group("timepoints"), feeds=conformancefeeds.group("timepoints").feeds[:1]
    )
    monkeypatch.setattr(gen_golden, "GROUPS", (shortened,))
    destination = tmp_path / "conformance"
    (destination / "ghost").mkdir(parents=True)
    (destination / "ghost" / "01-stale.pb").write_bytes(b"")
    before = _fingerprint(corpus.CORPUS)

    assert gen_golden.main(["--conformance", "--out", str(destination)]) == 0

    assert (destination / "timepoints" / shortened.feeds[0].name).exists()
    assert not (destination / "ghost").exists(), "a group nothing claims survived regeneration"
    assert _fingerprint(destination) != before
    assert _fingerprint(corpus.CORPUS) == before
