"""The shared-walk contract, proved against a fake walk before a real one exists.

This module was written before the first real walk was: `HeaderValidator` and
`StopValidator` have no stateful loop between them, and the four validators that
do came later. So the walk under test here is a fake, a generator yielding a
fixed event sequence, and what is asserted is the part no real walk would assert
any better: that the
body runs once however many rules read it, that each rule sees only its own id,
and that upstream's emission order survives the filter.

The event sequence is invented rather than ported. Its shape is what matters:
several ids interleaved in one stream, the same id more than once, in the order
one upstream validator would have emitted them.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules._shared.walks import (
    Event,
    events_for,
    prefixes_for,
    walk_events,
    walk_key,
)
from gtfs_rt_validator.rules.errors import RuleContractError
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from gtfs_rt_validator.runner.context import RuleContext
from gtfs_rt_validator.static._stoptimes import EMPTY_STOP_TIMES
from gtfs_rt_validator.static.adapter import RawTables
from gtfs_rt_validator.static.context import StaticContext

READING = Reading(1_700_000_000_000, ClockSource.FIXED)


def at(index: int) -> dict[str, object]:
    """The entity path a `StopTimeUpdateValidator` walk knows and a rule does not."""
    return {ENTITY_PATH_KEY: f"entity[0].trip_update.stop_time_update[{index}]"}


EVENTS = (
    Event("E009", "trip_id 1 stop_sequence 1", at(0)),
    Event("E036", "trip_id 1 stop_sequence 2", at(1)),
    Event("E009", "trip_id 1 stop_sequence 3", at(2)),
    Event("E051", "trip_id 1 stop_sequence 4", at(3)),
)

#: The walks here never read the message, so it can be anything distinguishable.
FIRST_MESSAGE = "message one"
SECOND_MESSAGE = "message two"


def a_context() -> RuleContext:
    """A context over a static feed with nothing in it, for its `memo` alone."""
    return RuleContext(
        static=StaticContext.build(RawTables([], [], [], [], EMPTY_STOP_TIMES, [], [])),
        timezone="America/New_York",
        clock=READING,
        source="a.pb",
    )


def counted(name: str, events: tuple[Event, ...] = EVENTS):
    """A fake walk, plus the list of messages its body has actually run over.

    The name is written onto `__qualname__` because that is what the memo key is
    built from, and two closures made here would otherwise be one key.
    """
    ran: list[object] = []

    def walk(message, ctx):
        ran.append(message)
        yield from events

    walk.__qualname__ = name
    return walk, ran


def test_a_rule_sees_only_the_events_that_carry_its_own_id():
    """What makes "one rule module per reported id" survive a validator that
    emits five ids from one loop."""
    walk, _ = counted("stop_time_updates")
    ctx = a_context()

    assert list(prefixes_for("E009", walk, FIRST_MESSAGE, ctx)) == [
        "trip_id 1 stop_sequence 1",
        "trip_id 1 stop_sequence 3",
    ]
    assert list(prefixes_for("E051", walk, FIRST_MESSAGE, ctx)) == ["trip_id 1 stop_sequence 4"]


def test_an_event_carries_the_context_only_the_walk_can_know():
    """The reason an event is not just `(rule_id, prefix)`.

    `entityPath` is one of the two context keys this project adds to the
    sibling's shape, and for a rule inside a stateful loop the path that
    identifies a finding is the loop's own position: which stop_time_update of
    which entity. The rule module cannot reconstruct it, because the walk is
    what did the walking. An event that carried only a prefix would leave every
    rule inside a shared loop unable to say where in the message it fired,
    which is roughly forty of the fifty-six.
    """
    walk, _ = counted("stop_time_updates")

    found = list(events_for("E009", walk, FIRST_MESSAGE, a_context()))

    assert [event.prefix for event in found] == [
        "trip_id 1 stop_sequence 1",
        "trip_id 1 stop_sequence 3",
    ]
    assert [event.context[ENTITY_PATH_KEY] for event in found] == [
        "entity[0].trip_update.stop_time_update[0]",
        "entity[0].trip_update.stop_time_update[2]",
    ]


def test_an_event_that_names_no_context_gets_an_empty_one():
    """A walk whose rules need no path says nothing, rather than each of its
    rules having to pass an empty dict in."""
    event = Event("E041", "trip_id 1")

    assert event.context == {}


def test_two_events_built_without_a_context_do_not_share_one():
    """The mutable-default trap, which a frozen dataclass does not prevent by
    itself. A walk that let a rule mutate this would poison every later event."""
    first = Event("E041", "trip_id 1")
    second = Event("E043", "trip_id 2")

    assert first.context is not second.context


def test_a_rule_the_walk_never_emitted_for_gets_nothing():
    walk, _ = counted("stop_time_updates")

    assert list(prefixes_for("E045", walk, FIRST_MESSAGE, a_context())) == []


def test_the_walk_body_runs_once_however_many_rules_read_it():
    """The whole point of memoising: twelve `StopTimeUpdateValidator` rules walk
    a feed once between them, not twelve times each."""
    walk, ran = counted("stop_time_updates")
    ctx = a_context()

    for rule_id in ("E009", "E036", "E051", "E045"):
        list(prefixes_for(rule_id, walk, FIRST_MESSAGE, ctx))

    assert ran == [FIRST_MESSAGE]


def test_the_events_are_materialised_so_the_second_reader_is_not_handed_a_spent_one():
    """A generator cannot be replayed, so caching the generator would give the
    first rule every event and every rule after it none."""
    walk, _ = counted("stop_time_updates")
    ctx = a_context()

    first = walk_events(walk, FIRST_MESSAGE, ctx)
    second = walk_events(walk, FIRST_MESSAGE, ctx)

    assert first == EVENTS
    assert second == EVENTS


def test_the_stream_keeps_upstreams_emission_order():
    """Filtering is what a rule does to the stream; it never reorders it, and
    the order two ids interleave in is upstream's, not the registry's."""
    walk, _ = counted("stop_time_updates")

    assert walk_events(walk, FIRST_MESSAGE, a_context()) == EVENTS


def test_the_next_message_runs_the_walk_again():
    """The memo lives on the context, and the runner builds one per message, so
    a cached walk can never answer for a message it was not computed from."""
    walk, ran = counted("stop_time_updates")

    walk_events(walk, FIRST_MESSAGE, a_context())
    walk_events(walk, SECOND_MESSAGE, a_context())

    assert ran == [FIRST_MESSAGE, SECOND_MESSAGE]


def test_two_walks_over_one_message_are_memoised_apart():
    """One message reaches several validators, and each has its own loop."""
    stop_times, stop_time_runs = counted("stop_time_updates")
    descriptors, descriptor_runs = counted("trip_descriptors", (Event("W009", "trip_id 1"),))
    ctx = a_context()

    assert list(prefixes_for("E009", stop_times, FIRST_MESSAGE, ctx)) != []
    assert list(prefixes_for("W009", descriptors, FIRST_MESSAGE, ctx)) == ["trip_id 1"]
    assert (stop_time_runs, descriptor_runs) == ([FIRST_MESSAGE], [FIRST_MESSAGE])


def test_the_memo_key_names_the_walk_and_is_namespaced():
    """A rule may memoise other things through `ctx.memo`, so a walk's entry
    cannot be a name another one might reach for, and two walks in different
    modules that happen to share a name cannot answer to one key.

    The expected key is written out here rather than recomputed by calling
    `walk_key`. A pair of `startswith("walk:")` and `endswith(...)` assertions
    would accept "walk:garbage.stop_time_updates", and comparing `ctx.memo`
    against `walk_key(walk)` accepts whatever that returns, so between them the
    module half of the key, which is the half that keeps two validators' walks
    apart, would never be checked at all.
    """
    walk, _ = counted("stop_time_updates")
    ctx = a_context()

    walk_events(walk, FIRST_MESSAGE, ctx)

    expected = f"walk:{__name__}.stop_time_updates"

    assert walk.__module__ == __name__
    assert walk.__qualname__ == "stop_time_updates"
    assert walk_key(walk) == expected
    assert list(ctx.memo) == [expected]


def test_two_walks_that_answer_to_one_key_are_a_bug_in_this_repository():
    """Not a finding about a feed: it is two modules in this tree claiming one
    memo entry, which would silently answer one walk with the other's events."""
    one, _ = counted("stop_time_updates")
    other, _ = counted("stop_time_updates", (("W009", "trip_id 1"),))
    ctx = a_context()

    walk_events(one, FIRST_MESSAGE, ctx)

    with pytest.raises(RuleContractError, match="stop_time_updates"):
        walk_events(other, FIRST_MESSAGE, ctx)
