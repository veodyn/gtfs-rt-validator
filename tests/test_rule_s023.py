"""S023: `modified_trip` alongside the five fields it replaces.

The clause names the five by hand, and so does the rule, so the test builds its
fixtures from the rule's own tuple rather than from a second list. A field the
proto adds to that sentence at a later pin fails the citation gate, which is the
signal to change both.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s023 import EMPTIED, check
from specfixtures import context, entity, message

#: A well-formed selector, which is what the clause expects to see alone.
SELECTOR = {"modifications_id": "M1", "affected_trip_id": "T1"}

#: A value the encoder accepts for each of the five, so a fixture can populate
#: one without knowing its type.
VALUES = {
    "trip_id": "T1",
    "route_id": "R1",
    "direction_id": 0,
    "start_time": "06:10:00",
    "start_date": "20260814",
}


def found(**trip):
    feed = message(entity(trip_update={"trip": dict(trip)}))
    return list(check(feed, context()) or ())


def prefixes(**trip):
    return [occurrence.prefix for occurrence in found(**trip)]


def test_the_rule_and_the_clause_name_the_same_five_fields():
    """The clause spells them out, so a sixth appearing in the rule without
    appearing in the sentence would be a rule wider than its citation."""
    assert EMPTIED == ("trip_id", "route_id", "direction_id", "start_time", "start_date")
    assert set(VALUES) == set(EMPTIED)


def test_a_modified_trip_alongside_a_route_id_reports():
    assert prefixes(modified_trip=SELECTOR, route_id="R1") == [
        "modified_trip M1 is set together with route_id"
    ]


def test_every_field_that_should_have_been_left_empty_is_named_in_one_occurrence():
    """One occurrence per descriptor rather than one per field: the defect is
    the descriptor being written two ways at once, not each field separately."""
    assert prefixes(modified_trip=SELECTOR, **VALUES) == [
        (
            "modified_trip M1 is set together with "
            "trip_id, route_id, direction_id, start_time, start_date"
        )
    ]


def test_each_of_the_five_reports_on_its_own():
    for name, value in VALUES.items():
        assert prefixes(modified_trip=SELECTOR, **{name: value}) == [
            f"modified_trip M1 is set together with {name}"
        ], name


def test_the_occurrence_locates_the_descriptor():
    (occurrence,) = found(modified_trip=SELECTOR, route_id="R1")

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].trip_update.trip"


def test_a_modified_trip_on_its_own_is_silent():
    """The satisfying fixture, and the shape the clause is written to produce."""
    assert prefixes(modified_trip=SELECTOR) == []


def test_a_descriptor_with_no_modified_trip_is_out_of_scope():
    """ "If this field is provided" is the antecedent. An ordinary descriptor
    setting all five is exactly what the rest of the message is for."""
    assert prefixes(**VALUES) == []


def test_a_selector_with_no_modifications_id_still_reports():
    """`modifications_id` is optional, so the opener has to survive without it
    rather than interpolating an empty string in the middle of a sentence."""
    assert prefixes(modified_trip={"affected_trip_id": "T1"}, route_id="R1") == [
        "modified_trip is set together with route_id"
    ]


def test_an_alert_selectors_descriptor_is_checked_too():
    """A TripDescriptor rides on three messages and the clause is about the
    descriptor, so a selector carrying both forms is the same defect."""
    feed = message(
        entity(alert={"informed_entity": [{"trip": {"modified_trip": SELECTOR, "route_id": "R1"}}]})
    )

    (occurrence,) = check(feed, context()) or ()

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].alert.informed_entity[0].trip"
