"""S052: `carriage_sequence` values that are not `1, 2, ... n` in list order.

The clause folds three sentences of one comment block. `:583` gives the first
carriage 1, `:584` gives the second 2 "and so forth", and `:589` says a carriage
with no data must still carry a valid `carriage_sequence`. An absent value
already breaks the run, because the field is `optional` with a proto2 default of
0, so a second rule for `:589` would report the same carriage twice.

`:585-588` says what a consumer does with a broken run, and it is why this is an
ERROR rather than advice: "If the second carriage in the direction of travel has
a value of 3, consumers will discard data for all carriages".
"""

from __future__ import annotations

from gtfs_rt_validator.rules.spec.s052 import check
from specfixtures import context, entity, message, prefixes


def vehicle(*sequences: int | None) -> dict[str, object]:
    """A VehiclePosition whose carriages carry these `carriage_sequence` values.

    `None` is a carriage that declares none at all, which is `:589`'s case.
    """
    carriages: list[dict[str, object]] = [
        {} if sequence is None else {"carriage_sequence": sequence} for sequence in sequences
    ]
    return {"trip": {"trip_id": "T1"}, "multi_carriage_details": carriages}


def run(*entities):
    return check(message(*entities), context())


def test_a_run_of_one_two_three_is_what_the_clause_asks_for():
    assert prefixes(run(entity(vehicle=vehicle(1, 2, 3)))) == []


def test_a_single_carriage_numbered_one_is_the_boundary():
    assert prefixes(run(entity(vehicle=vehicle(1)))) == []


def test_a_vehicle_with_no_carriages_is_not_a_finding():
    assert prefixes(run(entity(vehicle=vehicle()))) == []


def test_a_single_carriage_numbered_two_is_reported():
    found = run(entity("bus", vehicle=vehicle(2)))

    assert prefixes(found) == ["entity ID bus carriage 1 has carriage_sequence 2, expected 1"]


def test_the_gap_the_proto_uses_as_its_own_example_is_reported():
    """`:586-588`: first carriage 1, second carriage 3, consumers discard the
    lot."""
    found = run(entity("bus", vehicle=vehicle(1, 3)))

    assert prefixes(found) == ["entity ID bus carriage 2 has carriage_sequence 3, expected 2"]


def test_a_carriage_with_no_carriage_sequence_is_reported_as_zero():
    """`:589`, folded. The field is optional with a proto2 default of 0, so an
    absent value already breaks the run and needs no rule of its own."""
    found = run(entity("bus", vehicle=vehicle(1, None)))

    assert prefixes(found) == ["entity ID bus carriage 2 has carriage_sequence 0, expected 2"]


def test_carriages_out_of_order_report_once_each():
    found = run(entity("bus", vehicle=vehicle(2, 1)))

    assert prefixes(found) == [
        "entity ID bus carriage 1 has carriage_sequence 2, expected 1",
        "entity ID bus carriage 2 has carriage_sequence 1, expected 2",
    ]


def test_the_order_is_the_list_order_not_the_sorted_one():
    """ "The first carriage in the direction of travel", which is the first in
    the repeated field. A run that sorts to 1,2,3 but is written 1,3,2 is still
    a defect."""
    found = run(entity("bus", vehicle=vehicle(1, 3, 2)))

    assert prefixes(found) == [
        "entity ID bus carriage 2 has carriage_sequence 3, expected 2",
        "entity ID bus carriage 3 has carriage_sequence 2, expected 3",
    ]


def test_the_occurrence_locates_the_carriage_and_carries_this_rules_id():
    found = run(entity("bus", vehicle=vehicle(1, 5)))

    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].vehicle.multi_carriage_details[1]"
    ]
    assert [occurrence.rule_id for occurrence in found] == ["S052"]
