"""E016: a trip_id with schedule_relationship ADDED that GTFS already has.

The mirror of E003, and the `else` arm of the same `if` in the dispatch:
`validation/rules/TripDescriptorValidator.java:108-111` for a TripUpdate and
`:156-159` for a VehiclePosition. It shares E003's two prefix shapes, the
TripUpdate one through `GtfsUtils.getTripId` and the VehiclePosition one built
inline out of an unguarded `getVehicle().getVehicle().getId()`.

**The enum gap silences this rule where it fires E003.** `GtfsUtils.isAddedTrip`
is `hasScheduleRelationship() && ... == ADDED`, and protobuf 2.6.1 files a
post-2015 enum value as an unknown field, so a trip declaring DUPLICATED is not
an ADDED trip: E003 fires for it when the trip is missing from GTFS, and this
rule stays quiet when the trip is present. Decoding with the current schema and
masking afterwards cannot produce that; see `tests/test_two_views.py`.

`checkE023` runs from this same `else` arm, after the E016 test, which is why a
trip present in GTFS can report E016 and E023 together.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.walk_trip_descriptor import trip_descriptors
from gtfs_rt_validator.rules._shared.walks import events_for
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "E016"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
