"""The notices array of modern `out/report.json`.

Five things are pinned here, each a requirement the writer would otherwise be
free to get wrong in a way nothing else notices. The summary block and the bytes
on disk are `tests/test_modern_output.py`; what order any of it comes out in is
`tests/test_modern_determinism.py`, and where a non-upstream rule's severity
comes from is `tests/test_declared_severity.py`.

1. **Severity is looked up, never written.** Not a literal, and not inferred
   from the id's first letter. `tests/test_packed_manifest.py` already fails the
   build on a severity literal under `src/`; this asserts the positive half for
   the upstream tier, whose severity is the manifest's.
2. **`totalNotices` is the true count**, not how many samples survived the
   export cap. A report saying 14 while holding 2 samples is the entire point
   of the shape.
3. **Ids keep their prefixes** and the writer parses none of them.
4. **Samples carry the source file and the entity path**, since a run spans
   many messages where the sibling's run is one feed.
5. **No joined message.** The prefix and the rule's occurrence suffix stay in
   separate places; nothing in the bytes holds the two concatenated.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from gtfs_rt_validator.report import manifest, modern
from gtfs_rt_validator.report.occurrence import (
    ENTITY_PATH_KEY,
    SOURCE_FILE_KEY,
    NoticeContainer,
    Occurrence,
)
from modernrun import E002_SUFFIX, MESSAGE, a_run, a_summary

SRC = Path(__file__).resolve().parent.parent / "src" / "gtfs_rt_validator"


def report() -> dict:
    return modern.build_report(a_run(), a_summary())


def entry_for(code: str) -> dict:
    return next(entry for entry in report()["notices"] if entry["code"] == code)


def test_an_entry_is_a_code_a_severity_a_total_and_a_sample():
    payload = report()
    assert [entry["code"] for entry in payload["notices"]] == ["E002", "W002"]
    assert [list(entry) for entry in payload["notices"]] == [
        ["code", "severity", "totalNotices", "sampleNotices"],
        ["code", "severity", "totalNotices", "sampleNotices"],
    ]


def test_severity_is_read_from_the_manifest_and_never_written_down():
    """One home for severity. The writer looks it up; it does not know it."""
    entries = {entry["code"]: entry["severity"] for entry in report()["notices"]}
    assert entries == {
        "E002": manifest.rule("E002").severity,
        "W002": manifest.rule("W002").severity,
    }
    assert entries["E002"] != entries["W002"]
    for name in ("modern.py", "summary.py"):
        tree = ast.parse((SRC / "report" / name).read_text(encoding="utf-8"))
        assert not [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and node.value in ("ERROR", "WARNING")
        ], f"{name} spells a severity; read it from the manifest"


def test_total_notices_is_the_true_count_not_the_sample_count():
    """The whole reason the shape carries two numbers."""
    container = a_run()
    entry = entry_for("E002")
    assert entry["totalNotices"] == 14
    assert len(entry["sampleNotices"]) == 2
    assert container.count_for("E002") == 14
    assert container.retained_for("E002") == 14


def test_a_rule_whose_samples_were_all_dropped_still_reports_its_total():
    """The count moves for every occurrence, retained or not, so a rule that
    only ever reached the dropped bucket is a real total with no sample to show.
    The sibling builds its entries from the retained notices, so this rule would
    vanish from its report; here it stays, because the total is the point."""
    container = NoticeContainer()
    container.observe_dropped("E002", 9)
    assert modern.build_report(container, a_summary())["notices"] == [
        {
            "code": "E002",
            "severity": manifest.rule("E002").severity,
            "totalNotices": 9,
            "sampleNotices": [],
        }
    ]


def test_samples_carry_the_source_file_and_the_entity_path():
    """A departure from the sibling, whose run is one feed and needs neither."""
    sample = entry_for("E002")["sampleNotices"][0]
    assert sample[SOURCE_FILE_KEY] == MESSAGE
    assert sample[ENTITY_PATH_KEY] == "entity[0].trip_update"
    assert sample["tripId"] == "27770"


def test_the_prefix_is_its_own_key_and_the_suffix_is_nowhere():
    """Upstream keeps the two halves apart and so does this. Neither writer
    joins them: compat emits `occurrencePrefix` and `occurrenceSuffix` as
    separate keys and modern emits the prefix alone, so what string a reader
    would put between them is a question no output format here answers."""
    assert manifest.rule("E002").occurrence_suffix == E002_SUFFIX
    assert E002_SUFFIX not in modern.dumps_json(report())
    assert entry_for("E002")["sampleNotices"][0][modern.PREFIX_KEY] == (
        "trip_id 27770 stop_sequence 0"
    )


def test_an_occurrence_with_no_prefix_carries_no_prefix_key():
    container = NoticeContainer()
    container.add(Occurrence("W003", context={"tripId": "277716"}))
    sample = modern.build_report(container, a_summary())["notices"][0]["sampleNotices"][0]
    assert modern.PREFIX_KEY not in sample


def test_a_null_context_value_is_absent_rather_than_null():
    """The sibling's `_defined`, which is what upstream's Gson does."""
    container = NoticeContainer()
    container.add(Occurrence("E002", "p", {"tripId": "277716", "routeId": None}))
    sample = modern.build_report(container, a_summary())["notices"][0]["sampleNotices"][0]
    assert sample == {modern.PREFIX_KEY: "p", "tripId": "277716"}


def test_an_id_no_tier_ever_declared_is_a_bug_and_raises():
    """Feeds cannot reach this: rule ids come from the registry, so an id that
    neither registered nor sits in the manifest is a rule this project never
    wrote down rather than anything a feed did. A `spec` id that *did* register
    resolves through its registration, which is `test_declared_severity.py`."""
    container = NoticeContainer()
    container.add(Occurrence("S999", "p", {}))
    with pytest.raises(KeyError):
        modern.build_report(container, a_summary())


def test_a_severity_source_can_still_be_supplied_for_an_id_no_registration_owns():
    """The hook `build_system_errors` fills, exercised on its own. Shipped code
    needs it for exactly that: a system error is not a rule."""
    container = NoticeContainer()
    container.add(Occurrence("S999", "p", {}))
    payload = modern.build_report(container, a_summary(), severity_of=lambda _: "INFO")
    assert payload["notices"][0]["severity"] == "INFO"
