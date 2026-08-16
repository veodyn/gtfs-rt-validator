"""E032: an alert with no informed_entity at all.

`validation/rules/TripDescriptorValidator.java:194-197`, the `else` of the
`entitySelectors != null && entitySelectors.size() > 0` test that opens the
alert half. There is no `checkE032` to port: it is a bare `addOccurrence`, so
the condition and the text live next to the branch in
`_shared/walk_trip_descriptor.py`.

The null half of that test is unreachable through the decoder, since a repeated
field with no occurrences reads back as an empty list rather than as nothing.

At most one occurrence per alert, and none of the per-selector checks run for
such an alert, so E032 never accompanies E033.

The prefix is `"alert ID " + entity.getId() + " does not have an
informed_entity"`, which repeats the rule's own suffix almost word for word;
that is upstream's text and stays.
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

RULE_ID = "E032"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
