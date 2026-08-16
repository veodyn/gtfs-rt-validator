"""Cohort D's and cohort E's jar fixtures: trip descriptors, then alerts.

Split out of `specshadowfeeds.py` for the reason that file was split out of
`specshadow.py`, so neither grows past the size hook. Same contract:
`tests/test_spec_tier_does_not_shadow_the_jar.py`'s docstring says what one
entry has to carry, and every `jar_ids` set here was **recorded from a real jar
run** rather than predicted.

Eleven rules, and the 2015 schema sorts them into three kinds. Which kind a
fixture is decides what its recorded verdict is evidence of, so each says so.

- **The jar cannot see the defect at all.** `modified_trip` (S023),
  `communication_period` and `impact_period` (S026), `cause_detail` (S027),
  `effect_detail` (S028) and `EntitySelector.direction_id` (S030) are all
  post-2015 fields, measured against `proto/schema_2015.py` rather than assumed:
  protobuf-java drops each into its unknown-field set, so the jar validates a
  descriptor or an alert with the defect removed. An empty verdict there says
  the fixture is clean, and the rule's declared overlap rests on the field being
  invisible rather than on upstream having looked and passed.
- **The jar can see the defect and says nothing.** `active_period` (S025),
  `header_text` and `description_text` (S029) are 2015 fields, and
  `ScheduleRelationship.ADDED` is 1 in the 2015 enum, so S024's descriptor is
  the one case in this module where the jar reads the very value the rule
  reports on. `start_time` (S021) is 2015's too. These four are the stronger
  measurement of the two.
- **The jar sees a different defect and reports that.** S018's and S019's
  antecedent is "the trip_id is not known", so every feed either rule can fire
  on is a W006 feed by construction. W006 is not the id either fixture's
  `not_emitted` names.
"""

from __future__ import annotations

from specshadow import (
    CLEAN_ALERT,
    CLOCK,
    SCHEDULED,
    STU_SCHEDULED,
    STU_UNSCHEDULED,
    UNSCHEDULED,
    Fixture,
    as_trip_update,
    stop_time,
)

__all__ = ["COHORT_DE_FIXTURES"]

#: `specshadowfeeds.DESCRIPTOR_ARTIFACT`, restated rather than imported: that
#: module imports this one, so reading its constant here would be a cycle. Same
#: id and the same cause on the other enum. `StopTimeUpdate.ScheduleRelationship`
#: gained `UNSCHEDULED = 3` after 2015, so protobuf-java drops it into the
#: unknown set, `hasScheduleRelationship()` answers false on the update and the
#: jar reports the relationship as unpopulated. Measured on S008's and S009's
#: fixtures before this one, and no rewording of a fixture changes it.
STOP_TIME_ARTIFACT = frozenset({"W009"})

#: What the jar has to say about a trip whose descriptor names no trip_id, which
#: is S018's and S019's shared antecedent: it reports the missing id. Not a
#: shadow of either rule but a consequence of the clause's own "if the trip_id
#: is not known", so no feed either rule can fire on avoids it.
TRIP_ID_UNKNOWN = frozenset({"W006"})

#: `TripDescriptor.ScheduleRelationship.ADDED`, which the 2015 enum also has at
#: 1. So S024's fixture is not a `DESCRIPTOR_ARTIFACT` case: the jar decodes the
#: member, `hasScheduleRelationship()` answers true, and W009 is silent.
ADDED = 1

#: A descriptor naming a route and no trip, which is S018's and S019's shared
#: antecedent and the `TripDescriptor` comment's second form.
ROUTE_SCOPED = {"route_id": "R1", "schedule_relationship": SCHEDULED}

#: An `ADDED` trip that is not in `trips.txt`, which is the shape the deprecated
#: member is *for*. E003 exempts an ADDED trip from having to exist and E016
#: reports an ADDED trip that does exist, so a trip_id upstream knows would have
#: put a second defect in the fixture and made E016 the thing being measured.
ADDED_TRIP = {"trip_id": "T9", "schedule_relationship": ADDED}

#: The one `frequencies.txt` trip, dated as S007's fixture dates it. S021 moves
#: only the time between its two messages, and `UNSCHEDULED` is what E013 asks
#: of an `exact_times=0` trip: `SCHEDULED` would draw E013 and an absent
#: relationship would draw W009, so the descriptor's own field cannot be left
#: alone here the way it can everywhere else.
FIRST_RUN = {"trip_id": "T1", "schedule_relationship": UNSCHEDULED}
STARTED = {"start_date": "20231114", "start_time": "09:50:00"}
MOVED = {"start_date": "20231114", "start_time": "09:55:00"}

#: What S021's updates have to be, which is the one combination S007 to S010 all
#: pass over: S007 wants an update that is not SCHEDULED, S008 wants a trip
#: outside `exact_times=0`, S009 wants a descriptor that is not UNSCHEDULED, and
#: S010 wants the updates to be UNSCHEDULED, which these are. The three
#: alternatives were measured rather than reasoned about: `stop_time()`'s
#: SCHEDULED updates make the fixture S007's and S010's as well, SKIPPED ones
#: make it P007's and S010's, and no updates at all make the jar report E041.
#: The cost of this one is `STOP_TIME_ARTIFACT`, and it is the only cost that is
#: not a second rule firing on the fixture.
UNSCHEDULED_STOPS = [
    stop_time(1, "S1", schedule_relationship=STU_UNSCHEDULED),
    stop_time(2, "S2", schedule_relationship=STU_UNSCHEDULED),
]

