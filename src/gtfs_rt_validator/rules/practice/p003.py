"""P003: the `vehicle.id` carrying a trip changed between two messages.

`:89`, the `VehicleDescriptor.id` row. The sentence asks for two things at once
and this rule is the second: an id that identifies a vehicle *uniquely*, and one
that identifies it *stably* over the trip. A vehicle id that is renumbered every
iteration cannot be joined to anything a consumer already knows, so a rider
watching one bus sees a new vehicle appear each refresh.

**The unique half is E052's and is not reported here.**
`VehicleValidator.java:84-94`, ported in `rules/upstream/e052.py`, keeps a set
per *message* and reports a second VehiclePosition claiming an id already seen.
It is one message wide, it never looks at the message before, and it is scoped
to VehiclePositions. This rule is the other axis: one trip, two sequential
messages of the same role, and both payloads that carry a `TripDescriptor`. A
feed with one entity per message is invisible to E052 and is exactly this rule's
surface, which `tests/test_rule_p003.py` states as a fixture rather than as a
sentence.

**Absent is not blank, and the two get different answers.**
`_shared/walk_sequence_ids.py` reports `None` for a payload naming no
`VehicleDescriptor` or a descriptor naming no `id`, and `""` for an id the feed
set to the empty string.

* `None` on either side is silent. An id that was never there cannot have moved,
  so a trip that gains or loses a descriptor is not instability; the missing id
  is a different defect, and W002 is the rule that reports it for a
  VehiclePosition. Reporting it here would report it twice under a citation
  about stability rather than about presence.
* `""` is a value. The producer set the field, a consumer keys on what it was
  handed, and a feed going from `""` to `V1` has moved the identifier every
  consumer joined on. `StringUtils.isEmpty` collapses the two cases and this
  rule may not, which is why the walk keeps them apart at all.

That makes the comparison well defined without a single "if empty" branch: two
values that are both present and differ is a change, everything else is not.
The ids are quoted in the occurrence text for the same reason, so a blank one
reads as a blank one rather than as a missing word.

**Per role, per payload, and only where both messages carry the trip.** All
three come from the walk rather than from here, and `p002.py` gives the
arguments; this rule differs from that one in exactly which field it compares.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_sequence_ids import sequence_ids
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.walk_sequence_ids import SequencedTrip
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "P003"

CLAUSE = "Should uniquely and stably identify a vehicle over the entire trip duration"

MOVED = (
    'the {payload} carrying trip_id {trip_id} has vehicle.id "{current}" in this message '
    'and had "{previous}" in the previous message of this feed'
)


@rule(RULE_ID, source=f"practice: {CLAUSE}", severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per trip whose vehicle id moved, in this message's order."""
    return [_found(record) for record in sequence_ids(message, ctx) if _moved(record)]


def _moved(record: SequencedTrip) -> bool:
    """Whether two ids that are both there differ. See the module docstring on
    why `None` on either side is not a change."""
    current, previous = record.current.vehicle_id, record.previous.vehicle_id
    return current is not None and previous is not None and current != previous


def _found(record: SequencedTrip) -> Occurrence:
    return Occurrence(
        RULE_ID,
        MOVED.format(
            payload=record.payload,
            trip_id=record.trip_id,
            current=record.current.vehicle_id,
            previous=record.previous.vehicle_id,
        ),
        {
            ENTITY_PATH_KEY: record.current.path,
            "tripId": record.trip_id,
            "vehicleId": record.current.vehicle_id,
            "previousVehicleId": record.previous.vehicle_id,
        },
    )
