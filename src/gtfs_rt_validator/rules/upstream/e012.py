"""E012: an entity timestamp greater than the header timestamp.

Two emission sites, `TimestampValidator.java:150-153` for a TripUpdate and
`:277-280` for a VehiclePosition. Both require the entity timestamp to be
non-zero, both require the *header* timestamp to be non-zero, and both compare
strictly, so an entity equal to the header is fine.

Neither site is gated on `isPosix`, and E012 is tested before E001 on the same
value, so a timestamp in milliseconds that is also greater than the header
reports under both ids. stop_time_update times are not checked against the
header at all; only the two entity timestamps are.

The prefix is the same local the VehiclePosition's E001 uses (`:276`), which is
why an absent vehicle descriptor gives `"vehicle_id  timestamp ..."` with two
spaces.
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

RULE_ID = "E012"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """Every E012 the shared walk saw, in entity order, TripUpdate before vehicle."""
    for event in events_for(RULE_ID, timestamps, message, ctx):
        yield Occurrence(RULE_ID, event.prefix, event.context)