#: One translation, tagged, so an alert carrying a `TranslatedString` for some
#: other reason is not also S031's (no translation) or S032's (two untagged).
SAID = {"translation": [{"text": "Fallen tree at First", "language": "en"}]}


def sequence_only(sequence: int) -> dict[str, object]:
    """A stop_time_update naming its position and no stop. S018's whole subject.

    Everything else is `stop_time()`'s, including the explicit
    `schedule_relationship` W009 reports the absence of and the two absolute
    times E043 and E044 want, so `stop_id` is the only thing missing.
    """
    return {
        "stop_sequence": sequence,
        "schedule_relationship": STU_SCHEDULED,
        "arrival": {"time": CLOCK + sequence * 60},
        "departure": {"time": CLOCK + sequence * 60 + 10},
    }


def alert(**fields: object) -> list[dict[str, object]]:
    """One entity carrying an alert, with `CLEAN_ALERT`'s selector.

    `informed_entity` is stated on every one of these because E032 and E033
    report an alert that selects nothing, and a fixture drawing either would be
    measuring them instead of the rule it is named after.
    """
    return [{"id": "a", "alert": {**CLEAN_ALERT, **fields}}]


COHORT_DE_FIXTURES: tuple[Fixture, ...] = (
    Fixture(
        "S018",
        [as_trip_update(trip=ROUTE_SCOPED, stop_time_update=[sequence_only(1), sequence_only(2)])],
        jar_ids=TRIP_ID_UNKNOWN,
        not_emitted="E040",
        note=(
            "both updates carry a stop_sequence, which is what E040 accepts and what the "
            "clause says is not sufficient, so E040 is absent and W006 is the whole verdict"
        ),
    ),
    Fixture(
        "S019",
        [
            as_trip_update(
                trip=ROUTE_SCOPED,
                stop_time_update=[stop_time(1, "S1", arrival={"delay": 30}), stop_time(2, "S2")],
            )
        ],
        jar_ids=TRIP_ID_UNKNOWN,
        not_emitted="E044",
        note=(
            "the arrival carries a delay and no time, which is what E044 accepts and what "
            "the clause forbids, so E044 is absent and W006 is the whole verdict. The "
            "updates state a stop_id, because a route-scoped update without one is S018's"
        ),
    ),
    Fixture(
        "S021",
        [
            as_trip_update(
                trip={**FIRST_RUN, **MOVED},
                timestamp=CLOCK + 1,
                stop_time_update=UNSCHEDULED_STOPS,
            )
        ],
        preceding=(
            [as_trip_update(trip={**FIRST_RUN, **STARTED}, stop_time_update=UNSCHEDULED_STOPS)],
        ),
        jar_ids=STOP_TIME_ARTIFACT,
        exact_times="0",
        note=(
            "W009 is the stop_time_update artifact rather than an overlap: the updates are "
            "UNSCHEDULED, which is 3 and post-2015. The row's column says none, and E017 "
            "and E018 are absent because the two headers differ by a second and increase"
        ),
    ),
    Fixture(
        "S023",
        [
            as_trip_update(
                trip={
                    "trip_id": "T1",
                    "schedule_relationship": SCHEDULED,
                    "modified_trip": {"modifications_id": "M1"},
                }
            )
        ],
    ),
    Fixture(
        "S024",
        [as_trip_update(trip=ADDED_TRIP)],
        not_emitted="E016",
        note=(
            "the one fixture here whose defect the jar decodes: ADDED is 1 in the 2015 "
            "enum too. E016 reports an ADDED trip that is in trips.txt and E003 reports a "
            "trip that is not, unless it is ADDED, so T9 is outside both and the jar is "
            "silent on a value it read"
        ),
    ),
    Fixture(
        "S025",
        alert(active_period=[{"start": CLOCK, "end": CLOCK + 3600}]),
        note=(
            "active_period is a 2015 field, so the jar read the deprecated field this rule "
            "reports and had nothing to say about it. E001 is the nearest upstream rule "
            "and the bounds are POSIX seconds at the run's own clock"
        ),
    ),
    Fixture(
        "S026",
        alert(
            communication_period=[{"start": CLOCK, "end": CLOCK + 3600}],
            impact_period=[{"start": CLOCK + 1800, "end": CLOCK + 7200}],
        ),
    ),
    Fixture("S027", alert(cause_detail=SAID)),
    Fixture("S028", alert(effect_detail=SAID)),
    Fixture(
        "S029",
        alert(header_text=SAID, description_text=SAID),
        note=(
            "both texts are 2015 fields, so the jar compared nothing it could not see: it "
            "read the two identical TranslatedStrings and reported neither"
        ),
    ),
    Fixture(
        "S030",
        [{"id": "a", "alert": {"informed_entity": [{"stop_id": "S1", "direction_id": 0}]}}],
        not_emitted="E033",
        note=(
            "the selector states a stop_id, which is on E033's list, so the jar sees a "
            "selector that specifies something. direction_id is post-2015 and invisible to "
            "it either way; 0 is stated rather than 1 because presence is what S030 reads"
        ),
    ),
)
