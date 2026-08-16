"""Feeds carrying unsigned fields past the signed maximum, and the archive for them.

protobuf-java 2.6.1 maps `uint32` onto Java's `int` and `uint64` onto `long`,
because Java has no unsigned integer type. Past the signed maximum every getter
therefore hands a rule a **negative** number, and that negative is what upstream
prints, compares, sorts and matches on. This project's decoder returns the true
unsigned value, which is right for the wire and for modern mode, so compat's
rule layer narrows at the read.

What a jar actually wrote for these eleven feeds is `unsignedpins.PINS`, split
into its own module so that the input and the oracle can be read apart.

Feeds are staged in the order given, one mtime apart, because upstream's loop
carries the previous message across files: `08` and `09` exist only so that a
header timestamp can equal the previous one, and `10` only so that one can fall
below it.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA
from gtfsfixtures import build_feed, minimal_tables

__all__ = ["FEEDS", "TS", "U32", "U32B", "U64", "U64B", "static_feed"]

#: 4294967295 is `(int) -1` and 4294967294 is `(int) -2`.
U32 = 4294967295
U32B = 4294967294

#: 18446744073709551615 is `(long) -1` and ...614 is `(long) -2`.
U64 = 18446744073709551615
U64B = 18446744073709551614

#: The header timestamp the uint32 feeds carry, and `run_jar.MTIME_BASE`, so the
#: clock a run reads off a staged file matches it and no feed is stale.
TS = 1_700_000_000


def _feed(entities: list[dict], timestamp: int = TS) -> bytes:
    header = {"gtfs_realtime_version": "1.0", "incrementality": 0, "timestamp": timestamp}
    return encode({"header": header, "entity": entities}, SCHEMA)


def _trip(trip_id: str, **rest: object) -> dict:
    return {"id": "e1", "trip_update": {"trip": {"trip_id": trip_id}, "timestamp": TS, **rest}}


#: Name to bytes, in staging order. `T1` is the one trip of
#: `gtfsfixtures.minimal_tables`, whose two `stop_times.txt` rows are
#: stop_sequences 1 and 2 at stops `S1` and `S2`; `T2` and `9999` are in no
#: `trips.txt` row, which is what keeps the E051 `break` from cutting a trip
#: short before the rule under test has run.
FEEDS: dict[str, bytes] = {
    # The stop_sequence itself, through `_shared/walk_stop_time_updates`.
    "01-seq-e051.pb": _feed([_trip("T1", stop_time_update=[{"stop_sequence": U32}])]),
    # E037's conditional `at stop_sequence` clause, on the second update.
    "02-seq-e037.pb": _feed(
        [
            _trip(
                "T1",
                stop_time_update=[
                    {"stop_sequence": 1, "stop_id": "S1", "arrival": {"delay": 0}},
                    {"stop_sequence": U32, "stop_id": "S1", "arrival": {"delay": 0}},
                ],
            )
        ]
    ),
    # E036's repeated value, on a trip no `stop_times.txt` row carries.
    "03-seq-e036.pb": _feed(
        [
            _trip(
                "9999",
                stop_time_update=[
                    {"stop_sequence": U32, "arrival": {"delay": 0}},
                    {"stop_sequence": U32, "arrival": {"delay": 0}},
                ],
            )
        ]
    ),
    # E002's `List<Integer>.toString()`, descending under both readings.
    "04-seq-e002.pb": _feed(
        [
            _trip(
                "9999",
                stop_time_update=[
                    {"stop_sequence": U32, "arrival": {"delay": 0}},
                    {"stop_sequence": U32B, "arrival": {"delay": 0}},
                ],
            )
        ]
    ),
    # `TimestampValidator`'s own stop description, which is not `GtfsUtils`'.
    "05-seq-timestamp.pb": _feed(
        [_trip("9999", stop_time_update=[{"stop_sequence": U32, "arrival": {"time": 1}}])]
    ),
    # direction_id, against T1, whose GTFS direction_id is `0`.
    "06-direction.pb": _feed(
        [{"id": "e1", "trip_update": {"trip": {"trip_id": "T1", "direction_id": U32}}}]
    ),
    # Every uint64 that reaches occurrence text as a raw number.
    "07-ts-entities.pb": _feed(
        [
            {"id": "e1", "trip_update": {"trip": {"trip_id": "T1"}, "timestamp": U64}},
            {
                "id": "e2",
                "vehicle": {
                    "trip": {"trip_id": "T1"},
                    "vehicle": {"id": "v1"},
                    "timestamp": U64,
                },
            },
            {"id": "e3", "alert": {"active_period": [{"start": U64, "end": U64B}]}},
        ],
        timestamp=U64B,
    ),
    # E017 needs two files whose bytes differ and whose header timestamps do not.
    "08-ts-equal-a.pb": _feed([_trip("T1")], timestamp=U64B),
    "09-ts-equal-b.pb": _feed([_trip("T2")], timestamp=U64B),
    # E018 needs a header below the previous one under both readings.
    "10-ts-decrease.pb": _feed([_trip("T1")], timestamp=U64 - 3),
    # W009's stop_time_update overload, which the trip overload's whole-feed
    # suppression list hides unless the trip itself declares a relationship.
    "11-seq-w009.pb": _feed(
        [
            {
                "id": "e1",
                "trip_update": {
                    "trip": {"trip_id": "T1", "schedule_relationship": 0},
                    "timestamp": TS,
                    "stop_time_update": [{"stop_sequence": U32, "arrival": {"delay": 0}}],
                },
            }
        ]
    ),
}


def static_feed(directory: Path) -> Path:
    """The GTFS archive both runs validate against, written under `directory`.

    `gtfsfixtures.minimal_tables` rather than `tests/fixtures/gtfs/testagency.zip`,
    because these eleven feeds are about unsigned wire values and a two-row
    archive is the smallest thing that carries the trip they name. Compat reads
    testagency fine now that it reads the static feed as onebusaway does; it
    could not while both modes went through the strict path, and that used to be
    the reason recorded here.
    """
    return build_feed(directory, minimal_tables())
