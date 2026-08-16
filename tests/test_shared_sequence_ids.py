"""`_shared/walk_sequence_ids.py`: this message's ids beside the last one's.

Two claims are worth more than the rest and both are about *which* message the
walk compares against.

**The per-role one.** `runner/context.py` settles that "previous" is the
previous message of the same role, never whatever was read last. A stability
walk that compared a VehiclePositions message against the TripUpdates message
that happened to precede it would report every id in a two-feed run as unstable,
and a single-role test cannot see that at all. So the last test here drives the
real runner over a two-role, two-cycle replay where each role's ids are stable
within the role and deliberately different between the roles: under a global
"previous" every trip is reported, under the per-role one nothing is.

**The per-payload one.** A combined feed carries a TripUpdate and a
VehiclePosition for the same trip, under two different entity ids, and their
order in the entity list is not specified anywhere. Aligning on `trip_id` alone
would compare one payload's entity id against the other's the moment that order
changed, so the key is the payload and the trip together.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.rules._shared import walk_sequence_ids
from gtfs_rt_validator.rules._shared.walk_sequence_ids import sequence_ids
from gtfs_rt_validator.runner.run import role_cycle, run
from rulefixtures import context, entity, message
from runnerfixtures import a_config, a_rule, registry_of
from specfixtures import sharing


def update(trip_id: str, vehicle_id: str | None = None) -> dict[str, object]:
    """A TripUpdate for one trip, optionally naming a vehicle."""
    built: dict[str, object] = {"trip": {"trip_id": trip_id}}
    if vehicle_id is not None:
        built["vehicle"] = {"id": vehicle_id}
    return built


def position(trip_id: str, vehicle_id: str | None = None) -> dict[str, object]:
    built: dict[str, object] = {"trip": {"trip_id": trip_id}}
    if vehicle_id is not None:
        built["vehicle"] = {"id": vehicle_id}
    return built


def walked(tmp_path, current, previous):
    return list(sequence_ids(current, context(tmp_path, previous=previous)))


def test_a_trip_in_both_messages_pairs_its_ids(tmp_path):
    was = message(entity(trip_update=update("T1", "V1"), entity_id="e1"))
    now = message(entity(trip_update=update("T1", "V2"), entity_id="e2"))

    found = walked(tmp_path, now, was)

    assert [(each.trip_id, each.current.entity_id, each.previous.entity_id) for each in found] == [
        ("T1", "e2", "e1")
    ]
    assert [(each.current.vehicle_id, each.previous.vehicle_id) for each in found] == [("V2", "V1")]


def test_a_trip_only_this_message_carries_is_not_paired(tmp_path):
    """The walk is an alignment, not a diff of the two entity lists. A trip that
    has just appeared has no earlier id to have changed from."""
    was = message(entity(trip_update=update("T1"), entity_id="e1"))
    now = message(
        entity(trip_update=update("T1"), entity_id="e1"),
        entity(trip_update=update("T2"), entity_id="e2"),
    )

    assert [each.trip_id for each in walked(tmp_path, now, was)] == ["T1"]


def test_a_trip_only_the_previous_message_carried_is_not_paired(tmp_path):
    was = message(entity(trip_update=update("T1"), entity_id="e1"))
    now = message(entity(trip_update=update("T2"), entity_id="e2"))

    assert walked(tmp_path, now, was) == []


def test_the_first_message_of_a_role_pairs_nothing(tmp_path):
    now = message(entity(trip_update=update("T1"), entity_id="e1"))

    assert walked(tmp_path, now, None) == []


def test_a_vehicle_position_is_walked_as_well_as_a_trip_update(tmp_path):
    was = message(entity(vehicle=position("T1", "V1"), entity_id="e1"))
    now = message(entity(vehicle=position("T1", "V1"), entity_id="e2"))

    found = walked(tmp_path, now, was)

    assert [(each.payload, each.current.entity_id) for each in found] == [("vehicle", "e2")]


def test_the_two_payloads_of_one_trip_are_two_entries(tmp_path):
    """And the entity ids do not cross. Reversing the entity list is what makes
    the claim: entity order is not specified, so a walk keyed on `trip_id` alone
    would answer differently for the same feed depending on it."""
    was = message(
        entity(trip_update=update("T1"), entity_id="tu-1"),
        entity(vehicle=position("T1"), entity_id="vp-1"),
    )
    now = message(
        entity(vehicle=position("T1"), entity_id="vp-1"),
        entity(trip_update=update("T1"), entity_id="tu-1"),
    )

    found = walked(tmp_path, now, was)

    assert {(each.payload, each.current.entity_id, each.previous.entity_id) for each in found} == {
        ("trip_update", "tu-1", "tu-1"),
        ("vehicle", "vp-1", "vp-1"),
    }


def test_an_entity_carrying_both_payloads_for_one_trip_is_two_entries(tmp_path):
    """`FeedMessageTest` builds exactly this shape, so it is not hypothetical."""
    was = message(entity(trip_update=update("T1"), vehicle=position("T1"), entity_id="e1"))
    now = message(entity(trip_update=update("T1"), vehicle=position("T1"), entity_id="e1"))

    assert sorted(each.payload for each in walked(tmp_path, now, was)) == [
        "trip_update",
        "vehicle",
    ]


def test_a_missing_vehicle_descriptor_reads_as_none_rather_than_blank(tmp_path):
    """`None` is "the feed named no vehicle" and `""` is "the feed named an empty
    one". P003 needs them apart: only the second is an id that could change."""
    was = message(entity(trip_update=update("T1"), entity_id="e1"))
    now = message(entity(trip_update=update("T1", ""), entity_id="e1"))

    found = walked(tmp_path, now, was)

    assert [(each.previous.vehicle_id, each.current.vehicle_id) for each in found] == [(None, "")]


