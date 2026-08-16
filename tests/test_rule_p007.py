"""P007: every stop_time_update SKIPPED on a trip that is not cancelled.

The clause's remedy is CANCELED, so the conformant twin of the violating feed
is the same trip with `schedule_relationship = CANCELED` and nothing else
changed. The exemption ("unless the trip was a `NEW` or `DUPLICATED` trip and
was subsequently canceled") gives two more silent cases.

The empty case matters as much as the full one: a TripUpdate with no
stop_time_updates at all vacuously has all of them SKIPPED, and firing there
would be reporting E041's finding under a second id.

`SKIPPED = 1` is in the 2015 stop_time_update enum, so the violating fixture is
whole to the jar. `NEW = 8` and `DUPLICATED = 6` are not in the 2015 trip enum,
so the two exempt fixtures decode there as SCHEDULED trips with all-SKIPPED
updates, which is indistinguishable from the violation. The exemption is only
expressible under the current schema.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.practice.p007 import check
from specfixtures import context, entity, message, occurrences, prefixes

TRIP = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]
STOP_TIME = SCHEMA.enums["TripUpdate.StopTimeUpdate.ScheduleRelationship"]


def stop_time(sequence: int, relationship: str = "SKIPPED") -> dict[str, object]:
    return {"stop_sequence": sequence, "schedule_relationship": STOP_TIME[relationship]}


def trip_update(
    *updates: dict[str, object], trip_id: str = "T1", relationship: str | None = None
) -> dict[str, object]:
    trip: dict[str, object] = {"trip_id": trip_id}
    if relationship is not None:
        trip["schedule_relationship"] = TRIP[relationship]
    return {"trip": trip, "stop_time_update": list(updates)}


def run(*entities):
    return check(message(*entities), context())


def reported(relationship: str = "SCHEDULED", count: int = 2, trip_id: str = "T1") -> str:
    return (
        f"trip_id {trip_id} has all {count} stop_time_updates SKIPPED "
        f"and is {relationship} rather than CANCELED"
    )


def test_a_trip_whose_every_stop_is_skipped_is_reported():
    found = run(entity(trip_update=trip_update(stop_time(1), stop_time(2))))

    assert prefixes(found) == [reported()]


def test_the_same_trip_marked_canceled_is_silent():
    """The conformant twin, and it is the clause's own remedy."""
    found = run(
        entity(trip_update=trip_update(stop_time(1), stop_time(2), relationship="CANCELED"))
    )

    assert prefixes(found) == []


def test_one_stop_still_being_visited_is_silent():
    """ "If no stops in a trip will be visited" is the antecedent, so a single
    unskipped stop takes the trip out of scope however many are skipped."""
    found = run(
        entity(trip_update=trip_update(stop_time(1), stop_time(2, relationship="SCHEDULED")))
    )

    assert prefixes(found) == []


def test_an_undeclared_stop_relationship_defaults_to_scheduled_and_is_a_visit():
    """proto2's default is SCHEDULED, so an update that says nothing says the
    stop will be visited."""
    found = run(entity(trip_update=trip_update(stop_time(1), {"stop_sequence": 2})))

    assert prefixes(found) == []


@pytest.mark.parametrize("relationship", ["NEW", "DUPLICATED"])
def test_a_new_or_duplicated_trip_is_exempt(relationship: str):
    """The clause's own "unless" half. Both are post-2015 members, so this
    silence exists only under the current schema."""
    found = run(
        entity(trip_update=trip_update(stop_time(1), stop_time(2), relationship=relationship))
    )

    assert prefixes(found) == []


@pytest.mark.parametrize("relationship", ["ADDED", "UNSCHEDULED", "REPLACEMENT", "DELETED"])
def test_no_other_relationship_is_exempt(relationship: str):
    """Three values are named by the sentence and nothing else is. DELETED is
    here because it is P008's exemption and not this one's, so a reader cannot
    assume the two rules share a set."""
    found = run(
        entity(trip_update=trip_update(stop_time(1), stop_time(2), relationship=relationship))
    )

    assert prefixes(found) == [reported(relationship)]


def test_a_trip_update_with_no_stop_time_updates_is_e041s_finding():
    """Vacuously every one of zero updates is SKIPPED. Firing here would report
    E041's finding under a second id, which is an overlap this rule does not
    declare."""
    assert prefixes(run(entity(trip_update=trip_update()))) == []


def test_one_skipped_stop_is_enough_to_be_all_of_them():
    assert prefixes(run(entity(trip_update=trip_update(stop_time(1))))) == [reported(count=1)]


@pytest.mark.parametrize("payload", ["vehicle", "alert"])
def test_only_trip_updates_carry_stop_time_updates(payload: str):
    payloads = {
        "vehicle": {"trip": {"trip_id": "T1"}},
        "alert": {"informed_entity": [{"trip": {"trip_id": "T1"}}]},
    }

    assert prefixes(run(entity(**{payload: payloads[payload]}))) == []


def test_every_trip_is_examined_in_feed_order():
    found = run(
        entity(trip_update=trip_update(stop_time(1), stop_time(2)), entity_id="A"),
        entity(trip_update=trip_update(stop_time(1), relationship="CANCELED"), entity_id="B"),
        entity(trip_update=trip_update(stop_time(1), trip_id="T3"), entity_id="C"),
    )

    assert prefixes(found) == [reported(), reported(count=1, trip_id="T3")]


def test_the_occurrence_locates_the_trip_update_and_carries_this_rules_id():
    found = occurrences(
        run(
            entity(trip_update=trip_update(stop_time(1), relationship="CANCELED"), entity_id="A"),
            entity(trip_update=trip_update(stop_time(1)), entity_id="B"),
        )
    )

    assert [one.rule_id for one in found] == ["P007"]
    assert [one.context["entityPath"] for one in found] == ["entity[1].trip_update"]
    assert [one.context["tripId"] for one in found] == ["T1"]
    assert [one.context["scheduleRelationship"] for one in found] == ["SCHEDULED"]
