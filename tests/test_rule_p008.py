"""P008: a live TripUpdate that predicts nothing in the future.

The clock is `specfixtures.READING`, a fixed 1_700_000_000_000 milliseconds, so
"the future" here is any `time` strictly greater than 1_700_000_000 seconds and
nothing in these fixtures depends on when the suite runs.

Four silences are the point of the file. A TripUpdate with **one** future
prediction is the conformant twin. A TripUpdate with **no** stop_time_updates
is E041's finding and not this rule's, which is what keeps the declared overlap
with E041 honest. A CANCELED or DELETED trip is asserting nothing about a journey in
progress. And a trip whose **every** stop_time_update is SKIPPED is P007's
finding: that was 90.2 percent of this rule's firing on a real agency, and the
last section of this module is where the two rules are checked for a gap
between them rather than only for the overlap that was removed.

The boundary is asserted in both directions, because "in the future" against a
clock is exactly where an off-by-one hides: a prediction for the clock's own
second is not in the future and one second later is.

`stop_time_update` and `StopTimeEvent.time` are both 2015-visible, so the
violating fixture is whole to the jar. `DELETED = 7` is not in the 2015 trip
enum, so the exempt fixture reads there as a SCHEDULED trip with past
predictions.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.practice.p007 import check as p007
from gtfs_rt_validator.rules.practice.p008 import check
from specfixtures import context, entity, message, occurrences, prefixes

TRIP = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]
STOP_TIME = SCHEMA.enums["TripUpdate.StopTimeUpdate.ScheduleRelationship"]

#: `specfixtures.READING` in seconds, which is what a `StopTimeEvent.time` is in.
NOW = 1_700_000_000

#: Every member of the trip enum, so the partition test below cannot go stale
#: by forgetting one a later pin adds.
TRIP_RELATIONSHIPS = tuple(sorted(TRIP))

#: The three an all-SKIPPED trip is blessed by: `:51`'s remedy and its two
#: "unless" members. P007 exempts all three and P008 now exempts every
#: all-SKIPPED trip, so these are the trips both rules pass over.
BLESSED = {"CANCELED", "NEW", "DUPLICATED"}


def stop_time(sequence: int, **events: object) -> dict[str, object]:
    return {"stop_sequence": sequence, **events}


def skipped(sequence: int, **events: object) -> dict[str, object]:
    """A stop the vehicle will not call at. `:246` makes its times optional."""
    return {"stop_sequence": sequence, "schedule_relationship": STOP_TIME["SKIPPED"], **events}


def trip_update(
    *updates: dict[str, object], trip_id: str = "T1", relationship: str | None = None
) -> dict[str, object]:
    trip: dict[str, object] = {"trip_id": trip_id}
    if relationship is not None:
        trip["schedule_relationship"] = TRIP[relationship]
    return {"trip": trip, "stop_time_update": list(updates)}


def run(*entities):
    return check(message(*entities), context())


def reported(count: int = 2, trip_id: str = "T1") -> str:
    return (
        f"trip_id {trip_id} has {count} stop_time_updates and none of them predicts "
        f"an arrival or departure after {NOW}"
    )


def test_a_trip_predicting_only_the_past_is_reported():
    found = run(
        entity(
            trip_update=trip_update(
                stop_time(1, arrival={"time": NOW - 600}),
                stop_time(2, departure={"time": NOW - 60}),
            )
        )
    )

    assert prefixes(found) == [reported()]


def test_one_future_prediction_is_enough_to_be_silent():
    """The conformant twin: the same two stops, the second one still ahead."""
    found = run(
        entity(
            trip_update=trip_update(
                stop_time(1, arrival={"time": NOW - 600}),
                stop_time(2, departure={"time": NOW + 60}),
            )
        )
    )

    assert prefixes(found) == []


def test_a_prediction_for_the_clocks_own_second_is_not_the_future():
    """The boundary, on the reported side. "In the future" is strict."""
    found = run(entity(trip_update=trip_update(stop_time(1, arrival={"time": NOW}))))

    assert prefixes(found) == [reported(count=1)]


def test_one_second_later_is_the_future():
    """The boundary, on the silent side."""
    found = run(entity(trip_update=trip_update(stop_time(1, arrival={"time": NOW + 1}))))

    assert prefixes(found) == []


@pytest.mark.parametrize("event", ["arrival", "departure"])
def test_either_event_can_carry_the_prediction(event: str):
    found = run(entity(trip_update=trip_update(stop_time(1, **{event: {"time": NOW + 60}}))))

    assert prefixes(found) == []


def test_an_event_stating_only_a_delay_predicts_no_time_at_all():
    """`StopTimeEvent` can carry `delay` without `time`, and a delay is not a
    predicted arrival time: the sentence asks for one."""
    found = run(entity(trip_update=trip_update(stop_time(1, arrival={"delay": 600}))))

    assert prefixes(found) == [reported(count=1)]


def test_a_stop_time_update_with_neither_event_predicts_nothing():
    found = run(entity(trip_update=trip_update(stop_time(1), stop_time(2))))

    assert prefixes(found) == [reported()]


@pytest.mark.parametrize("relationship", ["CANCELED", "DELETED"])
def test_a_cancelled_or_deleted_trip_asserts_nothing_about_a_journey(relationship: str):
    found = run(
        entity(
            trip_update=trip_update(
                stop_time(1, arrival={"time": NOW - 600}), relationship=relationship
            )
        )
    )

    assert prefixes(found) == []


@pytest.mark.parametrize("relationship", ["SCHEDULED", "ADDED", "UNSCHEDULED", "NEW"])
def test_every_other_relationship_is_in_scope(relationship: str):
    found = run(
        entity(
            trip_update=trip_update(
                stop_time(1, arrival={"time": NOW - 600}), relationship=relationship
            )
        )
    )

    assert prefixes(found) == [reported(count=1)]


def test_a_trip_whose_every_stop_is_skipped_is_p007s_finding():
    """Measured over the recorded MBTA feed: 618 of P008's 685 occurrences, 90.2
    percent, were trips P007 already reported. The mechanism is mechanical, so
    the overlap is not a coincidence of one agency: a trip whose every
    stop_time_update is SKIPPED carries no time anywhere, so it cannot carry a
    prediction, so P008 reported it necessarily."""
    assert prefixes(run(entity(trip_update=trip_update(skipped(1), skipped(2))))) == []


def test_a_skipped_trip_carrying_past_times_is_still_p007s_finding():
    """`:246` makes a SKIPPED stop's times optional rather than forbidden, so
    the exemption reads the relationships and not the absence of times."""
    found = run(
        entity(
            trip_update=trip_update(
                skipped(1, arrival={"time": NOW - 600}),
                skipped(2, departure={"time": NOW - 60}),
            )
        )
    )

    assert prefixes(found) == []


def test_one_stop_still_being_called_at_leaves_the_trip_in_scope():
    """The narrowing is "every update is SKIPPED", not "any update is". A trip
    with one stop left to serve and no prediction for it is this rule's."""
    found = run(
        entity(trip_update=trip_update(skipped(1), stop_time(2, arrival={"time": NOW - 60})))
    )

    assert prefixes(found) == [reported()]


