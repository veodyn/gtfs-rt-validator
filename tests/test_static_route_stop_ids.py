"""`StaticContext.route_stop_ids`, the one member with no `GtfsMetadata` counterpart.

Every other member of `StaticContext` is a field of upstream's `GtfsMetadata`
under a snake_case name, and `tests/test_static_context.py` pins that list. This
one is not: upstream never needs a route-to-stops map because none of its 56
rules asks the question, and P012 does. So its expectations come from the join
it performs rather than from any Java, and its own file exists because
`test_static_context.py` is at the file cap.

The claim under test that matters most is the one that is not about a value:
this is derived from `trips` and `trip_stop_times`, both already built, so
`static/adapter.py`'s "the exact set a realtime run reads" comment over its
seven tables stays true. `test_it_reads_no_table_the_seven_do_not_already_cover`
is that claim, asserted rather than left to a docstring.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.static.adapter import SEVEN_TABLES, load_static
from gtfs_rt_validator.static.context import StaticContext
from gtfsfixtures import build_feed, minimal_tables


def context_from(tmp_path: Path, tables) -> StaticContext:
    return StaticContext.build(load_static(build_feed(tmp_path, tables)))


def trip(trip_id: str, route_id: str) -> dict[str, object]:
    return {"trip_id": trip_id, "route_id": route_id, "service_id": "SVC1", "direction_id": "0"}


def stop_time(trip_id: str, stop_id: str, sequence: str) -> dict[str, object]:
    return {
        "trip_id": trip_id,
        "arrival_time": "07:00:00",
        "departure_time": "07:00:00",
        "stop_id": stop_id,
        "stop_sequence": sequence,
    }


def route(route_id: str) -> dict[str, object]:
    return {
        "route_id": route_id,
        "agency_id": "A1",
        "route_short_name": route_id,
        "route_type": "3",
    }


def test_a_routes_stops_are_the_union_over_its_trips(tmp_path):
    """Two trips of one route, each visiting one stop the other does not."""
    tables = minimal_tables()
    tables["trips.txt"] = [trip("T1", "R1"), trip("T2", "R1")]
    tables["stop_times.txt"] = [
        stop_time("T1", "S1", "1"),
        stop_time("T1", "S2", "2"),
        stop_time("T2", "S2", "1"),
        stop_time("T2", "S3", "2"),
    ]
    tables["stops.txt"].append(
        {"stop_id": "S3", "stop_name": "S3", "stop_lat": "40", "stop_lon": "-73"}
    )

    ctx = context_from(tmp_path, tables)

    assert ctx.route_stop_ids == {"R1": frozenset({"S1", "S2", "S3"})}


def test_two_routes_do_not_pool_their_stops(tmp_path):
    tables = minimal_tables()
    tables["routes.txt"].append(route("R2"))
    tables["trips.txt"] = [trip("T1", "R1"), trip("T2", "R2")]
    tables["stop_times.txt"] = [stop_time("T1", "S1", "1"), stop_time("T2", "S2", "1")]

    ctx = context_from(tmp_path, tables)

    assert ctx.route_stop_ids == {"R1": frozenset({"S1"}), "R2": frozenset({"S2"})}


def test_a_repeated_stop_is_one_member(tmp_path):
    """It is a set of stops served, not a count of visits. A loop route that
    returns to its first stop names that stop once."""
    tables = minimal_tables()
    tables["stop_times.txt"] = [
        stop_time("T1", "S1", "1"),
        stop_time("T1", "S2", "2"),
        stop_time("T1", "S1", "3"),
    ]

    ctx = context_from(tmp_path, tables)

    assert ctx.route_stop_ids == {"R1": frozenset({"S1", "S2"})}


def test_a_route_whose_trips_visit_nothing_is_absent_rather_than_empty(tmp_path):
    """`trips_with_multi_stops`'s own convention, and here it is load bearing.

    P012 fires when an alert names every stop of a route. An empty entry would
    satisfy "every stop of R2" for an alert naming any stop at all, because the
    empty set is a subset of everything, so an absent key is the answer that
    cannot be misread.
    """
    tables = minimal_tables()
    tables["routes.txt"].append(route("R2"))
    tables["trips.txt"] = [trip("T1", "R1"), trip("T2", "R2")]
    tables["stop_times.txt"] = [stop_time("T1", "S1", "1")]

    ctx = context_from(tmp_path, tables)

    assert ctx.route_stop_ids == {"R1": frozenset({"S1"})}
    assert "R2" not in ctx.route_stop_ids


def test_a_route_with_no_trips_at_all_is_absent(tmp_path):
    tables = minimal_tables()
    tables["routes.txt"].append(route("R2"))

    ctx = context_from(tmp_path, tables)

    assert set(ctx.route_stop_ids) == {"R1"}


def test_a_stop_time_for_a_trip_no_trips_row_declares_belongs_to_no_route(tmp_path):
    """The join walks `trips`, so an orphan `stop_times.txt` row has no route to
    join to. `trip_stop_times` still holds it, which is the sibling's behaviour
    that `test_static_context.py` measures; it just reaches no route here."""
    tables = minimal_tables()
    tables["stop_times.txt"] = [stop_time("T1", "S1", "1"), stop_time("T9", "S2", "1")]

    ctx = context_from(tmp_path, tables)

    assert ctx.route_stop_ids == {"R1": frozenset({"S1"})}
    assert "T9" in ctx.trip_stop_times


def test_the_values_are_frozen(tmp_path):
    """P012 holds one of these across a whole message. A mutable set handed out
    of the static context would let a rule edit the feed for every later rule."""
    ctx = context_from(tmp_path, minimal_tables())

    assert all(isinstance(value, frozenset) for value in ctx.route_stop_ids.values())


def test_it_reads_no_table_the_seven_do_not_already_cover(tmp_path):
    """The eighth-table claim, asserted rather than promised in a docstring.

    `trips.txt` and `stop_times.txt` are two of the seven and are already loaded
    for `trips` and `trip_stop_times`. Nothing else is consulted, which this
    shows by rebuilding the map from those two members alone and getting the
    same answer.
    """
    tables = minimal_tables()
    tables["trips.txt"] = [trip("T1", "R1"), trip("T2", "R1")]
    tables["stop_times.txt"] = [stop_time("T1", "S1", "1"), stop_time("T2", "S2", "1")]

    ctx = context_from(tmp_path, tables)

    rebuilt: dict[str, set[str]] = {}
    for trip_id, row in ctx.trips.items():
        for stop in ctx.trip_stop_times.get(trip_id, []):
            rebuilt.setdefault(row["route_id"], set()).add(stop.stop_id)
    assert ctx.route_stop_ids == {key: frozenset(value) for key, value in rebuilt.items()}
    assert "trips.txt" in SEVEN_TABLES and "stop_times.txt" in SEVEN_TABLES
