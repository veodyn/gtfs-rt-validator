"""W003, against upstream's own `CrossFeedDescriptorValidatorTest.testW003`.

Every assertion marked "upstream" is transcribed from the real
`CrossFeedDescriptorValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testW003`, lines 42-203), case by case in its order, not from a
second-hand summary of it. Upstream asserts *counts* and nothing else, so every
assertion about occurrence text or order below is ours, read off
`CrossFeedDescriptorValidator.java:125-164`.

Upstream's test passes its message as `combinedFeedMessage` directly, bypassing
`BatchProcessor`'s `GtfsUtils.isCombinedFeed` gate; `crossfeedfixtures.combined`
is the same thing, a compat cycle whose single message is its own combined view.

Where a container below holds more than one entry, Java hash iteration order
reaches output. Those orders are measured, from `tools/DumpHashOrder.java` under
JDK 17.0.19, and `rules/_shared/javahash.py` has to reproduce them.
"""

from __future__ import annotations

from crossfeedfixtures import combined, combined_of, trip_update, vehicle_position
from gtfs_rt_validator.proto.decode import decode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA
from gtfs_rt_validator.rules.upstream.w003 import RULE_ID, check
from jarcorpus import input_bytes, parsed
from rulefixtures import context, entity, message, occurrences, prefixes

#: The one crafted feed in the committed corpus that mixes entity types, and so
#: the only one the jar ran this validator against.
GOLDEN_FEED = "04-combined-feed.pb"


def golden_prefixes() -> list[str]:
    """W003's occurrence prefixes, in order, out of the committed jar output."""
    groups = parsed(GOLDEN_FEED)
    group = next(g for g in groups if g["errorMessage"]["validationRule"]["errorId"] == RULE_ID)
    return [occurrence["prefix"] for occurrence in group["occurrenceList"]]


# --- upstream's testW003, case by case --------------------------------------


def test_the_same_trip_and_vehicle_id_in_both_halves_is_not_a_finding(tmp_path):
    """Upstream, testW003 case 1 (`:51-66`): TripUpdate and VehiclePosition on
    one entity, both trip_id `1.1` and vehicle.id `1`, `expected.clear()`."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position("1", "1.1")),
    )

    assert occurrences(check(built, ctx)) == []


def test_four_ids_none_of_which_the_other_half_has_reports_four_times(tmp_path):
    """Upstream, testW003 case 2 (`:68-82`): VehiclePosition moved to trip_id
    `100` and vehicle.id `44` while the TripUpdate keeps `1.1` and `1`,
    `expected.put(W003, 4)`."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position("44", "100")),
    )

    assert len(occurrences(check(built, ctx))) == 4


def test_two_entities_with_cleared_ids_report_four_times(tmp_path):
    """Upstream, testW003 case 3 (`:84-120`): the TripUpdates' vehicle.id and
    the VehiclePositions' trip_id both cleared, two entities, four warnings.
    Everything lands in the two sets, so loops 3 and 4 do the reporting."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("100", None), vehicle_position("44", None)),
        entity(trip_update("101", None), vehicle_position("45", None)),
    )

    assert len(occurrences(check(built, ctx))) == 4


def test_two_entities_with_empty_string_ids_report_four_times(tmp_path):
    """Upstream, testW003 case 4 (`:122-157`): the same feed with `setId("")`
    and `setTripId("")` instead of `clearId()` and `clearTripId()`, and the same
    four warnings. `StringUtils.isEmpty` is null or zero length, so the two
    spellings take the same branch."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("100", ""), vehicle_position("44", "")),
        entity(trip_update("101", ""), vehicle_position("45", "")),
    )

    assert len(occurrences(check(built, ctx))) == 4


def test_a_feed_with_no_trip_updates_reports_nothing(tmp_path):
    """Upstream, testW003 case 5 (`:159-168`): the TripUpdate cleared off the
    only entity, `expected.clear()`. `tripUpdateCount == 0` returns early."""
    built, ctx = combined(tmp_path, entity(vehicle=vehicle_position("45", "")))

    assert occurrences(check(built, ctx)) == []


