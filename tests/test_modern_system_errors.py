"""`out/system_errors.json`: the four things upstream logs and drops.

`BatchProcessor` writes nothing at all for a file it could not read, could not
decode, or whose name it could not parse a timestamp out of, so a corrupt file
in an archive replay currently vanishes without trace. Recording them is a
deliberate improvement on upstream, which is why the file has its own structure
rather than being folded into the notices.

The structure is the sibling's: the same `code`/`severity`/`totalNotices`/
`sampleNotices` entry, in the same `{"notices": [...]}` envelope, written by the
same builder the report uses. Only the severity source differs, because a system
error is not one of upstream's 61 rules and so has no manifest entry.
"""

from __future__ import annotations

import ast
from pathlib import Path

from gtfs_rt_validator.proto.errors import DecodeError
from gtfs_rt_validator.report import manifest, modern, system_errors
from gtfs_rt_validator.report.occurrence import SOURCE_FILE_KEY, NoticeContainer

SRC = Path(__file__).resolve().parent.parent / "src" / "gtfs_rt_validator"


def a_run() -> NoticeContainer:
    container = NoticeContainer()
    system_errors.system_error(
        container,
        system_errors.SystemErrorCode.UNREADABLE_FILE,
        "archive/locked.pb",
        PermissionError(13, "Permission denied"),
    )
    system_errors.system_error(
        container,
        system_errors.SystemErrorCode.DECODE_FAILURE,
        "archive/truncated.pb",
        DecodeError("truncated varint", at=7),
    )
    return container


def test_the_envelope_and_the_entry_are_the_siblings():
    payload = modern.build_system_errors(a_run())
    assert list(payload) == ["notices"]
    assert [list(entry) for entry in payload["notices"]] == [
        ["code", "severity", "totalNotices", "sampleNotices"],
        ["code", "severity", "totalNotices", "sampleNotices"],
    ]


def test_a_sample_says_which_file_which_exception_and_what_it_said():
    """The sibling's three context fields, with its `filename` renamed to the
    key the report's own samples already use for the same fact."""
    entry = modern.build_system_errors(a_run())["notices"][0]
    assert entry["code"] == system_errors.SystemErrorCode.DECODE_FAILURE
    assert entry["totalNotices"] == 1
    assert entry["sampleNotices"] == [
        {
            SOURCE_FILE_KEY: "archive/truncated.pb",
            "exception": "DecodeError",
            "message": "truncated varint (at byte 7)",
        }
    ]


def test_the_codes_are_the_four_the_spec_names():
    assert {code.value for code in system_errors.SystemErrorCode} == {
        "unreadable_file_error",
        "feed_decode_error",
        "missing_required_field_error",
        "unparsable_file_name_timestamp_error",
    }


def test_a_missing_required_field_is_its_own_code_not_a_plain_decode_failure():
    """`decode.py:189` raises `DecodeError` for both, so the caller that catches
    it asks here rather than matching the message itself."""
    assert (
        system_errors.code_for_decode_error(
            DecodeError("required field FeedHeader.gtfs_realtime_version is not set")
        )
        is system_errors.SystemErrorCode.MISSING_REQUIRED_FIELD
    )
    assert (
        system_errors.code_for_decode_error(DecodeError("truncated varint", at=7))
        is system_errors.SystemErrorCode.DECODE_FAILURE
    )


def test_extra_context_rides_along_with_the_three_fields():
    """A file-name timestamp failure carries the Java exception it stands in for
    and the log line upstream would have written; both are `clock.py`'s to
    supply and neither is invented here."""
    container = NoticeContainer()
    system_errors.system_error(
        container,
        system_errors.SystemErrorCode.UNPARSABLE_FILE_NAME_TIMESTAMP,
        "archive/not-a-timestamp.pb",
        ValueError("text could not be parsed at index 0"),
        context={"javaException": "java.time.format.DateTimeParseException"},
    )
    sample = modern.build_system_errors(container)["notices"][0]["sampleNotices"][0]
    assert sample["javaException"] == "java.time.format.DateTimeParseException"
    assert sample[SOURCE_FILE_KEY] == "archive/not-a-timestamp.pb"


def test_severity_is_still_the_manifests_and_still_not_a_literal():
    """A system error reports at its own declared severity, which lives in the
    manifest like every other severity, because writing the word here would be
    the second home the packed-manifest test forbids.

    It is deliberately not borrowed from any rule: an earlier version read it
    off E001, which tied the two together for no reason and would have moved
    system errors silently if upstream ever downgraded that rule."""
    assert system_errors.severity() == manifest.SYSTEM_ERROR_SEVERITY
    assert system_errors.severity() != manifest.rule("W003").severity
    for entry in modern.build_system_errors(a_run())["notices"]:
        assert entry["severity"] == system_errors.severity()
    tree = ast.parse((SRC / "report" / "system_errors.py").read_text(encoding="utf-8"))
    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value in ("ERROR", "WARNING")
    ]


def test_the_total_is_the_true_count_here_too():
    container = NoticeContainer(max_exports_per_rule=1)
    for index in range(5):
        system_errors.system_error(
            container,
            system_errors.SystemErrorCode.DECODE_FAILURE,
            f"archive/{index}.pb",
            DecodeError("truncated varint"),
        )
    entry = modern.build_system_errors(container)["notices"][0]
    assert entry["totalNotices"] == 5
    assert len(entry["sampleNotices"]) == 1


def test_an_empty_run_still_writes_the_file(tmp_path):
    """Upstream's silence is the gap; an empty array says the run looked."""
    _, written = modern.write_reports(
        tmp_path / "out", NoticeContainer(), NoticeContainer(), modern.RunSummary(validated_at="t")
    )
    assert written.read_text(encoding="utf-8") == '{\n  "notices": []\n}\n'
