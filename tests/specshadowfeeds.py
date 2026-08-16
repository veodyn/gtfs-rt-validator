"""One fixture per spec-tier rule of cohorts A to C, and the jar's verdict on it.

Split out of `specshadow.py` at the file size hook's limit. Every `jar_ids` set
was recorded from a real jar run rather than predicted, and the two that are not
empty carry their reason: `DESCRIPTOR_ARTIFACT` below, and S020's note.

`not_emitted` is the claim this file exists to test. Where a rule declares an
overlap with one of the 56, which is what `OVERLAP` in
`tests/test_tier_overlap.py` records, the fixture is built so that only that
spec rule's own defect is present, and the named id must be absent from what the
jar says. A rule that declares no overlap carries `None` here.

Cohorts D and E sit in `specshadowcohortde.py`, cohorts F and G in
`specshadowcohortfg.py` and cohort H's ten
`TripModifications` rules in `specshadowcohorth.py`, for the same size-hook
reason this module sits outside `specshadow.py`, and `FIXTURES` at the foot is
the tuples joined. That is what the jar test and `tests/tieroverlap.py` read, so
a cohort module is invisible to both until it is named there.
"""

from __future__ import annotations

from specshadow import (
    CLEAN_ALERT,
    CLOCK,
    DATED,
    DUPLICATED,
    MANY_SEATS,
    NEW,
    STU_SCHEDULED,
    STU_SKIPPED,
    STU_UNSCHEDULED,
    UNSCHEDULED,
    Fixture,
    as_trip_update,
    as_vehicle,
    stop_time,
)
from specshadowcohortde import COHORT_DE_FIXTURES
from specshadowcohortfg import COHORT_FG_FIXTURES
from specshadowcohorth import COHORT_H_FIXTURES

__all__ = ["DESCRIPTOR_ARTIFACT", "FIXTURES"]

#: The one id several fixtures make the jar emit, and a descriptor artifact
#: rather than an overlap. Upstream reports "schedule relationship not
#: populated"; the field *is* populated, with a member number the 2015 enum has
#: none for, so protobuf-java drops it into the unknown set and
#: `hasScheduleRelationship()` answers false. No rule about a post-2015 enum
#: member can avoid it, and no rewording of a fixture changes it.
DESCRIPTOR_ARTIFACT = frozenset({"W009"})

UNSCHEDULED_TRIP = {"trip_id": "T1", "schedule_relationship": UNSCHEDULED}
DUPLICATED_TRIP = {"trip_id": "T1", "schedule_relationship": DUPLICATED}
DUPLICATE_PROPERTIES = {
    "trip_id": "T1-copy",
    "start_date": "20231115",
    "start_time": "10:00:00",
}
UNSCHEDULED_STOPS = [
    stop_time(1, "S1", schedule_relationship=STU_UNSCHEDULED),
    stop_time(2, "S2", schedule_relationship=STU_UNSCHEDULED),
]
#: A stop the vehicle will not call at, predicting occupancy and nothing else.
#: SKIPPED rather than absent so that E043 and E044 are exempt and S005 is the
#: only rule left with anything to say.
SKIPPED_WITH_OCCUPANCY = {
    "stop_sequence": 2,
    "stop_id": "S2",
    "schedule_relationship": STU_SKIPPED,
    "departure_occupancy_status": MANY_SEATS,
}

#: One event where `stop_times.txt` gives two, which is S006's whole subject.
ARRIVAL_ONLY = {
    "stop_sequence": 1,
    "stop_id": "S1",
    "schedule_relationship": STU_SCHEDULED,
    "arrival": {"time": CLOCK + 60},
}

