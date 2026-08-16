"""P010: a NEW or REPLACEMENT trip whose stop_time_updates state no scheduled_time.

The clause asks for `scheduled_time` "for all timepoints" and this rule asks for
it *somewhere*, which is the narrowing recorded against `106#1` in
`upstream/practice-clause-verdicts.json`. The test that holds the narrowing is
`test_one_scheduled_time_anywhere_is_enough`: a trip with three stops and one
scheduled_time is silent, because this rule cannot know which of the three
`stop_times.timepoint` calls a timepoint.

The last test is the disjointness claim against S004, the spec tier's converse
rule. The two may never fire on one stop_time_update, and asserting it
here is cheaper than discovering it on a real feed.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.practice.p010 import check
from gtfs_rt_validator.rules.spec.s004 import check as s004_check
from specfixtures import context, entity, message, prefixes

RELATIONSHIPS = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]

SCHEDULED_TIME = 1_700_000_000


def stop_time(sequence: int, **events: object) -> dict[str, object]:
    return {"stop_sequence": sequence, "stop_id": f"S{sequence}", **events}


def trip_update(*updates: dict[str, object], relationship: str = "NEW") -> dict[str, object]:
    trip = {"trip_id": "T1", "schedule_relationship": RELATIONSHIPS[relationship]}
    return {"trip": trip, "stop_time_update": list(updates)}


def run(*entities):
    return check(message(*entities), context())


def reported(relationship: str = "NEW") -> str:
    return f"trip_id T1 is {relationship} and no stop_time_update provides a scheduled_time"


def test_a_new_trip_with_no_scheduled_times_is_reported():
    found = run(entity(trip_update=trip_update(stop_time(1), stop_time(2))))

    assert prefixes(found) == [reported()]


def test_a_new_trip_stating_a_scheduled_time_is_silent():
    """The conformant twin: the same two stops, one of them scheduled."""
    found = run(
        entity(
            trip_update=trip_update(
                stop_time(1, arrival={"scheduled_time": SCHEDULED_TIME}), stop_time(2)
            )
        )
    )

    assert prefixes(found) == []


def test_a_scheduled_time_on_the_departure_alone_is_enough():
    found = run(
        entity(trip_update=trip_update(stop_time(1, departure={"scheduled_time": SCHEDULED_TIME})))
    )

    assert prefixes(found) == []


def test_one_scheduled_time_anywhere_is_enough():
    """The narrowing, as an assertion. "For all timepoints" would report this
    trip; which of its three stops is a timepoint comes from
    `stop_times.timepoint`, so this rule asks the half it can answer."""
    found = run(
        entity(
            trip_update=trip_update(
                stop_time(1),
                stop_time(2, arrival={"scheduled_time": SCHEDULED_TIME}),
                stop_time(3),
            )
        )
    )

    assert prefixes(found) == []


def test_a_replacement_trip_is_in_scope_too():
    found = run(entity(trip_update=trip_update(stop_time(1), relationship="REPLACEMENT")))

    assert prefixes(found) == [reported("REPLACEMENT")]


@pytest.mark.parametrize(
    "relationship", ["SCHEDULED", "ADDED", "UNSCHEDULED", "CANCELED", "DUPLICATED"]
)
def test_no_other_relationship_is_in_scope(relationship):
    """DUPLICATED is in the list because the clause says "new or replacement"
    and nothing else. A duplicate copies a trip GTFS already schedules."""
    found = run(entity(trip_update=trip_update(stop_time(1), relationship=relationship)))

    assert prefixes(found) == []


def test_an_absent_schedule_relationship_is_scheduled_and_out_of_scope():
    found = run(entity(trip_update={"trip": {"trip_id": "T1"}, "stop_time_update": [stop_time(1)]}))

    assert prefixes(found) == []


def test_a_new_trip_with_no_stop_time_updates_is_not_this_rules_finding():
    """A trip carrying no stop_time_update has nothing that could carry a
    scheduled_time, and the empty TripUpdate is E041's subject. Firing here
    would report every NEW stub twice under two different ids."""
    found = run(entity(trip_update=trip_update()))

    assert prefixes(found) == []


def test_a_stop_time_event_with_a_time_but_no_scheduled_time_is_still_a_finding():
    """`time` is the prediction and `scheduled_time` is what it deviates from.
    A trip stating only predictions has not said what it was scheduled to do."""
    found = run(entity(trip_update=trip_update(stop_time(1, arrival={"time": SCHEDULED_TIME}))))

    assert prefixes(found) == [reported()]


def test_a_vehicle_position_has_no_stop_time_updates():
    found = run(
        entity(vehicle={"trip": {"trip_id": "T1", "schedule_relationship": RELATIONSHIPS["NEW"]}})
    )

    assert prefixes(found) == []


def test_the_occurrence_locates_the_trip_update_and_carries_this_rules_id():
    found = run(entity(trip_update=trip_update(stop_time(1))))

    assert [one.context["entityPath"] for one in found] == ["entity[0].trip_update"]
    assert [one.rule_id for one in found] == ["P010"]
    assert [one.context["scheduleRelationship"] for one in found] == ["NEW"]


def test_one_occurrence_per_trip_not_per_stop():
    found = run(entity(trip_update=trip_update(stop_time(1), stop_time(2), stop_time(3))))

    assert len(found) == 1


@pytest.mark.parametrize("relationship", ["NEW", "REPLACEMENT", "SCHEDULED", "CANCELED"])
@pytest.mark.parametrize("scheduled", [True, False])
def test_p010_and_s004_can_never_both_fire(relationship, scheduled):
    """S004 reports `scheduled_time` where the proto forbids it and P010 reports
    its absence where the document asks for it. S004's exempt set is NEW,
    REPLACEMENT and DUPLICATED; P010's scope is NEW and REPLACEMENT, a subset of
    it. So the two are disjoint by construction, and this walks the corners."""
    events = {"arrival": {"scheduled_time": SCHEDULED_TIME}} if scheduled else {}
    feed = message(
        entity(trip_update=trip_update(stop_time(1, **events), relationship=relationship))
    )

    both = prefixes(check(feed, context())) and prefixes(s004_check(feed, context()))

    assert not both
