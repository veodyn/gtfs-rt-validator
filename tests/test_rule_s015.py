"""S015: a `TripProperties.trip_id` that `trips.txt` already uses.

The clause is on the field that names the *new* trip, so the whole point is
that the id is new. Reusing one from GTFS makes the duplicate indistinguishable
from the trip it duplicates, which is why the sentence is a `must`.

Not E016. That rule fires on a `TripDescriptor.trip_id` that GTFS knows under
an ADDED relationship; this reads a different field on a different message, and
the jar check in `tests/test_spec_tier_does_not_shadow_the_jar.py` is what says
so empirically.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.spec.s015 import check
from specfixtures import entity, feed_context, message, prefixes

TRIP = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]

DUPLICATED = TRIP["DUPLICATED"]


def trip_update(new_trip_id: str | None = None, relationship: int = DUPLICATED):
    built: dict[str, object] = {"trip": {"trip_id": "T1", "schedule_relationship": relationship}}
    if new_trip_id is not None:
        built["trip_properties"] = {
            "trip_id": new_trip_id,
            "start_date": "20260814",
            "start_time": "10:00:00",
        }
    return built


def run(tmp_path, *entities):
    return check(message(*entities), feed_context(tmp_path))


def test_a_new_trip_id_is_what_the_clause_asks_for(tmp_path):
    assert prefixes(run(tmp_path, entity(trip_update=trip_update("T1-copy")))) == []


def test_a_trip_id_trips_txt_already_uses_is_reported(tmp_path):
    """T1 is `minimal_tables()`'s one trip."""
    found = run(tmp_path, entity(trip_update=trip_update("T1")))

    assert prefixes(found) == ["trip_properties.trip_id T1 is already a trip_id in the (CSV) GTFS"]


def test_a_trip_update_with_no_trip_properties_is_not_a_finding(tmp_path):
    assert prefixes(run(tmp_path, entity(trip_update=trip_update()))) == []


def test_the_rule_reads_the_field_rather_than_the_relationship(tmp_path):
    """The sentence is on the field, so a producer that populated it under some
    other relationship has still collided with GTFS. That the field should not
    be populated at all there is S014's separate finding."""
    found = run(tmp_path, entity(trip_update=trip_update("T1", relationship=TRIP["NEW"])))

    assert len(found) == 1


def test_the_occurrence_locates_the_properties_and_carries_this_rules_id(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update("T1")))

    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.trip_properties"
    ]
    assert [occurrence.rule_id for occurrence in found] == ["S015"]
