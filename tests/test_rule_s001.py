"""S001: a `FeedEntity` carrying no payload, or more than one.

The payload set comes from the descriptor rather than from a list written in the
rule, so this suite exercises all six of the current schema's: `trip_update`,
`vehicle`, `alert`, `shape`, `stop` and `trip_modifications`. Three of those
six the 2015 descriptor cannot see at all, which is why the rule is unreachable
from a jar run rather than a duplicate of anything in it.

The clause's own parenthesis is the second half of the predicate: a deleted
entity is exempt, because a DIFFERENTIAL feed deletes by id and has nothing to
put in a payload.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.spec.s001 import check
from specfixtures import context, entity, message, prefixes

TRIP_UPDATE = {"trip": {"trip_id": "T1"}}
VEHICLE = {"trip": {"trip_id": "T1"}}
ALERT = {"informed_entity": [{"route_id": "R1"}]}
SHAPE = {"shape_id": "SH1", "encoded_polyline": "_p~iF~ps|U_ulL"}


def run(*entities):
    return check(message(*entities), context())


def test_one_payload_is_what_the_clause_asks_for():
    assert prefixes(run(entity(trip_update=TRIP_UPDATE))) == []


def test_each_of_the_six_payloads_satisfies_it_on_its_own():
    """The rule reads `FeedEntity`'s message-typed fields, so a payload added at
    a later pin is covered without a change here. All six of this pin's are."""
    for name, payload in (
        ("trip_update", TRIP_UPDATE),
        ("vehicle", VEHICLE),
        ("alert", ALERT),
        ("shape", SHAPE),
        ("stop", {"stop_id": "S9"}),
        ("trip_modifications", {"service_dates": ["20260814"]}),
    ):
        assert prefixes(run(entity(**{name: payload}))) == [], name


def test_an_entity_with_no_payload_at_all_is_reported():
    assert prefixes(run(entity("lonely"))) == ["entity ID lonely carries no payload"]


def test_an_entity_with_two_payloads_names_both_in_field_order():
    found = run(entity("busy", vehicle=VEHICLE, trip_update=TRIP_UPDATE))

    assert prefixes(found) == ["entity ID busy carries 2 payloads: trip_update, vehicle"]


def test_a_deleted_entity_with_no_payload_is_exempt():
    """ "unless the entity is being deleted": a DIFFERENTIAL feed deletes by id."""
    assert prefixes(run(entity("gone", is_deleted=True))) == []


def test_a_deleted_entity_with_two_payloads_is_exempt_too():
    """The parenthesis is on the whole sentence, not on the "no payload" half."""
    assert prefixes(run(entity("gone", is_deleted=True, alert=ALERT, vehicle=VEHICLE))) == []


def test_is_deleted_written_false_is_not_a_deletion():
    """Presence is not truth here, unlike E039: the clause exempts an entity
    that is *being deleted*, and `is_deleted = false` says it is not."""
    assert prefixes(run(entity("here", is_deleted=False))) == ["entity ID here carries no payload"]


def test_entities_are_reported_in_feed_order():
    found = run(entity("one"), entity("two", trip_update=TRIP_UPDATE), entity("three"))

    assert prefixes(found) == [
        "entity ID one carries no payload",
        "entity ID three carries no payload",
    ]
    assert [occurrence.context["entityPath"] for occurrence in found] == ["entity[0]", "entity[2]"]


def test_every_occurrence_carries_this_rules_id():
    assert [occurrence.rule_id for occurrence in run(entity("one"))] == ["S001"]
