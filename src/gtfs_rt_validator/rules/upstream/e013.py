"""E013: an exact_times = 0 trip whose schedule_relationship is neither UNSCHEDULED nor empty.

Ported from `validation/rules/FrequencyTypeZeroValidator.java:69` and `:99` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`. One site per half of an entity,
both written as the same double negative:

```java
if (!(!trip.hasScheduleRelationship() || trip.getScheduleRelationship().equals(UNSCHEDULED)))
```

which fires when the field is **present and not UNSCHEDULED**. An absent field
is the allowed "empty" case, which upstream's own test wanted to assert and
could not: `:137-139` is commented out with a FIXME saying its builder would not
produce a descriptor without one.

**That makes this rule enum-sensitive, and the two schemas disagree.** A
post-2015 value such as `DUPLICATED` (6) is not in the enum the jar compiles
against, so protobuf-java files it as an unknown field, `hasScheduleRelationship()`
is false, and the rule reads it as empty and says nothing. Measured: a feed
carrying 6 produced no E013 from the pinned jar at all. Nothing here has to know
that; it falls out of decoding with the 2015 schema, which is exactly why compat
decodes with it rather than masking a current-schema decode afterwards.

**The value reaches output as a name, not a number.** Java concatenates the enum
by `Enum.toString()`, which is the protobuf constant name, so the prefix ends
`schedule_relationship ADDED`. The name table is the schema's own rather than
four literals here; `SCHEDULE_RELATIONSHIP` below says which schema and why
either one answers.

The gate, and the reason the two halves are guarded differently, is in
`rules/_shared/frequencies.py` with the entity walk.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules._shared.frequencies import frequency_zero_halves, half_id_text
from gtfs_rt_validator.rules._shared.javafmt import java_enum
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext, RuleResult

RULE_ID = "E013"

FIELD = "schedule_relationship"

#: `TripDescriptor.ScheduleRelationship.UNSCHEDULED`, the one allowed value.
#: Both schemas number it 2.
UNSCHEDULED = 2

#: The constant names, taken from the pinned proto's schema rather than written
#: out. It is a strict superset of the 2015 enum with identical numbers for the
#: four they share, so it names every value either decode can put in this field:
#: a compat run can only see the 2015 four, and a modern run can see the rest.
#: Reading a generated table beats four literals a regenerated schema could not
#: correct.
SCHEDULE_RELATIONSHIP = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> RuleResult:
    """One occurrence per half whose descriptor names something other than UNSCHEDULED."""
    for _entity, half in frequency_zero_halves(message, ctx.static.exact_times_zero_trip_ids):
        trip = half.get("trip")
        if trip.has(FIELD) and trip.get(FIELD) != UNSCHEDULED:
            name = java_enum(trip.get(FIELD), SCHEDULE_RELATIONSHIP)
            yield Occurrence(RULE_ID, f"{half_id_text(half)} {FIELD} {name}")
