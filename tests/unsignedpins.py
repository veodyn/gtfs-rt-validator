"""What a real jar wrote for `unsignedfeeds.FEEDS`, measured on JDK 17.0.19.

The oracle for the whole unsigned-rendering set. `tests/test_jar_unsigned.py`
re-derives it from a running jar and `tests/test_unsigned_prefixes.py` holds this
project to it, so neither module carries the expectation on its own.

**Complete, not a sample.** Every occurrence the jar wrote is here, including the
ones with nothing to do with unsigned integers, because a subset would let a fix
that *added* a spurious occurrence pass. The comparison is over the multiset and
not the sequence: compat output order is upstream's validator registration
order, owned by `report/compat.py` and pinned by `tests/test_compat_writer.py`,
so this module does not restate it.

Several pins turn on the fact that Java compares these values signed as well as
printing them signed, which is why the rule layer narrows at the read rather than
at the render:

- `02-seq-e037.pb` sends stop_sequence 1 then 4294967295. That is `[1, -1]` to
  `Ordering.natural().isStrictlyOrdered`, so the jar emits an E002 that a
  comparison on the unsigned values misses entirely.
- `08`, `09` and `10` each carry an entity timestamp of 1700000000 under a
  header of -2, so `tripUpdateTimestamp > headerTimestamp` holds and E012 fires.
  Unsigned, 1700000000 is far below the header and it does not.
- `07-ts-entities.pb` follows a header of 1700000000 with one of -2, which is
  E018 upstream and would be W007 on the unsigned values.
- `11-seq-w009.pb` follows a header of -4 with one of 1700000000, and the jar
  prints the interval between them as 1700000004.

Split from `unsignedfeeds.py` by the file-size hook, on a seam that is real
enough: that module is the input to a run and this one is the answer to it.
"""

from __future__ import annotations

__all__ = ["PINS", "expected"]

#: E019's prefix, twice over the line limit and repeated seven times below.
#: Nothing to do with unsigned integers; it is here because `PINS` is complete.
#: The second spelling is upstream's own arithmetic on a `frequencies.txt`
#: end_time past the hour, which is why it reads `09:120:00`.
_E019 = (
    "GTFS-rt trip_id T1 has start_time of  and GTFS frequencies.txt start_time "
    "is 09:50:00 with a headway of 600 seconds "
)
_E019_WRAPPED = (
    "GTFS-rt trip_id T1 has start_time of  and GTFS frequencies.txt start_time "
    "is 09:120:00 with a headway of 600 seconds "
)

