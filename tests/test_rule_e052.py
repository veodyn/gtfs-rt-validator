"""E052, against upstream's own `VehicleValidatorTest.testE052`.

Every assertion marked "upstream" is transcribed from the real
`VehicleValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testE052`, lines 772-801), not from a second-hand summary of it. Upstream
asserts *counts* and nothing else, so every assertion about occurrence text
below is ours, read off `VehicleValidator.java:84-94`.

The rule is the only one in this validator that needs state across entities:
`vehicleIds` is a `HashSet` built once per `validate` call (`:70`), so the
*first* copy of a duplicated id is the one that is never reported and n copies
give n-1 occurrences. It also sits in the `else` of the W002 test, so a blank
vehicle.id is a warning and is never a duplicate however many times it appears.

Upstream's own test gives both of its entities the same `entity.id`, which is
`FeedMessageTest`'s `TEST_ENTITY`, so the occurrence text it produces does not
distinguish the two. That is ported as it stands.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules.upstream.e052 import check
from rulefixtures import context, entity, message, minimal, occurrences, prefixes


def vehicle(vehicle_id: str | None) -> dict[str, object]:
    """A VehiclePosition with no position at all, as upstream's testE052 builds."""
    return {} if vehicle_id is None else {"vehicle": {"id": vehicle_id}}


def run(tmp_path: Path, *entities: Mapping[str, object]) -> Sequence[Occurrence]:
    return occurrences(check(message(*entities), context(tmp_path, minimal())))


def with_ids(tmp_path: Path, *vehicle_ids: str | None) -> Sequence[Occurrence]:
    return run(tmp_path, *(entity(vehicle=vehicle(each)) for each in vehicle_ids))


# --- upstream's own case, stage by stage ------------------------------------


def test_a_single_vehicle_reports_nothing(tmp_path):
    """Upstream, testE052: "No error, as there is only one vehicle in the feed"."""
    assert with_ids(tmp_path, "1") == []


def test_two_entities_with_the_same_vehicle_id_report_once(tmp_path):
    """Upstream, testE052: a second entity with vehicle.id `1`,
    `expected.put(E052, 1)`."""
    assert len(with_ids(tmp_path, "1", "1")) == 1


# --- the occurrence text, which upstream's test never looks at --------------


def test_every_occurrence_carries_this_rules_id(tmp_path):
    assert [found.rule_id for found in with_ids(tmp_path, "1", "1")] == ["E052"]


def test_the_prefix_names_the_entity_and_the_repeated_id(tmp_path):
    """Ours, read off `:90`. `vehicle.id` with a dot, as everywhere in
    `GtfsUtils`, though this site writes it inline rather than calling it."""
    assert prefixes(with_ids(tmp_path, "1", "1")) == ["entity ID TEST_ENTITY has vehicle.id 1"]


def test_the_entity_named_is_the_later_one(tmp_path):
    """Ours, and the half upstream's test cannot see, because both of its
    entities are `TEST_ENTITY`. The occurrence is logged while walking the
    duplicate, so it names the duplicate's entity and not the original's."""
    found = run(
        tmp_path,
        entity(vehicle=vehicle("1"), entity_id="first"),
        entity(vehicle=vehicle("1"), entity_id="second"),
    )

    assert prefixes(found) == ["entity ID second has vehicle.id 1"]


def test_the_occurrence_locates_the_vehicle_position_it_came_from(tmp_path):
    found = with_ids(tmp_path, "1", "1")

    assert found[0].context[ENTITY_PATH_KEY] == "entity[1].vehicle"


# --- the counting, and the W002 branch it sits in ---------------------------


def test_n_copies_of_one_id_give_n_minus_one_occurrences(tmp_path):
    """Ours. The set is checked before the id is added, so only the first copy
    escapes."""
    assert len(with_ids(tmp_path, "1", "1", "1")) == 2


def test_two_different_ids_are_not_duplicates(tmp_path):
    assert with_ids(tmp_path, "1", "2") == []


def test_an_empty_vehicle_id_is_never_a_duplicate(tmp_path):
    """Ours. `:84` sends the empty id to W002 and E052 is the `else`, so the
    set never sees it and three blanks are three warnings and no error."""
    assert with_ids(tmp_path, "", "", "") == []


def test_a_vehicle_position_with_no_descriptor_is_never_a_duplicate(tmp_path):
    """Ours, for the same reason: `getVehicle().getId()` is `""`."""
    assert with_ids(tmp_path, None, None) == []


def test_a_trip_update_carrying_the_same_vehicle_id_is_not_a_duplicate(tmp_path):
    """Ours. `:84-94` is inside `if (entity.hasVehicle())`, so the TripUpdate
    half of W002 puts nothing into the set."""
    found = run(
        tmp_path,
        entity(trip_update={"trip": {"trip_id": "T1"}, "vehicle": {"id": "1"}}),
        entity(vehicle=vehicle("1")),
    )

    assert found == []


def test_duplicates_are_reported_in_feed_order(tmp_path):
    found = run(
        tmp_path,
        entity(vehicle=vehicle("1"), entity_id="one"),
        entity(vehicle=vehicle("2"), entity_id="two"),
        entity(vehicle=vehicle("2"), entity_id="three"),
        entity(vehicle=vehicle("1"), entity_id="four"),
    )

    assert prefixes(found) == [
        "entity ID three has vehicle.id 2",
        "entity ID four has vehicle.id 1",
    ]
