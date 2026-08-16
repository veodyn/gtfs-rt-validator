"""E047: a VehiclePosition and a TripUpdate that pair the same ids differently.

Ported from `validation/rules/CrossFeedDescriptorValidator.java:202-235` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`. Upstream calls the two halves from
inside W003's first two loops (`:134`, `:147`) but collects them into a separate
list and emits that list after W003's whole group (`:166-171`), so this module
walks the same two containers of `rules/_shared/crossfeed.py`'s index in the
same order and reports only its own findings.

**Both halves fire only when the *other* feed knows the key.** `get` returning
null, or the empty string, means there is nothing to compare against and W003
has already said the id is missing; `StringUtils.isEmpty` is null or zero
length, so a blank id that reached a map cannot produce a mismatch either.

**The block exemption exists on one side only.** `checkE047VehiclePositions`
reads `trips.txt` and lets the pairing through when both trips exist, both carry
a `block_id`, and the two match: one vehicle serving two trips of one block is
legal (upstream issue #255). `checkE047TripUpdates` reads no GTFS at all, so the
same two trips still report when it is the vehicle_ids that differ. That
asymmetry is upstream's, not an oversight here.

**The two prefixes each interpolate one id twice.** The TripUpdates side writes
`trip.getKey()` on both sides of its sentence and the VehiclePositions side
writes `vehicle.getKey()` on both, so the "does not match" clause always repeats
the id the two feeds agree on rather than naming the one they disagree about.
Under `--compat` that is the byte sequence to reproduce.

`Trip.getBlockId()` is `null` for a trip whose `block_id` cell is blank, and the
sibling's loader types a blank cell as `None`, so the two agree and the
`isEmpty` test needs no special case here.
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
    from gtfs_rt_validator.static.context import StaticContext

RULE_ID = "E047"

TRIP_UPDATES_SIDE = (
    "vehicle_id {tu_vehicle_id} and trip_id {trip_id} pairing in TripUpdates does not match "
    "vehicle_id {vp_vehicle_id} and trip_id {trip_id} pairing in VehiclePositions feed"
)

VEHICLE_POSITIONS_SIDE = (
    "trip_id {vp_trip_id} and vehicle_id {vehicle_id} pairing in VehiclePositions does not match "
    "trip_id {tu_trip_id} and vehicle_id {vehicle_id} pairing in TripUpdates feed and trip "
    "block_ids aren't the same"
)


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """The TripUpdates half over W003's loop 1, then the VehiclePositions half.

    `message` is unread for the same reason as in W003: the subject is the
    cycle, which is `ctx.combined`.
    """
    index = index_for(ctx)
    if index is None:
        return

    for trip_id, tu_vehicle_id in index.trip_updates_trip_to_vehicle.items():
        vp_vehicle_id = index.vehicle_positions_trip_to_vehicle.get(trip_id, "")
        if vp_vehicle_id and tu_vehicle_id != vp_vehicle_id:
            yield Occurrence(
                RULE_ID,
                TRIP_UPDATES_SIDE.format(
                    tu_vehicle_id=tu_vehicle_id,
                    trip_id=trip_id,
                    vp_vehicle_id=vp_vehicle_id,
                ),
            )

    for vehicle_id, vp_trip_id in index.vehicle_positions_vehicle_to_trip.items():
        tu_trip_id = index.trip_updates_vehicle_to_trip.get(vehicle_id, "")
        if (
            tu_trip_id
            and vp_trip_id != tu_trip_id
            and not _same_block(ctx.static, vp_trip_id, tu_trip_id)
        ):
            yield Occurrence(
                RULE_ID,
                VEHICLE_POSITIONS_SIDE.format(
                    vp_trip_id=vp_trip_id,
                    vehicle_id=vehicle_id,
                    tu_trip_id=tu_trip_id,
                ),
            )


def _same_block(static: StaticContext, vp_trip_id: str, tu_trip_id: str) -> bool:
    """`:225-229` inverted: true is the exemption, so no occurrence.

    Every one of upstream's four disjuncts is a reason to report, and this is
    their negation: both trips in `trips.txt`, both with a non-blank `block_id`,
    and the two equal.
    """
    one = static.trips.get(vp_trip_id)
    other = static.trips.get(tu_trip_id)
    if one is None or other is None:
        return False
    block = one.get("block_id")
    return bool(block) and block == other.get("block_id")
