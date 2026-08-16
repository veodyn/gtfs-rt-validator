"""E047, against upstream's own `CrossFeedDescriptorValidatorTest.testE047`.

Every assertion marked "upstream" is transcribed from the real
`CrossFeedDescriptorValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testE047`, lines 209-449), case by case in its order, not from a
second-hand summary of it. Upstream asserts counts for E047 *and* W003 in the
same rows, and those W003 counts are asserted here too: this rule and W003 read
one index, so a row where E047 is right and W003 is wrong means the index is
wrong.

Every assertion about occurrence text is ours, read off
`CrossFeedDescriptorValidator.java:202-235`.

The static feed is `crossfeedfixtures.testagency_tables`, which carries
`testagency.zip`'s block_ids: trips `6.1` and `7.1` share `block.1`, and `44`,
`45`, `100` and `101` are in no `trips.txt` row, which is what makes
`tripA == null` reachable.
"""

from __future__ import annotations

from crossfeedfixtures import combined, trip_update, vehicle_position
from gtfs_rt_validator.rules.upstream.e047 import RULE_ID, check
from gtfs_rt_validator.rules.upstream.w003 import check as w003
from rulefixtures import context, entity, message, occurrences, prefixes

TRIP_UPDATES_SIDE = (
    "vehicle_id 1 and trip_id 1.1 pairing in TripUpdates does not match vehicle_id 44 "
    "and trip_id 1.1 pairing in VehiclePositions feed"
)

VEHICLE_POSITIONS_SIDE = (
    "trip_id 44 and vehicle_id 1 pairing in VehiclePositions does not match trip_id 1.1 "
    "and vehicle_id 1 pairing in TripUpdates feed and trip block_ids aren't the same"
)


def counts(built, ctx) -> tuple[int, int]:
    """How many E047 and how many W003, which is what upstream asserts."""
    return len(occurrences(check(built, ctx))), len(occurrences(w003(built, ctx)))


# --- upstream's testE047, case by case --------------------------------------


def test_the_same_pairing_in_both_halves_is_not_a_finding(tmp_path):
    """Upstream, testE047 case 1 (`:218-233`): trip_id `1.1` and vehicle.id `1`
    on both, `expected.clear()`."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position("1", "1.1")),
    )

    assert counts(built, ctx) == (0, 0)


def test_one_trip_id_with_two_vehicle_ids_reports_from_the_trip_updates_side(tmp_path):
    """Upstream, testE047 case 2 (`:235-252`): VehiclePosition moved to
    vehicle.id `44` while keeping trip_id `1.1`, `E047 = 1`, `W003 = 2`."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position("44", "1.1")),
    )

    assert counts(built, ctx) == (1, 2)
    assert prefixes(check(built, ctx)) == [TRIP_UPDATES_SIDE]


def test_one_vehicle_id_with_two_trip_ids_reports_from_the_vehicle_positions_side(tmp_path):
    """Upstream, testE047 case 3 (`:254-270`): VehiclePosition moved to trip_id
    `44` while keeping vehicle.id `1`, `E047 = 1`, `W003 = 2`. Trip `44` is in
    no `trips.txt` row, so `tripA == null` and the block test never runs."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position("1", "44")),
    )

    assert counts(built, ctx) == (1, 2)
    assert prefixes(check(built, ctx)) == [VEHICLE_POSITIONS_SIDE]


def test_two_ids_that_share_nothing_are_four_warnings_and_no_error(tmp_path):
    """Upstream, testE047 case 4 (`:272-287`): VehiclePosition at trip_id `44`
    and vehicle.id `45`, `expected.clear()` then `W003 = 4`. Neither `get`
    finds anything, so E047 never reaches its comparison."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position("45", "44")),
    )

    assert counts(built, ctx) == (0, 4)


def test_two_vehicle_positions_with_an_empty_trip_id_are_four_warnings(tmp_path):
    """Upstream, testE047 case 5 (`:289-315`): VehiclePosition trip_id `""` on
    two entities, vehicle.ids `45` and `100`, the second entity with no
    TripUpdate at all, `W003 = 4` and no E047."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position("45", "")),
        entity(vehicle=vehicle_position("100", "")),
    )

    assert counts(built, ctx) == (0, 4)


def test_two_vehicle_positions_with_a_cleared_trip_id_are_four_warnings(tmp_path):
    """Upstream, testE047 case 6 (`:317-343`): the same feed with `clearTripId()`
    instead of `setTripId("")`, and the same counts."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position("45", None)),
        entity(vehicle=vehicle_position("100", None)),
    )

    assert counts(built, ctx) == (0, 4)


