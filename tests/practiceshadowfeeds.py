"""The band fixtures: four or more cases each for P004 and P005.

Split out of `practiceshadow.py` so neither file grows past the size hook, and
because this one is the reviewable artifact: every `jar_ids` set here was
recorded from a real jar run rather than predicted, and the whole claim of
decision 3 is what those sets contain.

**A band rule gets four cases, not two.** Inside the band, outside it on the
upstream rule's side, outside it on the compliant side, and the boundary, which
is where a band split goes wrong. P004 has two boundaries, 30 and 35, and one
extra case at 36 because 35-silent-36-firing is the measurement that proves
W007's comparison is strict rather than the docstring that claims it.

Cohorts D, E and F add their fixtures to `FIXTURES` below; the test module's
docstring says what a new one has to carry. Cohort F's two live in
`practiceshadowcohortf.py` and are imported, for the same size-hook reason this
file was split off in the first place, and the seven rules that reached the close
step with no fixture at all live in `practiceshadowgap.py`.
"""

from __future__ import annotations

from practiceshadow import (
    CLOCK,
    Fixture,
    Message,
    as_trip_update,
    as_vehicle,
)
from practiceshadowcohortf import P012_FIXTURES, P015_FIXTURES
from practiceshadowgap import GAP_FIXTURES

__all__ = ["FIXTURES", "IN_BAND"]


def interval(seconds: int) -> tuple[Message, ...]:
    """Two messages whose header timestamps are `seconds` apart.

    Each entity's own timestamp tracks its message's header, so the only thing
    that changes between the two files is the interval under test. File `n` is
    stamped `CLOCK + n`, so the second header sits `seconds - 1` ahead of its
    own clock, which is inside E050's 60-second tolerance for every interval
    here and behind W008's 65 for none.
    """
    return (
        Message(CLOCK, [as_trip_update(timestamp=CLOCK)]),
        Message(CLOCK + seconds, [as_trip_update(timestamp=CLOCK + seconds)]),
    )


def stale(age: int) -> tuple[Message, ...]:
    """One message with a fresh header and a VehiclePosition `age` seconds old."""
    return (Message(CLOCK, [as_vehicle(timestamp=CLOCK - age)]),)


P004_FIXTURES = (
    Fixture("P004", "in band, 33 seconds", interval(33), not_emitted="W007"),
    Fixture(
        "P004",
        "the upper boundary, 35 seconds",
        interval(35),
        not_emitted="W007",
        note="W007 compares strictly against 35, so 35 is this rule's and nobody else's",
    ),
    Fixture(
        "P004",
        "the lower boundary, 30 seconds",
        interval(30),
        fires=False,
        note='"at least once every 30 seconds" is satisfied by exactly 30',
    ),
    Fixture(
        "P004",
        "one second above the band, 36 seconds",
        interval(36),
        fires=False,
        jar_ids=frozenset({"W007"}),
        note="the first interval W007 reaches, which is what makes 35 the band's edge",
    ),
    Fixture(
        "P004",
        "well above the band, 40 seconds",
        interval(40),
        fires=False,
        jar_ids=frozenset({"W007"}),
    ),
    Fixture("P004", "compliant, 20 seconds", interval(20), fires=False),
)

P005_FIXTURES = (
    Fixture("P005", "in band, 100 seconds old", stale(100)),
    Fixture(
        "P005",
        "one second past the boundary, 91 seconds old",
        stale(91),
        note="nothing upstream reaches a stale entity timestamp at any age",
    ),
    Fixture(
        "P005",
        "the boundary, 90 seconds old",
        stale(90),
        fires=False,
        note='"should not be older than 90 seconds" is satisfied by exactly 90',
    ),
    Fixture("P005", "compliant, current", stale(0), fires=False),
    Fixture(
        "P005",
        "the E012 neighbour, an entity ahead of its header",
        (Message(CLOCK - 10, [as_vehicle(timestamp=CLOCK)]),),
        fires=False,
        jar_ids=frozenset({"E012"}),
        note="E012 is the entity against the header; this rule is the entity against the clock",
    ),
)

#: `TripDescriptor.ScheduleRelationship.CANCELED` and `Alert.Effect.NO_SERVICE`,
#: by number as this file spells every other enum value.
CANCELED, NO_SERVICE = 3, 1


