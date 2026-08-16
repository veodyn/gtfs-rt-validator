"""The index W003 and E047 share, and what a cycle means for it.

`CrossFeedDescriptorValidator` builds six containers in one pass and then runs
two rules off them. This project puts each reported id in its own module, so the
pass lives here and both modules read it, the same arrangement `_shared/walks.py`
makes for the loops.

Nothing upstream asserts any of this directly: its test goes through `validate`
and counts occurrences. The two rule tests port those counts; what is pinned
here is the index itself, so a change to the build fails next to the Java it
came from rather than as four surprising prefixes.

Named roles have no upstream counterpart at all. `runner/context.py` settles
what a cycle is, and the last section is what that means for these two rules.
"""

from __future__ import annotations

from crossfeedfixtures import combined, combined_roles, trip_update, vehicle_position
from gtfs_rt_validator.rules._shared.crossfeed import MEMO_KEY, index_for
from rulefixtures import context, entity


def index(tmp_path, *entities, **kwargs):
    _, ctx = combined(tmp_path, *entities, **kwargs)
    return index_for(ctx)


# --- the two early returns --------------------------------------------------


def test_a_message_that_is_not_its_cycles_host_has_no_index(tmp_path):
    """`combinedFeedMessage == null` (`:50-53`)."""
    assert index_for(context(tmp_path)) is None


def test_a_cycle_with_no_trip_updates_has_no_index(tmp_path):
    """`tripUpdateCount == 0` (`:119-122`)."""
    assert index(tmp_path, entity(vehicle=vehicle_position("44", "100"))) is None


def test_a_cycle_with_no_vehicle_positions_has_no_index(tmp_path):
    """`vehiclePositionCount == 0`, the other half of the same test."""
    assert index(tmp_path, entity(trip_update("1.1", "1"))) is None


def test_an_entity_with_a_blank_id_still_counts_towards_the_gate(tmp_path):
    """The counts at `:82` and `:100` increment on presence, before the
    `StringUtils.isEmpty` test at `:88` and `:106`. So a feed whose every id is
    the empty string still gets past the gate, with both maps empty and both
    sets holding `""`."""
    built = index(
        tmp_path,
        entity(trip_update("", ""), vehicle_position("", "")),
    )

    assert built is not None
    assert built.trips_without_vehicles == ("",)
    assert built.vehicles_without_trips == ("",)


def test_a_trip_update_with_a_descriptor_but_no_trip_id_does_not_count(tmp_path):
    """`hasTripId` (`:181-183`) needs the nested field, and absent is the one
    thing that is not blank. Its `hasTrip()` half cannot be reached from a
    decoded message at all: `TripUpdate.trip` is `required` in both schemas, so
    a TripUpdate without one fails `isInitialized` and the whole file is
    skipped before any rule sees it."""
    assert (
        index(tmp_path, entity(trip_update(vehicle_id="1"), vehicle_position("44", "100"))) is None
    )


def test_a_vehicle_position_with_no_vehicle_descriptor_does_not_count(tmp_path):
    """`hasVehicleId` (`:191-193`), whose two halves are both live: both fields
    of a VehiclePosition are optional."""
    assert (
        index(
            tmp_path,
            entity(trip_update("1.1", "1"), vehicle_position(trip_id="100", vehicle=False)),
        )
        is None
    )


# --- the four maps ----------------------------------------------------------


def test_both_halves_index_forward_and_inverse(tmp_path):
    built = index(tmp_path, entity(trip_update("1.1", "1"), vehicle_position("44", "100")))

    assert built is not None
    assert built.trip_updates_trip_to_vehicle == {"1.1": "1"}
    assert built.trip_updates_vehicle_to_trip == {"1": "1.1"}
    assert built.vehicle_positions_vehicle_to_trip == {"44": "100"}
    assert built.vehicle_positions_trip_to_vehicle == {"100": "44"}


def test_a_shared_vehicle_id_collapses_only_the_vehicle_keyed_map(tmp_path):
    """`:93` is keyed by trip_id and `:94` by vehicle_id, so two TripUpdates
    sharing a vehicle_id keep both entries in the first and one in the second.
    Two earlier readings of upstream both said "both maps collapse", and the
    Java at those lines says otherwise."""
    built = index(
        tmp_path,
        entity(trip_update("1.1", "1")),
        entity(trip_update("1.2", "1")),
        entity(vehicle=vehicle_position("44", "100")),
    )

    assert built is not None
    assert built.trip_updates_trip_to_vehicle == {"1.1": "1", "1.2": "1"}
    assert built.trip_updates_vehicle_to_trip == {"1": "1.2"}


def test_a_shared_trip_id_collapses_the_trip_keyed_map_to_the_last_write(tmp_path):
    """The mirror: `put` is last-write-wins on whichever key it is given."""
    built = index(
        tmp_path,
        entity(trip_update("1.1", "1")),
        entity(trip_update("1.1", "2")),
        entity(vehicle=vehicle_position("44", "100")),
    )

    assert built is not None
    assert built.trip_updates_trip_to_vehicle == {"1.1": "2"}
    assert built.trip_updates_vehicle_to_trip == {"1": "1.1", "2": "1.1"}


