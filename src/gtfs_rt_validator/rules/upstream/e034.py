"""E034: an alert agency_id that GTFS `agency.txt` does not have.

`checkE034` in `validation/rules/TripDescriptorValidator.java:416-422`, once per
`informed_entity`, guarded on `hasAgencyId()`. The only rule in this validator
that reads `agency_ids`.

**What it compares against is not always an agency_id.** `BatchProcessor` never
calls `setDefaultAgencyId`, so onebusaway's reader falls back to
`agency.setId(agency.getName())` for an agency whose `agency_id` cell is blank.
On a single-agency feed that omits the column, this rule therefore matches
realtime agency ids against the agency *name*. `agency_id_of` in
`static/_tables.py` reproduces that, and it is a property of the static layer
rather than of this rule.

The prefix is `"alert ID " + entity.getId() + " agency_id " +
entitySelector.getAgencyId()`.
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

RULE_ID = "E034"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
