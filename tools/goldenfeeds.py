"""The crafted `.pb` corpus the goldens are generated from.

Small, hand-built and committed, which is the opposite of the archive corpus the
spec describes: that one has to be recorded live from named feeds and cannot be
authored. These eight files exist to pin the *output contract* rather than rule
semantics, so each one is chosen for a property of the jar's writer or of
`BatchProcessor`'s file loop, and the rules they happen to trip are a bonus.

Built with `proto/encode.py` against the 2015 schema, the view upstream compiles
against. Order is the sorted-name order `run_jar.plan` stamps mtimes in and is
load-bearing: the last four files test the loop's cross-file state.

The `Feed` record and the nested-dict builders are `tools/feedbuild.py`'s,
shared with the tier 1 conformance corpus in `tools/conformancefeeds.py`. What
stays here is the eight feeds themselves, because each one is chosen for a
property of the writer rather than for a rule.
"""

from __future__ import annotations

from feedbuild import SCHEMA, Feed, encode

# 2017-07-14T02:40:00Z, far enough behind the stamped mtimes that W008 ("header
# timestamp is older than 65 seconds") fires deterministically.
FEED_TS = 1_500_000_000

# trip_id 1.1 and 1.2 exist in tests/fixtures/gtfs/testagency.zip; "not-in-gtfs"
# deliberately does not.
KNOWN_TRIP = "1.1"
OTHER_TRIP = "1.2"


def header(timestamp: int | None = FEED_TS) -> dict:
    value: dict = {"gtfs_realtime_version": "1.0", "incrementality": 0}
    if timestamp is not None:
        value["timestamp"] = timestamp
    return value


def _no_timestamps() -> bytes:
    """No header timestamp, no trip timestamp, no vehicle id, no stop_time_updates."""
    return encode(
        {
            "header": header(None),
            "entity": [{"id": "e1", "trip_update": {"trip": {"trip_id": KNOWN_TRIP}}}],
        },
        SCHEMA,
    )


def _unsorted() -> bytes:
    """stop_sequence 3 then 1, which E002 reports as a list rather than a scalar."""
    return encode(
        {
            "header": header(),
            "entity": [
                {
                    "id": "e1",
                    "trip_update": {
                        "trip": {"trip_id": KNOWN_TRIP},
                        "timestamp": FEED_TS,
                        "vehicle": {"id": "v1"},
                        "stop_time_update": [
                            {"stop_sequence": 3, "arrival": {"time": FEED_TS + 100}},
                            {"stop_sequence": 1, "arrival": {"time": FEED_TS + 200}},
                        ],
                    },
                }
            ],
        },
        SCHEMA,
    )


def _invalid_utf8() -> bytes:
    """A trip_id that is not valid UTF-8, spliced in after encoding.

    `encode` takes `str` and would refuse these bytes, which is correct: the
    point is a feed no well-behaved producer writes. protobuf-java replaces each
    bad byte with U+FFFD while decoding, and Jackson then writes those characters
    as raw UTF-8 rather than as `\\uXXXX` escapes, which is the escaping fact the
    golden pins.
    """
    # A two-ASCII-character placeholder, swapped for two raw bytes afterwards.
    # Same length on the wire, so every enclosing length prefix stays correct;
    # a shorter or longer splice would need four of them rewritten by hand.
    placeholder = b"XX"
    blob = encode(
        {
            "header": header(),
            "entity": [
                {
                    "id": "e1",
                    "trip_update": {
                        "trip": {"trip_id": placeholder.decode()},
                        "timestamp": FEED_TS,
                    },
                }
            ],
        },
        SCHEMA,
    )
    if blob.count(placeholder) != 1:
        raise AssertionError(f"{placeholder!r} is not unique in the encoded feed")
    return blob.replace(placeholder, b"\xff\xfe")


def _combined() -> bytes:
    """One message carrying both a TripUpdate and a VehiclePosition.

    `GtfsUtils.isCombinedFeed` gates CrossFeedDescriptorValidator on exactly
    this, and W003 is the only rule at the pin whose `occurrenceSuffix` is the
    empty string. Its four occurrences come out of Java `HashSet` iteration, so
    the golden pins that order too.
    """
    return encode(
        {
            "header": header(),
            "entity": [
                {
                    "id": "t1",
                    "trip_update": {
                        "trip": {"trip_id": KNOWN_TRIP},
                        "timestamp": FEED_TS,
                        "vehicle": {"id": "vOnlyTU"},
                    },
                },
                {
                    "id": "v1",
                    "vehicle": {
                        "trip": {"trip_id": OTHER_TRIP},
                        "timestamp": FEED_TS,
                        "vehicle": {"id": "vOnlyVP"},
                        "position": {"latitude": 40.0, "longitude": -73.0},
                    },
                },
            ],
        },
        SCHEMA,
    )


def _after_skips() -> bytes:
    """Same header timestamp as 04, different content, three skipped files later.

    E017 ("header timestamp is not strictly greater") compares against the
    previous *processed* message. `BatchProcessor` assigns `prevMessage` only at
    the end of a successful iteration, so if E017 fires here it proves the three
    intervening skips left that state untouched.
    """
    return encode(
        {
            "header": header(),
            "entity": [
                {
                    "id": "e1",
                    "trip_update": {
                        "trip": {"trip_id": "not-in-gtfs"},
                        "timestamp": FEED_TS,
                        "vehicle": {"id": "v9"},
                    },
                }
            ],
        },
        SCHEMA,
    )


_COMBINED = _combined()

FEEDS: tuple[Feed, ...] = (
    Feed("01-no-timestamps.pb", "missing timestamps everywhere", _no_timestamps()),
    Feed("02-unsorted-stop-times.pb", "stop_time_updates out of order", _unsorted()),
    Feed("03-invalid-utf8.pb", "trip_id that is not valid UTF-8", _invalid_utf8()),
    Feed("04-combined-feed.pb", "TripUpdate and VehiclePosition together", _COMBINED),
    Feed(
        "05-duplicate-of-04.pb", "byte-identical to 04, so dedupe skips it", _COMBINED, "duplicate"
    ),
    Feed("06-truncated.pb", "six 0xff bytes, which protobuf-java rejects", b"\xff" * 6, "decode"),
    Feed("07-empty.pb", "zero bytes, so the required header is missing", b"", "decode"),
    Feed("08-after-skips.pb", "valid again after three skips, and E017 proves it", _after_skips()),
)
