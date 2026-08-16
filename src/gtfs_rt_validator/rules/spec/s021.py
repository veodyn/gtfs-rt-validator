"""S021: a frequency-based trip whose start_time moved between two messages.

`TripDescriptor.start_time`'s comment reaches this after saying that an
exact_times=0 trip's start_time "may be arbitrary, and is initially expected to
be the first departure of the trip":

    Once established, the start_time of this frequency-based trip should be
    considered immutable, even if the first departure time changes -- that time
    change may instead be reflected in a StopTimeUpdate.

So the antecedent is exact_times=0 specifically, which is what
`ctx.static.exact_times_zero_trip_ids` answers. For exact_times=1 the value is
constrained by `frequencies.txt` arithmetic instead, which is E019.

**What `ctx.previous` is, because this is the spec tier's only rule that reads
it.** `runner/context.py` fixes it as the previous message *of the same role*,
never whatever the runner read last: comparing a VehiclePositions message
against the TripUpdates message that happened to precede it compares two
unrelated snapshots, which `tests/test_runner_rules.py` pins against a run that
interleaves roles. `runner/run.py` keys its `previous` dict on
`one.source.role` and fills it only after a message has been validated, so the
first message of a role sees `None` and a role whose file failed to decode never
becomes anybody's previous. Under `--compat` there is one role, so the same
reading is upstream's global one; this rule never runs there.

**A trip instance is `(trip_id, start_date)`, and a message that states two
start_times for one is not compared at all.** An absent start_date is part of
the key rather than a wildcard: two messages that both omit it describe the same
instance as far as either states, and a message that adds one is describing a
different instance from the one before it.

The key cannot include `start_time`, because that is the value being compared:
a rule keyed on it would find every moved start_time under a key of its own and
could never fire. But `start_time` is exactly what tells two runs of one
exact_times=0 trip apart. `trip_id`'s own comment says so, at `:804`: "For
frequency-based trip, start_time and start_date might also be necessary" to
uniquely identify the trip. So a message naming `(trip_id, start_date)` twice
with two start_times is naming two runs, not one run twice, and nothing in the
descriptors says which run the next message's descriptor is. Such a key is
dropped from both messages rather than resolved first-descriptor-wins: comparing
the second run against the first run's value reports a change on a feed where
nothing moved, which is a finding about the rule and not about the feed. Two
descriptors that agree on the value are one instance stated twice, and the first
of them carries the finding, the way `_shared/feed_index.py` keeps the first of
a repeated id; the duplicate descriptor itself is S003's.

E017 and E018 also compare two messages, and they compare header timestamps.
Nothing upstream compares a descriptor field across messages at all.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator, Sequence
from typing import TYPE_CHECKING, Any

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY, Occurrence
from gtfs_rt_validator.rules._shared.schedule_relationship import TripRelationship, relationships
from gtfs_rt_validator.rules._shared.trip_descriptor_spec import trip_text
from gtfs_rt_validator.rules.registry import rule

if TYPE_CHECKING:  # `runner.context` reaches the static layer, and so the sibling.
    from gtfs_rt_validator.proto.decode import Msg
    from gtfs_rt_validator.runner.context import RuleContext

RULE_ID = "S021"

# Quoted as the proto writes it, `--` included: the citation gate compares
# bytes, so a tidied dash would fail `tests/test_clause_citations.py`.
CLAUSE = (
    "spec: Once established, the start_time of this frequency-based trip should be "
    "considered immutable, even if the first departure time changes -- that time change "
    "may instead be reflected in a StopTimeUpdate."
)

#: The memo scope the previous message's walk is kept under. Without it the
#: second `relationships` call in one context is answered with this message's
#: records, and every comparison becomes a value against itself.
PREVIOUS = "previous"

Instance = tuple[str, str]


@rule(RULE_ID, source=CLAUSE, severity=manifest.Severity.WARNING)
def check(message: Msg, ctx: RuleContext) -> Sequence[Occurrence] | None:
    if ctx.previous is None:
        return None
    frequency_trips = ctx.static.exact_times_zero_trip_ids
    established = _start_times(relationships(ctx.previous, ctx, scope=PREVIOUS), frequency_trips)
    if not established:
        return None
    return [
        Occurrence(
            RULE_ID,
            f"{_instance_text(found.trip)} start_time changed from {was} to {now}",
            {ENTITY_PATH_KEY: found.path},
        )
        for instance, (found, now) in _instances(
            relationships(message, ctx), frequency_trips
        ).items()
        for was in [established.get(instance)]
        if was is not None and was != now
    ]


def _stated(
    found: Sequence[TripRelationship], frequency_trips: Collection[str]
) -> Iterator[tuple[TripRelationship, Instance, Any]]:
    """Each descriptor that names a frequency-based trip and states a start_time."""
    for record in found:
        trip = record.trip
        if trip.get("trip_id") in frequency_trips and trip.has("start_time"):
            yield record, (trip.get("trip_id"), trip.get("start_date")), trip.get("start_time")


def _instances(
    found: Sequence[TripRelationship], frequency_trips: Collection[str]
) -> dict[Instance, tuple[TripRelationship, Any]]:
    """Each instance this message states one start_time for, first record kept.

    An instance stated with two different start_times is two runs of one
    frequency-based trip rather than one run, so it is dropped: see the module
    docstring for why comparing the second against the first is a finding about
    the rule.
    """
    stated: dict[Instance, tuple[TripRelationship, Any]] = {}
    ambiguous: set[Instance] = set()
    for record, instance, start_time in _stated(found, frequency_trips):
        if stated.get(instance, (record, start_time))[1] != start_time:
            ambiguous.add(instance)
        stated.setdefault(instance, (record, start_time))
    return {instance: kept for instance, kept in stated.items() if instance not in ambiguous}


def _start_times(
    found: Sequence[TripRelationship], frequency_trips: Collection[str]
) -> dict[Instance, Any]:
    """What the previous message established, one start_time per instance."""
    return {
        instance: start_time
        for instance, (_, start_time) in _instances(found, frequency_trips).items()
    }


def _instance_text(trip: Msg) -> str:
    """`trip_id T1 start_date 20260814`, with the date only when there is one."""
    named = trip_text(trip)
    return f"{named} start_date {trip.get('start_date')}" if trip.has("start_date") else named
