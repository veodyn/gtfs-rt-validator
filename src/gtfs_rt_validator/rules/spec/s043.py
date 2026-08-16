"""S043: a `StopSelector.stop_id` that neither feed defines.

Cites `1242#1`, the whole comment on the field:

> Must be the same as in stops.txt in the corresponding GTFS feed.

`must` is where the ERROR comes from, and `stops.txt` is the whole permitted
answer: the sentence names one place and there is no second one.

**A `Stop` entity of the same feed does not resolve this field, and that is the
correction.** The first draft read a `StopSelector` through the same widened
resolution `ReplacementStop.stop_id` gets, on the reasoning that a realtime feed
may define stops of its own. It may, and `:1259` says so for that other field
in so many words. It says nothing of the kind here, and `:1163` says why it
could not: a `start_stop_selector` names "the first stop_time of the *original*
trip", and a stop this feed has just invented is not on the original trip. The
two selectors and the replacement stops are the two halves of one `Modification`
and they point in opposite directions, one into the schedule being changed and
one into the change. So `_shared/references.py` has two entry points, and this
rule takes `selected_stop_resolves`, which cannot be handed a `FeedIndex` at
all. S046 keeps the widened `stop_resolves`.

The index is still read, for one thing: a value `stops.txt` lacks that a `Stop`
entity of this feed does define is a producer who put a new stop where a
selector goes, and the occurrence says so rather than calling it a typo.

**Why this is not E011, which asserts the same thing about other fields.**
E011 walks three sites (`StopValidator.java:53-101`): a StopTimeUpdate, a
VehiclePosition, an alert's informed entities. `TripModifications` is in none of
them and is not in the 2015 schema E011 decodes with at all, so the boundary is
the field rather than the question. `rules/upstream/e011.py` must not grow a
branch for this message: the fix for an upstream rule that is too narrow for the
current source is a new id.

**No jar oracle, and no jar counter-oracle either.** `StopSelector` postdates the
jar, so a fixture whose only defect is this one decodes there as unknown fields
and the jar emits nothing at all. The declared overlap with E011, which
`OVERLAP` in `tests/test_tier_overlap.py` records, rests on reading
`StopValidator.java` and not on a differential.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.manifest import Severity
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.feed_index import index
from gtfs_rt_validator.rules._shared.references import (
    selected_stop_resolves,
    selected_stop_unresolved,
)
from gtfs_rt_validator.rules._shared.walk_trip_modifications import SELECTOR_FIELDS, modifications
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S043"

CLAUSE = "spec: Must be the same as in stops.txt in the corresponding GTFS feed."


@rule(RULE_ID, source=CLAUSE, severity=Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """Both selectors of every modification, the ones naming a stop_id only.

    The selector names come from `SELECTOR_FIELDS` rather than being spelled
    again here, so this rule and S042 cannot come to disagree about where a
    `StopSelector` lives.
    """
    feed = index(message, ctx)
    for record in modifications(message, ctx):
        for name in SELECTOR_FIELDS:
            selector = record.modification.get(name)
            if not selector.has("stop_id"):
                continue
            stop_id = selector.get("stop_id")
            if not selected_stop_resolves(stop_id, ctx):
                yield Occurrence(
                    RULE_ID,
                    selected_stop_unresolved(stop_id, feed),
                    {ENTITY_PATH_KEY: f"{record.path}.{name}"},
                )
