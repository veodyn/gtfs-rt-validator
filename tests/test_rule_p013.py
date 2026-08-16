"""P013: `StopTimeEvent.delay` on a stop_time_update of an exact_times=0 trip.

A frequency-based trip with `exact_times=0` has no scheduled departure, so
there is nothing for a delay to be measured from. The overlap with E046 is the
thing to keep straight and the last test states it: E046 asks whether GTFS has
arrival or departure times for the delay to be added to, and this rule says the
delay should not be there at all. Different questions, and the fixtures differ
in which one they answer.

Everything here is 2015-visible: `delay`, `StopTimeEvent` and
`frequencies.txt` all predate the current schema, so the jar reads this fixture
whole and will have its own opinions about it.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.rules.practice.p013 import check
from specfixtures import entity, feed_context, message, minimal, prefixes


def tables(exact_times: str = "0"):
    built = minimal()
    built["frequencies.txt"][0]["exact_times"] = exact_times
    return built


def stop_time(sequence: int, **events: object) -> dict[str, object]:
    return {"stop_sequence": sequence, "stop_id": f"S{sequence}", **events}


def trip_update(*updates: dict[str, object], trip_id: str = "T1", **rest: object):
    return {"trip": {"trip_id": trip_id}, "stop_time_update": list(updates), **rest}


def run(tmp_path, *entities, exact_times: str = "0"):
    return check(message(*entities), feed_context(tmp_path, tables(exact_times)))


def reported(index: int, event: str) -> str:
    return f"trip_id T1 stop_time_update[{index}] {event} has delay on an exact_times=0 trip"


def test_a_delay_on_a_frequency_trip_is_reported(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update(stop_time(1, arrival={"delay": 30}))))

    assert prefixes(found) == [reported(0, "arrival")]


def test_a_time_instead_of_a_delay_is_silent(tmp_path):
    """The conformant twin, and the clause's own remedy: "`time` should be
    provided to indicate arrival/departure predictions"."""
    found = run(
        tmp_path, entity(trip_update=trip_update(stop_time(1, arrival={"time": 1_700_000_000})))
    )

    assert prefixes(found) == []


def test_a_delay_of_zero_is_still_a_delay(tmp_path):
    """proto2 presence, not truthiness. A producer that states a delay of zero
    on a trip with no schedule has still stated a deviation from nothing."""
    found = run(tmp_path, entity(trip_update=trip_update(stop_time(1, departure={"delay": 0}))))

    assert prefixes(found) == [reported(0, "departure")]


def test_an_empty_exact_times_cell_reads_as_zero(tmp_path):
    """`GtfsMetadata` types the column as a primitive int, so blank is 0 and the
    set is the same one E006, E013 and W005 read."""
    found = run(
        tmp_path,
        entity(trip_update=trip_update(stop_time(1, arrival={"delay": 30}))),
        exact_times="",
    )

    assert prefixes(found) == [reported(0, "arrival")]


def test_an_exact_times_one_trip_is_out_of_scope(tmp_path):
    """An `exact_times=1` trip does have a fixed schedule, so a delay against it
    means something. P011 is the rule about that trip's start_time."""
    found = run(
        tmp_path,
        entity(trip_update=trip_update(stop_time(1, arrival={"delay": 30}))),
        exact_times="1",
    )

    assert prefixes(found) == []


def test_a_trip_absent_from_frequencies_txt_is_out_of_scope(tmp_path):
    found = run(
        tmp_path,
        entity(trip_update=trip_update(stop_time(1, arrival={"delay": 30}), trip_id="T2")),
    )

    assert prefixes(found) == []


def test_both_events_of_one_update_report_separately_arrival_first(tmp_path):
    found = run(
        tmp_path,
        entity(
            trip_update=trip_update(stop_time(1, arrival={"delay": 30}, departure={"delay": 45}))
        ),
    )

    assert prefixes(found) == [reported(0, "arrival"), reported(0, "departure")]


def test_every_stop_time_update_is_examined(tmp_path):
    found = run(
        tmp_path,
        entity(
            trip_update=trip_update(
                stop_time(1, arrival={"time": 1_700_000_000}),
                stop_time(2, departure={"delay": 60}),
            )
        ),
    )

    assert prefixes(found) == [reported(1, "departure")]


def test_the_trip_updates_own_delay_field_is_not_this_clause(tmp_path):
    """The sentence names `TripUpdate.StopTimeUpdate`'s `StopTimeEvent`.
    `TripUpdate.delay` is a different field with a different meaning, and `:62`
    is the statement about it; the verdict file rejects that one under R3."""
    found = run(tmp_path, entity(trip_update=trip_update(stop_time(1), delay=90)))

    assert prefixes(found) == []


@pytest.mark.parametrize("payload", ["vehicle", "alert"])
def test_only_trip_updates_carry_stop_time_updates(tmp_path, payload):
    payloads = {
        "vehicle": {"trip": {"trip_id": "T1"}},
        "alert": {"informed_entity": [{"trip": {"trip_id": "T1"}}]},
    }

    assert prefixes(run(tmp_path, entity(**{payload: payloads[payload]}))) == []


def test_the_occurrence_locates_the_event_and_carries_this_rules_id(tmp_path):
    found = run(
        tmp_path,
        entity(trip_update=trip_update(stop_time(1), stop_time(2, departure={"delay": 10}))),
    )

    assert [one.context["entityPath"] for one in found] == [
        "entity[0].trip_update.stop_time_update[1].departure"
    ]
    assert [one.rule_id for one in found] == ["P013"]
    assert [one.context["tripId"] for one in found] == ["T1"]
