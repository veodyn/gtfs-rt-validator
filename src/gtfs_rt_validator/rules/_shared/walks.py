"""One stateful loop per upstream validator, read by every rule inside it.

Upstream puts several rules in one loop. `StopTimeUpdateValidator` walks a
TripUpdate's stop_time_updates once and emits E002, E009, E036, E037, E040,
E041, E042, E043, E044, E045, E046 and E051 out of that single pass;
`TripDescriptorValidator` and `TimestampValidator` do the same for their own
sets. This project puts each reported id in its own module. Both can be true at
once only if the loop lives in one place and the modules read it, which is what
this module is.

**The shape.** A walk is a generator `(message, ctx) -> Iterator[Event]`,
yielding events in upstream's own emission order. A rule module filters the
stream for its own id and turns what is left into occurrences:

    def check(message, ctx):
        return [Occurrence(RULE_ID, event.prefix, event.context)
                for event in events_for(RULE_ID, stop_time_updates, message, ctx)]

An `Event` carries a context as well as a prefix, because the thing that
locates a finding for a rule inside a loop is the loop's own position, and the
rule cannot rebuild it. See `Event`.

**The memo.** `walk_events` caches the event list on `ctx.memo`, which the
runner builds fresh per message, so twelve rules walk one feed once between
them. The list is materialised because a generator cannot be replayed: caching
the generator itself would hand the first rule every event and every rule after
it none. The key is the walk's own module and qualified name, namespaced under
`walk:` so a rule memoising something else cannot collide with it, and two
walks that answer to one key raise rather than quietly returning each other's
events.

**Why a rule may not walk on its own.** Upstream's control flow is reproduced
here and nowhere else, because three of its behaviours are properties of the
shared loop rather than of any rule in it, and a per-rule reimplementation gets
each of them wrong in the direction of emitting more than the jar does.

- **E051 breaks the loop.** When a stop_time_update names a stop_sequence that
  is in no `stop_times.txt` row of that trip, upstream logs E051 and `break`s,
  abandoning the rest of that trip's stop_time_updates for *every* rule in the
  validator, not only for E051. A rule walking independently keeps going and
  reports findings upstream never reaches.
- **W009's suppression list is whole-feed.** `errorListW009` is not reset per
  TripUpdate, so once any W009 exists anywhere in the feed, including one from
  an earlier entity's TripDescriptor, the first stop_time_update of every later
  TripUpdate flips `foundW009` whether or not it added anything, and that
  trip's remaining stop_time_updates are never checked. A port with a per-trip
  list emits strictly more occurrences than upstream. It is a bug, and under
  `--compat` reproducing it is the requirement.
- **E022 carries its previous values forward conditionally.** `previousArrival`
  and `previousDeparture` advance only when that field was present on *this*
  stop_time_update, so "previous stop" means "the most recent stop that had
  this field", and comparisons reach back past a stop_time_update that had only
  the other one. Its eight comparisons are independent `if`s that can all fire
  from one stop_time_update.

One generator per looping validator lives next to this docstring.
`HeaderValidator` and `StopValidator` contribute none, having no loop between
them, and `tests/test_shared_walks.py` pins the contract against a fake walk.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from gtfs_rt_validator.rules.errors import RuleContractError

if TYPE_CHECKING:  # A type-only edge: every rule imports this, and importing
    # the runner at run time would drag the static layer and the sibling in
    # behind it. `tests/test_only_adapter_touches_the_sibling.py` is the check.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["Event", "Walk", "events_for", "prefixes_for", "walk_events", "walk_key"]


@dataclass(frozen=True, slots=True)
class Event:
    """One thing a walk saw: the id upstream logged there, and how to describe it.

    `prefix` is upstream's occurrence prefix verbatim, and is the whole of what
    `--compat` needs. The suffix belongs to the rule, never to the event.

    `context` is why this is not a `(rule_id, prefix)` pair. Modern reports
    carry `entityPath` alongside the prefix, and for a rule inside a stateful
    loop the path that locates a finding is the loop's own position:
    `entity[3].trip_update.stop_time_update[1]`. The rule module cannot rebuild
    that, because the walk is what did the walking, and roughly forty of the
    fifty-six rules live inside one. Under `--compat` the writer ignores it, so
    carrying it costs nothing there.

    A walk whose rules need no path passes nothing and gets an empty dict of its
    own. `default_factory` rather than a shared literal: frozen stops the field
    being rebound, not the dict being mutated through it.
    """

    rule_id: str
    prefix: str = ""
    context: dict[str, object] = field(default_factory=dict)


#: A walk itself. `message` is a decoded `Msg`, typed loosely for the same
#: reason `registry.RuleFn` is: this module is under the rules layer, and
#: nothing here needs the decoder's own type to do its job.
Walk = Callable[[Any, "RuleContext"], Iterator[Event]]

#: Namespaces the memo entry, so a rule caching something of its own under a
#: plain name can never land on a walk's events.
KEY_PREFIX = "walk:"


def walk_key(walk: Walk) -> str:
    """The memo entry one walk owns, for one message.

    Module plus qualified name, which distinguishes every walk this project
    will write from every other: they are module-level generators, one per
    upstream validator, so no two share both. Identity would distinguish them
    too, but a string keeps `ctx.memo` readable in a debugger and keeps the
    field a plain `dict[str, Any]` for every other user of it.
    """
    return f"{KEY_PREFIX}{walk.__module__}.{walk.__qualname__}"


def walk_events(walk: Walk, message: Any, ctx: RuleContext) -> tuple[Event, ...]:
    """Everything `walk` yields for `message`, running its body at most once.

    Materialised into a tuple, because the second reader of a generator gets
    nothing. Cached under `walk_key` on the context the runner built for this
    message, so the cache dies with the message rather than outliving it.

    The walk is passed the message rather than reading one off the context on
    purpose: `ctx` also carries `previous`, and a walk over that would be
    memoised under this message's key. If a rule ever needs one, it needs its
    own walk and its own key, not this function with a different argument.
    """
    key = walk_key(walk)
    cached = ctx.memo.get(key)
    if cached is not None:
        if cached[0] is not walk:
            raise RuleContractError(
                f"two walks answer to the memo key {key}; one walk owns one key, so give one of "
                f"them a name of its own rather than let it read the other's events"
            )
        return cached[1]
    events = tuple(walk(message, ctx))
    ctx.memo[key] = (walk, events)
    return events


def events_for(rule_id: str, walk: Walk, message: Any, ctx: RuleContext) -> Iterator[Event]:
    """The events `rule_id` alone is responsible for, in upstream's order.

    The filter never reorders and never deduplicates: upstream emits what its
    loop emits, and a rule reporting twice about one entity is upstream
    reporting twice about one entity.

    This is the one a rule should reach for, because it keeps the `context` the
    walk attached. `prefixes_for` below drops it.
    """
    for event in walk_events(walk, message, ctx):
        if event.rule_id == rule_id:
            yield event


def prefixes_for(rule_id: str, walk: Walk, message: Any, ctx: RuleContext) -> Iterator[str]:
    """`events_for`, keeping only the prefix.

    For a rule whose walk attaches no context, where the empty dict on every
    event would be noise in the rule body. A rule that drops a context its walk
    did attach silently loses `entityPath` from its modern report, so reach for
    `events_for` unless the walk genuinely yields none.
    """
    for event in events_for(rule_id, walk, message, ctx):
        yield event.prefix
