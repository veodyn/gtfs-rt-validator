"""Cohort H's jar fixtures: the ten `TripModifications` rules, S041 to S050.

Split out of `specshadowfeeds.py` for the reason that file was split out of
`specshadow.py`, so neither grows past the size hook, and the way
`specshadowcohortfg.py` and the practice tier's cohort modules do. Same
contract: every `jar_ids` set here was **recorded from a real jar run** rather
than predicted.

**Nine of these ten fixtures get the weakest form of a clean jar run there is,
and the file says so rather than letting an empty set look like an answer.**
`specshadowcohortfg.py` names two strengths of evidence; this cohort is almost
entirely the weaker one, and one step weaker still than the shapes half of that
file.

- **The jar cannot decode the message the defect sits on.**
  `FeedEntity.trip_modifications` is field 8 and the 2015 `FeedEntity` declares
  five, so `TripModifications`, `Modification`, `StopSelector`,
  `ReplacementStop` and `SelectedTrips` all land whole in the unknown field set.
  The jar never sees a `start_stop_selector`, a `travel_time_to_stop` or a
  `service_dates` value at all. Silence is what a message it cannot read looks
  like, so for S041 to S044 and S046 to S050 it is *consistent with* the
  declared overlap and is not evidence for it. What settles those is reading the
  Java, which is where each declaration came from; this file only records that
  the jar was asked and answered nothing.
- **S045 is the one fixture the jar decoded half of**, and that half is the half
  the 56 could have reported. Its defect is a pair: a `TripModifications`
  selecting `T1` and a `TripUpdate` declaring `schedule_relationship =
  REPLACEMENT` for the same trip. The `TripUpdate` is a 2015 message and
  protobuf-java parsed it into typed fields; `REPLACEMENT = 5` is not in the
  2015 `ScheduleRelationship`, so it landed in the unknown set and the jar
  reported `W009`, which is `DESCRIPTOR_ARTIFACT` and not an overlap. The other
  half of the pair is still invisible, so even here the jar could not have
  paired them, and S045's declaration of no overlap rests on the same reading
  rather than on this run.

**Three rules changed after they first landed and the fixtures exercise what
they do now**, which is why two of them look unlike their neighbours:

- **S043 resolves against `stops.txt` alone.** Its fixture names a stop that
  only a `Stop` entity of the same feed defines, which the widened resolution
  would have accepted and this rule reports, with the "is a new stop" tail
  `_shared/references.py` writes for exactly that producer. S046's fixture is
  the deliberate contrast: the same construction under `ReplacementStop.stop_id`
  is silent, because `:1259` permits a realtime-defined stop there and `:1163`
  does not permit one on a selector, so S046's own defect has to be a stop_id
  neither feed defines.
- **S044 returns early only when `-ignoreShapes` withheld the ids.** No fixture
  here can state that, or the two states it used to be conflated with, because
  the flag is a `Request` field and the static tables are the harness's; the
  three states are asserted directly in `tests/test_rule_s044.py`, one test
  each, including the archive with no `shapes.txt` that used to be silent. What
  this fixture states is the resolution itself, over the four-point `shapes.txt`
  `minimal_tables()` writes.
- **S049 reports both edges of the week**, so its fixture states one date on
  each side of a `service_dates` that is inside it. Neither edge is written
  relative to the run's day: `20200101` is before and `20991231` is more than
  seven days after any day this harness could run on, and the middle value is
  the run's own day under the mtime clock, which is what makes the window's
  shape visible in one message.

**S045's fixture is one role, and that is a harness limit rather than a
choice.** The rule reads `ctx.combined` and joins across every role of a cycle,
and `tests/test_rule_s045.py` covers that directly, two-role cycle and all. This
harness stages one cycle per fixture whose messages are files of a **directory
replay under one role**, which is `ctx.previous`'s shape and not `combined`'s,
and the jar assertion depends on it: `BatchProcessor` carries the previous
message across the files of a run. So a two-role fixture is not expressible
here without changing what the jar is asked, and the cross-role half of S045 is
tested where a jar is not involved.
"""

