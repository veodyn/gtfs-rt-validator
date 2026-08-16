"""S008: an UNSCHEDULED stop_time_update on a trip that is not frequency-based.

The mirror of S007 and a different clause: `:259` says which trips may *not*
use the value, where `:242` says which trips should. Both halves of the sentence
are one predicate here, because a trip absent from `frequencies.txt` and a trip
present with `exact_times = 1` are the two ways of not being in
`exact_times_zero_trip_ids`.

A descriptor with no `trip_id` names no trip, so there is no GTFS row to decide
against and the rule says nothing. W006 is the rule about the missing trip_id.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.spec.s008 import check
from specfixtures import entity, feed_context, message, minimal, prefixes

STOP_TIME = SCHEMA.enums["TripUpdate.StopTimeUpdate.ScheduleRelationship"]


def tables(exact_times: str = "1"):
    built = minimal()
    built["frequencies.txt"][0]["exact_times"] = exact_times
    return built


def update(relationship: str | None = "UNSCHEDULED") -> dict[str, object]:
    built: dict[str, object] = {"stop_id": "S1"}
    if relationship is not None:
        built["schedule_relationship"] = STOP_TIME[relationship]
    return built


def trip_update(*updates: dict[str, object], **descriptor: object) -> dict[str, object]:
    trip: dict[str, object] = {"trip_id": "T1"} if not descriptor else dict(descriptor)
    return {"trip": trip, "stop_time_update": list(updates)}


def run(tmp_path, *entities, exact_times: str = "1"):
    return check(message(*entities), feed_context(tmp_path, tables(exact_times)))


def test_an_exact_times_zero_trip_may_use_it(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update(update())), exact_times="0")

    assert prefixes(found) == []


def test_an_exact_times_one_trip_may_not(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update(update())))

    assert prefixes(found) == [
        "trip_id T1 stop_time_update[0] is UNSCHEDULED on a trip that is not exact_times=0"
    ]


def test_a_trip_absent_from_frequencies_txt_may_not_either(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update(update(), trip_id="T2")))

    assert prefixes(found) == [
        "trip_id T2 stop_time_update[0] is UNSCHEDULED on a trip that is not exact_times=0"
    ]


def test_a_scheduled_update_is_not_in_scope(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update(update("SCHEDULED"))))

    assert prefixes(found) == []


def test_an_absent_relationship_is_not_unscheduled(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update(update(None))))

    assert prefixes(found) == []


def test_a_descriptor_with_no_trip_id_names_no_trip(tmp_path):
    """Nothing to look up in `frequencies.txt`, so nothing to say. W006 is the
    rule about the missing trip_id."""
    found = run(tmp_path, entity(trip_update=trip_update(update(), route_id="R1")))

    assert prefixes(found) == []


def test_every_unscheduled_update_of_the_trip_reports(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update(update(), update("SCHEDULED"), update())))

    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.stop_time_update[0]",
        "entity[0].trip_update.stop_time_update[2]",
    ]
    assert [occurrence.rule_id for occurrence in found] == ["S008", "S008"]
