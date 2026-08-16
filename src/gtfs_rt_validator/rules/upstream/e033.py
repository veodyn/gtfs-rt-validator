"""E033: an alert informed_entity that specifies nothing.

`checkE033` in `validation/rules/TripDescriptorValidator.java:388-405`, once per
`informed_entity` and before every other alert-side check.

The condition is two nested tests. The outer one asks whether the selector
itself carries an agency_id, a route_id, a route_type or a stop_id; **`trip` is
not in that list**. The inner one then asks whether the trip is absent
altogether or is present and carries neither a trip_id nor a route_id. So a
selector holding only an empty `trip` sub-message reports, and one holding a
trip with either id does not.

The prefix contains a doubled `"do not not reference"`. That is in the source at
`:402` and is reproduced verbatim: under `--compat` the text is the contract.
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

RULE_ID = "E033"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
