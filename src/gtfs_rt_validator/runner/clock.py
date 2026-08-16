"""The "current time" handed to every rule, derived rather than observed.

Upstream never calls `System.currentTimeMillis()` in batch mode. It computes one
`long timestamp` per file and passes it into every validator
(`BatchProcessor.processFeeds` L263), which is what makes an archive replay
reproducible. Two sources, chosen by `-sort` (L220-232): the modification time
under `DATE_MODIFIED`, or `TimestampUtils.getTimestampFromFileName` under `NAME`
inside a `catch (DateTimeParseException | StringIndexOutOfBoundsException)` that
falls back to the modification time.

So `-sort name` is not only an ordering: it switches the clock, and it degrades
silently to the modification time on any name it cannot read.

**Timezone.** Nothing here is naive. Both sources are instants: a modification
time is an epoch offset, and the file-name parse is anchored by the literal "Z"
that `ZonedDateTime.parse` requires (see `timestamp_from_file_name`), so the
encoded assumption is UTC and this module makes it explicit. Milliseconds since
the epoch is the currency, because that is what upstream hands the rules.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import ClassVar

__all__ = [
    "ClockSource",
    "FileNameTimestampError",
    "Reading",
    "SortBy",
    "compat_reading",
    "last_modified_millis",
    "millis_from_datetime",
    "modern_reading",
    "remove_extension",
    "timestamp_from_file_name",
]


class SortBy(Enum):
    """`BatchProcessor.SortBy` (L330-332).

    Lives here rather than beside the walk because upstream reads it twice and
    the clock is the reading with consequences: L171 uses it to pick a
    comparator, L221 uses it to pick where time comes from.
    """

    DATE_MODIFIED = "date"
    NAME = "name"

    @classmethod
    def from_cli(cls, value: str | None) -> SortBy:
        """`Main.getSortBy` L158-176.

        The `switch` is a case-sensitive String match with a `default` arm, so an
        absent flag, an unrecognised value and `-sort DATE` all land on
        `DATE_MODIFIED` without complaint.
        """
        return cls.NAME if value == cls.NAME.value else cls.DATE_MODIFIED


class ClockSource(Enum):
    """Where a reading came from, so `system_errors.json` can say."""

    FILE_NAME = "file_name"
    LAST_MODIFIED = "last_modified"
    FIXED = "fixed"
    NOW = "now"


@dataclass(frozen=True, slots=True)
class Reading:
    """One file's clock: milliseconds since the epoch, plus its provenance."""

    millis: int
    source: ClockSource
    #: Upstream's L229 log line, when the file-name parse failed and the
    #: modification time stood in. Modern mode records it; compat drops it.
    fallback_reason: str | None = None

    @property
    def moment(self) -> dt.datetime:
        return dt.datetime.fromtimestamp(self.millis / 1000, tz=dt.UTC)


class FileNameTimestampError(ValueError):
    """A file name `TimestampUtils.getTimestampFromFileName` would refuse.

    `kind` records which of upstream's two exception classes this stands in for,
    since `BatchProcessor` L228 catches both and the distinction only survives
    in the log line.
    """

    #: kind -> the Java exception it mirrors.
    JAVA_EXCEPTIONS: ClassVar[dict[str, str]] = {
        "name_too_short": "java.lang.StringIndexOutOfBoundsException",
        "unparsable": "java.time.format.DateTimeParseException",
    }

    def __init__(self, file_name: str, kind: str, detail: str) -> None:
        self.file_name = file_name
        self.kind = kind
        self.detail = detail
        super().__init__(f"{file_name!r}: {detail}")

    @property
    def java_exception(self) -> str:
        return self.JAVA_EXCEPTIONS[self.kind]


