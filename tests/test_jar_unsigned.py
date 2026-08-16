"""`unsignedpins.PINS`, re-derived from a real jar rather than transcribed.

The expensive half of the unsigned-integer set, next to
`tests/test_unsigned_prefixes.py` the way `test_jar_differential.py` sits next to
`test_jar_goldens.py`. It skips cleanly with no jar, because `jar-build/` and
`*.jar` are gitignored:

    .venv/bin/python tools/build_jar.py

Without this module the pins would be a claim about Java that nothing checks. A
Python-side rendering can always be made to agree with a wrong expectation, and
the only thing that cannot is upstream's own output.

The static feed is built here rather than taken from `tests/fixtures/gtfs/`, for
the reason `unsignedfeeds.static_feed` gives: the committed `testagency.zip`
loads in the jar and not in this project, so no differential can stand on it.
"""

from __future__ import annotations

import json

import pytest

from jarcorpus import import_tool
from unsignedfeeds import FEEDS, static_feed
from unsignedpins import PINS, expected

jarenv = import_tool("jarenv")
run_jar = import_tool("run_jar")


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


@pytest.fixture(scope="module")
def wrote(tmp_path_factory) -> dict[str, list[tuple[str, str]]]:
    """Feed name to the sorted `(rule_id, prefix)` pairs the jar wrote for it.

    One jar invocation for the whole module. The feeds are handed over in
    `FEEDS` order, which `run_jar.stage` turns into mtimes one second apart, so
    the previous-message chain E012, E017, E018 and W007 depend on runs as this
    fixture is written.
    """
    root = tmp_path_factory.mktemp("jar-unsigned")
    outcome = run_jar.run(FEEDS, static_feed(root))
    assert not outcome.skipped, outcome.summary()
    return {name: _pairs(blob) for name, blob in outcome.results.items()}


def _pairs(blob: bytes) -> list[tuple[str, str]]:
    """One `.results.json` as the sorted `(rule_id, prefix)` pairs it reports."""
    return sorted(
        (row["errorMessage"]["validationRule"]["errorId"], occurrence["prefix"])
        for row in json.loads(blob)
        for occurrence in row["occurrenceList"]
    )


@needs_jar
@pytest.mark.parametrize("name", list(FEEDS))
def test_the_jar_writes_the_pinned_output(name, wrote) -> None:
    """A red diff here means the pin is stale, not that the jar is wrong. Never
    edit the expectation to make it pass: re-measure, then fix the renderer."""
    assert wrote[name] == expected(name)


@needs_jar
def test_the_pins_exhibit_the_signed_narrowing_they_exist_for(wrote) -> None:
    """The point of the corpus, asserted about the corpus itself.

    A feed set that had drifted into carrying no negative at all would still
    satisfy every equality above while proving nothing, so each of the four
    fields is checked to have reached at least one prefix as a negative.
    """
    printed = {prefix for pins in PINS.values() for _rule, prefix in pins}
    assert any("stop_sequence -1" in prefix for prefix in printed)
    assert any("stop_sequence [-1, -1]" in prefix for prefix in printed)
    assert any("direction_id is -1" in prefix for prefix in printed)
    assert any("timestamp -1" in prefix for prefix in printed)
    assert any("header.timestamp of -2" in prefix for prefix in printed)
    assert any("active_period.start -1" in prefix for prefix in printed)


@needs_jar
def test_the_jar_reads_the_feed_this_project_reads(wrote) -> None:
    """`static_feed` has to load in both, or the two runs are not comparable.

    The jar loading it is what this asserts; `tests/test_unsigned_prefixes.py`
    producing any occurrence at all is what asserts the other half.
    """
    assert set(wrote) == set(FEEDS)
    assert all(pairs for pairs in wrote.values())