from __future__ import annotations

from specshadow import CLOCK, Fixture, stop_time, trip_update

__all__ = ["COHORT_H_FIXTURES", "DESCRIPTOR_ARTIFACT"]

#: `TripDescriptor.ScheduleRelationship.REPLACEMENT`, by number because the 2015
#: enum has no member for it. `specshadow` exports the four numbers its own
#: fixtures need and this is the fifth.
REPLACEMENT = 5

#: What `specshadowfeeds.DESCRIPTOR_ARTIFACT` records, for the same reason and
#: against the same Java, `TripDescriptorValidator.java:470-474`: the field is
#: populated with a number the 2015 enum has none for, protobuf-java files it as
#: unknown, and `hasScheduleRelationship()` answers false.
DESCRIPTOR_ARTIFACT = frozenset({"W009"})

#: A station, appended to `stops.txt` for S047 alone. Both stops
#: `minimal_tables()` writes are `location_type=0`, and S047's whole subject is a
#: replacement stop whose static row says something else.
STATION: dict[str, object] = {
    "stop_id": "ST1",
    "stop_name": "Station",
    "stop_lat": "27.96",
    "stop_lon": "-82.46",
    "location_type": "1",
}

#: The run's own day: `CLOCK` in `America/New_York`, which `minimal_tables()`
#: puts in `agency.txt` and `_shared/servicedates.py` reads the day in.
TODAY = "20231114"

#: One replacement stop the rules have nothing to say about: `S2` is in
#: `stops.txt` with `location_type=0`, and one value cannot fail S048's
#: monotonicity on its own.
CLEAN_STOP: dict[str, object] = {"stop_id": "S2", "travel_time_to_stop": 60}

#: A selector naming a stop_time of the original trip by position, which is what
#: `:1163` says a `start_stop_selector` is for. By sequence rather than by
#: stop_id so that S043 has nothing to resolve here.
FIRST_STOP: dict[str, object] = {"stop_sequence": 1}


def modification(**overrides: object) -> dict[str, object]:
    """One `Modification` the ten rules are silent on, before its defect.

    Every fixture but S041's states a `start_stop_selector`, because a rule
    under test should fail on its own defect and never on a neighbour's.
    """
    built: dict[str, object] = {
        "start_stop_selector": dict(FIRST_STOP),
        "replacement_stops": [dict(CLEAN_STOP)],
    }
    built.update(overrides)
    return built


def modifying(*changes: dict[str, object], **overrides: object) -> dict[str, object]:
    """One entity carrying a `TripModifications` over `minimal_tables()`'s trip.

    `service_dates` is written only where a fixture asks for it. A
    `TripModifications` that states none is a legal message no rule of this
    cohort reports, and a date that is inside the week today is one more thing
    for a reader to check against the clock.
    """
    built: dict[str, object] = {
        "selected_trips": [{"trip_ids": ["T1"], "shape_id": "SH1"}],
        "modifications": [dict(change) for change in changes],
    }
    built.update(overrides)
    return {"id": "TM", "trip_modifications": built}


def replaced() -> dict[str, object]:
    """A `TripUpdate` declaring `T1` REPLACEMENT, which is half of S045's defect.

    Each event states a `scheduled_time` as well as a `time`, because P010 warns
    when a REPLACEMENT trip provides none and this fixture is S045's rather than
    that rule's. To the jar both events carry a `time`, so E043 and E044 are
    silent, and `scheduled_time` is a post-2015 field it never sees.
    """
    stops = [
        stop_time(
            sequence,
            stop_id,
            arrival={"time": CLOCK + sequence * 60, "scheduled_time": CLOCK + sequence * 60},
            departure={
                "time": CLOCK + sequence * 60 + 10,
                "scheduled_time": CLOCK + sequence * 60 + 10,
            },
        )
        for sequence, stop_id in ((1, "S1"), (2, "S2"))
    ]
    return {
        "id": "a",
        "trip_update": trip_update(
            trip={"trip_id": "T1", "schedule_relationship": REPLACEMENT},
            stop_time_update=stops,
        ),
    }


