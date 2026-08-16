"""The loop: acquire a cycle, build each message's context, walk the registry.

`BatchProcessor.processFeeds` taken apart along the seams the rest of this
package already cut. Acquisition is `acquire.py`, the static feed and the two
feeds upstream dies on are `gate.py`, what a rule is handed and hands back is
`context.py`. What is left here is the order things happen in, and three
properties that depend on it.

**A rule's exception is never caught.** A rule that raises is a bug in this
project, not a malformed feed. Catching it would turn a broken rule into a rule
that silently finds nothing, which is indistinguishable from a clean feed in the
report. There is no `except` in this module at all.

**The duplicate basis moves only after a message is written.** `_Run.record` is
upstream's L295 and runs last, so a file skipped for any other reason never
becomes the comparison basis and a sink that raises leaves the basis where it
was. What "written" means for a run with no sink is decided there, because
upstream cannot be told not to write and so has no reading to copy. The filter
is per role: with one role that is upstream's single `prevHash` exactly, and
with several it stops two roles publishing byte-identical empty feeds from
shadowing each other, which a single global basis would do.

**A cycle is validated as a unit.** Every role that decoded is in the cycle
view, and a role that did not is absent from it rather than carried forward from
an earlier cycle. The whole view goes on **every** role's context, because
reading another role's file and reporting for the cycle are different questions;
`context.py` records why alignment is positional, and its `RuleContext.combined`
derives which single message answers the second one.

Mode does not branch here. It chose the schema and the registry in `config.py`,
it chooses the clock in `acquire.py` because the two modes genuinely read
different clocks, and it chooses the writer in the caller.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.report.occurrence import NoticeContainer
from gtfs_rt_validator.runner.acquire import Decoded, acquire
from gtfs_rt_validator.runner.clock import Reading
from gtfs_rt_validator.runner.config import RunConfig, prepare
from gtfs_rt_validator.runner.context import CombinedFeed, RuleContext, collect
from gtfs_rt_validator.runner.dedupe import DuplicateFilter
from gtfs_rt_validator.runner.equal_message import guard_equal_message
from gtfs_rt_validator.runner.mode import Mode
from gtfs_rt_validator.runner.sources import Cycle, Source, file_cycles, role_cycle, url_cycle

__all__ = [
    "MessageResult",
    "RunConfig",
    "RunResult",
    "Source",
    "file_cycles",
    "prepare",
    "role_cycle",
    "run",
    "url_cycle",
]


@dataclass(frozen=True, slots=True)
class MessageResult:
    """One validated message, handed to the sink before the basis moves.

    The compat writer's unit of work: `source.name` with `.results.json`
    appended is the file upstream writes, and `notices` holds this message's
    occurrences and no other's.
    """

    source: Source
    reading: Reading
    digest: bytes
    message: Msg
    notices: NoticeContainer


@dataclass(frozen=True, slots=True)
class RunResult:
    """What the whole run found, for the modern writer and the summary.

    It deliberately holds no decoded messages: an archive replay is thousands of
    files, and anything that needs one gets it from the sink as the run goes.
    `inputs` and `roles` are `RunSummary`'s `gtfsRealtimeInputs` and `feedRoles`.
    """

    notices: NoticeContainer
    system_errors: NoticeContainer
    messages_validated: int
    files_skipped: int
    inputs: tuple[str, ...]
    roles: dict[str, str]
    #: The ids of the registry this run walked, in walk order: `RunSummary`'s
    #: `rulesRun`. Read off `config.registry` in `_Run.result` rather than
    #: rebuilt at write time, so a run whose registry was short reports a short
    #: list instead of the number the mode is supposed to hold. No default, for
    #: the same reason: a constructor that could leave it out would let a caller
    #: publish "no rules ran" by omission.
    rules_run: tuple[str, ...]


def _message_container(mode: Mode) -> NoticeContainer:
    """The per-message container, capped for modern and uncapped for compat.

    **Upstream has no cap.** `RuleUtils.addOccurrence` (`util/RuleUtils.java:37-41`)
    is an unconditional `list.add(om)`, and `writeResults` serialises whatever
    the list holds. The caps this project carries otherwise are the *sibling's*,
    for the modern report, where a bounded file is the point.

    Applying them under compat is a silent divergence rather than a safe default:
    a feed with 100,001 TripUpdates that all lack a `vehicle_id` gives upstream
    100,001 W002 occurrences and would give this project 100,000, with nothing in
    the output saying so. A byte comparison would go red on a file too large to
    read the diff of, which is the worst way to find out.

    Mode picks a container here rather than a rule or the writer branching on it,
    which is the same shape as mode picking a descriptor and a registry.
    Unbounded memory under compat is upstream's own behaviour, not a new risk
    this introduces.
    """
    if mode is Mode.COMPAT:
        return NoticeContainer(max_total=sys.maxsize, max_per_rule=sys.maxsize)
    return NoticeContainer()


class _Run:
    """The mutable half of a run, so the loop below reads as its own shape.

    Per-role duplicate bases and per-role previous messages; both are per role
    for the reasons `context.py` gives, and both are identical to upstream's
    single global state whenever there is one role, which is every compat run.
    """

    __slots__ = ("filters", "inputs", "notices", "previous", "roles", "skipped", "validated")

    def __init__(self) -> None:
        self.notices = NoticeContainer()
        self.filters: dict[str, DuplicateFilter] = {}
        self.previous: dict[str, tuple[Msg, Reading]] = {}
        self.inputs: list[str] = []
        self.roles: dict[str, str] = {}
        self.validated = 0
        self.skipped = 0

    def filter_for(self, role: str) -> DuplicateFilter:
        return self.filters.setdefault(role, DuplicateFilter())

    def record(self, one: Decoded, result: MessageResult) -> None:
        """`BatchProcessor` L295-296, and the order is the whole point.

        Upstream writes a results file for every input it validates and cannot
        be told not to (L283-284, unconditional), so "written" has no upstream
        reading for a run with no sink. This project's answer is that a run's
        own `RunResult` is its write of record and the sink is an additional
        consumer that a per-file writer hangs off. So the findings land in the
        aggregate first and the basis moves last, and it moves for a sink-less
        run too.

        The alternative, freezing the basis whenever no sink was passed, was
        rejected: `api.validate` defaults `sink` to `None`, so the same archive
        would report a different number of validated messages depending on
        whether anything was listening. That is a disagreement about the feed,
        not about the output, and no reading of upstream produces it.
        """
        self.notices.merge(result.notices)
        self.previous[one.source.role] = (one.message, one.reading)
        self.validated += 1
        self.filter_for(one.source.role).mark_written(one.digest)

    def result(self, config: RunConfig) -> RunResult:
        return RunResult(
            notices=self.notices,
            system_errors=config.system_errors,
            messages_validated=self.validated,
            files_skipped=self.skipped,
            inputs=tuple(self.inputs),
            roles=self.roles,
            rules_run=config.registry.ids(),
        )


def run(
    config: RunConfig,
    cycles: Iterable[Cycle],
    *,
    sink: Callable[[MessageResult], None] | None = None,
) -> RunResult:
    """Validate every message of every cycle, in order.

    `sink` is called once per validated message, before the duplicate basis
    moves, which is what makes "the basis is the last file *written*" a property
    of this loop rather than a comment about it. It is optional, and
    `_Run.record` says what that means for the basis.
    """
    state = _Run()
    for cycle in cycles:
        decoded = _acquire_cycle(cycle, config, state)
        if not decoded:
            continue
        cycle_view = CombinedFeed.of(
            {one.source.role: one.message for one in decoded},
            {one.source.role: one.source.name for one in decoded},
            {one.source.role: one.reading for one in decoded},
        )
        for one in decoded:
            result = _validate(one, config, cycle_view, state.previous)
            if sink is not None:
                sink(result)
            state.record(one, result)
    return state.result(config)


def _acquire_cycle(cycle: Cycle, config: RunConfig, state: _Run) -> list[Decoded]:
    """Every source of one cycle that produced a message, in cycle order."""
    decoded: list[Decoded] = []
    for source in cycle:
        state.inputs.append(source.name)
        state.roles.setdefault(source.role, source.name)
        one = acquire(source, config, state.filter_for(source.role))
        if one is None:
            state.skipped += 1
            continue
        decoded.append(one)
    return decoded


def _validate(
    one: Decoded,
    config: RunConfig,
    cycle_view: CombinedFeed,
    previous: dict[str, tuple[Msg, Reading]],
) -> MessageResult:
    """Walk the registry in its order and collect what each rule returned.

    Registry order is output order under compat, so the walk preserves it and
    the container does not reorder what it is given.

    One context per message, so `memo` is built here, once, and every rule of
    this message shares it. That is the whole of its lifetime: the next message
    gets the next context and therefore the next dict, and nothing a rule cached
    can answer for a message it was not computed from. Written out rather than
    left to the field's default factory, because a default is a promise about
    construction and this is a promise about the loop.
    """
    was = previous.get(one.source.role)
    if config.abort_on_equal_message and was is not None:
        # `TimestampValidator.java:66-68`, hoisted ahead of the walk. Upstream
        # throws from the third of nine validators and writes nothing for the
        # file either way, so where in the walk it dies is not observable;
        # `runner/equal_message.py` records the reading and the measurement.
        guard_equal_message(one.message, was[0], one.source.name)
    ctx = RuleContext(
        static=config.static,
        timezone=config.timezone,
        clock=one.reading,
        source=one.source.name,
        role=one.source.role,
        previous=was[0] if was else None,
        previous_clock=was[1] if was else None,
        cycle=cycle_view,
        memo={},
    )
    container = _message_container(config.mode)
    for registered in config.registry:
        found = registered.check(one.message, ctx)
        container.add_all(collect(found, rule_id=registered.rule_id, source=one.source.name))
    return MessageResult(one.source, one.reading, one.digest, one.message, container)
