"""The clock is an input, not an ambient fact.

Every expectation here is pinned to upstream at 7041fa3, specifically
`BatchProcessor.processFeeds` L220-232 and `TimestampUtils.getTimestampFromFileName`
L179-185. See `tools/.upstream/7041fa3.../` for the cached Java.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest

from gtfs_rt_validator.runner.clock import (
    ClockSource,
    FileNameTimestampError,
    SortBy,
    compat_reading,
    last_modified_millis,
    modern_reading,
    remove_extension,
    timestamp_from_file_name,
)

# "TripUpdates-2017-02-18T20-01-08Z.pb" is the example in TimestampUtils' javadoc
# (L172). 2017-02-18T20:01:08Z as milliseconds since the epoch.
EXAMPLE_NAME = "TripUpdates-2017-02-18T20-01-08Z.pb"
EXAMPLE_MILLIS = 1487448068000

# The same instant to the minute. ISO_LOCAL_TIME makes the seconds optional, and
# the three characters that frees are exactly what a bracketed zone region costs.
MINUTE_MILLIS = 1487448060000


def _touch(tmp_path: Path, name: str, millis: int) -> Path:
    path = tmp_path / name
    path.write_bytes(b"\x00")
    os.utime(path, ns=(millis * 1_000_000, millis * 1_000_000))
    return path


class TestRemoveExtension:
    """FilenameUtils.removeExtension, which runs before the 20-character slice."""

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("TripUpdates.pb", "TripUpdates"),
            ("TripUpdates", "TripUpdates"),
            # Only the last extension goes. This is why a second run over a
            # directory feeds `x.pb.results.json` back in as `x.pb.results`.
            ("x.pb.results.json", "x.pb.results"),
            ("trailing.", "trailing"),
            (".pb", ""),
            ("", ""),
            # indexOfExtension returns NOT_FOUND when the last separator comes
            # after the last dot, so a dotted directory keeps the whole string.
            ("a.d/plain", "a.d/plain"),
        ],
    )
    def test_matches_commons_io(self, name: str, expected: str) -> None:
        assert remove_extension(name) == expected


class TestTimestampFromFileName:
    def test_the_javadoc_example(self) -> None:
        assert timestamp_from_file_name(EXAMPLE_NAME) == EXAMPLE_MILLIS

    @pytest.mark.parametrize(
        "name",
        [
            "2017-02-18T20-01-08Z.pb",  # exactly 20 characters after the extension
            "2017-02-18T20-01-08Z",  # no extension at all
            "anything at all-2017-02-18T20-01-08Z.pb",  # any prefix
            # The last ten characters are `replaceAll("-", ":")`-ed, so a name
            # that already carries colons parses identically.
            "TripUpdates-2017-02-18T20:01:08Z.pb",
            "TripUpdates-2017-02-18T20-01:08Z.pb",
            # Measured, not reasoned: ISO_LOCAL_DATE_TIME is built with
            # parseCaseInsensitive(), so the "T" and the "Z" may be lower case.
            "TripUpdates-2017-02-18t20-01-08Z.pb",
            "TripUpdates-2017-02-18T20-01-08z.pb",
        ],
    )
    def test_accepted_shapes(self, name: str) -> None:
        assert timestamp_from_file_name(name) == EXAMPLE_MILLIS

    @pytest.mark.parametrize(
        "name",
        [
            "TripUpdates-2017-02-18T20-01Z[Z].pb",
            "TripUpdates-2017-02-18T20:01Z[Z].pb",  # already colon-separated
            "TripUpdates-2017-02-18t20-01z[Z].pb",  # the offset is case-insensitive
            "xx2017-02-18T20-01Z[Z]",  # no extension, and a two-character prefix
        ],
    )
    def test_a_bracketed_zone_region_buys_the_seconds_back(self, name: str) -> None:
        """Upstream hands the window to ISO_DATE_TIME, not to a format string.

        `ZonedDateTime.parse` needs a zone, "Z" is the only offset that fits, and
        the optional bracketed region nested behind it fits only once the seconds
        are gone. All four were measured against a JDK 17 run of L179-185.
        """
        assert timestamp_from_file_name(name) == MINUTE_MILLIS

    def test_year_zero(self) -> None:
        """ISO_LOCAL_DATE reaches a year `datetime` cannot represent.

        java.time reads 0000 as 1 BC on the proleptic Gregorian calendar. A JDK
        17 run of upstream's three lines returns this exact value.
        """
        assert timestamp_from_file_name("0000-01-01T00-00-00Z.pb") == -62167219200000

    def test_year_nine_thousand_nine_hundred_and_ninety_nine(self) -> None:
        assert timestamp_from_file_name("9999-12-31T23-59-59Z.pb") == 253402300799000

    @pytest.mark.parametrize(
        ("name", "kind"),
        [
            # substring(len-20, len-10) on a short name throws
            # StringIndexOutOfBoundsException (caught at BatchProcessor L228).
            ("short.pb", "name_too_short"),
            ("", "name_too_short"),
            ("1234567890123456789.pb", "name_too_short"),  # 19, one short
            # ZonedDateTime.parse throws DateTimeParseException.
            ("aaaaaaaaaaaaaaaaaaaa.pb", "unparsable"),
            # Only the time half is hyphen-to-colon replaced; the date half must
            # already carry ISO hyphens.
            ("TripUpdates-2017:02:18T20-01-08Z.pb", "unparsable"),
            # ISO_LOCAL_DATE resolves STRICT, so February 30th is rejected.
            ("TripUpdates-2017-02-30T20-01-08Z.pb", "unparsable"),
            # ZonedDateTime.parse needs an offset, and only "Z" fits ten
            # characters alongside "THH:MM:SS".
            ("TripUpdates-2017-02-18T20-01-089.pb", "unparsable"),
            # Hours run 0-23 under STRICT, so 24:01:08 is not a valid time, and
            # neither minute 60 nor a leap second survives the same resolver.
            ("TripUpdates-2017-02-18T24-01-08Z.pb", "unparsable"),
            ("TripUpdates-2017-02-18T20-60-08Z.pb", "unparsable"),
            ("TripUpdates-2017-02-18T20-01-60Z.pb", "unparsable"),
            # The builder calls parseCaseSensitive() immediately before the zone
            # region, so the region alone is case-sensitive where everything
            # around it is not, and "Z" is the only one-character zone id there is.
            ("TripUpdates-2017-02-18T20-01Z[z].pb", "unparsable"),
            ("TripUpdates-2017-02-18T20-01Z[Y].pb", "unparsable"),
            # The bracket is nested inside the offset, so it cannot stand alone.
            ("TripUpdates-2017-02-18T20-01+[Z].pb", "unparsable"),
            # A numeric offset never fits: "+01" leaves nine characters where the
            # slice takes ten, and the window slides off the timestamp instead.
            ("TripUpdates-2017-02-18T20-01-08+01.pb", "unparsable"),
            # Measured, not reasoned: DecimalStyle.STANDARD takes ASCII digits
            # only, where Python's `\d` also matches Arabic-Indic ones.
            ("TripUpdates-٢017-02-18T20-01-08Z.pb", "unparsable"),
            ("TripUpdates-2017-02-18T20-01-0٢Z.pb", "unparsable"),
            # The extension strip happens first, so a second extension shifts
            # the twenty-character window off the timestamp.
            ("TripUpdates-2017-02-18T20-01-08Z.pb.results.json", "unparsable"),
        ],
    )
    def test_rejected_shapes(self, name: str, kind: str) -> None:
        with pytest.raises(FileNameTimestampError) as caught:
            timestamp_from_file_name(name)
        assert caught.value.kind == kind
        assert caught.value.file_name == name

    def test_the_parse_assumes_utc(self) -> None:
        """ "Z" is the only offset that fits, so the encoded timezone is UTC."""
        parsed = dt.datetime.fromtimestamp(timestamp_from_file_name(EXAMPLE_NAME) / 1000, tz=dt.UTC)
        assert parsed == dt.datetime(2017, 2, 18, 20, 1, 8, tzinfo=dt.UTC)


class TestSortBy:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("name", SortBy.NAME),
            ("date", SortBy.DATE_MODIFIED),
            (None, SortBy.DATE_MODIFIED),
            # Main.getSortBy L169-171: an unrecognised value is not an error.
            ("modified", SortBy.DATE_MODIFIED),
            # `switch` on a String is case sensitive.
            ("NAME", SortBy.DATE_MODIFIED),
        ],
    )
    def test_from_cli(self, value: str | None, expected: SortBy) -> None:
        assert SortBy.from_cli(value) == expected


class TestCompatReading:
    def test_date_modified_ignores_a_parseable_name(self, tmp_path: Path) -> None:
        path = _touch(tmp_path, EXAMPLE_NAME, 999_000)
        reading = compat_reading(path, SortBy.DATE_MODIFIED)
        assert reading.millis == 999_000
        assert reading.source is ClockSource.LAST_MODIFIED
        assert reading.fallback_reason is None

    def test_name_uses_the_file_name(self, tmp_path: Path) -> None:
        path = _touch(tmp_path, EXAMPLE_NAME, 999_000)
        reading = compat_reading(path, SortBy.NAME)
        assert reading.millis == EXAMPLE_MILLIS
        assert reading.source is ClockSource.FILE_NAME

    def test_name_falls_back_to_last_modified(self, tmp_path: Path) -> None:
        path = _touch(tmp_path, "unparseable.pb", 999_000)
        reading = compat_reading(path, SortBy.NAME)
        assert reading.millis == 999_000
        assert reading.source is ClockSource.LAST_MODIFIED
        assert reading.fallback_reason is not None
        assert "unparseable.pb" in reading.fallback_reason

    def test_last_modified_is_floor_divided_to_milliseconds(self, tmp_path: Path) -> None:
        path = tmp_path / "x.pb"
        path.write_bytes(b"")
        os.utime(path, ns=(1_700_000_000_999_999, 1_700_000_000_999_999))
        assert last_modified_millis(path) == 1_700_000_000


class TestModernReading:
    def test_at_pins_the_clock(self, tmp_path: Path) -> None:
        when = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
        reading = modern_reading(_touch(tmp_path, "x.pb", 5_000), at=when)
        assert reading.millis == 1577836800000
        assert reading.source is ClockSource.FIXED

    def test_at_wins_over_directory_replay(self, tmp_path: Path) -> None:
        when = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
        path = _touch(tmp_path, EXAMPLE_NAME, 5_000)
        reading = modern_reading(path, at=when, directory_replay=True, sort_by=SortBy.NAME)
        assert reading.source is ClockSource.FIXED

    def test_a_naive_at_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="timezone"):
            modern_reading(_touch(tmp_path, "x.pb", 5_000), at=dt.datetime(2020, 1, 1))  # noqa: DTZ001

    def test_directory_replay_keeps_upstream_behaviour(self, tmp_path: Path) -> None:
        path = _touch(tmp_path, EXAMPLE_NAME, 5_000)
        assert modern_reading(path, directory_replay=True, sort_by=SortBy.NAME) == compat_reading(
            path, SortBy.NAME
        )
        assert modern_reading(path, directory_replay=True) == compat_reading(
            path, SortBy.DATE_MODIFIED
        )

    def test_a_single_file_defaults_to_now(self, tmp_path: Path) -> None:
        before = int(dt.datetime.now(tz=dt.UTC).timestamp() * 1000)
        reading = modern_reading(_touch(tmp_path, EXAMPLE_NAME, 5_000))
        after = int(dt.datetime.now(tz=dt.UTC).timestamp() * 1000)
        assert reading.source is ClockSource.NOW
        assert before <= reading.millis <= after

    def test_a_url_has_no_path_and_defaults_to_now(self) -> None:
        assert modern_reading(None).source is ClockSource.NOW