def sequential(first: dict[str, object], second: dict[str, object]) -> tuple[Message, ...]:
    """Two messages one second apart, carrying one entity each.

    One second because the interval must be inside P004's and W007's bands and
    the two files must differ: the runner drops a message byte-identical to the
    last one of its role, and a stability fixture whose second message was
    dropped would have no previous message to compare against. Each entity's
    timestamp tracks its own header for the reason `interval` gives.
    """
    return (Message(CLOCK, [first]), Message(CLOCK + 1, [second]))


def renamed(first: str, second: str) -> tuple[Message, ...]:
    """One trip carried by two entity ids, one per message. P002."""
    return sequential(
        as_trip_update(entity_id=first, timestamp=CLOCK),
        as_trip_update(entity_id=second, timestamp=CLOCK + 1),
    )


def revehicled(first: str, second: str) -> tuple[Message, ...]:
    """One trip naming two vehicle ids, one per message. P003."""
    return sequential(
        as_trip_update(timestamp=CLOCK, vehicle={"id": first}),
        as_trip_update(timestamp=CLOCK + 1, vehicle={"id": second}),
    )


def cancelled(start_date: str, entity_id: str) -> dict[str, object]:
    """A CANCELED TripUpdate for the one trip, on one day. P006."""
    return as_trip_update(
        entity_id=entity_id,
        trip={"trip_id": "T1", "schedule_relationship": CANCELED, "start_date": start_date},
    )


def alerted(trip_id: str = "T1") -> dict[str, object]:
    """The Alert `:50` asks for beside the cancellations.

    Its selector states `schedule_relationship` for the reason `practiceshadow`
    gives: W009 reports an absent one on any TripDescriptor, `informed_entity`'s
    included, and a run of this fixture without it was measured emitting W009
    from both the jar and compat. It states CANCELED rather than SCHEDULED
    because that is what the trips it selects say.
    """
    return {
        "id": "alert",
        "alert": {
            "effect": NO_SERVICE,
            "informed_entity": [{"trip": {"trip_id": trip_id, "schedule_relationship": CANCELED}}],
        },
    }


def cancellation(*extra: dict[str, object]) -> tuple[Message, ...]:
    """One message cancelling the trip on two days, plus whatever else."""
    return (Message(CLOCK, [cancelled("20231114", "a"), cancelled("20231115", "b"), *extra]),)


P002_FIXTURES = (
    Fixture("P002", "the entity id moved", renamed("a", "b")),
    Fixture(
        "P002",
        "the entity id was kept",
        renamed("a", "a"),
        fires=False,
        note="the conformant twin: one byte of one entity id apart from the fixture above",
    ),
)

P003_FIXTURES = (
    Fixture("P003", "the vehicle id moved", revehicled("1", "2")),
    Fixture(
        "P003",
        "the vehicle id was kept",
        revehicled("1", "1"),
        fires=False,
        note="the conformant twin",
    ),
)

P006_FIXTURES = (
    Fixture("P006", "two cancelled days and no alert", cancellation()),
    Fixture(
        "P006",
        "two cancelled days and the alert the clause asks for",
        cancellation(alerted()),
        fires=False,
        note="the conformant twin: the same cancellations with the NO_SERVICE Alert beside them",
    ),
)

FIXTURES: tuple[Fixture, ...] = (
    P004_FIXTURES
    + P005_FIXTURES
    + P002_FIXTURES
    + P003_FIXTURES
    + P006_FIXTURES
    + P012_FIXTURES
    + P015_FIXTURES
    + GAP_FIXTURES
)

#: The fixtures carrying the tier's strongest claim: the jar emits nothing on an
#: in-band fixture of each band rule. Named here so
#: the assertion is over a list somebody can read rather than over a substring
#: of a case name.
#:
#: **Two, not three.** A third band rule, P014, was proposed for an
#: `exact_times=0` trip whose `TripDescriptor.schedule_relationship` is absent.
#: Its in-band fixture made the jar emit W009: `TripDescriptorValidator.java`
#: `:470-474` fires on `!hasScheduleRelationship()` for any TripDescriptor, and
#: `_shared/walk_trip_descriptor.py:141-142` calls it with no suppression guard,
#: so P014's trigger was a strict subset of W009's and no feed shape escaped it.
#: The rule was retired rather than exempted, and clause `143#2`'s verdict in
#: `upstream/practice-clause-verdicts.json` carries the measurement.
IN_BAND = ("P004 in band, 33 seconds", "P005 in band, 100 seconds old")