def test_a_feed_with_no_vehicle_positions_reports_nothing(tmp_path):
    """Upstream, testW003 case 6 (`:170-200`): two TripUpdates with empty
    vehicle.ids and no VehiclePosition anywhere, `expected.clear()`."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("100", "")),
        entity(trip_update("101", "")),
    )

    assert occurrences(check(built, ctx)) == []


# --- the occurrence text, which upstream's test never looks at --------------


def test_every_occurrence_carries_this_rules_id(tmp_path):
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position("44", "100")),
    )

    assert {found.rule_id for found in occurrences(check(built, ctx))} == {RULE_ID}


def test_the_four_prefixes_are_the_four_java_writes_in_loop_order(tmp_path):
    """Ours, read off `:125-164`. Loop 1 reports the TripUpdates trip_id then
    its vehicle_id, then loop 2 reports the VehiclePositions vehicle_id then its
    trip_id. Each map holds one entry here, so hash order cannot reorder it."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position("44", "100")),
    )

    assert prefixes(check(built, ctx)) == [
        "trip_id 1.1 is in TripUpdates but not in VehiclePositions feed",
        "vehicle_id 1 is in TripUpdates but not in VehiclePositions feed",
        "vehicle_id 44 is in VehiclePositions but not in TripUpdates feed",
        "trip_id 100 is in VehiclePositions but not in TripUpdates feed",
    ]


def test_the_two_sets_are_reported_after_both_maps_in_java_hash_order(tmp_path):
    """Ours, and the same feed as upstream's case 3. Loop 3 walks
    `tripsWithoutVehicles` and loop 4 walks `vehiclesWithoutTrips`; measured
    under JDK 17.0.19, `{"100", "101"}` iterates `100, 101` and `{"44", "45"}`
    iterates `44, 45`."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("100", None), vehicle_position("44", None)),
        entity(trip_update("101", None), vehicle_position("45", None)),
    )

    assert prefixes(check(built, ctx)) == [
        "trip_id 100 is in TripUpdates but not in VehiclePositions feed",
        "trip_id 101 is in TripUpdates but not in VehiclePositions feed",
        "vehicle_id 44 is in VehiclePositions but not in TripUpdates feed",
        "vehicle_id 45 is in VehiclePositions but not in TripUpdates feed",
    ]


def test_the_golden_feed_reports_what_the_jar_reported_for_it_in_its_order(tmp_path):
    """Ours, and the check that ties this rule to a real jar run: the committed
    `.pb` decoded and the committed `.results.json` read, rather than either
    restated here. `04-combined-feed.pb` is the only crafted feed that mixes
    entity types, which is what makes it the only one the jar ran this validator
    against."""
    built = decode(input_bytes(GOLDEN_FEED), SCHEMA)

    assert prefixes(check(built, combined_of(tmp_path, built))) == golden_prefixes()


# --- the guards -------------------------------------------------------------


def test_a_message_that_is_not_its_cycles_host_reports_nothing(tmp_path):
    """Ours. `combinedFeedMessage == null` (`:50-53`) is `ctx.combined is None`
    here, which the runner leaves on every message but its cycle's host."""
    built = message(entity(trip_update("1.1", "1"), vehicle_position("44", "100")))

    assert occurrences(check(built, context(tmp_path))) == []


def test_a_trip_update_with_no_trip_id_is_not_indexed_and_does_not_count(tmp_path):
    """Ours. `hasTripId` is `hasTrip() && getTrip().hasTripId()` (`:181-183`),
    so a TripUpdate whose TripDescriptor carries no trip_id leaves
    `tripUpdateCount` at zero and the whole validator returns early."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update(vehicle_id="1"), vehicle_position("44", "100")),
    )

    assert occurrences(check(built, ctx)) == []


def test_a_vehicle_position_with_no_vehicle_id_is_not_indexed_and_does_not_count(tmp_path):
    """Ours, the mirror of the above through `hasVehicleId` (`:191-193`)."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1"), vehicle_position(trip_id="100", vehicle=False)),
    )

    assert occurrences(check(built, ctx)) == []


