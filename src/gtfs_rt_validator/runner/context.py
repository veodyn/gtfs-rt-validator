"""What a rule is handed, and what it hands back.

Two things every rule module would otherwise have to guess at are settled here,
because 57 modules guessing separately is 57 divergences.

**1. A rule returns occurrences; the runner collects them.** The alternative,
appending to a container the rule is handed, is equally compatible with "notices
are data appended to a container, never exceptions": that rule is about
exceptions, and both shapes obey it. The question is who appends, and the answer
is the runner, for three reasons. It is the only party that knows which file the
message came from, so `SOURCE_FILE_KEY` is stamped once here instead of in 57
rule bodies that each have to remember. It can reject an occurrence carrying
another rule's id, which a shared container cannot even notice. And a rule that
returns is callable from a test with no container in sight, which is what the
registry's decorator already promises by returning the function unchanged.

The cost of returning is that a rule could materialise a huge list before any
cap applies. That is why the contract is an *iterable* and why `collect` is
itself a generator: a rule may be a generator, each occurrence reaches
`NoticeContainer.add` before the next one is pulled, and the retention cap drops
what it must with nothing else alive. A `collect` that returned a tuple would
have answered the objection in its docstring and not in its code. `None` is
accepted as well, because a plain-function rule that returns early returns
`None` rather than `()`.

**2. Named feed roles, and the semantics that have to be settled before E047 and
W003 can run across them.** Upstream has no answer to copy: its
cross-feed rules only fire when one message happens to carry more than one
entity type, so an agency publishing TripUpdates and VehiclePositions separately
never gets them checked at all. Three decisions, none of which needs a number:

- **Alignment is positional.** A *cycle* is one message per role, and roles
  advance together; a cross-feed rule sees the cycle, never a role's message
  paired with some other role's from another cycle. Aligning by feed header
  timestamp within a tolerance was rejected twice over: the tolerance would be
  an invented constant, and the header timestamp is a value this project is
  simultaneously validating (E012, E017, E018), so a feed with a wrong one would
  misalign the very comparison meant to catch it. A role whose file failed to
  decode is absent from its cycle rather than carried forward, so a stale
  snapshot can never stand in for a missing one.
- **"Previous" is per role.** The previous message of the same role, never
  whatever was read last. Comparing a VehiclePositions message against the
  TripUpdates message that happened to precede it is exactly the unrelated
  snapshot this rules out. Compat has one role, so per role and global are
  the same thing there and upstream's behaviour is unchanged.
- **The host role's clock governs a cross-feed check.** `combined` reaches
  exactly one message per cycle, the first role present in `ROLE_ORDER`, which
  is the CLI's own `-tu -vp -sa` order. So a cross-feed rule fires once per
  cycle rather than once per role, and the clock it reads is the clock of the
  message it was called with. Any other choice needs a tiebreak anyway; a fixed
  order is the one that makes the same run report the same thing twice.

Under compat there is one unnamed role, `rt`, whose cycle is the single message
itself. E047 and W003 therefore fire exactly where the jar fires them.

**Reading the cycle and reporting for it are two questions, and the context
answers them with two members.** `cycle` is the whole cycle and is on every
role's context; `combined` is that same view handed only to the host. One field
used to answer both, and it cost a rule that merely wants to *look* at another
role's file the ability to do so at all: a VehiclePositions message in a
`-tu -vp -sa` run could not see the Alerts feed, because `-tu` was the host. A
message has every right to read what is beside it; what it must not do is emit
the cycle's cross-feed findings a second time. So `combined` is derived from
`cycle` and `role` rather than stored, which makes it impossible for a caller to
hand a non-host message the token that says it reports for the cycle, and leaves
every existing reader of `combined` seeing exactly what it saw before.

The two are the same object under compat, where the one unnamed role is always
the first role present, so no compat-reachable rule can observe the split.

**3. `memo`, the one mutable field, is where a shared walk lives.** Upstream
puts several rules inside one stateful loop, and this project puts each of them
in its own module, so the loop has to run once and be read many times.
`rules/_shared/walks.py` holds the loops and says why they may not be
reimplemented per rule; `memo` is where it caches one, so twelve
`StopTimeUpdateValidator` rules walk a TripUpdate once rather than twelve times.

The two alternatives were rejected on soundness, not on taste. A cache keyed on
`id(message)` is wrong the moment a `Msg` is collected and CPython hands its
address to the next one, which silently answers one message's walk with
another's. A cache on the message itself cannot exist: `Msg` declares
`__slots__` (`proto/decode.py`), so it has no `__dict__` to put one in, and
widening those slots would grow every decoded submessage in a feed to pay for a
cache almost none of them use.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import SOURCE_FILE_KEY, Occurrence
from gtfs_rt_validator.rules.errors import RuleContractError
from gtfs_rt_validator.runner.clock import Reading
from gtfs_rt_validator.static.context import StaticContext

# `RuleContractError` is re-exported rather than defined here. It belongs to the
# rule layer, which every rule imports and which therefore may not reach the
# sibling; `rules/errors.py` says what went wrong when it lived in this module.
__all__ = [
    "DEFAULT_ROLE",
    "ROLE_ALERTS",
    "ROLE_ORDER",
    "ROLE_TRIP_UPDATES",
    "ROLE_VEHICLE_POSITIONS",
    "CombinedFeed",
    "RuleContext",
    "RuleContractError",
    "RuleResult",
    "collect",
    "host_role",
    "role_key",
]

#: Upstream's single unnamed feed, `-gtfsRealtimePath`. Every compat message has
#: this role, which is what makes "per role" state identical to upstream's
#: single global state under `--compat`.
DEFAULT_ROLE = "rt"

ROLE_TRIP_UPDATES = "tu"
ROLE_VEHICLE_POSITIONS = "vp"
ROLE_ALERTS = "sa"

#: Role precedence, and it is the CLI's own flag order. The first role present
#: in a cycle hosts that cycle's cross-feed rules.
ROLE_ORDER = (ROLE_TRIP_UPDATES, ROLE_VEHICLE_POSITIONS, ROLE_ALERTS, DEFAULT_ROLE)

#: What a rule hands back: occurrences, or nothing. See the module docstring.
RuleResult = Iterable[Occurrence] | None


def host_role(roles: Iterable[str]) -> str:
    """Which role of a cycle hosts its cross-feed rules.

    A role nobody declared sorts after every declared one, alphabetically, so
    an unknown role can never displace `-tu` and two unknown roles still order
    deterministically.
    """
    ordered = sorted(roles, key=role_key)
    if not ordered:
        raise RuleContractError("a cycle with no roles has no host")
    return ordered[0]


def role_key(role: str) -> tuple[int, str]:
    """`ROLE_ORDER` position, then the name for a role nobody declared."""
    return (ROLE_ORDER.index(role), "") if role in ROLE_ORDER else (len(ROLE_ORDER), role)


@dataclass(frozen=True, slots=True)
class CombinedFeed:
    """Every role's message for one cycle, as one thing to iterate.

    `entities()` is the loop `CrossFeedDescriptorValidator` writes over a single
    `FeedMessage`, widened to span the cycle. Under compat there is one role, so
    it is that loop unchanged.
    """

    host_role: str
    messages: Mapping[str, Msg]
    sources: Mapping[str, str]
    clocks: Mapping[str, Reading]

    @classmethod
    def of(
        cls,
        messages: Mapping[str, Msg],
        sources: Mapping[str, str],
        clocks: Mapping[str, Reading],
    ) -> CombinedFeed:
        return cls(host_role(messages), dict(messages), dict(sources), dict(clocks))

    def roles(self) -> tuple[str, ...]:
        """The roles that decoded, in `ROLE_ORDER`."""
        return tuple(sorted(self.messages, key=role_key))

    def message(self, role: str) -> Msg | None:
        return self.messages.get(role)

    def source(self, role: str) -> str | None:
        return self.sources.get(role)

    def clock(self, role: str) -> Reading | None:
        return self.clocks.get(role)

    def entities(self) -> Iterator[tuple[str, int, Msg]]:
        """Role, index within that role's message, entity. Roles in order."""
        for role in self.roles():
            for index, entity in enumerate(self.messages[role].get("entity")):
                yield role, index, entity


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Everything a rule may read that is not the message it was given.

    `timezone` is a string and never `None`, unlike `StaticContext.timezone`:
    the gate has already decided what an agency-less feed means, so no rule has
    to. `previous_clock` travels with `previous` because a rule comparing two
    messages that had only one clock would compare a timestamp against the wrong
    now. `cycle` is every role's message for this instant and is on every role's
    context; `combined` is the host's view of it and is a property below.

    `memo` is the one mutable field on a frozen dataclass, and the module
    docstring says why it exists here and nowhere else. Frozen still means what
    it says: no rule may rebind a field, and the dict is scratch space shared by
    every rule that sees one message, never state carried to the next one. The
    runner builds a fresh one per message rather than leaning on the default
    factory, which exists so a context constructed in a test still has one.
    """

    static: StaticContext
    timezone: str
    clock: Reading
    source: str
    role: str = DEFAULT_ROLE
    previous: Msg | None = None
    previous_clock: Reading | None = None
    cycle: CombinedFeed | None = None
    memo: dict[str, Any] = field(default_factory=dict)

    @property
    def combined(self) -> CombinedFeed | None:
        """The cycle, but only on the message that reports for it.

        The question this answers is "am I the one who reports?", and it is not
        the question `cycle` answers. A cross-feed rule reads this, so it fires
        once per cycle rather than once per role and its occurrences are not
        emitted three times by a `-tu -vp -sa` run. A rule that only wants to
        look at another role's file reads `cycle`, and gets an answer whichever
        role it is on.

        **`None` here means "not mine to report", and `cycle is None` means "no
        cycle at all".** They are different, and a rule must not treat them
        alike: a single-file run genuinely has no other role, so its own message
        is the whole scope and a scan of it is a complete answer. Not hosting a
        cycle says nothing about what is in the feed, only about which message
        speaks for it.

        Derived rather than stored so the two cannot disagree, and so
        `RuleContext(combined=...)` is a `TypeError` rather than a way to hand a
        guest message the host's token.
        """
        if self.cycle is None or self.role != self.cycle.host_role:
            return None
        return self.cycle


def collect(result: RuleResult, *, rule_id: str, source: str) -> Iterator[Occurrence]:
    """Turn what a rule returned into occurrences the container can take.

    A generator, so a generator rule streams the whole way: nothing here holds a
    reference to an occurrence it has already yielded, and a rule with a million
    findings costs one occurrence at a time rather than a million-element list
    built before the cap can drop any of it.

    Stamps the source file onto any occurrence that did not name one itself; a
    cross-feed rule that reports against another role's file names it and keeps
    it. Both contract failures below are raised as the offending occurrence is
    reached rather than before the first one is handed on, so a container may
    already hold this rule's earlier findings when one lands. That costs nothing:
    `RuleContractError` is a bug in this repository, it is caught nowhere, and
    the run it kills has no report to contaminate.
    """
    if result is None:
        return
    for found in result:
        if not isinstance(found, Occurrence):
            raise RuleContractError(
                f"{rule_id} returned {found!r}, which is not an Occurrence; a rule returns "
                f"occurrences, an iterable of them, or None"
            )
        if found.rule_id != rule_id:
            raise RuleContractError(
                f"{rule_id} returned an occurrence for {found.rule_id}; one rule module reports "
                f"one id, which is what makes the file name the code"
            )
        yield _stamped(found, source)


def _stamped(found: Occurrence, source: str) -> Occurrence:
    if SOURCE_FILE_KEY in found.context:
        return found
    return replace(found, context={SOURCE_FILE_KEY: source, **found.context})
