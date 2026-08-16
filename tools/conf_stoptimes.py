"""Tier 1 feeds about stop_time_updates and about the clock.

Files 05 to 15 of the `bullrunner` sequence, including the three the jar skips
and the one after them that proves cross-file state survived the skips.
`tools/conf_common.py` explains the timeline and the archive.
"""

from __future__ import annotations

from conf_common import DELAYED, STU_NO_DATA, STU_SCHEDULED, clock, quiet_trip
from feedbuild import Feed, entity, header, message, pb, stu, trip_update


def _stop_time_updates() -> bytes:
    """One trip whose six stop_time_updates are each missing something else.

    Sorted by stop_sequence on purpose: E002 stops `StopTimeUpdateValidator`'s
    walk for the trip, so a file that tripped it would report nothing else about
    these updates. The last update carries neither a stop_sequence nor a
    stop_id, which is E040 and, because trip `1` visits stop `222` twice, E009
    as well.
    """
    return pb(
        message(
            header(clock(-26)),
            entity(
                "each-one-different",
                trip_update=trip_update(
                    quiet_trip("1"),
                    stu(1, "222", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    stu(2, schedule_relationship=STU_SCHEDULED),
                    stu(3, arrival={}, schedule_relationship=STU_SCHEDULED),
                    stu(4, arrival=DELAYED, departure={}, schedule_relationship=STU_SCHEDULED),
                    stu(5, arrival=DELAYED, schedule_relationship=STU_NO_DATA),
                    stu(arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="stu-1",
                    timestamp=clock(-26),
                ),
            ),
        )
    )


def _unsorted() -> bytes:
    """stop_sequence 3 before stop_sequence 1, which E002 reports as a list."""
    return pb(
        message(
            header(clock(-25)),
            entity(
                "backwards",
                trip_update=trip_update(
                    quiet_trip("1"),
                    stu(3, "214", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    stu(1, "222", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="sort-1",
                    timestamp=clock(-25),
                ),
            ),
        )
    )


def _repeated_sequence() -> bytes:
    return pb(
        message(
            header(clock(-24)),
            entity(
                "same-sequence-twice",
                trip_update=trip_update(
                    quiet_trip("5"),
                    stu(1, arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    stu(1, arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="seq-1",
                    timestamp=clock(-24),
                ),
            ),
        )
    )


def _repeated_stop() -> bytes:
    return pb(
        message(
            header(clock(-23)),
            entity(
                "same-stop-twice",
                trip_update=trip_update(
                    quiet_trip("1"),
                    stu(stop_id="230", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    stu(stop_id="230", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="stop-1",
                    timestamp=clock(-23),
                ),
            ),
        )
    )


def _gtfs_mismatch() -> bytes:
    """stop_sequence 2 named for the wrong stop, and a stop_sequence GTFS has not."""
    return pb(
        message(
            header(clock(-22)),
            entity(
                "does-not-match-gtfs",
                trip_update=trip_update(
                    quiet_trip("1"),
                    stu(2, "214", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    stu(99, "230", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="match-1",
                    timestamp=clock(-22),
                ),
            ),
        )
    )


def _stop_time_ordering() -> bytes:
    """A departure before its own arrival, then an arrival before both."""
    return pb(
        message(
            header(clock(-21)),
            entity(
                "times-go-backwards",
                trip_update=trip_update(
                    quiet_trip("1"),
                    stu(
                        1,
                        "222",
                        arrival={"time": clock(400)},
                        departure={"time": clock(300)},
                        schedule_relationship=STU_SCHEDULED,
                    ),
                    stu(
                        2,
                        "230",
                        arrival={"time": clock(200)},
                        departure={"time": clock(600)},
                        schedule_relationship=STU_SCHEDULED,
                    ),
                    vehicle_id="order-1",
                    timestamp=clock(-21),
                ),
            ),
        )
    )


def _out_of_range_times() -> bytes:
    """A millisecond timestamp and one 100,000 seconds ahead of the clock.

    Both are also greater than the header timestamp, so E012 comes with them.
    """
    return pb(
        message(
            header(clock(-20)),
            entity(
                "milliseconds",
                trip_update=trip_update(
                    quiet_trip("1"),
                    stu(1, "222", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="range-1",
                    timestamp=1_500_000_000_000,
                ),
            ),
            entity(
                "far-ahead",
                trip_update=trip_update(
                    quiet_trip("2"),
                    stu(1, "222", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="range-2",
                    timestamp=clock(100_000),
                ),
            ),
        )
    )


def _after_skips() -> bytes:
    """The same header timestamp as `11-out-of-range-times.pb`, three skips later.

    E017 compares against the previous *processed* message, and `BatchProcessor`
    assigns `prevMessage` only at the end of a successful iteration, so E017
    firing here proves the duplicate and the two decode failures between them
    left that state untouched.
    """
    return pb(
        message(
            header(clock(-20)),
            entity(
                "different-content-same-header",
                trip_update=trip_update(
                    quiet_trip("6"),
                    stu(1, arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="skips-1",
                    timestamp=clock(-20),
                ),
            ),
        )
    )


_OUT_OF_RANGE = _out_of_range_times()

STOP_TIME_FEEDS: tuple[Feed, ...] = (
    Feed(
        "05-stop-time-updates.pb",
        "six updates each missing something else",
        _stop_time_updates(),
    ),
    Feed("06-unsorted.pb", "stop_sequence 3 before stop_sequence 1", _unsorted()),
    Feed("07-repeated-sequence.pb", "the same stop_sequence twice in a row", _repeated_sequence()),
    Feed("08-repeated-stop.pb", "the same stop_id twice in a row", _repeated_stop()),
    Feed("09-gtfs-mismatch.pb", "a stop_sequence GTFS pairs with another stop", _gtfs_mismatch()),
    Feed(
        "10-stop-time-ordering.pb",
        "a departure before its arrival, then an arrival before both",
        _stop_time_ordering(),
    ),
    Feed(
        "11-out-of-range-times.pb",
        "a millisecond timestamp and one far ahead of the clock",
        _OUT_OF_RANGE,
    ),
    Feed(
        "12-duplicate-of-11.pb",
        "byte-identical to 11, so dedupe skips it",
        _OUT_OF_RANGE,
        "duplicate",
    ),
    Feed("13-truncated.pb", "six 0xff bytes, which protobuf-java rejects", b"\xff" * 6, "decode"),
    Feed("14-empty-file.pb", "zero bytes, so the required header is missing", b"", "decode"),
    Feed(
        "15-after-skips.pb",
        "valid again after three skips, and E017 proves it",
        _after_skips(),
    ),
)