def test_empty_ids_on_both_halves_of_two_entities_are_four_warnings(tmp_path):
    """Upstream, testE047 case 7 (`:345-382`): TripUpdate vehicle.id `""` with
    trip_ids `1` and `2`, VehiclePosition trip_id `""` with vehicle.ids `45` and
    `46`, `W003 = 4` and no E047. Both maps stay empty, so both counts come from
    entities whose ids are present and blank."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1", ""), vehicle_position("45", "")),
        entity(trip_update("2", ""), vehicle_position("46", "")),
    )

    assert counts(built, ctx) == (0, 4)


def test_cleared_ids_on_both_halves_of_two_entities_are_four_warnings(tmp_path):
    """Upstream, testE047 case 8 (`:384-422`): the same with `clearId()` and
    `clearTripId()`."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1", None), vehicle_position("45", None)),
        entity(trip_update("2", None), vehicle_position("46", None)),
    )

    assert counts(built, ctx) == (0, 4)


def test_two_trips_in_one_block_share_a_vehicle_without_an_error(tmp_path):
    """Upstream, testE047 case 9 (`:424-448`): TripUpdate `6.1` / `45` against
    VehiclePosition `7.1` / `45`, where `6.1` and `7.1` share `block.1`, so the
    same vehicle serving both is legal. `expected.clear()` then `W003 = 2`. This
    is the only exemption in either rule and it exists on this side only."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("6.1", "45"), vehicle_position("45", "7.1")),
    )

    assert counts(built, ctx) == (0, 2)


# --- the block exemption, which upstream tests only in the passing direction -


def test_two_trips_in_different_blocks_are_an_error(tmp_path):
    """Ours. `6.1` is in `block.1` and `6.2` is in `block.2`, so the final
    `!tripA.getBlockId().equals(tripB.getBlockId())` fires."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("6.1", "45"), vehicle_position("45", "6.2")),
    )

    assert len(occurrences(check(built, ctx))) == 1


def test_a_trip_with_no_block_id_is_not_exempt(tmp_path):
    """Ours, the `StringUtils.isEmpty(tripA.getBlockId())` half of `:228`.
    `1.1` has a blank `block_id`, which the sibling's loader types as `None`,
    and blank is not the same as matching."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("6.1", "45"), vehicle_position("45", "1.1")),
    )

    assert len(occurrences(check(built, ctx))) == 1


def test_the_exemption_is_not_available_on_the_trip_updates_side(tmp_path):
    """Ours, and the asymmetry worth a test of its own: `checkE047TripUpdates`
    (`:202-210`) reads no GTFS at all. Two trips in one block still report when
    it is the vehicle_ids that differ."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("6.1", "45"), vehicle_position("46", "6.1")),
    )

    assert prefixes(check(built, ctx)) == [
        (
            "vehicle_id 45 and trip_id 6.1 pairing in TripUpdates does not match vehicle_id 46 "
            "and trip_id 6.1 pairing in VehiclePositions feed"
        )
    ]


# --- the occurrence text and the guards -------------------------------------


def test_every_occurrence_carries_this_rules_id(tmp_path):
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position("44", "1.1")),
    )

    assert [found.rule_id for found in occurrences(check(built, ctx))] == [RULE_ID]


def test_the_trip_updates_prefix_interpolates_the_one_trip_id_twice(tmp_path):
    """Ours, read off `:207`: `trip.getKey()` appears on both sides of the
    sentence, so the two trip_ids in that message are always the same string.
    That reads like a bug and is reproduced deliberately."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position("44", "1.1")),
    )

    assert prefixes(check(built, ctx))[0].count("trip_id 1.1") == 2


def test_the_vehicle_positions_prefix_interpolates_the_one_vehicle_id_twice(tmp_path):
    """Ours, read off `:231`, the mirror of the above through `vehicle.getKey()`."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position("1", "44")),
    )

    assert prefixes(check(built, ctx))[0].count("vehicle_id 1") == 2


def test_both_sides_can_report_from_one_feed_trip_updates_first(tmp_path):
    """Ours. The two halves are called from W003's loops 1 and 2 in that order,
    so a feed that mismatches both ways reports the TripUpdates side first."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position("44", "1.1")),
        entity(vehicle=vehicle_position("1", "44")),
    )

    assert prefixes(check(built, ctx)) == [TRIP_UPDATES_SIDE, VEHICLE_POSITIONS_SIDE]


def test_a_message_that_is_not_its_cycles_host_reports_nothing(tmp_path):
    """Ours. `combinedFeedMessage == null` (`:50-53`) is `ctx.combined is None`."""
    built = message(entity(trip_update("1.1", "1"), vehicle_position("44", "1.1")))

    assert occurrences(check(built, context(tmp_path))) == []


def test_a_feed_with_no_vehicle_positions_reports_nothing(tmp_path):
    """Ours, the second early return (`:119-122`) from this rule's side."""
    built, ctx = combined(tmp_path, entity(trip_update("1.1", "1")))

    assert occurrences(check(built, ctx)) == []
