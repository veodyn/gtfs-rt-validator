"""S051: two `CarriageDetails` of one VehiclePosition sharing an `id`.

"per vehicle" is the scope, so two vehicles may each carry a carriage called
`1`; the same vehicle may not carry two. `CarriageDetails.id` is `optional`, so
the carriages that declare none are not compared against each other: a
`CarriageDetails` with no id is not a carriage called "".
"""

from __future__ import annotations

from gtfs_rt_validator.rules.spec.s051 import check
from specfixtures import context, entity, message, prefixes


def vehicle(*carriages: dict[str, object], trip_id: str = "T1") -> dict[str, object]:
    return {"trip": {"trip_id": trip_id}, "multi_carriage_details": list(carriages)}


def carriage(carriage_id: str | None = None, **rest: object) -> dict[str, object]:
    return dict(rest) if carriage_id is None else {"id": carriage_id, **rest}


def run(*entities):
    return check(message(*entities), context())


def test_distinct_carriage_ids_are_not_a_finding():
    assert prefixes(run(entity(vehicle=vehicle(carriage("A"), carriage("B"))))) == []


def test_a_vehicle_with_no_carriages_is_not_a_finding():
    assert prefixes(run(entity(vehicle=vehicle()))) == []


def test_two_carriages_sharing_an_id_report_once():
    found = run(entity("bus", vehicle=vehicle(carriage("A"), carriage("A"))))

    assert prefixes(found) == ["entity ID bus carriage id A is claimed by 2 carriages"]


def test_two_vehicles_may_each_have_a_carriage_called_a():
    """ "Should be unique per vehicle", and these are two vehicles."""
    found = run(
        entity("one", vehicle=vehicle(carriage("A"), trip_id="T1")),
        entity("two", vehicle=vehicle(carriage("A"), trip_id="T2")),
    )

    assert prefixes(found) == []


def test_carriages_with_no_id_are_not_compared_against_each_other():
    """`id` is optional, so two carriages that declare none are two carriages
    with no id rather than two carriages called ""."""
    found = run(entity(vehicle=vehicle(carriage(), carriage())))

    assert prefixes(found) == []


def test_an_id_written_as_the_empty_string_is_declared_and_is_compared():
    """Presence, not truth: a producer that wrote `id = ""` twice has written
    the same id twice."""
    found = run(entity("bus", vehicle=vehicle(carriage(""), carriage(""))))

    assert prefixes(found) == ["entity ID bus carriage id  is claimed by 2 carriages"]


def test_the_occurrence_names_the_carriage_positions_and_this_rules_id():
    found = run(entity("bus", vehicle=vehicle(carriage("A"), carriage("B"), carriage("A"))))

    assert [occurrence.context["carriageIndexes"] for occurrence in found] == [[0, 2]]
    assert [occurrence.context["entityPath"] for occurrence in found] == ["entity[0].vehicle"]
    assert [occurrence.rule_id for occurrence in found] == ["S051"]