#: Feed name to every `(rule_id, prefix)` a real jar wrote for it, on JDK 17.0.19
#: at the pinned SHA, sorted. Re-derived by `tests/test_jar_unsigned.py`.
PINS: dict[str, tuple[tuple[str, str], ...]] = {
    "01-seq-e051.pb": (
        ("E019", _E019),
        ("E043", "trip_id T1 stop_sequence -1"),
        ("E051", "GTFS-rt trip_id T1 contains stop_sequence -1"),
        ("W002", "trip_id T1"),
        ("W009", "trip_id T1"),
        ("W009", "trip_id T1 stop_sequence -1 (and potentially more for this trip)"),
    ),
    "02-seq-e037.pb": (
        ("E002", "trip_id T1 stop_sequence [1, -1]"),
        ("E017", "header.timestamp of 1700000000"),
        ("E019", _E019),
        ("E037", "trip_id T1 has repeating stop_id S1 at stop_sequence -1"),
        ("E051", "GTFS-rt trip_id T1 contains stop_sequence -1"),
        ("W002", "trip_id T1"),
        ("W009", "trip_id T1"),
        ("W009", "trip_id T1 stop_sequence 1 (and potentially more for this trip)"),
    ),
    "03-seq-e036.pb": (
        ("E002", "trip_id 9999 stop_sequence [-1, -1]"),
        ("E003", "trip_id 9999"),
        ("E017", "header.timestamp of 1700000000"),
        ("E036", "trip_id 9999 has repeating stop_sequence -1"),
        ("W002", "trip_id 9999"),
        ("W009", "trip_id 9999"),
        ("W009", "trip_id 9999 stop_sequence -1 (and potentially more for this trip)"),
    ),
    "04-seq-e002.pb": (
        ("E002", "trip_id 9999 stop_sequence [-1, -2]"),
        ("E003", "trip_id 9999"),
        ("E017", "header.timestamp of 1700000000"),
        ("W002", "trip_id 9999"),
        ("W009", "trip_id 9999"),
        ("W009", "trip_id 9999 stop_sequence -1 (and potentially more for this trip)"),
    ),
    "05-seq-timestamp.pb": (
        ("E001", "trip_id 9999 stop_sequence -1 arrival_time 1"),
        ("E003", "trip_id 9999"),
        ("E017", "header.timestamp of 1700000000"),
        ("W002", "trip_id 9999"),
        ("W009", "trip_id 9999"),
        ("W009", "trip_id 9999 stop_sequence -1 (and potentially more for this trip)"),
    ),
    "06-direction.pb": (
        ("E017", "header.timestamp of 1700000000"),
        ("E019", _E019),
        ("E024", "GTFS-rt trip_id T1 trip.direction_id is -1 but GTFS trip.direction_id is 0"),
        ("E041", "trip_id T1"),
        ("W001", "trip_id T1"),
        ("W002", "trip_id T1"),
        ("W009", "trip_id T1"),
    ),
    "07-ts-entities.pb": (
        ("E001", "alert in entity e3 active_period.end -2"),
        ("E001", "alert in entity e3 active_period.start -1"),
        ("E001", "header.timestamp"),
        ("E001", "trip_id T1 timestamp -1"),
        ("E001", "vehicle_id v1 timestamp -1"),
        ("E012", "trip_id T1 timestamp -1"),
        ("E012", "vehicle_id v1 timestamp -1"),
        ("E018", "header.timestamp of -2 is less than the header.timestamp of 1700000000"),
        ("E019", _E019_WRAPPED),
        ("E019", _E019),
        ("E032", "alert ID e3 does not have an informed_entity"),
        ("E041", "trip_id T1"),
        ("W002", "trip_id T1"),
        ("W003", "vehicle_id v1 is in VehiclePositions but not in TripUpdates feed"),
        ("W009", "trip_id T1"),
        ("W009", "trip_id T1"),
    ),
    "08-ts-equal-a.pb": (
        ("E001", "header.timestamp"),
        ("E012", "trip_id T1 timestamp 1700000000"),
        ("E017", "header.timestamp of -2"),
        ("E019", _E019),
        ("E041", "trip_id T1"),
        ("W002", "trip_id T1"),
        ("W009", "trip_id T1"),
    ),
    "09-ts-equal-b.pb": (
        ("E001", "header.timestamp"),
        ("E003", "trip_id T2"),
        ("E012", "trip_id T2 timestamp 1700000000"),
        ("E017", "header.timestamp of -2"),
        ("E041", "trip_id T2"),
        ("W002", "trip_id T2"),
        ("W009", "trip_id T2"),
    ),
    "10-ts-decrease.pb": (
        ("E001", "header.timestamp"),
        ("E012", "trip_id T1 timestamp 1700000000"),
        ("E018", "header.timestamp of -4 is less than the header.timestamp of -2"),
        ("E019", _E019),
        ("E041", "trip_id T1"),
        ("W002", "trip_id T1"),
        ("W009", "trip_id T1"),
    ),
    "11-seq-w009.pb": (
        ("E019", _E019),
        ("E051", "GTFS-rt trip_id T1 contains stop_sequence -1"),
        ("W002", "trip_id T1"),
        ("W007", "1700000004 second interval between consecutive header.timestamps"),
        ("W009", "trip_id T1 stop_sequence -1 (and potentially more for this trip)"),
    ),
}


def expected(name: str) -> list[tuple[str, str]]:
    """One feed's pins, sorted, ready to compare against a run's own sorted pairs."""
    return sorted(PINS[name])
