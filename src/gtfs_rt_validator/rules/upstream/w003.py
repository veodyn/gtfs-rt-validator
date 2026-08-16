"""W003: an id in one half of a combined feed that the other half does not have.

Ported from `validation/rules/CrossFeedDescriptorValidator.java:125-164` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`. The index the four loops read is
built in `rules/_shared/crossfeed.py`, which E047 shares; this module is the
loops and the four sentences.

**Four loops, in this order, and no de-duplication.** Two over the maps and two
over the sets, and the same id can legitimately report twice from different
loops. Loops 1 and 2 test two conditions each, so one map entry can produce two
occurrences.

**The two `contains` clauses are the subtle part.** Loop 1 does not report a
vehicle_id merely because it is in no VehiclePositions map: it also checks
`vehiclesWithoutTrips`, because a VehiclePosition carrying that vehicle_id and
no trip_id put it in the set instead of the map, and the id *is* in the other
feed. Loop 2 mirrors that against `tripsWithoutVehicles`. Dropping either clause
turns every blank-id feed into twice the warnings the jar reports.

**Where the order comes from.** Loops 1 and 2 iterate `HashMap.entrySet()` and
loops 3 and 4 iterate a `HashSet`, so this is the only rule in the project whose
output order is Java hash iteration order. The index hands the four containers
over already in that order; `rules/_shared/javahash.py` is what reproduces it,
and it refuses rather than guess for a key set that Java would treeify.

**The occurrence suffix is the empty string** (`ValidationRules.java`), so the
whole message is the prefix and the writer emits `"occurrenceSuffix" : ""`
rather than omitting the key. That is pinned by `tests/test_jar_output_contract.py`
against a real jar run, not asserted here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.crossfeed import index_for
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer, and
    # so the sibling, which nothing under `rules/` may import at run time.
    from collections.abc import Iterator

    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "W003"

TRIP_MISSING_FROM_VEHICLE_POSITIONS = (
    "trip_id {} is in TripUpdates but not in VehiclePositions feed"
)
VEHICLE_MISSING_FROM_VEHICLE_POSITIONS = (
    "vehicle_id {} is in TripUpdates but not in VehiclePositions feed"
)
VEHICLE_MISSING_FROM_TRIP_UPDATES = (
    "vehicle_id {} is in VehiclePositions but not in TripUpdates feed"
)
TRIP_MISSING_FROM_TRIP_UPDATES = "trip_id {} is in VehiclePositions but not in TripUpdates feed"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """Four loops over the cycle's index, in the Java's order.

    `message` is unread: this rule is about the whole cycle, which is
    `ctx.combined`, and the message it was handed is only one role's share of
    it. Under `--compat` the two are the same object.
    """
    index = index_for(ctx)
    if index is None:
        return

    # The two sets are membership tests here, not iteration, so a feed with many
    # blank ids does not turn each loop quadratic.
    without_vehicles = frozenset(index.trips_without_vehicles)
    without_trips = frozenset(index.vehicles_without_trips)

    for trip_id, vehicle_id in index.trip_updates_trip_to_vehicle.items():
        if trip_id not in index.vehicle_positions_trip_to_vehicle:
            yield Occurrence(RULE_ID, TRIP_MISSING_FROM_VEHICLE_POSITIONS.format(trip_id))
        missing = vehicle_id not in index.vehicle_positions_vehicle_to_trip
        if missing and vehicle_id not in without_trips:
            yield Occurrence(RULE_ID, VEHICLE_MISSING_FROM_VEHICLE_POSITIONS.format(vehicle_id))

    for vehicle_id, trip_id in index.vehicle_positions_vehicle_to_trip.items():
        if vehicle_id not in index.trip_updates_vehicle_to_trip:
            yield Occurrence(RULE_ID, VEHICLE_MISSING_FROM_TRIP_UPDATES.format(vehicle_id))
        if trip_id not in index.trip_updates_trip_to_vehicle and trip_id not in without_vehicles:
            yield Occurrence(RULE_ID, TRIP_MISSING_FROM_TRIP_UPDATES.format(trip_id))

    for trip_id in index.trips_without_vehicles:
        if trip_id not in index.vehicle_positions_trip_to_vehicle:
            yield Occurrence(RULE_ID, TRIP_MISSING_FROM_VEHICLE_POSITIONS.format(trip_id))

    for vehicle_id in index.vehicles_without_trips:
        if vehicle_id not in index.trip_updates_vehicle_to_trip:
            yield Occurrence(RULE_ID, VEHICLE_MISSING_FROM_TRIP_UPDATES.format(vehicle_id))