COHORT_ABC_FIXTURES: tuple[Fixture, ...] = (
    Fixture("S001", [{"id": "a"}]),
    Fixture(
        "S002",
        [{"id": "same", "alert": CLEAN_ALERT}, {"id": "same", "alert": CLEAN_ALERT}],
        not_emitted="E052",
        note="E052 is vehicle.id, a different field on a different message",
    ),
    Fixture("S003", [as_trip_update("a"), as_trip_update("b")]),
    Fixture(
        "S004",
        [
            as_trip_update(
                stop_time_update=[
                    stop_time(1, "S1", arrival={"time": CLOCK + 60, "scheduled_time": CLOCK}),
                    stop_time(2, "S2"),
                ]
            )
        ],
    ),
    Fixture(
        "S005", [as_trip_update(stop_time_update=[stop_time(1, "S1"), SKIPPED_WITH_OCCUPANCY])]
    ),
    Fixture(
        "S006",
        [as_trip_update(stop_time_update=[ARRIVAL_ONLY, stop_time(2, "S2")])],
        not_emitted="E043",
        note="one event, where E043 needs neither: the two bands cannot overlap",
    ),
    Fixture(
        "S007",
        [as_trip_update(trip={**UNSCHEDULED_TRIP, **DATED})],
        not_emitted="E013",
        exact_times="0",
        note="the descriptor is UNSCHEDULED, which E013 accepts; the updates are not",
    ),
    Fixture(
        "S008",
        [as_trip_update(trip=UNSCHEDULED_TRIP, stop_time_update=UNSCHEDULED_STOPS)],
        jar_ids=DESCRIPTOR_ARTIFACT,
    ),
    Fixture(
        "S009", [as_trip_update(stop_time_update=UNSCHEDULED_STOPS)], jar_ids=DESCRIPTOR_ARTIFACT
    ),
    Fixture("S010", [as_trip_update(trip=UNSCHEDULED_TRIP)]),
    Fixture(
        "S011",
        [
            as_trip_update(
                stop_time_update=[
                    stop_time(1, "S1", stop_time_properties={"assigned_stop_id": "S2"}),
                    stop_time(2, "S2"),
                ]
            )
        ],
    ),
    Fixture(
        "S012",
        [
            as_trip_update(
                stop_time_update=[
                    stop_time(1, "S1", stop_time_properties={"assigned_stop_id": "DUMMY"}),
                    stop_time(2, "S2"),
                ]
            )
        ],
        not_emitted="E011",
        note="E011 reads StopTimeUpdate.stop_id, which is S1 here and is real",
    ),
    Fixture("S013", [as_trip_update(trip=DUPLICATED_TRIP)], jar_ids=DESCRIPTOR_ARTIFACT),
    Fixture("S014", [as_trip_update(trip_properties={"trip_id": "T1x"})]),
    Fixture(
        "S015",
        [
            as_trip_update(
                trip=DUPLICATED_TRIP, trip_properties={**DUPLICATE_PROPERTIES, "trip_id": "T1"}
            )
        ],
        jar_ids=DESCRIPTOR_ARTIFACT,
        not_emitted="E016",
        note="E016 is about a TripDescriptor.trip_id under ADDED, which this is not",
    ),
    Fixture("S016", [as_trip_update(trip_properties={"shape_id": "NOPE"})]),
    Fixture(
        "S017",
        [as_trip_update(trip={"trip_id": "T1", "schedule_relationship": NEW}, delay=30)],
        jar_ids=DESCRIPTOR_ARTIFACT,
        not_emitted="E046",
        note="E046 compares a stop_time_update delay against stop_times.txt, not this field",
    ),
    Fixture(
        "S020",
        [
            as_trip_update("a"),
            as_vehicle(
                "b",
                vehicle={"id": "2"},
                trip={"trip_id": "T9-copy", "schedule_relationship": DUPLICATED},
            ),
        ],
        jar_ids=DESCRIPTOR_ARTIFACT | {"E003", "W003"},
        not_emitted="E047",
        note=(
            "the duplicate's trip_id is not in trips.txt by construction (E003) and has no "
            "TripUpdate of its own (W003). Neither is E047, which needs one vehicle_id paired "
            "with two trip_ids, and the vehicles here are 1 and 2"
        ),
    ),
    # There is no `S022` fixture and there is no `S022`. The rule was retired
    # because its trigger was a strict subset of E013's:
    # `_shared/frequencies.py:129` gates E013's TripUpdate half on
    # `exact_times_zero_trip_ids` alone, `e013.py:68` fires on a
    # `schedule_relationship` that is present and not `UNSCHEDULED`, and
    # `DUPLICATED` is 6. This file could never have shown it, which is the
    # instructive part: the fixture's recorded verdict was `W009` alone, because
    # the 2015 enum has no `DUPLICATED` and the jar reads the field as absent.
    # `tests/writtenrules.py` carries the measurement and `879#1`'s verdict in
    # `upstream/spec-clause-verdicts.json` is what reverses it.
    Fixture(
        "S051",
        [
            as_vehicle(
                multi_carriage_details=[
                    {"id": "C", "carriage_sequence": 1},
                    {"id": "C", "carriage_sequence": 2},
                ]
            )
        ],
    ),
    Fixture(
        "S052",
        [
            as_vehicle(
                multi_carriage_details=[
                    {"id": "C1", "carriage_sequence": 1},
                    {"id": "C2", "carriage_sequence": 3},
                ]
            )
        ],
    ),
)

#: Cohort A to C's, plus every later cohort's from next door. One tuple, because
#: `FIXTURES` is what both the jar test and `tests/tieroverlap.py` read and a
#: cohort's fixtures are not visible to either until they are in it.
FIXTURES: tuple[Fixture, ...] = (
    COHORT_ABC_FIXTURES + COHORT_DE_FIXTURES + COHORT_FG_FIXTURES + COHORT_H_FIXTURES
)
