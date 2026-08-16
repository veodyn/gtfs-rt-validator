"""The resolved schedule_relationship walk, read by ten of the spec tier's rules.

Four claims:

- the proto2 default is resolved once and answered by name, so a rule compares
  `"DUPLICATED"` rather than a number it had to look up;
- "absent" and "explicitly SCHEDULED" are both SCHEDULED and are still
  distinguishable, because S014's predicate is about a field being populated;
- `ADDED`'s deprecation is read from the schema rather than listed here, which
  is what makes a deprecation at a later pin reach the rule through the pin;
- ten rules reading it in one context resolve the message once.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules._shared import schedule_relationship as sr
from gtfs_rt_validator.rules._shared.schedule_relationship import (
    DEPRECATED_TRIP_RELATIONSHIPS,
    relationships,
    stop_time_relationship,
    trip_relationship,
)
from gtfs_rt_validator.rules.errors import RuleContractError
from specfixtures import context, entity, message, sharing

DUPLICATED = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]["DUPLICATED"]
ADDED = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]["ADDED"]
SKIPPED = SCHEMA.enums["TripUpdate.StopTimeUpdate.ScheduleRelationship"]["SKIPPED"]


def trip_update(schedule_relationship=None, *updates):
    trip = {"trip_id": "1.1"}
    if schedule_relationship is not None:
        trip["schedule_relationship"] = schedule_relationship
    return {"trip": trip, "stop_time_update": list(updates)}


def test_an_absent_relationship_resolves_to_the_proto2_default():
    """`SCHEDULED = 0`, which is what protobuf-java answers for a field that was
    never on the wire, and what every rule downstream has to agree with."""
    found = relationships(message(entity(trip_update=trip_update())), context())

    assert [record.relationship for record in found] == ["SCHEDULED"]
    assert [record.declared for record in found] == [False]


def test_an_explicit_relationship_is_answered_by_name_and_marked_declared():
    found = relationships(message(entity(trip_update=trip_update(DUPLICATED))), context())

    assert [(record.relationship, record.declared) for record in found] == [("DUPLICATED", True)]


def test_the_stop_time_updates_resolve_beside_their_trip():
    """S009 and S010 are the two directions of one triangle, so both need the
    trip's answer and every update's answer out of one walk."""
    feed = message(
        entity(
            trip_update=trip_update(None, {"stop_sequence": 1}, {"schedule_relationship": SKIPPED})
        )
    )

    (record,) = relationships(feed, context())

    assert [
        (update.index, update.relationship, update.declared) for update in record.stop_time_updates
    ] == [
        (0, "SCHEDULED", False),
        (1, "SKIPPED", True),
    ]


def test_every_trip_descriptor_in_the_message_is_reached_with_its_path():
    """A TripDescriptor rides on three things, and S024 is about the value
    wherever it appears, so a walk that read only TripUpdates would miss two of
    them."""
    feed = message(
        entity("a", trip_update=trip_update(ADDED)),
        entity("b", vehicle={"trip": {"trip_id": "2.1", "schedule_relationship": ADDED}}),
        entity("c", alert={"informed_entity": [{"trip": {"trip_id": "3.1"}}]}),
    )

    found = relationships(feed, context())

    assert [(record.payload, record.path) for record in found] == [
        ("trip_update", "entity[0].trip_update.trip"),
        ("vehicle", "entity[1].vehicle.trip"),
        ("alert", "entity[2].alert.informed_entity[0].trip"),
    ]


def test_a_vehicle_without_a_trip_is_not_a_trip_descriptor():
    """`getTrip()` on a VehiclePosition that names none answers a default
    instance, so a walk that did not test presence would report a SCHEDULED
    trip for every vehicle in the feed."""
    feed = message(entity(vehicle={}), entity(alert={"informed_entity": [{"stop_id": "A"}]}))

    assert relationships(feed, context()) == ()


def test_the_deprecated_members_are_read_from_the_schema():
    """S024 fires on `ADDED` because the pinned proto says
    `ADDED = 1 [deprecated = true]`, and this is where that fact enters the
    rules layer. A tuple written here instead would go on being true after the
    pin stopped saying it."""
    assert frozenset({"ADDED"}) == DEPRECATED_TRIP_RELATIONSHIPS
    assert (
        SCHEMA.enum_deprecated("TripDescriptor.ScheduleRelationship")
        == DEPRECATED_TRIP_RELATIONSHIPS
    )


def test_the_names_this_module_publishes_are_members_of_the_enums_they_name():
    """Every constant is checked against the schema at import, so a member
    renamed at a later pin is an import error rather than a rule that quietly
    never fires again."""
    for name in (
        sr.ADDED,
        sr.CANCELED,
        sr.DELETED,
        sr.DUPLICATED,
        sr.NEW,
        sr.REPLACEMENT,
        sr.UNSCHEDULED,
        sr.SCHEDULED,
    ):
        assert name in SCHEMA.enums["TripDescriptor.ScheduleRelationship"]
    for name in (sr.STOP_TIME_SCHEDULED, sr.STOP_TIME_UNSCHEDULED, sr.NO_DATA, sr.SKIPPED):
        assert name in SCHEMA.enums["TripUpdate.StopTimeUpdate.ScheduleRelationship"]


def test_the_two_helpers_answer_a_message_a_rule_already_holds():
    """A rule inside another walk has the descriptor and not the record, so the
    resolution is a function as well as a walk."""
    feed = message(entity(trip_update=trip_update(DUPLICATED, {"schedule_relationship": SKIPPED})))
    payload = feed.get("entity")[0].get("trip_update")

    assert trip_relationship(payload.get("trip")) == "DUPLICATED"
    assert stop_time_relationship(payload.get("stop_time_update")[0]) == "SKIPPED"


def test_a_number_no_member_carries_is_a_bug_in_this_repository():
    """Unreachable through a decode, which drops an unknown enum value into
    `unknown` and leaves the field absent. Reachable by handing this helper a
    message built by hand, which is a caller error rather than a feed defect."""

    class NotFromTheDecoder:
        def has(self, name):
            return True

        def get(self, name):
            return 4242

    with pytest.raises(RuleContractError, match="4242"):
        trip_relationship(NotFromTheDecoder())


def test_nine_rules_sharing_one_context_resolve_the_message_once(monkeypatch):
    """The memo's point, and this is the walk with the most readers in the spec
    tier: S004, S007, S008, S009, S010, S013, S014, S017 and S024. Ten
    until S022 was retired for being a strict subset of E013, which changes the
    count in the name and nothing about what the memo has to do."""
    runs = sharing(monkeypatch, sr, "_build")
    feed = message(entity(trip_update=trip_update(DUPLICATED)))
    ctx = context()

    for _ in range(10):
        assert [record.relationship for record in relationships(feed, ctx)] == ["DUPLICATED"]

    assert runs == [feed]
