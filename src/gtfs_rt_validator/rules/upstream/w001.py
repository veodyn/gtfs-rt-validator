"""W001: a timestamp that is not populated.

Three emission sites in `validation/rules/TimestampValidator.java`, all
reached from the walk in `rules/_shared/walk_timestamp.py`: the header
(`:99`), a TripUpdate (`:148`) and a VehiclePosition (`:274`).

**The header site is half of a fork.** It fires only when the header timestamp
is 0 *and* `GtfsUtils.isV2orHigher` answered false. When that call throws, on a
`gtfs_realtime_version` that `Float.parseFloat` refuses, upstream's flag was
already `true` and E048 is logged here instead. `e048.py` is the other half, and
`_shared/versions.is_v2_or_higher` raises rather than answering `False` so that
both halves can exist.

**The three prefixes have three different shapes**, and only the middle one
goes through a `GtfsUtils` helper:

- `"header"`, the bare literal.
- `GtfsUtils.getTripId(entity, tripUpdate)`, which falls back to the entity id.
- `"vehicle_id " + vehiclePosition.getVehicle().getId()`, built inline with no
  presence guard at either step, so an absent vehicle gives a trailing space
  rather than the entity id. It is **not** `GtfsUtils.getVehicleId`, which
  spells the field `vehicle.id` and does fall back.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.walk_timestamp import timestamps
from gtfs_rt_validator.rules._shared.walks import events_for
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "W001"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """Every W001 the shared walk saw, in upstream's emission order."""
    for event in events_for(RULE_ID, timestamps, message, ctx):
        yield Occurrence(RULE_ID, event.prefix, event.context)