def test_an_empty_trip_id_still_counts_as_a_trip_update(tmp_path):
    """Ours, and the distinction the coordinator's audit turned up: the count at
    `:82` increments on *presence*, before the `StringUtils.isEmpty` test at
    `:88`. So a TripUpdate whose trip_id is `""` gets past the second early
    return, and the empty string itself becomes the key in
    `tripsWithoutVehicles`."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("", None), vehicle_position("44", None)),
    )

    assert prefixes(check(built, ctx)) == [
        "trip_id  is in TripUpdates but not in VehiclePositions feed",
        "vehicle_id 44 is in VehiclePositions but not in TripUpdates feed",
    ]


# --- the maps, and what collapses in them -----------------------------------


def test_two_trip_updates_sharing_a_vehicle_id_keep_both_trip_keyed_entries(tmp_path):
    """Ours. `:93` is keyed by trip_id and `:94` by vehicle_id, so a shared
    vehicle_id collapses only the second of the two. Both trips therefore report
    from loop 1, and the shared vehicle_id reports twice with it."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1")),
        entity(trip_update("1.2", "1")),
        entity(vehicle=vehicle_position("44", "100")),
    )

    assert prefixes(check(built, ctx)) == [
        "trip_id 1.1 is in TripUpdates but not in VehiclePositions feed",
        "vehicle_id 1 is in TripUpdates but not in VehiclePositions feed",
        "trip_id 1.2 is in TripUpdates but not in VehiclePositions feed",
        "vehicle_id 1 is in TripUpdates but not in VehiclePositions feed",
        "vehicle_id 44 is in VehiclePositions but not in TripUpdates feed",
        "trip_id 100 is in VehiclePositions but not in TripUpdates feed",
    ]


def test_two_trip_updates_sharing_a_trip_id_collapse_to_the_last_one(tmp_path):
    """Ours. `:93` is last-write-wins on the trip_id key, so the second
    TripUpdate's vehicle_id is the one that survives, and the first one's is
    never reported."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1")),
        entity(trip_update("1.1", "2")),
        entity(vehicle=vehicle_position("44", "100")),
    )

    assert prefixes(check(built, ctx)) == [
        "trip_id 1.1 is in TripUpdates but not in VehiclePositions feed",
        "vehicle_id 2 is in TripUpdates but not in VehiclePositions feed",
        "vehicle_id 44 is in VehiclePositions but not in TripUpdates feed",
        "trip_id 100 is in VehiclePositions but not in TripUpdates feed",
    ]


def test_a_vehicle_id_that_is_in_the_other_half_without_a_trip_is_not_a_finding(tmp_path):
    """Ours, the `&& !vehiclesWithoutTrips.contains(...)` half of `:130`. The
    vehicle_id is in VehiclePositions, just not in a map, so W003 does not claim
    it is missing there."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", "1")),
        entity(vehicle=vehicle_position("1", None)),
    )

    assert prefixes(check(built, ctx)) == [
        "trip_id 1.1 is in TripUpdates but not in VehiclePositions feed",
    ]


def test_a_trip_id_that_is_in_the_other_half_without_a_vehicle_is_not_a_finding(tmp_path):
    """Ours, the mirror of `:143`."""
    built, ctx = combined(
        tmp_path,
        entity(trip_update("1.1", None)),
        entity(vehicle=vehicle_position("44", "1.1")),
    )

    assert prefixes(check(built, ctx)) == [
        "vehicle_id 44 is in VehiclePositions but not in TripUpdates feed",
    ]


# Named roles have no counterpart upstream, so what a cross-file cycle means for
# these two rules is asserted against the shared index in
# `tests/test_shared_crossfeed.py` rather than through W003's loops.