def test_an_entity_whose_descriptor_names_no_trip_is_skipped(tmp_path):
    """`TripDescriptor.trip_id` is optional in both schemas, and an entity with
    no trip_id cannot be aligned with anything."""
    was = message(entity(trip_update={"trip": {"route_id": "R1"}}, entity_id="e1"))
    now = message(entity(trip_update={"trip": {"route_id": "R1"}}, entity_id="e2"))

    assert walked(tmp_path, now, was) == []


def test_the_first_entity_wins_when_one_message_names_a_trip_twice(tmp_path):
    """Two TripUpdates for one trip instance is what S003 and E047 report; this
    walk is not the place to report it a third time, so it takes the first and
    stays deterministic."""
    was = message(entity(trip_update=update("T1"), entity_id="first-was"))
    now = message(
        entity(trip_update=update("T1"), entity_id="first-now"),
        entity(trip_update=update("T1"), entity_id="second-now"),
    )

    found = walked(tmp_path, now, was)

    assert [each.current.entity_id for each in found] == ["first-now"]


def test_the_path_locates_the_entity_that_carried_the_id(tmp_path):
    was = message(entity(trip_update=update("T1"), entity_id="e1"))
    now = message(
        entity(vehicle=position("T9"), entity_id="other"),
        entity(trip_update=update("T1"), entity_id="e1"),
    )

    found = walked(tmp_path, now, was)

    assert [each.current.path for each in found] == ["entity[1].trip_update"]


def test_two_rules_reading_one_message_walk_it_once(tmp_path, monkeypatch):
    runs = sharing(monkeypatch, walk_sequence_ids, "_build")
    was = message(entity(trip_update=update("T1"), entity_id="e1"))
    now = message(entity(trip_update=update("T1"), entity_id="e2"))
    ctx = context(tmp_path, previous=was)

    sequence_ids(now, ctx)
    sequence_ids(now, ctx)

    assert len(runs) == 1


def written(path: Path, timestamp: int, *entities: dict[str, object]) -> Path:
    """One message on disk. The timestamp moves between cycles because the
    runner's `DuplicateFilter` drops a message byte-identical to the last one of
    its role, and a feed refreshed with the same contents does move it."""
    header = {"gtfs_realtime_version": "2.0", "incrementality": 0, "timestamp": timestamp}
    path.write_bytes(encode({"header": header, "entity": list(entities)}, V2015))
    return path


def test_a_two_role_run_compares_each_role_against_its_own_previous(tmp_path):
    """The test the single-role version cannot be.

    Both roles carry trip `T1`, under entity ids that are stable within a role
    and different between the roles. Under the per-role contract nothing here
    has changed. Under a global "previous", the VehiclePositions message of each
    cycle would be compared against the TripUpdates message of the same cycle
    and both ids would read as having changed every time.
    """
    seen: list[tuple[str, tuple[tuple[str, str, str], ...]]] = []

    def check(msg, ctx):
        found = sequence_ids(msg, ctx)
        seen.append(
            (ctx.role, tuple((f.trip_id, f.previous.entity_id, f.current.entity_id) for f in found))
        )
        return ()

    config = a_config(tmp_path, registry=registry_of(a_rule("E001", check)))
    tu = entity(trip_update=update("T1"), entity_id="tu-e")
    vp = entity(vehicle=position("T1"), entity_id="vp-e")
    first = {
        "tu": written(tmp_path / "tu-1.pb", 1_700_000_000, tu),
        "vp": written(tmp_path / "vp-1.pb", 1_700_000_000, vp),
    }
    second = {
        "tu": written(tmp_path / "tu-2.pb", 1_700_000_030, tu),
        "vp": written(tmp_path / "vp-2.pb", 1_700_000_030, vp),
    }

    run(config, [role_cycle(first), role_cycle(second)])

    assert [role for role, _ in seen] == ["tu", "vp", "tu", "vp"]
    assert [found for _, found in seen[:2]] == [(), ()], "the first cycle has no previous"
    assert [found for _, found in seen[2:]] == [
        (("T1", "tu-e", "tu-e"),),
        (("T1", "vp-e", "vp-e"),),
    ], "each role saw its own previous message, so neither id moved"