def test_an_id_without_its_partner_lands_in_a_set_and_in_no_map(tmp_path):
    built = index(
        tmp_path,
        entity(trip_update("1.1", None), vehicle_position("44", None)),
    )

    assert built is not None
    assert built.trip_updates_trip_to_vehicle == {}
    assert built.vehicle_positions_vehicle_to_trip == {}
    assert (built.trips_without_vehicles, built.vehicles_without_trips) == (("1.1",), ("44",))


# --- iteration order --------------------------------------------------------


def test_the_two_iterated_maps_come_back_in_java_hash_order(tmp_path):
    """Measured under JDK 17.0.19: `{"100", "101", "44", "45"}` iterates
    `44, 100, 45, 101`, which is neither insertion nor sorted order. The two
    lookup-only maps are left in insertion order, because upstream reaches them
    through `containsKey` and `get` only and their order never escapes."""
    built = index(
        tmp_path,
        *[
            entity(trip_update(trip_id, "v"), vehicle_position(trip_id, "t"))
            for trip_id in ("100", "101", "44", "45")
        ],
    )

    assert built is not None
    assert list(built.trip_updates_trip_to_vehicle) == ["44", "100", "45", "101"]
    assert list(built.vehicle_positions_vehicle_to_trip) == ["44", "100", "45", "101"]


def test_the_two_sets_come_back_in_java_hash_order(tmp_path):
    """The same key set through the two `HashSet`s, which the differential
    measured to iterate identically to a `HashMap`."""
    built = index(
        tmp_path,
        *[
            entity(trip_update(trip_id, None), vehicle_position(trip_id, None))
            for trip_id in ("100", "101", "44", "45")
        ],
    )

    assert built is not None
    assert built.trips_without_vehicles == ("44", "100", "45", "101")
    assert built.vehicles_without_trips == ("44", "100", "45", "101")


# --- the memo ---------------------------------------------------------------


def test_the_index_is_built_once_per_message(tmp_path):
    """Two rules read this, and the runner builds one `memo` per message, so the
    pass runs once between them."""
    _, ctx = combined(tmp_path, entity(trip_update("1.1", "1"), vehicle_position("44", "100")))

    assert index_for(ctx) is index_for(ctx)
    assert MEMO_KEY in ctx.memo


def test_an_early_return_is_memoised_too(tmp_path):
    """`None` is an answer, and recomputing it per rule would walk the entities
    again for every rule that asks."""
    _, ctx = combined(tmp_path, entity(trip_update("1.1", "1")))

    assert index_for(ctx) is None
    assert ctx.memo[MEMO_KEY] is None


# --- named roles ------------------------------------------------------------


def test_a_cycle_spans_every_roles_message(tmp_path):
    """Upstream's cross-feed rules only fire when a single file mixes entity
    types, so an agency publishing TripUpdates and VehiclePositions separately
    never gets them compared at all. A cycle is one message per role, so here
    they are."""
    _, ctx = combined_roles(
        tmp_path,
        {
            "tu": [entity(trip_update("1.1", "1"))],
            "vp": [entity(vehicle=vehicle_position("44", "100"))],
        },
    )
    built = index_for(ctx)

    assert built is not None
    assert built.trip_updates_trip_to_vehicle == {"1.1": "1"}
    assert built.vehicle_positions_vehicle_to_trip == {"44": "100"}


def test_a_cycle_missing_a_role_falls_to_the_same_early_return(tmp_path):
    """A role whose file failed to decode is absent from its cycle rather than
    carried forward, which is one of the two counts at zero."""
    _, ctx = combined_roles(tmp_path, {"tu": [entity(trip_update("1.1", "1"))]})

    assert index_for(ctx) is None


def test_entities_are_read_in_role_order_then_wire_order(tmp_path):
    """`CombinedFeed.entities()` is the pass's input, and its order is what
    decides which of two writes to one key wins."""
    _, ctx = combined_roles(
        tmp_path,
        {
            "vp": [entity(vehicle=vehicle_position("44", "100"))],
            "tu": [entity(trip_update("1.1", "1")), entity(trip_update("1.1", "2"))],
        },
    )
    built = index_for(ctx)

    assert built is not None
    assert built.trip_updates_trip_to_vehicle == {"1.1": "2"}


def test_the_index_reads_the_cycle_and_never_the_hosts_own_message(tmp_path):
    """`index_for` takes no message: everything comes off `ctx.combined`. A rule
    that read the message it was handed instead would see one role's entities
    out of a cycle's several, and the host role here carries no
    VehiclePosition at all."""
    _, ctx = combined_roles(
        tmp_path,
        {
            "tu": [entity(trip_update("1.1", "1"))],
            "vp": [entity(vehicle=vehicle_position("44", "100"))],
        },
    )
    built = index_for(ctx)

    assert ctx.role == "tu"
    assert built is not None and built.vehicle_positions_vehicle_to_trip == {"44": "100"}