def remove_extension(file_name: str) -> str:
    """`FilenameUtils.removeExtension`, which runs before the 20-character slice.

    commons-io takes the *last* dot, and only when no path separator follows it
    (`indexOfExtension`). One consequence matters operationally: `x.pb` and
    `x.pb.results.json` do not reduce to the same stem, so a replay of a
    directory that already holds results parses neither the same way.
    """
    last_separator = max(file_name.rfind("/"), file_name.rfind("\\"))
    dot = file_name.rfind(".")
    if dot == -1 or last_separator > dot:
        return file_name
    return file_name[:dot]


# Everything `ZonedDateTime.parse(date + time, ISO_DATE_TIME)` accepts in exactly
# twenty characters, enumerated against a JDK 17 run of the same three lines
# rather than reasoned about. 1,043,366 candidates went through both sides and
# 2,605 were accepted; these two shapes are all of them.
#
# ISO_DATE_TIME is ISO_LOCAL_DATE_TIME, then an optional offset with an optional
# bracketed zone region nested inside that. `ZonedDateTime.parse` fails without a
# zone, so the offset is mandatory, and "Z" is the only one that fits: "+01"
# leaves nine characters where the slice takes ten. `ISO_LOCAL_TIME` makes the
# seconds optional, and dropping them frees exactly the three characters "[Z]"
# costs, which is why a minute-precision name with a bracketed zone region is
# legal. Nothing else fits: a fraction needs "THH:MM:SS.1Z", twelve into ten, and
# a zone region longer than one character needs room the offset already spent.
#
# The date half is never hyphen-replaced, so it must already carry ISO hyphens,
# and it is always ten characters: `SignStyle.EXCEEDS_PAD` rejects a sign on a
# four-digit year under strict parsing, and a five-digit year leaves nine for the
# time, which no shape can fill.
#
# Three details came out of the sweep rather than out of reading the grammar.
# `ISO_LOCAL_DATE_TIME` opens with `parseCaseInsensitive()` and the setting
# outlives the composite formatter, so "t", "z" and a lowercase offset all parse;
# the builder turns it back off with `parseCaseSensitive()` immediately before the
# zone region, so "[z]" is refused where "[Z]" is taken; and `DecimalStyle`
# accepts ASCII digits only, so "٢017-02-18T20-01-08Z" is rejected where Python's
# `\d` would have matched it.
_ISO_WINDOW = re.compile(
    r"\A(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})"
    r"[Tt](?P<hour>[0-9]{2}):(?P<minute>[0-9]{2})"
    r"(?::(?P<second>[0-9]{2})[Zz]|[Zz]\[Z\])\Z"
)

#: A whole Gregorian cycle, in days. `datetime`'s MINYEAR is 1, but
#: `ISO_LOCAL_DATE` accepts year 0000 and java.time reads it as 1 BC on the
#: proleptic Gregorian calendar. Four hundred years repeat the calendar exactly,
#: so year 0 validates and converts by borrowing year 400 and subtracting.
_GREGORIAN_CYCLE_MILLIS = 146_097 * 86_400_000


