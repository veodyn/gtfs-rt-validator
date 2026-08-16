"""S041: a `Modification` that declares no `start_stop_selector`.

Cites `1165#1`, which is one of the few sentences in the pinned proto that says
outright that an `optional` field is required:

> `start_stop_selector` is required and is used to define the reference stop
> used with `travel_time_to_stop`.

The field is declared `optional` for the same reason `Shape.shape_id` is, proto2
having no way to add a required field later, so the comment is the normative
source and the wire cardinality is not. `required` is what makes this an ERROR.

**Presence, never content.** A `StopSelector` that carries neither
`stop_sequence` nor `stop_id` is S042's finding, at its own clause `1238#1`.
Reporting it here as well would charge one mistake to two clauses, which is the
double-counting `tests/test_tier_overlap.py` exists to prevent.

No upstream rule reaches this message: `TripModifications` postdates the jar, so
the differential can neither confirm this rule nor refute the claim that it
borders nothing upstream (`OVERLAP` in `tests/test_tier_overlap.py` names no
neighbour for S041).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.manifest import Severity
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_trip_modifications import modifications
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S041"

CLAUSE = (
    "spec: `start_stop_selector` is required and is used to define the reference stop "
    "used with `travel_time_to_stop`."
)


@rule(RULE_ID, source=CLAUSE, severity=Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """One pass over the shared modification walk."""
    for record in modifications(message, ctx):
        if not record.modification.has("start_stop_selector"):
            yield Occurrence(
                RULE_ID,
                "a Modification with no start_stop_selector",
                {ENTITY_PATH_KEY: record.path},
            )
