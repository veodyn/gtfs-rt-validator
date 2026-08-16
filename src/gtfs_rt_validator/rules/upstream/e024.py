"""E024: a realtime direction_id that GTFS `trips.txt` disagrees with.

`checkE024` in `validation/rules/TripDescriptorValidator.java:329-339`, called
unconditionally on both vehicle-bearing sides (`:124` and `:173`) and guarded
inside on `trip.hasDirectionId()`. A realtime trip_id that is in no `trips.txt`
row reports nothing here; that is E003's finding.

**The comparison is a string comparison** in Java:
`gtfsTrip.getDirectionId()` is a `String` holding the raw cell and it is tested
against `String.valueOf(directionId)`. A GTFS `direction_id` that is null, which
is what a blank column gives, therefore always reports when the realtime one is
present, and the occurrence prints the literal `"null"` that Java's
concatenation makes of it.

**This rule compares text, so the loader decides whether it is right.**
`TripDescriptorValidator.java:329` reads `gtfsTrip.getDirectionId()`, which
onebusaway holds as a `java.lang.String` carrying `trips.txt` verbatim
(confirmed with `javap -p` on `onebusaway-gtfs-1.3.87.jar`), and tests it
against `String.valueOf(directionId)`. So `00` is not `0`.

A compat read through the sibling's typed path used to lose that: the column is
declared an ENUM into an INTEGER column, the text is dropped before the insert,
and every spelling arrived as the same `int` the realtime side carries, so the
comparison passed where the jar reports. `static/adapter.py`'s
`load_static_as_onebusaway` reads the raw cell instead, and
`tests/test_rule_e024.py` now asserts the jar's own prefix for every spelling,
one jar run per cell, rather than recording a divergence. Two are worth knowing:
onebusaway trims, so `" 0"` agrees, and `0.0` fails to load at all.

The prefix is `"GTFS-rt " + getVehicleAndTripIdText(entity) +
" trip.direction_id is " + directionId + " but GTFS trip.direction_id is " +
gtfsTrip.getDirectionId()`.
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

RULE_ID = "E024"


@rule(RULE_ID)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence]:
    return [
        Occurrence(RULE_ID, event.prefix, event.context)
        for event in events_for(RULE_ID, trip_descriptors, message, ctx)
    ]