COHORT_H_FIXTURES: tuple[Fixture, ...] = (
    Fixture("S041", [modifying({"replacement_stops": [dict(CLEAN_STOP)]})]),
    Fixture(
        "S042",
        [modifying(modification(start_stop_selector={}))],
        not_emitted="E040",
        note="E040 is the same shape on StopTimeUpdate, a message with different fields",
    ),
    Fixture(
        "S043",
        [
            modifying(modification(start_stop_selector={"stop_id": "SNEW"})),
            {"id": "SE", "stop": {"stop_id": "SNEW"}},
        ],
        not_emitted="E011",
        note=(
            "the stop is defined by a Stop entity of this feed and by nothing in stops.txt, "
            "which is the resolution S043 no longer accepts and S046 still does. E011 walks "
            "three sites and TripModifications is none of them, and the jar cannot decode "
            "the selector to disagree"
        ),
    ),
    Fixture(
        "S044",
        [modifying(modification(), selected_trips=[{"trip_ids": ["T1"], "shape_id": "NOSHAPE"}])],
        note="shapes.txt is the four-point one minimal_tables() writes, so the ids were read",
    ),
    Fixture(
        "S045",
        [replaced(), modifying(modification())],
        jar_ids=DESCRIPTOR_ARTIFACT,
        note=(
            "REPLACEMENT is 5 and the 2015 enum stops at 3, so the jar reads the descriptor "
            "as stating none. The TripModifications half is invisible to it either way, so "
            "it could not have paired the two"
        ),
    ),
    Fixture(
        "S046",
        [
            modifying(
                modification(replacement_stops=[{"stop_id": "NOSTOP", "travel_time_to_stop": 60}])
            )
        ],
        not_emitted="E011",
        note=(
            "neither feed defines NOSTOP, because a Stop entity defining it would resolve "
            "here where the same construction is S043's defect. E011's world is stops.txt "
            "alone and this message is not one of its three sites"
        ),
    ),
    Fixture(
        "S047",
        [
            modifying(
                modification(replacement_stops=[{"stop_id": "ST1", "travel_time_to_stop": 60}])
            )
        ],
        not_emitted="E015",
        extra_stops=(STATION,),
        note=(
            "the station resolves, so S046 is silent and only its location_type is wrong. "
            "E015 is this predicate on StopTimeUpdate.stop_id, which this fixture has none of"
        ),
    ),
    Fixture(
        "S048",
        [
            modifying(
                modification(
                    replacement_stops=[
                        {"stop_id": "S1", "travel_time_to_stop": 120},
                        {"stop_id": "S2", "travel_time_to_stop": 60},
                    ]
                )
            )
        ],
        note=(
            "both values are positive: the negative-number half of :1257 is recorded "
            "accepted-in-part and this rule does not check it, so a fixture stating one "
            "would assert a verdict the rule never claimed"
        ),
    ),
    Fixture(
        "S049",
        [modifying(modification(), service_dates=["20200101", TODAY, "20991231"])],
        note=(
            "one date on each side of the window and one inside it, so the fixture reports "
            "twice and the middle value shows where the rule stands down. The two "
            "occurrences carry different wording, elapsed and more than 7 days after"
        ),
    ),
    Fixture(
        "S050",
        [modifying(modification(), service_dates=["20231301"])],
        not_emitted="E021",
        note=(
            "month 13, so S049 has no distance to measure and stands aside. E021 is this "
            "predicate on TripDescriptor.start_date, which this fixture has none of, and it "
            "resolves SMART where this rule parses strictly"
        ),
    ),
)
