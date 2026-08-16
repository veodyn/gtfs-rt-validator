"""What the stop_time_update walk owes `_shared/walks.py`, rather than upstream.

Split from `test_shared_walk_stop_time_updates.py` at the 300-line file cap, and
split here because these are a different question: that file is about upstream's
control flow, and this one is about the walk being a well-behaved shared stream.
Nothing here has a Java counterpart, so every assertion is **ours**.

- One body run per message, whatever twelve rules ask for.
- Only TripUpdate entities (`StopTimeUpdateValidator.java:76-77`).
- Every event carries the loop position a rule cannot rebuild.
- The enum numbers the checks module writes as literals are the numbers both
  generated schemas hold.
"""

from __future__ import annotations

from gtfs_rt_validator.proto import schema_2015, schema_current
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared import stop_time_update_checks as checks
from gtfs_rt_validator.rules._shared.walk_stop_time_updates import stop_time_updates
from gtfs_rt_validator.rules._shared.walks import walk_events, walk_key
from rulefixtures import entity, message
from stufixtures import feed, rule_context, stu, trip_update, walk

STOP_RELATIONSHIP = "TripUpdate.StopTimeUpdate.ScheduleRelationship"
TRIP_RELATIONSHIP = "TripDescriptor.ScheduleRelationship"


def test_the_walk_body_runs_once_per_message_however_many_rules_read_it(tmp_path):
    one = feed(trip_update(stu(), trip_id="1.1"))
    ctx = rule_context(tmp_path)

    first = walk_events(stop_time_updates, one, ctx)
    second = walk_events(stop_time_updates, one, ctx)

    assert first is second
    assert walk_key(stop_time_updates) in ctx.memo


def test_only_trip_update_entities_are_walked(tmp_path):
    """`:76-77`. A VehiclePosition and an alert are not this validator's business
    however malformed they are."""
    other = message(
        entity(vehicle={"stop_id": "A"}),
        entity(alert={"informed_entity": [{"stop_id": "A"}]}),
    )

    assert walk_events(stop_time_updates, other, rule_context(tmp_path)) == ()


def test_every_stop_time_update_event_carries_the_walks_own_position(tmp_path):
    """The entity path is the thing a rule inside a stateful loop cannot rebuild,
    which is why `Event` carries a context at all."""
    found = walk(tmp_path, trip_update(stu(), stu(), trip_id="1.1"))

    assert [event.context[ENTITY_PATH_KEY] for event in found] == [
        "entity[0].trip_update.stop_time_update[0]",
        "entity[0].trip_update.stop_time_update[0]",
        "entity[0].trip_update.stop_time_update[1]",
        "entity[0].trip_update.stop_time_update[1]",
    ]


def test_e041_and_e002_are_located_at_the_trip_update_not_a_stop_time_update(tmp_path):
    """Both are per-TripUpdate: E041 fires before the loop and E002 after it.

    The unsorted TripUpdate names no trip_id, which is upstream's own `testE002`
    shape and not an oversight: with a trip_id the walk would fail to find
    stop_sequence 5 in that trip's three rows, report E051 and break before the
    second stop_time_update ever reached the list E002 reads."""
    empty = walk(tmp_path, trip_update(trip_id="1.1"))
    unsorted = walk(
        tmp_path, trip_update(stu(5, arrival={"delay": 60}), stu(1, arrival={"delay": 60}))
    )

    assert empty[0].context[ENTITY_PATH_KEY] == "entity[0].trip_update"
    assert [event.context[ENTITY_PATH_KEY] for event in unsorted if event.rule_id == "E002"] == [
        "entity[0].trip_update"
    ]


def test_a_later_entity_is_located_by_its_own_index(tmp_path):
    found = walk(tmp_path, trip_update(trip_id="1.1"), trip_update(trip_id="1.1"))

    assert [event.context[ENTITY_PATH_KEY] for event in found] == [
        "entity[0].trip_update",
        "entity[1].trip_update",
    ]


def test_the_enum_numbers_match_both_schemas():
    """`_shared/stop_time_update_checks.py` writes SKIPPED, NO_DATA and CANCELED
    as plain numbers, because a rule may be handed a message decoded under either
    schema. This is the check that the two agree, so the numbers are measured
    rather than assumed."""
    for schema in (schema_2015.SCHEMA, schema_current.SCHEMA):
        assert schema.enums[STOP_RELATIONSHIP]["SKIPPED"] == checks.SKIPPED
        assert schema.enums[STOP_RELATIONSHIP]["NO_DATA"] == checks.NO_DATA
        assert schema.enums[TRIP_RELATIONSHIP]["CANCELED"] == checks.CANCELED
