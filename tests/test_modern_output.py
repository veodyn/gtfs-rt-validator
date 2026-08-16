"""The summary block, and the bytes both reports land as.

The notices array is `tests/test_modern_writer.py`; this file is about the other
half of `report.json` and about the serialiser, which owes three things:

1. **Same container, same bytes.** The writer reads no clock and no
   environment, so every run-dependent value arrives in the summary.
2. **A field that was never set is absent, not null.** The sibling's rule, and
   Gson's default on the far side of it.
3. **A non-finite float survives the write.** `wire.py:235` unpacks a float
   straight out of a feed, so NaN and the infinities are values a vehicle
   position can carry, and bare `NaN` is not JSON.
"""

from __future__ import annotations

import json
import math

from gtfs_rt_validator.report import modern
from gtfs_rt_validator.report.occurrence import NoticeContainer, Occurrence
from gtfs_rt_validator.report.summary import RUN_DEPENDENT, RunSummary
from gtfs_rt_validator.version import VERSION
from modernrun import MESSAGE, a_run, a_summary


def test_the_report_is_a_summary_and_then_the_notices():
    payload = modern.build_report(a_run(), a_summary())
    assert list(payload) == ["summary", "notices"]
    assert payload["summary"]["validatorVersion"] == VERSION
    assert payload["summary"]["gtfsInput"] == "feed.zip"
    assert payload["summary"]["gtfsRealtimeInputs"] == [MESSAGE]


def test_a_summary_field_that_was_never_set_is_absent_rather_than_null():
    """A key set to empty stays; a key never set disappears. Different states."""
    summary = modern.build_report(a_run(), RunSummary(validated_at="2026-08-14T09:00:00Z"))
    assert "gtfsInput" not in summary["summary"]
    assert "validationTimeSeconds" not in summary["summary"]
    assert summary["summary"]["gtfsRealtimeInputs"] == []


def test_the_run_dependent_fields_are_named_once():
    """Two runs over the same inputs differ in exactly these, and both arrive as
    arguments rather than being read here."""
    assert set(RUN_DEPENDENT) == {"validatedAt", "validationTimeSeconds"}
    assert set(RUN_DEPENDENT) <= set(
        modern.build_report(a_run(), RunSummary(validated_at="t", validation_time_seconds=1.5))[
            "summary"
        ]
    )


def test_a_non_finite_float_is_rendered_the_way_java_renders_it():
    """`allow_nan=False` would otherwise kill the whole write over one feed's
    latitude, and the report would not be written at all."""
    container = NoticeContainer()
    container.add(Occurrence("E002", "p", {"lat": math.nan, "lon": math.inf, "alt": -math.inf}))
    payload = json.loads(modern.dumps_json(modern.build_report(container, a_summary())))
    assert payload["notices"][0]["sampleNotices"][0] == {
        modern.PREFIX_KEY: "p",
        "lat": "NaN",
        "lon": "Infinity",
        "alt": "-Infinity",
    }


def test_the_same_container_produces_the_same_bytes():
    first = modern.dumps_json(modern.build_report(a_run(), a_summary()))
    second = modern.dumps_json(modern.build_report(a_run(), a_summary()))
    assert first == second


def test_write_reports_creates_the_directory_and_writes_both_files(tmp_path):
    out = tmp_path / "out"
    written = modern.write_reports(out, a_run(), NoticeContainer(), a_summary())
    assert written == (out / modern.REPORT_NAME, out / modern.SYSTEM_ERRORS_NAME)
    text = (out / modern.REPORT_NAME).read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text) == modern.build_report(a_run(), a_summary())
    assert json.loads((out / modern.SYSTEM_ERRORS_NAME).read_text(encoding="utf-8")) == {
        "notices": []
    }