@pytest.mark.parametrize("relationship", TRIP_RELATIONSHIPS)
def test_an_all_skipped_trip_escapes_both_rules_only_where_both_clauses_bless_it(
    relationship: str,
):
    """The gap check the narrowing owes. P008 is now silent on every all-SKIPPED
    trip, so P007 has to be the one that reports it, and the trips neither
    reports must be exactly the three `:51` exempts by name."""
    feed = message(
        entity(trip_update=trip_update(skipped(1), skipped(2), relationship=relationship))
    )
    ctx = context()

    assert prefixes(check(feed, ctx)) == []
    assert bool(prefixes(p007(feed, ctx))) is (relationship not in BLESSED)


def test_a_trip_update_with_no_stop_time_updates_is_e041s_finding():
    """The conjunct that keeps the two disjoint. E041 already reports a
    non-CANCELED TripUpdate carrying no updates, and "at least one
    stop_time_update" is also half of this rule's proxy for a trip in progress:
    without one, no producer is asserting a live prediction."""
    assert prefixes(run(entity(trip_update=trip_update()))) == []


@pytest.mark.parametrize("payload", ["vehicle", "alert"])
def test_only_trip_updates_are_in_scope(payload: str):
    """The sentence names `TripUpdates`, and nothing else carries a
    stop_time_update to look at."""
    payloads = {
        "vehicle": {"trip": {"trip_id": "T1"}},
        "alert": {"informed_entity": [{"trip": {"trip_id": "T1"}}]},
    }

    assert prefixes(run(entity(**{payload: payloads[payload]}))) == []


def test_every_trip_is_examined_in_feed_order():
    found = run(
        entity(trip_update=trip_update(stop_time(1, arrival={"time": NOW - 60})), entity_id="A"),
        entity(trip_update=trip_update(stop_time(1, arrival={"time": NOW + 60})), entity_id="B"),
        entity(
            trip_update=trip_update(stop_time(1), trip_id="T3"),
            entity_id="C",
        ),
    )

    assert prefixes(found) == [reported(count=1), reported(count=1, trip_id="T3")]


def test_the_occurrence_locates_the_trip_update_and_carries_this_rules_id():
    found = occurrences(
        run(
            entity(
                trip_update=trip_update(stop_time(1, arrival={"time": NOW + 60})), entity_id="A"
            ),
            entity(trip_update=trip_update(stop_time(1)), entity_id="B"),
        )
    )

    assert [one.rule_id for one in found] == ["P008"]
    assert [one.context["entityPath"] for one in found] == ["entity[1].trip_update"]
    assert [one.context["tripId"] for one in found] == ["T1"]
    assert [one.context["stopTimeUpdateCount"] for one in found] == [1]
