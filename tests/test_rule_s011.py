"""S011: `StopTimeUpdate.stop_id` disagreeing with `assigned_stop_id`.

Both must be populated for the clause to have an antecedent. The sentence
before it, "If this field is populated, it is preferred to omit
`StopTimeUpdate.stop_id`", is the advice; this is the constraint on a producer
who did not take it.

Not E011, which asks whether a `stop_id` is in `stops.txt`: this one compares
two fields of the feed against each other and never opens the static feed.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.spec.s011 import check
from specfixtures import context, entity, message, prefixes


def update(stop_id: str | None = None, assigned: str | None = None) -> dict[str, object]:
    built: dict[str, object] = {}
    if stop_id is not None:
        built["stop_id"] = stop_id
    if assigned is not None:
        built["stop_time_properties"] = {"assigned_stop_id": assigned}
    return built


def trip_update(*updates: dict[str, object]) -> dict[str, object]:
    return {"trip": {"trip_id": "T1"}, "stop_time_update": list(updates)}


def run(*entities):
    return check(message(*entities), context())


def test_the_two_agreeing_is_what_the_clause_asks_for():
    assert prefixes(run(entity(trip_update=trip_update(update("A", "A"))))) == []


def test_the_two_disagreeing_is_reported():
    found = run(entity(trip_update=trip_update(update("A", "B"))))

    assert prefixes(found) == [
        "trip_id T1 stop_time_update[0] stop_id A does not match assigned_stop_id B"
    ]


def test_an_assigned_stop_id_with_no_stop_id_is_the_preferred_shape():
    assert prefixes(run(entity(trip_update=trip_update(update(assigned="B"))))) == []


def test_a_stop_id_with_no_assigned_stop_id_has_no_antecedent():
    assert prefixes(run(entity(trip_update=trip_update(update("A"))))) == []


def test_stop_time_properties_with_no_assigned_stop_id_is_not_populated():
    found = run(
        entity(
            trip_update={
                "trip": {"trip_id": "T1"},
                "stop_time_update": [
                    {"stop_id": "A", "stop_time_properties": {"stop_headsign": "X"}}
                ],
            }
        )
    )

    assert prefixes(found) == []


def test_an_empty_string_on_either_side_is_still_populated():
    """Presence, not truth. A producer that wrote `stop_id = ""` beside an
    assigned stop has written two values that do not match."""
    found = run(entity(trip_update=trip_update(update("", "B"))))

    assert prefixes(found) == [
        "trip_id T1 stop_time_update[0] stop_id  does not match assigned_stop_id B"
    ]


def test_each_offending_update_reports_once():
    found = run(entity(trip_update=trip_update(update("A", "A"), update("A", "B"))))

    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.stop_time_update[1]"
    ]
    assert [occurrence.rule_id for occurrence in found] == ["S011"]
