"""S005: `departure_occupancy_status` with no arrival, no departure and no NO_DATA.

The clause tells a producer how to say "I have an occupancy prediction and no
time prediction": set the stop_time_update's schedule_relationship to NO_DATA,
whose own comment at `:250` says "Neither arrival nor departure should be
supplied". So the three conditions are one shape, and a WARNING because the
sentence says `should`.

The relationship read is the stop_time_update's, which is the one the sentence
names, and not the trip's.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.spec.s005 import check
from specfixtures import context, entity, message, prefixes

STOP_TIME = SCHEMA.enums["TripUpdate.StopTimeUpdate.ScheduleRelationship"]
MANY_SEATS = SCHEMA.enums["VehiclePosition.OccupancyStatus"]["MANY_SEATS_AVAILABLE"]


def update(relationship: str | None = None, **rest: object) -> dict[str, object]:
    built: dict[str, object] = {"stop_id": "S1", **rest}
    if relationship is not None:
        built["schedule_relationship"] = STOP_TIME[relationship]
    return built


def trip_update(*updates: dict[str, object]) -> dict[str, object]:
    return {"trip": {"trip_id": "T1"}, "stop_time_update": list(updates)}


def run(*entities):
    return check(message(*entities), context())


def test_no_data_is_what_the_clause_asks_for():
    found = run(
        entity(
            trip_update=trip_update(
                update("NO_DATA", departure_occupancy_status=MANY_SEATS),
            )
        )
    )

    assert prefixes(found) == []


def test_an_arrival_beside_it_is_not_a_finding():
    found = run(
        entity(
            trip_update=trip_update(
                update(departure_occupancy_status=MANY_SEATS, arrival={"time": 1})
            )
        )
    )

    assert prefixes(found) == []


def test_a_departure_beside_it_is_not_a_finding():
    found = run(
        entity(
            trip_update=trip_update(
                update(departure_occupancy_status=MANY_SEATS, departure={"time": 1})
            )
        )
    )

    assert prefixes(found) == []


def test_an_empty_departure_still_counts_as_supplied():
    """Presence, not content: `hasDeparture()` is what the sentence asks about,
    and an empty StopTimeEvent is E044's business rather than this rule's."""
    found = run(
        entity(trip_update=trip_update(update(departure_occupancy_status=MANY_SEATS, departure={})))
    )

    assert prefixes(found) == []


def test_neither_event_and_not_no_data_is_reported():
    found = run(entity(trip_update=trip_update(update(departure_occupancy_status=MANY_SEATS))))

    assert prefixes(found) == [
        "trip_id T1 stop_time_update[0] has only departure_occupancy_status but is SCHEDULED"
    ]


def test_a_skipped_update_is_still_reported():
    """SKIPPED makes arrival and departure optional (`:246`) but says nothing
    about occupancy, so the clause's own remedy is still NO_DATA."""
    found = run(
        entity(trip_update=trip_update(update("SKIPPED", departure_occupancy_status=MANY_SEATS)))
    )

    assert prefixes(found) == [
        "trip_id T1 stop_time_update[0] has only departure_occupancy_status but is SKIPPED"
    ]


def test_an_update_with_no_occupancy_status_is_not_a_finding():
    found = run(entity(trip_update=trip_update(update())))

    assert prefixes(found) == []


def test_the_occurrence_locates_the_update_and_carries_this_rules_id():
    found = run(
        entity(trip_update=trip_update(update(), update(departure_occupancy_status=MANY_SEATS)))
    )

    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.stop_time_update[1]"
    ]
    assert [occurrence.rule_id for occurrence in found] == ["S005"]
