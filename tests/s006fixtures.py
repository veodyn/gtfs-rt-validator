"""The static tables and message builders `test_rule_s006.py` runs against.

Split out at the file cap, the way `p015fixtures.py` is. S006 is the one spec
rule whose finding depends on *where in the trip* a stop sits, so it needs more
than one shape of `stop_times.txt`: a trip whose last row carries one time, a
trip whose last row carries two, a trip of a single stop, and a trip that
visits the same stop twice. Each is a named table here rather than four
dictionaries inlined at four call sites.

`minimal_tables()` gives T1 two stops, S1 then S2, both rows carrying an
`arrival_time` and a `departure_time`.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.spec.s006 import check
from specfixtures import feed_context, message, minimal

STOP_TIME = SCHEMA.enums["TripUpdate.StopTimeUpdate.ScheduleRelationship"]

#: S3 with a `departure_time` only, which is the half of the clause's
#: antecedent that must *not* fire. Appending it also makes S2 a middle stop.
DEPARTURE_ONLY = {
    "trip_id": "T1",
    "arrival_time": "",
    "departure_time": "25:10:00",
    "stop_id": "S3",
    "stop_sequence": "3",
    "pickup_type": "0",
}

STOP_S3 = {
    "stop_id": "S3",
    "stop_name": "Third",
    "stop_lat": "28.00",
    "stop_lon": "-82.40",
    "location_type": "0",
}

#: A second visit to S1, so T1 is a loop and `stop_id` alone no longer says
#: which of the trip's rows an update is about.
RETURN_TO_S1 = {
    "trip_id": "T1",
    "arrival_time": "25:15:00",
    "departure_time": "25:15:00",
    "stop_id": "S1",
    "stop_sequence": "4",
    "pickup_type": "0",
}

#: A trip of exactly one stop, which is its own first stop and its own last.
SOLO_TRIP = {
    "trip_id": "T2",
    "route_id": "R1",
    "service_id": "SVC1",
    "direction_id": "0",
    "shape_id": "SH1",
}

SOLO_STOP_TIME = {
    "trip_id": "T2",
    "arrival_time": "25:20:00",
    "departure_time": "25:20:00",
    "stop_id": "S1",
    "stop_sequence": "1",
    "pickup_type": "0",
}


def tables():
    """T1 over S1, S2 and S3, with only the first two rows carrying both times."""
    return minimal(stops=[STOP_S3], stop_times=[DEPARTURE_ONLY])


def loop_tables():
    """T1 over S1, S2 and S1 again, every row carrying both times."""
    return minimal(stop_times=[RETURN_TO_S1])


def solo_tables():
    """T1 as `minimal_tables()` leaves it, plus T2 over a single stop."""
    return minimal(trips=[SOLO_TRIP], stop_times=[SOLO_STOP_TIME])


def update(relationship: str | None = None, **rest: object) -> dict[str, object]:
    built: dict[str, object] = dict(rest)
    if relationship is not None:
        built["schedule_relationship"] = STOP_TIME[relationship]
    return built


def trip_update(*updates: dict[str, object], trip_id: str = "T1") -> dict[str, object]:
    return {"trip": {"trip_id": trip_id}, "stop_time_update": list(updates)}


def run(tmp_path, *entities):
    """S006 over `tables()`, which is what most of the module asks about."""
    return check(message(*entities), feed_context(tmp_path, tables()))


def run_over(tmp_path, built, *entities):
    """`run`, over a table the test named instead of `tables()`."""
    return check(message(*entities), feed_context(tmp_path, built))