def timestamp_from_file_name(file_name: str) -> int:
    """`TimestampUtils.getTimestampFromFileName` L179-185.

        String fileNameNoExtension = FilenameUtils.removeExtension(fileName);
        String date = fileNameNoExtension.substring(len - 20, len - 10);
        String time = fileNameNoExtension.substring(len - 10, len).replaceAll("-", ":");
        ZonedDateTime zdt = ZonedDateTime.parse(date + time, DateTimeFormatter.ISO_DATE_TIME);
        return zdt.toInstant().toEpochMilli();

    So the twenty characters are counted *after* the extension is removed, only
    the trailing ten are hyphen-to-colon replaced, and the prefix is free:
    "TripUpdates-2017-02-18T20-01-08Z.pb" is upstream's own example (L172).

    Raises `FileNameTimestampError` where upstream raises either of the two
    exceptions its caller catches: a stem under twenty characters gives
    `StringIndexOutOfBoundsException` out of `substring`, anything else gives
    `DateTimeParseException`. `ISO_LOCAL_DATE` resolves STRICT, so an impossible
    calendar date such as 2017-02-30 is a parse failure too, and so are hour 24,
    minute 60 and a leap second.

    The accepted set is `_ISO_WINDOW` above, enumerated against a JDK 17 run of
    the same three lines over a million candidates rather than read off the
    format string upstream never wrote. "TripUpdates-2017-02-18T20-01Z[Z].pb" is
    as legal as the seconds-precision name and used to be refused here.
    """
    stem = remove_extension(file_name)
    if len(stem) < 20:
        raise FileNameTimestampError(
            file_name,
            "name_too_short",
            f"stem {stem!r} is {len(stem)} characters, and the slice needs 20",
        )
    candidate = stem[-20:-10] + stem[-10:].replace("-", ":")
    matched = _ISO_WINDOW.match(candidate)
    if matched is None:
        raise FileNameTimestampError(
            file_name, "unparsable", f"{candidate!r} is not an ISO instant"
        )
    field = matched.groupdict()
    year, month, day = (int(field[name]) for name in ("year", "month", "day"))
    hour, minute = int(field["hour"]), int(field["minute"])
    # The bracketed shape stops at the minute, which is what makes room for "[Z]".
    second = int(field["second"] or 0)
    shift = _GREGORIAN_CYCLE_MILLIS if year == 0 else 0
    try:
        moment = dt.datetime(
            year + (400 if shift else 0), month, day, hour, minute, second, tzinfo=dt.UTC
        )
    except ValueError as invalid:
        raise FileNameTimestampError(file_name, "unparsable", str(invalid)) from invalid
    return millis_from_datetime(moment) - shift


def millis_from_datetime(moment: dt.datetime) -> int:
    """`Instant.toEpochMilli()`. Rejects a naive datetime rather than guessing."""
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ValueError(f"{moment!r} has no timezone; the clock is an instant, not a wall time")
    return int(moment.timestamp() * 1000)


def last_modified_millis(path: Path) -> int:
    """`Files.getLastModifiedTime(path).toMillis()`.

    The JDK builds that FileTime from whole seconds plus a non-negative
    nanosecond remainder, so sub-millisecond precision is floored, not rounded.
    """
    return path.stat().st_mtime_ns // 1_000_000


def compat_reading(path: Path, sort_by: SortBy) -> Reading:
    """`BatchProcessor.processFeeds` L220-232, fallback included."""
    if sort_by is SortBy.DATE_MODIFIED:
        return Reading(last_modified_millis(path), ClockSource.LAST_MODIFIED)
    try:
        return Reading(timestamp_from_file_name(path.name), ClockSource.FILE_NAME)
    except FileNameTimestampError as failed:
        return Reading(
            last_modified_millis(path),
            ClockSource.LAST_MODIFIED,
            # Upstream's L229 wording, so a system error reads like its log.
            f"Couldn't parse timestamp from file name '{path.name}' - "
            f"using date modified instead: {failed.java_exception}: {failed.detail}",
        )


def modern_reading(
    path: Path | None,
    *,
    at: dt.datetime | None = None,
    directory_replay: bool = False,
    sort_by: SortBy = SortBy.DATE_MODIFIED,
) -> Reading:
    """Modern mode's clock: now by default, `--at` to pin it, upstream on replay.

    `at` wins over `directory_replay`. The alternative reading, that replay
    always derives its clock from the files, would make `--at archive/` a flag
    that silently did nothing, and the flag exists precisely to make a run
    reproducible. `path` is None for a URL, which has no modification time.
    """
    if at is not None:
        return Reading(millis_from_datetime(at), ClockSource.FIXED)
    if directory_replay and path is not None:
        return compat_reading(path, sort_by)
    return Reading(millis_from_datetime(dt.datetime.now(tz=dt.UTC)), ClockSource.NOW)
