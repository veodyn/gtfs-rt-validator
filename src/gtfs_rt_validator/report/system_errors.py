"""What upstream logs and drops, recorded instead.

`BatchProcessor` catches an unreadable file, a decode failure and a file name it
cannot parse a timestamp out of, logs each one, and moves to the next file
without writing any results for it. So a corrupt file in an archive replay
vanishes without trace. Modern mode records the four of them here, which is a
deliberate improvement on upstream rather than an accident.

The structure is the sibling's, deliberately: the same
`code`/`severity`/`totalNotices`/`sampleNotices` entry that `modern.py` builds
for findings, in the same `{"notices": [...]}` envelope, so one reader reads
both files. Two things differ and both are recorded:

- **Four codes, not one.** The sibling has a single
  `runtime_exception_in_loader_error` because its loader has one way to fail.
  These are four different failures and the file says which.
- **`sourceFile`, not `filename`.** The sibling keeps upstream's field name for
  a notice it has to match; nothing here has to match anything, and a sample in
  `report.json` already names its file with `SOURCE_FILE_KEY`. One name for one
  fact across both files.

A system error is not one of upstream's 61 rules, so there is no manifest entry
to read a severity from, and no license to write the word down either: the
packed-manifest test fails the build on a severity literal under `src/`. It
reports at `manifest.SYSTEM_ERROR_SEVERITY`, so severity keeps its single home.

An earlier version of this module borrowed E001's severity through an exemplar
id. That read correctly, and was wrong in principle: it tied every system error
to a rule it has nothing to do with, so an upstream change to E001 would have
moved them silently.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from gtfs_rt_validator.proto.errors import DecodeError
from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import SOURCE_FILE_KEY, NoticeContainer, Occurrence

__all__ = [
    "SystemErrorCode",
    "code_for_decode_error",
    "severity",
    "system_error",
]

#: The sibling's three context fields, with its `filename` renamed.
EXCEPTION_KEY = "exception"
MESSAGE_KEY = "message"

#: `decode.py` raises `DecodeError` for a missing required field as well as for
#: bytes protobuf-java would refuse, and only the reason tells them apart. The
#: prefix is that raise site's wording, not a guess about somebody's feed.
REQUIRED_FIELD_REASON = "required field "


class SystemErrorCode(StrEnum):
    """The four this module records: an unreadable file, a decode failure, a
    missing required field, and a file name whose timestamp would not parse."""

    UNREADABLE_FILE = "unreadable_file_error"
    DECODE_FAILURE = "feed_decode_error"
    MISSING_REQUIRED_FIELD = "missing_required_field_error"
    UNPARSABLE_FILE_NAME_TIMESTAMP = "unparsable_file_name_timestamp_error"


def severity() -> str:
    """Read, not written. The manifest is severity's only home."""
    return manifest.SYSTEM_ERROR_SEVERITY


def system_error(
    container: NoticeContainer,
    code: SystemErrorCode,
    source_file: str,
    exc: Exception,
    *,
    context: Mapping[str, object] | None = None,
) -> None:
    """Record a failure of the run rather than a finding about a feed.

    The exception's class name is kept alongside its message, as the sibling
    keeps it: when the message is empty the class is the only thing that says
    what went wrong. `context` carries whatever the caller knows on top, such as
    the Java exception a file-name timestamp failure stands in for, which
    `runner/clock.py` owns and this module does not guess at.
    """
    container.add(
        Occurrence(
            rule_id=code.value,
            context={
                SOURCE_FILE_KEY: source_file,
                EXCEPTION_KEY: type(exc).__name__,
                MESSAGE_KEY: str(exc),
                **(context or {}),
            },
        )
    )


def code_for_decode_error(exc: DecodeError) -> SystemErrorCode:
    """Which of the two decode failures this is, asked once rather than pattern
    matched at every call site that catches one."""
    if exc.reason.startswith(REQUIRED_FIELD_REASON):
        return SystemErrorCode.MISSING_REQUIRED_FIELD
    return SystemErrorCode.DECODE_FAILURE
