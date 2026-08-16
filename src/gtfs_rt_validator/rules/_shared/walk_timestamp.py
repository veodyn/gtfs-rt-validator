"""`TimestampValidator`'s single pass, read by the eleven rules inside it.

`validation/rules/TimestampValidator.java` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2`: a header block (`:86-135`) and then
one loop over the entities (`:137-300`), emitting W001, W007, W008, E001, E012,
E017, E018, E022, E025, E048 and E050 out of shared state. `_shared/walks.py`
says why a rule may not walk on its own; this module is one of the loops that
docstring is about. Deliberately not added *to* that module, which is the
contract shared with the other validators' walks.

The stop_time_update half lives in `walk_timestamp_stops.py`, split off by the
file-size hook. The seam it landed on is a real one: everything in this module
is per entity and everything in that one is the two values E022 carries between
stops.

Four things here are parity surface rather than logic, and each is the kind of
thing a tidier port loses.

**The E048-versus-W001 fork.** `headerTimestamp` is read with no `has` test
(`:86`), so an absent header timestamp is 0 and 0 is the branch discriminator.
In that branch upstream pre-initialises `isV2orHigher = true`, calls
`GtfsUtils.isV2orHigher` inside a `try`, and on exception **leaves the flag
true** (`:88-93`), so a header whose `gtfs_realtime_version`
`Float.parseFloat` refuses logs **E048, not W001**. That is the exact opposite of
`HeaderValidator.java:60-62`, which catches the identical exception and skips
E049 entirely. Both halves are compat surface, which is why
`_shared/versions.is_v2_or_higher` raises instead of answering a tidy `False`:
`rules/upstream/e049.py` swallows the raise and this module ignores it.

**The previous-message chain is one if/else-if.** `:123-133`: equal fires E017,
less fires E018, and only a strictly greater interval is compared against 35 for
W007. Three independent tests would let E018 and W007 fire together, which
upstream cannot do. Both are gated on there being a previous message *and* its
header timestamp being non-zero.

**`currentTimeText` is computed once** (`:81`) and reused by every E050
occurrence, so a message with three future timestamps names one "now" three
times.

**Every timestamp is read through `javafmt.int64`.** All three `timestamp`
fields and both `TimeRange` bounds are `uint64`, and protobuf-java hands a rule
the signed `long`, so `headerTimestamp < previousTimestamp` and
`tripUpdateTimestamp > headerTimestamp` are signed comparisons. Measured: a
header of 18446744073709551614 after one of 1700000000 is E018 upstream and
would be W007 on the unsigned values. `interval` is narrowed too, because
Java's `long` subtraction wraps.

**On `feedMessage.equals(previousFeedMessage)`** (`:66-68`): upstream throws
`IllegalArgumentException` there and no rule here ever does. The abort is
reproducible under `--compat`, opt-in, and it lives in `runner/equal_message.py`
because mode is descriptor, registry and writer, never a branch inside a rule.
See `_previous_header_timestamp`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.rules._shared.ids import trip_id_text
from gtfs_rt_validator.rules._shared.javafmt import int64
from gtfs_rt_validator.rules._shared.times import (
    age_millis,
    is_in_future,
    is_posix,
    posix_to_clock,
)
from gtfs_rt_validator.rules._shared.timestamp_pass import (
    HEADER_PATH,
    IN_FUTURE_TOLERANCE_SECONDS,
    MAX_AGE_SECONDS,
    MINIMUM_REFRESH_INTERVAL_SECONDS,
    Pass,
    at,
)
from gtfs_rt_validator.rules._shared.timestamp_text import (
    clock_and_value,
    in_future,
    stale_header,
    to_seconds,
)
from gtfs_rt_validator.rules._shared.versions import is_v2_or_higher
from gtfs_rt_validator.rules._shared.walk_timestamp_stops import stop_time_update_events
from gtfs_rt_validator.rules._shared.walks import Event

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and the
    # sibling, and nothing under `rules/` may import that at run time.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["timestamps"]

_MILLIS_PER_SECOND = 1000


def timestamps(message: Msg, ctx: RuleContext) -> Iterator[Event]:
    """Every finding `TimestampValidator` makes, in its own emission order."""
    header = message.get("header")
    current_time_millis = ctx.clock.millis
    run = Pass(
        header_timestamp=int64(header.get("timestamp")),
        current_time_millis=current_time_millis,
        # `:81`, once for the whole message, so three E050 occurrences on one
        # message cannot name three different seconds.
        current_time_text=posix_to_clock(to_seconds(current_time_millis), ctx.timezone),
        timezone=ctx.timezone,
    )
    yield from _header_events(header, run, ctx)
    for index, entity in enumerate(message.get("entity")):
        if entity.has("trip_update"):
            yield from _trip_update_events(entity, index, run)
        if entity.has("vehicle"):
            yield from _vehicle_events(entity, index, run)
        if entity.has("alert"):
            yield from _alert_events(entity, index)


def _header_events(header: Msg, run: Pass, ctx: RuleContext) -> Iterator[Event]:
    """`:86-135`, both arms of the zero test and the previous-message chain."""
    header_timestamp = run.header_timestamp
    if header_timestamp == 0:
        yield _missing_header_timestamp(header)
        return
    if not is_posix(header_timestamp):
        yield Event("E001", "header.timestamp", at(HEADER_PATH))
    else:
        age = age_millis(run.current_time_millis, header_timestamp)
        if age > MAX_AGE_SECONDS * _MILLIS_PER_SECOND:
            yield Event("W008", stale_header(age), at(HEADER_PATH))
        if is_in_future(run.current_time_millis, header_timestamp, IN_FUTURE_TOLERANCE_SECONDS):
            yield Event(
                "E050",
                in_future(
                    "header.timestamp",
                    clock_and_value(header_timestamp, run.timezone),
                    age,
                    run.current_time_text,
                    run.current_time_millis,
                ),
                at(HEADER_PATH),
            )
    yield from _against_previous(header_timestamp, ctx)


def _missing_header_timestamp(header: Msg) -> Event:
    """`:87-100`. The `try` leaves the flag `true`, so a junk version is E048.

    `except ValueError` is narrower than Java's `catch (Exception)`, and
    deliberately: `is_v2_or_higher` raises exactly where `Float.parseFloat`
    throws, and that is a fact about the feed. Anything else out of that call
    would be a bug in this repository and must not be swallowed.
    """
    try:
        v2_or_higher = is_v2_or_higher(header)
    except ValueError:
        v2_or_higher = True
    if v2_or_higher:
        # `:96`, and the prefix really is the empty string: the whole message a
        # reader sees is the rule's suffix in the manifest.
        return Event("E048", "", at(HEADER_PATH))
    return Event("W001", HEADER_PATH, at(HEADER_PATH))


def _against_previous(header_timestamp: int, ctx: RuleContext) -> Iterator[Event]:
    """`:120-134`, one if/else-if over the interval. At most one of the three."""
    previous = _previous_header_timestamp(ctx)
    if previous is None:
        return
    # `long interval = headerTimestamp - previousTimestamp` (`:122`). Both
    # operands are already the signed narrowing; the difference is narrowed too
    # because Java's `-` wraps at 64 bits where Python's widens without bound.
    interval = int64(header_timestamp - previous)
    if header_timestamp == previous:
        yield Event("E017", f"header.timestamp of {header_timestamp}", at(HEADER_PATH))
    elif header_timestamp < previous:
        yield Event(
            "E018",
            f"header.timestamp of {header_timestamp} is less than "
            f"the header.timestamp of {previous}",
            at(HEADER_PATH),
        )
    elif interval > MINIMUM_REFRESH_INTERVAL_SECONDS:
        yield Event(
            "W007",
            f"{interval} second interval between consecutive header.timestamps",
            at(HEADER_PATH),
        )


def _previous_header_timestamp(ctx: RuleContext) -> int | None:
    """`previousFeedMessage != null && previous header timestamp != 0`, as one test.

    **No rule here reproduces the throw at `:66-68`, and by default nothing
    does.** Upstream raises `IllegalArgumentException` when the current and
    previous messages are equal, and `BatchProcessor.java:263` does not catch it,
    so the whole run dies with no `.results.json` for that file or for any file
    after it. Reproducing that trades a complete report for none, so the chain
    above simply runs and E017 fires, which is the finding the guard exists to
    keep meaningful. `runner/dedupe.py` reproduces the MD5 skip itself, so an
    ordinary byte-identical duplicate never reaches a rule at all.

    A compat run that wants the parity anyway asks for it with
    `cliargs.EQUAL_MESSAGE_ABORT_FLAG`, and `runner/equal_message.py` performs it
    from the loop rather than from here. Modern ignores the request outright.
    """
    if ctx.previous is None:
        return None
    previous = int64(ctx.previous.get("header").get("timestamp"))
    return None if previous == 0 else previous


def _trip_update_events(entity: Msg, index: int, run: Pass) -> Iterator[Event]:
    """`:138-265`: the TripUpdate's own timestamp, then its stop_time_updates."""
    trip_update = entity.get("trip_update")
    timestamp = int64(trip_update.get("timestamp"))
    trip_id = trip_id_text(entity, trip_update)
    where = at(f"entity[{index}].trip_update")
    if timestamp == 0:
        yield Event("W001", trip_id, where)
    else:
        yield from _entity_timestamp_events(
            f"{trip_id} timestamp {timestamp}", f"{trip_id} timestamp", timestamp, where, run
        )
    yield from stop_time_update_events(trip_update, trip_id, index, run)


