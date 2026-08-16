"""Cohort D and E's shadow fixtures: P009, P010, P011 and P013.

Split out of `practiceshadowgap.py` for the file-size hook, and along the seam
that already existed: these four are the cohort that landed four rules and no
fixture, while P001, P007 and P008 were measured out of band by their own
cohorts and only had to be moved in. What both halves have in common is in
`practiceshadowgap.py`'s docstring, W009 and the 2015 decode included.
"""

from __future__ import annotations

from practiceshadow import (
    CLOCK,
    DATED,
    SCHEDULED,
    UNSCHEDULED,
    Fixture,
    Message,
    as_trip_update,
    stop_time,
    trip_update,
)

__all__ = ["COHORT_DE_FIXTURES"]

#: `TripDescriptor.ScheduleRelationship`, post-2015 half. Neither is in the enum
#: the jar compiles against, so protobuf-java files the value as an unknown
#: field and `hasScheduleRelationship()` answers false.
NEW, REPLACEMENT = 8, 5

#: What the spec tier's `specshadowfeeds.DESCRIPTOR_ARTIFACT` records, for the same
#: reason and against the same Java lines, `TripDescriptorValidator.java:470-474`.
DESCRIPTOR_ARTIFACT = frozenset({"W009"})

#: A trip descriptor stating a post-2015 relationship over the one GTFS trip.
NEW_TRIP = {"trip_id": "T1", "schedule_relationship": NEW}


P009_FIXTURES = (
    Fixture(
        "P009",
        "a NEW trip with no trip_headsign",
        (
            Message(
                CLOCK,
                [
                    as_trip_update(
                        trip=NEW_TRIP,
                        stop_time_update=[
                            stop_time(
                                1, "S1", arrival={"time": CLOCK + 60, "scheduled_time": CLOCK + 60}
                            ),
                            stop_time(2, "S2"),
                        ],
                    )
                ],
            ),
        ),
        jar_ids=DESCRIPTOR_ARTIFACT,
        note=(
            "W009 is the 2015 decode of NEW, not an overlap: the member is post-2015, the jar "
            "reads the field as absent and TripDescriptorValidator.java:470-474 reports it. "
            "One stop states a scheduled_time so this is P009's fixture and not P010's"
        ),
    ),
    Fixture(
        "P009",
        "a NEW trip that states its headsign",
        (
            Message(
                CLOCK,
                [
                    as_trip_update(
                        trip=NEW_TRIP,
                        trip_properties={"trip_headsign": "Alewife"},
                        stop_time_update=[
                            stop_time(
                                1, "S1", arrival={"time": CLOCK + 60, "scheduled_time": CLOCK + 60}
                            ),
                            stop_time(2, "S2"),
                        ],
                    )
                ],
            ),
        ),
        fires=False,
        jar_ids=DESCRIPTOR_ARTIFACT,
        note="the conformant twin: same NEW trip, one headsign added",
    ),
)

P010_FIXTURES = (
    Fixture(
        "P010",
        "a REPLACEMENT trip stating no scheduled_time anywhere",
        (
            Message(
                CLOCK,
                [
                    as_trip_update(
                        trip={"trip_id": "T1", "schedule_relationship": REPLACEMENT},
                        trip_properties={"trip_headsign": "Alewife"},
                    )
                ],
            ),
        ),
        jar_ids=DESCRIPTOR_ARTIFACT,
        note=(
            "W009 for the same decode reason as P009's. The headsign is stated so P009 is "
            "silent and this fixture is about P010 alone"
        ),
    ),
    Fixture(
        "P010",
        "a REPLACEMENT trip whose first stop states one",
        (
            Message(
                CLOCK,
                [
                    as_trip_update(
                        trip={"trip_id": "T1", "schedule_relationship": REPLACEMENT},
                        trip_properties={"trip_headsign": "Alewife"},
                        stop_time_update=[
                            stop_time(
                                1, "S1", arrival={"time": CLOCK + 60, "scheduled_time": CLOCK + 60}
                            ),
                            stop_time(2, "S2"),
                        ],
                    )
                ],
            ),
        ),
        fires=False,
        jar_ids=DESCRIPTOR_ARTIFACT,
        note="the conformant twin: one scheduled_time is all the rule asks for",
    ),
)


def alert(start_time: str) -> dict[str, object]:
    """An Alert selecting the one GTFS trip at a stated `start_time`.

    `schedule_relationship` is stated for the reason `practiceshadow` gives:
    W009 reports an absent one on any `TripDescriptor`, `informed_entity`'s
    included.
    """
    return {
        "id": "alert",
        "alert": {
            "informed_entity": [
                {
                    "trip": {
                        "trip_id": "T1",
                        "start_time": start_time,
                        "schedule_relationship": SCHEDULED,
                    }
                }
            ]
        },
    }


#: `minimal_tables()` gives T1 one `frequencies.txt` period from 06:00:00 with a
#: 600-second headway, so the departures are 06:00:00, 06:10:00 and so on.
ON_HEADWAY, OFF_HEADWAY = "06:10:00", "06:05:00"

P011_FIXTURES = (
    Fixture(
        "P011",
        "an alert start_time off the headway",
        (Message(CLOCK, [alert(OFF_HEADWAY)]),),
        exact_times="1",
        not_emitted="E019",
        note=(
            "E019's check reads entity.has('trip_update') and entity.has('vehicle') only, so "
            "it cannot reach an Alert; this fixture is the empirical half of that reading"
        ),
    ),
    Fixture(
        "P011",
        "an alert start_time on the headway",
        (Message(CLOCK, [alert(ON_HEADWAY)]),),
        fires=False,
        exact_times="1",
        note="the conformant twin: one headway later",
    ),
)

#: A frequency-based trip stated the way E013 asks for, so the fixture is about
#: the `delay` on its stop_time_update and not about its descriptor.
FREQUENCY_TRIP = {"trip_id": "T1", "schedule_relationship": UNSCHEDULED, **DATED}


def frequency_update(**stop: object) -> dict[str, object]:
    """One `exact_times=0` TripUpdate whose first stop takes `stop`."""
    return {
        "id": "a",
        "trip_update": trip_update(
            trip=FREQUENCY_TRIP,
            stop_time_update=[stop_time(1, "S1", **stop), stop_time(2, "S2")],
        ),
    }


P013_FIXTURES = (
    Fixture(
        "P013",
        "an arrival carrying delay on a frequency-based trip",
        (Message(CLOCK, [frequency_update(arrival={"time": CLOCK + 60, "delay": 30})]),),
        exact_times="0",
    ),
    Fixture(
        "P013",
        "the same arrival with no delay",
        (Message(CLOCK, [frequency_update(arrival={"time": CLOCK + 60})]),),
        fires=False,
        exact_times="0",
        note="the conformant twin: the delay removed and nothing else",
    ),
)

COHORT_DE_FIXTURES: tuple[Fixture, ...] = (
    P009_FIXTURES + P010_FIXTURES + P011_FIXTURES + P013_FIXTURES
)
