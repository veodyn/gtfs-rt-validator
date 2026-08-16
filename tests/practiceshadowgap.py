"""The shadow fixtures for the seven rules that had none when the tier closed.

`practiceshadowfeeds.py` was written by the band cohort and grew cohort F's two;
P001, P007 to P011 and P013 arrived with no entry, for two reasons their cohorts
recorded rather than hid. P001's could not be expressed at all until
`practiceshadow.Message` carried `gtfs_realtime_version`, since that field is the
rule's entire subject and `blobs` hard-coded `"2.0"`. The rest were left as
close-step work. This module is that close step, so every one of the 14 practice
rules now has a jar verdict recorded against a feed rather than reasoned about.

Every `jar_ids` here was **measured**, one jar invocation per fixture, and two of
them are not empty. Both are the same 2015-decode artefact the spec tier hit six
times and named `specshadowfeeds.DESCRIPTOR_ARTIFACT`: `NEW` (8) and `REPLACEMENT` (5) are
post-2015 members, protobuf-java files an unknown enum value as an unknown field,
`hasScheduleRelationship()` answers false, and `TripDescriptorValidator.java`
`:470-474` reports W009 for exactly that. It is the decoder, not an overlap:
P009 and P010 declare none in `test_tier_overlap.OVERLAP`, and no upstream rule
about headsigns or scheduled times exists to say otherwise.

Three of these rules (P001, P007, P008) had their jar verdict measured out of
band while they were being written. Those measurements are reproduced here as
fixtures rather than cited, which is the whole point of moving them in.
"""

from __future__ import annotations

from practiceshadow import (
    CLOCK,
    Fixture,
    Message,
    as_trip_update,
    stop_time,
)
from practiceshadowcohortde import COHORT_DE_FIXTURES

__all__ = ["GAP_FIXTURES"]

#: `TripUpdate.StopTimeUpdate.ScheduleRelationship.SKIPPED`, by number as this
#: harness spells every other enum value.
STU_SKIPPED = 1

P001_FIXTURES = (
    Fixture(
        "P001",
        "a 1.0 header over one clean TripUpdate",
        (Message(CLOCK, [as_trip_update()], gtfs_realtime_version="1.0"),),
        not_emitted="E038",
        note=(
            "E038 accepts 1.0 as a valid version and E048 and E049 gate on v2 rather than "
            "asking for it, so the jar has nothing to say about a v1.0 header"
        ),
    ),
    Fixture(
        "P001",
        "a 2.0 header over the same TripUpdate",
        (Message(CLOCK, [as_trip_update()]),),
        fires=False,
        note="the conformant twin: one character of the header apart from the fixture above",
    ),
)

P007_FIXTURES = (
    Fixture(
        "P007",
        "every stop_time_update SKIPPED on a SCHEDULED trip",
        (
            Message(
                CLOCK,
                [
                    as_trip_update(
                        stop_time_update=[
                            stop_time(1, "S1", schedule_relationship=STU_SKIPPED),
                            stop_time(2, "S2", schedule_relationship=STU_SKIPPED),
                        ]
                    )
                ],
            ),
        ),
    ),
    Fixture(
        "P007",
        "one stop_time_update still served",
        (
            Message(
                CLOCK,
                [
                    as_trip_update(
                        stop_time_update=[
                            stop_time(1, "S1", schedule_relationship=STU_SKIPPED),
                            stop_time(2, "S2"),
                        ]
                    )
                ],
            ),
        ),
        fires=False,
        note="the conformant twin: one stop is still served, so the trip is not a cancellation",
    ),
)

#: Both predictions behind the clock, which is the file's mtime at `CLOCK`.
PAST_STOPS = [
    stop_time(1, "S1", arrival={"time": CLOCK - 600}, departure={"time": CLOCK - 590}),
    stop_time(2, "S2", arrival={"time": CLOCK - 300}, departure={"time": CLOCK - 290}),
]

P008_FIXTURES = (
    Fixture(
        "P008",
        "every prediction behind the clock",
        (Message(CLOCK, [as_trip_update(stop_time_update=PAST_STOPS)]),),
        not_emitted="E041",
        note=(
            "E041 wants a TripUpdate to carry some stop_time_update and this one carries two, "
            "so the jar is silent where the practice rule asks whether either is a prediction"
        ),
    ),
    Fixture(
        "P008",
        "one prediction still ahead of the clock",
        (Message(CLOCK, [as_trip_update()]),),
        fires=False,
        note="the conformant twin: `trip_update()`'s own stops are all ahead of `CLOCK`",
    ),
)

GAP_FIXTURES: tuple[Fixture, ...] = (
    P001_FIXTURES + P007_FIXTURES + P008_FIXTURES + COHORT_DE_FIXTURES
)
