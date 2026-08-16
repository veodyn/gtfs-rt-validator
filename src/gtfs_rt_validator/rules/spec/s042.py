"""S042: a `StopSelector` that selects nothing.

Cites `1238#1`, the second sentence of the `StopSelector` message comment:

> At least one of the two values must be provided.

`must` is where the ERROR comes from. The two values are `stop_sequence` and
`stop_id`, and a selector carrying neither names no stop at all, so the
`Modification` it belongs to has no span to apply.

**Two sites, and they are measured rather than listed by hand.** A `StopSelector`
appears at `Modification.start_stop_selector` and `Modification.end_stop_selector`
and nowhere else in the pinned proto; `tests/test_rule_s042.py` asserts that
against `schema_current.SCHEMA` so a third site at a later pin is a red test.
They are walked in declaration order, which is what makes a modification with
two broken selectors report start before end.

**Not E040.** E040 is "one of the fields below must necessarily be set" on
`StopTimeUpdate`, a different message with different fields, and it is
unreachable from here. The jar cannot refute that boundary by running: it
predates `StopSelector` and decodes the whole `TripModifications` entity as
unknown fields.

**Absence is somebody else's finding, or nobody's.** An absent
`start_stop_selector` is S041 at `1165#1`. An absent `end_stop_selector` is what
`:1168` describes, and decision 1 rejects that clause under R4 because its
antecedent, "no stop_time is replaced", is itself defined by the field's absence.
So this rule reads only the selectors that are on the wire.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.manifest import Severity
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.walk_trip_modifications import SELECTOR_FIELDS, modifications
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S042"

CLAUSE = "spec: At least one of the two values must be provided."

#: The two fields of `StopSelector` itself, which is the "two values" the clause
#: counts. The two fields that *carry* a selector are `SELECTOR_FIELDS`, shared
#: with S043 so the two rules cannot disagree about where a selector lives.
VALUES = ("stop_sequence", "stop_id")


@rule(RULE_ID, source=CLAUSE, severity=Severity.ERROR)
def check(message: Msg, ctx: RuleContext) -> Iterator[Occurrence]:
    """Both selectors of every modification, the ones on the wire only."""
    for record in modifications(message, ctx):
        for name in SELECTOR_FIELDS:
            if not record.modification.has(name):
                continue
            selector = record.modification.get(name)
            if not any(selector.has(value) for value in VALUES):
                yield Occurrence(
                    RULE_ID,
                    f"{name} with neither stop_sequence nor stop_id",
                    {ENTITY_PATH_KEY: f"{record.path}.{name}"},
                )
