"""S012: an `assigned_stop_id` that `stops.txt` does not define.

`272#1`, and it is a **definitional** clause rather than a normative one:
"Refers to a stop_id defined in the GTFS stops.txt." carries no modal verb, so
`tools/scan_clauses.py` merges it from the verdict file's `definitional` list
with its severity pinned to ERROR by the kind. There is no advisory reading of a
value domain. A real-time stop assignment naming a stop nobody defined cannot be
applied by any consumer, which is a different thing from an ill-advised
assignment. Do not try to re-cite this to something with a "must"; the four
guards in the generator exist to keep the slot from becoming an escape hatch.

**Not E011**, which reads `StopTimeUpdate.stop_id`. Different field, same
message, and the two can disagree, which is S011. All three can fire on one
update and each says something the others do not; `tests/test_rule_s012.py`
shows the two-way separation against E011 itself.

The rest of the block at `:273-278` is rejected under R3: "should not result in
a significantly different trip experience for the end user" is not decidable
from feed bytes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import relationships
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, which nothing under `rules/` may import at run time.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "S012"

CLAUSE = "Refers to a stop_id defined in the GTFS stops.txt."

UNKNOWN = (
    "trip_id {trip_id} stop_time_update[{index}] assigned_stop_id {stop_id} is not in stops.txt"
)

PROPERTIES = "stop_time_properties"

ASSIGNED = "assigned_stop_id"


@rule(RULE_ID, source=f"spec: {CLAUSE}", severity=manifest.Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per assigned stop the static feed does not define."""
    return [
        found
        for record in relationships(message, ctx)
        if record.payload == "trip_update"
        for found in _of_trip(record, ctx)
    ]


def _of_trip(record: TripRelationship, ctx: RuleContext) -> list[Occurrence]:
    trip_id = record.trip.get("trip_id")
    known = ctx.static.stop_ids
    return [
        Occurrence(
            RULE_ID,
            UNKNOWN.format(
                trip_id=trip_id,
                index=stop_time.index,
                stop_id=stop_time.update.get(PROPERTIES).get(ASSIGNED),
            ),
            {
                ENTITY_PATH_KEY: stop_time.path,
                "tripId": trip_id,
                "assignedStopId": stop_time.update.get(PROPERTIES).get(ASSIGNED),
            },
        )
        for stop_time in record.stop_time_updates
        if stop_time.update.get(PROPERTIES).has(ASSIGNED)
        and stop_time.update.get(PROPERTIES).get(ASSIGNED) not in known
    ]
