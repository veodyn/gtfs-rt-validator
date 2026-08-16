"""Current-schema feeds and a bare context, for the spec tier's shared walks.

`rulefixtures` builds under `schema_2015`, because every rule it serves is an
upstream rule the jar decodes that way. Almost nothing the spec tier reads
exists there: `Shape`, `Stop`, `TripModifications`, `TripProperties` and
`TranslatedImage` are all post-2015, so a fixture for one of them built through
`rulefixtures` would encode as nothing at all and every test over it would pass
by being empty. So these go through the real encoder and decoder under
`schema_current`, which is the schema modern mode decodes with.

`context` here is deliberately not `rulefixtures.context`. These walks read
`ctx.memo` and, in one case, `ctx.static`; building a real archive on disk per
test would make the sibling loader a dependency of a memoisation assertion.

`feed_context` is the one for a rule that does read the static feed, and it is
not `rulefixtures.context` either, for the reason that module's own docstring
names: it loads through onebusaway's reader, because every rule it serves is a
port of a jar rule and the jar's static feed comes out of `GtfsReader`. A spec
rule only ever runs in modern mode, where `runner/gate.py:prepare_static` picks
the sibling's strict typed reader instead, so that is the loader a spec rule's
test has to see.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping
from pathlib import Path

from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from gtfs_rt_validator.runner.context import CombinedFeed, RuleContext
from gtfs_rt_validator.static.adapter import RawTables, load_static
from gtfs_rt_validator.static.context import StaticContext
from gtfsfixtures import build_feed, minimal_tables
from rulefixtures import minimal

__all__ = [
    "ENTITY_ID",
    "READING",
    "context",
    "counted",
    "cycle_of",
    "entity",
    "feed_context",
    "message",
    "minimal",
    "occurrences",
    "prefixes",
    "sharing",
    "static_context",
]

#: `FeedMessageTest.ENTITY_ID`, kept from `rulefixtures` so a path or a prefix
#: reads the same across both tiers' tests.
ENTITY_ID = "TEST_ENTITY"

#: A fixed clock, so nothing here depends on when the suite runs.
READING = Reading(1_700_000_000_000, ClockSource.FIXED)


def message(*entities: Mapping[str, object], version: str = "2.0", **header: object) -> Msg:
    """A decoded `FeedMessage` under the current schema, one entity per mapping."""
    head: dict[str, object] = {"gtfs_realtime_version": version, **header}
    return decode(encode({"header": head, "entity": list(entities)}, SCHEMA), SCHEMA)


def entity(entity_id: str = ENTITY_ID, **payloads: object) -> dict[str, object]:
    """One `FeedEntity` carrying whichever payloads are named.

    Keyword rather than positional, unlike `rulefixtures.entity`: the current
    `FeedEntity` has six payload fields rather than three, and naming them at
    the call site is what keeps a `trip_modifications` fixture readable.
    """
    return {"id": entity_id, **payloads}


def context(**overrides: object) -> RuleContext:
    """A context over a static feed with nothing in it, for its `memo` alone."""
    built: dict[str, object] = {
        "static": StaticContext.build(RawTables([], [], [], [], [], [], [])),
        "timezone": "America/New_York",
        "clock": READING,
        "source": "rt.pb",
    }
    built.update(overrides)
    return RuleContext(**built)  # type: ignore[arg-type]


def cycle_of(messages: Mapping[str, Msg], *, clock: Reading = READING) -> CombinedFeed:
    """One cycle, one message per named role, the way `runner/run.py` builds one.

    Four test modules need one, and a cycle built by hand is exactly where the
    host role and the file names can quietly stop matching what the runner does.
    Which role a *context* over this cycle belongs to is that context's `role`,
    and it no longer has to be the host: `ctx.cycle` reaches every role and only
    `ctx.combined`, the token that says "you report for this cycle", is derived
    from the two agreeing.
    """
    return CombinedFeed.of(
        messages,
        {role: f"{role}.pb" for role in messages},
        dict.fromkeys(messages, clock),
    )


def counted(build):
    """`build`, wrapped so a test can see how many times its body actually ran.

    The wrapper carries the wrapped function's `__module__` and `__qualname__`,
    because those are what the memo key is built from: a wrapper with its own
    name would be memoised under its own key and would prove nothing about the
    function under test.
    """
    runs: list[object] = []

    def wrapper(message_, ctx):
        runs.append(message_)
        return build(message_, ctx)

    wrapper.__module__ = build.__module__
    wrapper.__qualname__ = build.__qualname__
    return wrapper, runs


def sharing(monkeypatch, module, name: str) -> list[object]:
    """Count how many times `module.name` actually runs, for the rest of a test.

    The six shared walks all memoise a module-level build, and the claim each
    one has to make is that two rules reading it in one context run that build
    once. Identity of the returned structure would be weaker: a build could
    return the same object twice for reasons that have nothing to do with the
    memo. This counts the body.
    """
    wrapper, runs = counted(getattr(module, name))
    monkeypatch.setattr(module, name, wrapper)
    return runs


def static_context(
    tmp_path: Path,
    tables: MutableMapping[str, list[dict[str, str]]] | None = None,
    *,
    ignore_shapes: bool = False,
) -> StaticContext:
    """A `StaticContext` built the way a *modern* run builds one.

    Through a real archive on disk and the sibling's strict reader, which is
    what `runner/gate.py:prepare_static` picks for `Mode.MODERN`.

    **`ignore_shapes` goes to both halves, because a real run puts it in both.**
    `adapter._requested` drops `shapes.txt` from the tables it asks for, so
    `RawTables.shapes` is empty before `StaticContext.build` ever sees it, and
    the gate then shuts on an empty list for a second reason. Passing the flag
    only to `build` modelled the gate and not the loader, which was invisible
    while `shape_points` was the only shape structure and stopped being
    invisible when `shape_ids` arrived: measured on this fixture, a feed built
    `ignore_shapes=True` still carried `SH1` in `shape_ids`. `rulefixtures`
    and `tripmodfixtures` both already do it this way.
    """
    return StaticContext.build(
        load_static(
            build_feed(tmp_path, tables if tables is not None else minimal_tables()),
            ignore_shapes=ignore_shapes,
        ),
        ignore_shapes=ignore_shapes,
    )


def feed_context(
    tmp_path: Path,
    tables: MutableMapping[str, list[dict[str, str]]] | None = None,
    *,
    ignore_shapes: bool = False,
    **overrides: object,
) -> RuleContext:
    """One rule context over a real static feed, for a rule that reads one."""
    built: dict[str, object] = {
        "static": static_context(tmp_path, tables, ignore_shapes=ignore_shapes),
        "timezone": "America/New_York",
        "clock": READING,
        "source": "rt.pb",
    }
    built.update(overrides)
    return RuleContext(**built)  # type: ignore[arg-type]


def occurrences(result: Iterable[Occurrence] | None) -> list[Occurrence]:
    """What a rule returned, as a list. `None` is a rule that returned early."""
    return [] if result is None else list(result)


def prefixes(result: Iterable[Occurrence] | None) -> list[str]:
    """Just the prefixes, in order, which is what most assertions are about."""
    return [found.prefix for found in occurrences(result)]
