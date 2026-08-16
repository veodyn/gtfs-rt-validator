"""The static feed, loaded once, and the three feeds upstream produces nothing for.

The first two are measured behaviours of upstream rather than reasoned ones, and
they have the same shape: upstream produces **no `.results.json` for any
file in the archive**, so a compat run that emitted anything at all on either
feed would be a parity failure on every file at once, not a small one. Compat
therefore refuses to run. Modern loads the feed and carries on, because the
sibling loads it cleanly and a realtime run that refused would be throwing away
work over a static-feed problem the sibling already reports on.

**1. The agency-less feed.** `BatchProcessor` reads the first agency's timezone
and hands it to `TimeZone.getTimeZone`, which throws an uncaught
`NullPointerException` on `null` (measured, JDK 17); `Main` catches only
`IOException | NoSuchAlgorithmException`, so the jar dies with a stack trace
before validating anything. Compat raises `CompatAbort` here, before the first
file is read, which reproduces the silence rather than the stack trace.

Modern substitutes UTC and records the substitution. The timezone reaches output
through nine `TimestampUtils.posixToClock` calls and nothing else: it formats
message text and decides no pass or fail, so it is not a reason to refuse a feed.
Upstream itself returns GMT for a timezone string it does not recognise, and
only `null` kills it, so UTC is the fallback upstream would have used had the
value merely been wrong instead of missing.

**2. The dangling foreign key.** onebusaway's `GtfsReader` aborts the entire read
on an unresolvable reference (`EntityReferenceNotFoundException`), while the
sibling at `35fac77` loads the row and reports nothing, which is why
`StaticContext.trip_stop_times` can hold a trip absent from `trips.txt`
(`tests/test_static_context.py` pins both halves). Compat pre-checks and refuses,
for the same reason as above. Accepting the permissive divergence would mean
emitting a full set of results for an archive the jar produces nothing for, and
"never weaken a differential comparison to make it pass" cuts the other way: the
red diff is the deliverable, and here the honest diff is "upstream ran nothing".

The pre-check covers the four references onebusaway resolves as entity fields
across the seven tables a realtime run reads, plus `routes.agency_id` when the
cell is populated. An *empty* `agency_id` is deliberately not checked: whether
onebusaway resolves an omitted one on a single-agency feed is not measured, and
a pre-check that guessed would refuse a feed the jar validates, which is worse
than the permissive direction because it produces no output to diff at all.

**3. The frequency period upstream spins on.** A `frequencies.txt` row with
`exact_times = 1` whose `headway_secs` cannot advance
`FrequencyTypeOneValidator`'s loop hangs the jar on the main thread, measured
with `jstack` at 12.1 seconds of CPU in 12.2 seconds of wall clock and no
results file for that feed or any after it. It is a live spin, so no timeout
ends it, and an infinite loop is not something to reproduce; for a feed that
reaches the loop the *observable* outcome is silence, and `CompatAbort` is how
this project produces silence. Modern records it and carries on, and its E019
walks such a period once instead of forever (`rules/_shared/frequencies.py`).

Unlike the first two, this one is an over-approximation and is meant to be:
upstream reaches the loop only for a trip some realtime TripUpdate or
VehiclePosition names (`FrequencyTypeOneValidator.java:53` and `:94`), so an
archive carrying such a row that no feed refers to is validated to completion by
the jar and would be refused here. Narrowing it would mean deciding per message,
and by then the decision is not the gate's to take: a rule may not know which
mode it is in, and the system-error container modern would record into never
reaches one.

The guard used to be measured *unreachable*, because both modes read the static
feed through the canonical static schema, which types `headway_secs` as a
required positive integer: a row carrying `0`, a negative or a blank failed to
type, `frequencies.txt` came back `dependency_failed`, and the archive raised
`StaticLoadError` before either mode was consulted. Compat reads the feed as
onebusaway does now (`Frequency.headwaySecs` is a plain `int`), so the archive
loads and the guard below is what stops the run.

**What is left over-approximates and still loses output.** Measured on a repacked
archive whose one exact_times = 1 row carries `headway_secs = 0`. Against a
realtime feed naming some other trip, the jar exits 0 and writes a full results
file, where compat refuses on the archive alone and writes nothing.
`tests/test_jar_frequency_divergence.py` runs both sides against the pinned jar
and pins that red diff rather than arguing it away. Modern still refuses at the
loader, which is the strict reader's call to make.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.report.occurrence import NoticeContainer
from gtfs_rt_validator.report.system_errors import SystemErrorCode, system_error
from gtfs_rt_validator.rules._shared.frequencies import cannot_advance, headway_secs
from gtfs_rt_validator.runner.mode import Mode
from gtfs_rt_validator.static._tables import split_frequencies
from gtfs_rt_validator.static.adapter import (
    RawTables,
    load_static,
    load_static_as_onebusaway,
)
from gtfs_rt_validator.static.context import StaticContext

__all__ = [
    "FALLBACK_TIMEZONE",
    "CompatAbort",
    "dangling_reference",
    "prepare_static",
    "spinning_frequency",
]

#: What modern uses when the feed declares no timezone. See above: it is what
#: upstream returns for a timezone it cannot recognise.
FALLBACK_TIMEZONE = "UTC"

#: table, column, and the table whose key column it must resolve against.
#: `trips.route_id -> Route`, `frequencies.trip_id -> Trip`,
#: `routes.agency_id -> Agency`: three of the five entity references onebusaway
#: declares among the seven tables loaded here.
#:
#: The other two are `_STOP_TIME_REFERENCES`, checked ahead of these because
#: that is where they sat when all five were scanned here. `stop_times.txt` is
#: never materialised, so nothing can scan it twice: `_stoptimes.read_stop_times`
#: answers for it while reading it and keeps the one offending row per reference.
_REFERENCES = (
    ("trips.txt", "route_id", "routes.txt", "route_id"),
    ("frequencies.txt", "trip_id", "trips.txt", "trip_id"),
    ("routes.txt", "agency_id", "agency.txt", "agency_id"),
)

#: column, target table, and the attribute holding that reference's first
#: offending row. Order is the precedence, and it is unchanged.
_STOP_TIME_REFERENCES = (
    ("trip_id", "trips.txt", "first_unknown_trip_id"),
    ("stop_id", "stops.txt", "first_unknown_stop_id"),
)


class CompatAbort(RuntimeError):
    """Upstream's run would have died here, so this one produces nothing.

    Not a notice and not a system error: it is the absence of *all* output that
    matches the jar, and a run that recorded something would already differ.

    The three raised from this module are raised before the first realtime file
    is read, so no writer can have run. `equal_message.EqualMessageAbort`
    subclasses this one and is raised mid-run instead, which is where upstream
    dies for it; the files already written stay written there too.
    """


def _rows(raw: RawTables, table: str) -> list[dict[str, object]]:
    return getattr(raw, table.removesuffix(".txt"))


def _unresolved(table: str, row_number: object, column: str, value: object, target: str) -> str:
    """The message, in one place, because two callers now render it."""
    return (
        f"{table} row {row_number} names {column} {value!r}, which is not in "
        f"{target}; onebusaway's reader aborts the whole read on that reference and "
        f"upstream then writes no results for any file"
    )


def dangling_reference(raw: RawTables) -> str | None:
    """The first reference onebusaway's reader would not have resolved, or None.

    Returns the message rather than raising, so the caller decides what it means
    and this function stays usable as a plain question.

    The two `stop_times.txt` references come first, exactly where they were when
    all five were scanned here. They are read off the table rather than scanned
    for, because that table is never held; see `_REFERENCES`.
    """
    for column, target, attribute in _STOP_TIME_REFERENCES:
        offending = getattr(raw.stop_times, attribute)
        if offending is not None:
            row_number, value = offending
            return _unresolved("stop_times.txt", row_number, column, value, target)
    for table, column, target, key in _REFERENCES:
        known = {row[key] for row in _rows(raw, target) if row.get(key) is not None}
        for row in _rows(raw, table):
            value = row.get(column)
            if value is None or value in known:
                continue
            return _unresolved(table, row.get("_row_number"), column, value, target)
    return None


def spinning_frequency(raw: RawTables) -> str | None:
    """The first exact_times = 1 period `FrequencyTypeOneValidator` would spin on.

    Returns the message rather than raising, like `dangling_reference` above, so
    the caller decides what it means. The selection is `split_frequencies`, the
    same one `StaticContext` builds `exact_times_one_trips` with, so a row this
    refuses is a row E019 would have walked and not some other reading of
    `exact_times`.

    "Would spin on" is the over-approximation the module docstring names: the
    row is a necessary condition and not a sufficient one, since upstream only
    enters the loop for a trip a realtime message names. The text says so, so
    nobody reading a refusal takes it for a measurement of that run.
    """
    _zero, one = split_frequencies(raw.frequencies)
    for trip_id, rows in one.items():
        for row in rows:
            if cannot_advance(row):
                return (
                    f"frequencies.txt row {row.get('_row_number')} gives trip {trip_id!r} a "
                    f"headway_secs of {headway_secs(row)} on an exact_times = 1 period; "
                    f"FrequencyTypeOneValidator advances its loop by headway_secs, so upstream "
                    f"spins there forever on any message naming that trip and writes no results "
                    f"for any file it has not already written. A run whose messages all name "
                    f"other trips is one the jar completes and this refuses"
                )
    return None


def prepare_static(
    path: Path,
    *,
    mode: Mode,
    system_errors: NoticeContainer,
    ignore_shapes: bool = False,
) -> tuple[StaticContext, str]:
    """Load the archive once and answer the questions above.

    Returns the context and the timezone every rule reads, which is a string
    rather than `StaticContext.timezone`'s `str | None`: the decision has been
    taken by the time a rule runs.

    **Mode picks the reader, and this is the only place it does.** Compat reads
    the archive as onebusaway's `GtfsReader` would, because that is the loader
    `BatchProcessor` uses and reproducing the jar means reproducing it. Modern
    reads it through the sibling's strict, typed path, because a modern run has
    no reason to inherit a lenient reader's blind spots. `static/adapter.py`
    carries the argument in full. No rule can tell which ran.
    """
    read = load_static_as_onebusaway if mode is Mode.COMPAT else load_static
    raw = read(path, ignore_shapes=ignore_shapes)
    if mode is Mode.COMPAT:
        _refuse_where_upstream_would_not_have_run(path, raw)
    else:
        _record_what_compat_refuses(path, raw, system_errors)
    static = StaticContext.build(raw, ignore_shapes=ignore_shapes)
    if static.timezone is not None:
        return static, static.timezone
    if mode is Mode.MODERN:
        system_error(
            system_errors,
            SystemErrorCode.MISSING_REQUIRED_FIELD,
            str(path),
            _NoTimezone(
                "agency.txt declares no row, so the feed declares no timezone; "
                f"using {FALLBACK_TIMEZONE}"
            ),
        )
    return static, FALLBACK_TIMEZONE


def _refuse_where_upstream_would_not_have_run(path: Path, raw: RawTables) -> None:
    """The three refusals, in the order upstream would have hit them.

    The reader dies before it finishes loading, `TimeZone.getTimeZone(null)`
    throws before the first file is opened, and the frequency loop spins in the
    middle of validating one. Only the order of the messages depends on it, but
    a reader comparing this against a jar log should find them in that order.
    """
    if not raw.agency:
        raise CompatAbort(
            f"{path} has no agency row, and upstream calls TimeZone.getTimeZone(null) on it, "
            f"which throws an uncaught NullPointerException and writes no results for any file"
        )
    dangling = dangling_reference(raw)
    if dangling is not None:
        raise CompatAbort(f"{path}: {dangling}")
    spinning = spinning_frequency(raw)
    if spinning is not None:
        raise CompatAbort(f"{path}: {spinning}")


def _record_what_compat_refuses(path: Path, raw: RawTables, system_errors: NoticeContainer) -> None:
    """Modern's half of the third refusal: record it and carry on.

    Only the third. The first two are load failures the sibling does not have,
    and modern's answer to them is to run anyway with no note, which the module
    docstring argues for. This one is different in kind: the archive is fine and
    the *jar* is broken on it for any message naming that trip, so a modern run
    has something to say about the feed and still no reason to refuse it.

    `MISSING_REQUIRED_FIELD` is the closest of the four codes
    `report/system_errors.SystemErrorCode` defines. It
    is not exact, since `headway_secs` is present and merely zero, and a fifth
    code is not this module's to invent.
    """
    spinning = spinning_frequency(raw)
    if spinning is not None:
        system_error(
            system_errors, SystemErrorCode.MISSING_REQUIRED_FIELD, str(path), _Spinning(spinning)
        )


class _NoTimezone(Exception):
    """The exception the sibling's system-error shape wants where this project
    has a condition rather than a caught error. Never raised, only recorded: its
    class name is what lands in `system_errors.json` beside the message."""


class _Spinning(Exception):
    """The same, for the frequency period upstream never comes back from."""