def _vehicle_events(entity: Msg, index: int, run: Pass) -> Iterator[Event]:
    """`:268-295`.

    The identifier is `"vehicle_id " + vehiclePosition.getVehicle().getId()`,
    read with no presence guard at either step, so a VehiclePosition with no
    `vehicle` gives `"vehicle_id "` with a trailing space. It is **not**
    `GtfsUtils.getVehicleId`, which spells the field `vehicle.id` and falls back
    to the entity id; this validator builds its own text inline.
    """
    position = entity.get("vehicle")
    timestamp = int64(position.get("timestamp"))
    vehicle_id = f"vehicle_id {position.get('vehicle').get('id')}"
    where = at(f"entity[{index}].vehicle")
    if timestamp == 0:
        yield Event("W001", vehicle_id, where)
    else:
        yield from _entity_timestamp_events(
            f"{vehicle_id} timestamp {timestamp}", f"{vehicle_id} timestamp", timestamp, where, run
        )


def _entity_timestamp_events(
    prefix: str, label: str, timestamp: int, where: dict[str, object], run: Pass
) -> Iterator[Event]:
    """The E012 / E001 / E050 ladder both entity halves run, `:150-165` and `:277-292`.

    Identical line for line between the two, down to E012 being tested before
    E001 on the same timestamp so that a non-POSIX value greater than the header
    reports both. Only the identifier text differs, which is what `prefix` and
    `label` carry.
    """
    if run.header_timestamp != 0 and timestamp > run.header_timestamp:
        yield Event("E012", prefix, where)
    if not is_posix(timestamp):
        yield Event("E001", prefix, where)
    elif is_in_future(run.current_time_millis, timestamp, IN_FUTURE_TOLERANCE_SECONDS):
        yield Event(
            "E050",
            in_future(
                label,
                clock_and_value(timestamp, run.timezone),
                age_millis(run.current_time_millis, timestamp),
                run.current_time_text,
                run.current_time_millis,
            ),
            where,
        )


def _alert_events(entity: Msg, index: int) -> Iterator[Event]:
    """`checkAlertE001`, `:344-360`: start then end, per active_period, E001 only.

    Both halves are guarded by `hasStart()` / `hasEnd()`, so an absent bound is
    not reported as the POSIX-invalid 0 it would otherwise decode to.

    `TimeRange.start` and `TimeRange.end` are `uint64`, so both are read through
    the same narrowing every timestamp above is: `isPosix` is asked of the signed
    value and the prefix prints the signed value. Both bounds sit far outside the
    POSIX window either way, so the narrowing changes the text and not the
    verdict.
    """
    for position, period in enumerate(entity.get("alert").get("active_period")):
        where = at(f"entity[{index}].alert.active_period[{position}]")
        for field in ("start", "end"):
            if not period.has(field):
                continue
            bound = int64(period.get(field))
            if not is_posix(bound):
                yield Event(
                    "E001",
                    f"alert in entity {entity.get('id')} active_period.{field} {bound}",
                    where,
                )
