"""The feed shapes `CrossFeedDescriptorValidatorTest` builds, for W003 and E047.

Both rules read one index over one combined view, so both tests need the same
three things: entities whose TripDescriptor and VehicleDescriptor can each be
absent, present-but-cleared or present-and-empty; a `RuleContext` carrying a
combined view; and a static feed shaped like `testagency.zip` where the block
exemption is observable.

**Cleared versus empty is the whole point of half of upstream's cases.**
`StringUtils.isEmpty` is commons-lang3, null or zero length, so a cleared id and
an id set to `""` take the same branch of the index build. They do *not* take
the same branch of the count, because `hasTripId()` and `hasVehicleId()` test
presence only: an entity whose trip_id is `""` still increments
`tripUpdateCount`. `None` below is upstream's `clearId()` / `clearTripId()`,
which leaves the descriptor present with the field unset, and `""` is its
`setId("")`. Pass `trip=False` or `vehicle=False` for the descriptor being
absent altogether, which upstream's own tests never build but the guards care
about. `trip_update(trip=False)` is the one combination that cannot be decoded:
`TripUpdate.trip` is `required` in both schemas, so a message without it fails
`isInitialized` and the file is skipped before any rule sees it.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import replace
from pathlib import Path

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.runner.clock import Reading
from gtfs_rt_validator.runner.context import (
    DEFAULT_ROLE,
    ROLE_TRIP_UPDATES,
    ROLE_VEHICLE_POSITIONS,
    CombinedFeed,
    RuleContext,
)
from gtfsfixtures import minimal_tables
from rulefixtures import READING, context, message

__all__ = [
    "ROLE_TRIP_UPDATES",
    "ROLE_VEHICLE_POSITIONS",
    "TESTAGENCY_TRIPS",
    "combined",
    "combined_of",
    "combined_roles",
    "testagency_tables",
    "trip_update",
    "vehicle_position",
]

#: The rows of `testagency.zip`'s `trips.txt` that these two rules can see, with
#: its own block_ids. Trips `6.1` and `7.1` share `block.1`, which is the whole
#: of E047's exemption, and `44`, `45`, `100` and `101` are deliberately absent
#: so that a lookup for them misses exactly as it does against the real feed.
TESTAGENCY_TRIPS: tuple[tuple[str, str], ...] = (
    ("1.1", ""),
    ("1.2", ""),
    ("1.3", ""),
    ("6.1", "block.1"),
    ("7.1", "block.1"),
    ("6.2", "block.2"),
    ("7.2", "block.2"),
)


def testagency_tables() -> dict[str, list[dict[str, str]]]:
    """`minimal_tables()` with `TESTAGENCY_TRIPS` added to `trips.txt`."""
    tables: dict[str, list[dict[str, str]]] = minimal_tables()
    tables["trips.txt"] += [
        {"route_id": "R1", "service_id": "SVC1", "trip_id": trip_id, "block_id": block_id}
        for trip_id, block_id in TESTAGENCY_TRIPS
    ]
    return tables


def _descriptors(
    trip_id: str | None,
    vehicle_id: str | None,
    *,
    trip: bool,
    vehicle: bool,
) -> dict[str, object]:
    built: dict[str, object] = {}
    if trip:
        built["trip"] = {} if trip_id is None else {"trip_id": trip_id}
    if vehicle:
        built["vehicle"] = {} if vehicle_id is None else {"id": vehicle_id}
    return built


def trip_update(
    trip_id: str | None = None,
    vehicle_id: str | None = None,
    *,
    trip: bool = True,
    vehicle: bool = True,
) -> dict[str, object]:
    """A TripUpdate carrying only the two descriptors this validator reads."""
    return _descriptors(trip_id, vehicle_id, trip=trip, vehicle=vehicle)


def vehicle_position(
    vehicle_id: str | None = None,
    trip_id: str | None = None,
    *,
    trip: bool = True,
    vehicle: bool = True,
) -> dict[str, object]:
    """A VehiclePosition, argument order matching how upstream reads one."""
    return _descriptors(trip_id, vehicle_id, trip=trip, vehicle=vehicle)


def combined(
    tmp_path: Path,
    *entities: Mapping[str, object],
    tables: MutableMapping[str, list[dict[str, str]]] | None = None,
    source: str = "rt.pb",
) -> tuple[Msg, RuleContext]:
    """One compat cycle: a single message that is its own combined view.

    That is what `runner/run.py` builds for `--compat`, where there is one
    unnamed role, and it is the shape upstream's own tests pass as
    `combinedFeedMessage`.
    """
    built = message(*entities)
    return built, combined_of(tmp_path, built, tables=tables, source=source)


def combined_of(
    tmp_path: Path,
    built: Msg,
    *,
    tables: MutableMapping[str, list[dict[str, str]]] | None = None,
    source: str = "rt.pb",
) -> RuleContext:
    """`combined`, for a message that has already been decoded.

    For the committed jar corpus, whose bytes are the point and must not be
    rebuilt from a dict here.
    """
    view = CombinedFeed.of({DEFAULT_ROLE: built}, {DEFAULT_ROLE: source}, {DEFAULT_ROLE: READING})
    return replace(
        context(tmp_path, tables if tables is not None else testagency_tables(), source=source),
        cycle=view,
    )


def combined_roles(
    tmp_path: Path,
    roles: Mapping[str, list[Mapping[str, object]]],
    *,
    tables: MutableMapping[str, list[dict[str, str]]] | None = None,
    clock: Reading = READING,
) -> tuple[Msg, RuleContext]:
    """A modern cycle: one message per named role, all in one combined view.

    Upstream has no counterpart, because its cross-feed rules only ever see a
    single file; `runner/context.py` settles what a cycle means here. The host
    role's message is returned, since that is the one the runner hands the rule.
    """
    messages = {role: message(*entities) for role, entities in roles.items()}
    view = CombinedFeed.of(
        messages,
        {role: f"{role}.pb" for role in messages},
        dict.fromkeys(messages, clock),
    )
    host = view.host_role
    return messages[host], replace(
        context(
            tmp_path, tables if tables is not None else testagency_tables(), source=f"{host}.pb"
        ),
        role=host,
        cycle=view,
    )
