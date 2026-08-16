"""Tier 1 feeds for the three groups that are not the long bullrunner sequence.

Each group is one jar invocation, because `-gtfs` takes one archive and
`-ignoreShapes` is a flag on the whole run. So a rule that needs a different
static feed needs a different group, and these are the three:

**`bullrunner-ignoring-shapes`** repeats two of the vehicle files under
`-ignoreShapes`, which is the only way to see the other half of E028 and E029.
With shapes, `GtfsMetadata` buffers the shape points and E028 reads "outside
entire GTFS shapes.txt coverage area"; without them it falls back to the
stops.txt bounds and says "stops.txt" instead, and E029 is not evaluated at all.
Both strings are in the goldens, so a writer that hard-coded either would fail.
Note that upstream declares the flag with `hasArg()` but reads it with
`hasOption()`, so `-ignoreShapes false` **enables** it and a bare `-ignoreShapes`
is a parse error. `tools/conformancerun.py` passes the value upstream ignores.

**`testagency2`** is upstream's other Apache-2.0 archive, and it carries three
things bullrunner does not: a stop with `location_type = 1` (E015), an
`agency.txt` with an `agency_id`, and `frequencies.txt` rows with
`exact_times = 1` (E019). Its trips also populate `direction_id` (E024) and its
trip `1.1` is not frequency-based, which is what makes E023 reachable.

**`timepoints`** is bullrunner with `arrival_time` and `departure_time` blank
everywhere except six stop_sequences. E046 is about exactly those blanks: a
realtime update with no time over a GTFS row that has none either.

`testagency2.zip` gives trips `18.1` and `18.1back` a `direction_id` of `N` and
`S`, the same invalid-GTFS cells `testagency.zip` has. onebusaway's `Trip`
carries `directionId` as a `java.lang.String`, so the jar reads them and so does
compat; the group used to be staged through a copy with those two cells blanked,
because compat read its static feed through the canonical static schema, which
types the column as an enum and refuses the archive outright.

`testagency2.zip` frequencies are `exact_times = 1` with `headway_secs` of 3600,
and the timepoints archive's are 600, so neither can reach
`FrequencyTypeOneValidator`'s measured infinite spin at `headway_secs = 0`.
"""

from __future__ import annotations

from conf_common import DELAYED, STU_SCHEDULED, UNSCHEDULED, clock
from conf_vehicles import OFF_SHAPE, OUTSIDE_COVERAGE
from feedbuild import (
    Feed,
    entity,
    header,
    message,
    pb,
    position,
    stu,
    trip,
    trip_update,
    vehicle_position,
)


def _ignoring_shapes(offset: int, vehicle_id: str, at: tuple[float, float]) -> bytes:
    return pb(
        message(
            header(clock(offset)),
            entity(
                vehicle_id,
                vehicle=vehicle_position(
                    trip(
                        "1",
                        start_time="07:00:00",
                        start_date="20160101",
                        schedule_relationship=UNSCHEDULED,
                    ),
                    vehicle_id=vehicle_id,
                    at=position(*at),
                    timestamp=clock(offset),
                ),
            ),
        )
    )


def _direction_and_locations() -> bytes:
    """A direction_id GTFS disagrees with, a start_time it disagrees with, and a
    stop whose `location_type` is 1."""
    return pb(
        message(
            header(clock(-30)),
            entity(
                "disagrees-with-gtfs",
                trip_update=trip_update(
                    trip(
                        "1.1",
                        direction_id=1,
                        start_time="00:30:00",
                        start_date="20160101",
                        schedule_relationship=0,
                    ),
                    stu(2, "B", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="ta2-1",
                    timestamp=clock(-30),
                ),
            ),
        )
    )


def _frequency_type_one() -> bytes:
    """Trip `15.1` is `exact_times = 1` with a 3600-second headway from 06:00:00,
    so a start_time one second off the hour is not a multiple of it."""
    return pb(
        message(
            header(clock(-29)),
            entity(
                "off-the-headway",
                trip_update=trip_update(
                    trip(
                        "15.1",
                        start_time="06:30:01",
                        start_date="20160101",
                        schedule_relationship=0,
                    ),
                    stu(1, "U", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="ta2-2",
                    timestamp=clock(-29),
                ),
            ),
        )
    )


def _times_missing_from_gtfs() -> bytes:
    """Updates with a delay but no time, over GTFS rows that carry no time."""
    return pb(
        message(
            header(clock(-30)),
            entity(
                "no-time-either-side",
                trip_update=trip_update(
                    trip(
                        "1",
                        start_time="07:00:00",
                        start_date="20160101",
                        schedule_relationship=UNSCHEDULED,
                    ),
                    stu(2, "230", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    stu(3, "214", departure=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="tp-1",
                    timestamp=clock(-30),
                ),
            ),
        )
    )


IGNORING_SHAPES_FEEDS: tuple[Feed, ...] = (
    Feed(
        "01-outside-coverage.pb",
        "E028 falls back to the stops.txt bounds",
        _ignoring_shapes(-30, "ignored-1", OUTSIDE_COVERAGE),
    ),
    Feed(
        "02-off-shape.pb",
        "E029 is not evaluated when shapes are ignored",
        _ignoring_shapes(-29, "ignored-2", OFF_SHAPE),
    ),
)

TESTAGENCY2_FEEDS: tuple[Feed, ...] = (
    Feed(
        "01-direction-and-locations.pb",
        "a direction_id, a start_time and a location_type GTFS disagrees with",
        _direction_and_locations(),
    ),
    Feed(
        "02-frequency-type-one.pb",
        "an exact_times = 1 start_time that is not a multiple of the headway",
        _frequency_type_one(),
    ),
)

TIMEPOINTS_FEEDS: tuple[Feed, ...] = (
    Feed(
        "01-times-missing-from-gtfs.pb",
        "no time in the update and none in stop_times.txt either",
        _times_missing_from_gtfs(),
    ),
)
