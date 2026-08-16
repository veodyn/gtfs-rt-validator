"""Builders for the hand-crafted `.pb` corpora, shared by both of them.

`tools/goldenfeeds.py` builds the eight feeds that pin the *output contract*;
`tools/conformancefeeds.py` builds the tier 1 conformance corpus that aims at
rule coverage. They want the same handful of nested dicts, so those live here
rather than being written twice with two sets of defaults that could drift.

Everything is encoded against the **2015 schema**, the view upstream compiles
against, through `proto/encode.py`. Fields absent from the dict are absent on
the wire, which is the whole point: most of the rules below fire on a field
nobody set.

Two conventions worth knowing before adding a feed:

- `trip()` writes `trip_id` only when it is given, because a `TripDescriptor`
  with no `trip_id` is exactly what W006 fires on, and
- `TripUpdate.trip` is `required` in both schemas, so a TripUpdate without one
  does not decode at all and would be a `06-truncated.pb`, not a finding.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA

__all__ = [
    "SCHEMA",
    "Feed",
    "alert",
    "encode",
    "entity",
    "header",
    "message",
    "pb",
    "position",
    "stu",
    "trip",
    "trip_update",
    "vehicle_position",
]


@dataclass(frozen=True)
class Feed:
    """One crafted input, and what the jar is expected to do with it.

    `skip` separates the two reasons upstream writes no results, which look
    identical from the output directory and are not the same claim.
    `"duplicate"` means the previous file's MD5 matched, so these bytes were
    never decoded and our decoder must still read them; `"decode"` means
    protobuf-java refused them, which is what `DecodeError` reproduces.
    """

    name: str
    why: str
    blob: bytes
    skip: str | None = None


def pb(value: Mapping[str, object]) -> bytes:
    """A `FeedMessage` dict as 2015-schema wire bytes."""
    return encode(dict(value), SCHEMA)


def header(
    timestamp: int | None, *, version: str = "1.0", incrementality: int | None = 0
) -> dict[str, object]:
    """A `FeedHeader`. `None` for either optional field leaves it off the wire.

    An absent `timestamp` is E048 and an absent `incrementality` is E049, but
    only from `gtfs_realtime_version` 2.0 upward: `HeaderValidator` reads the
    version first and both checks are inside that branch.
    """
    built: dict[str, object] = {"gtfs_realtime_version": version}
    if incrementality is not None:
        built["incrementality"] = incrementality
    if timestamp is not None:
        built["timestamp"] = timestamp
    return built


def message(head: Mapping[str, object], *entities: Mapping[str, object]) -> dict[str, object]:
    return {"header": dict(head), "entity": [dict(each) for each in entities]}


def entity(entity_id: str, *, is_deleted: bool | None = None, **payload) -> dict[str, object]:
    """One `FeedEntity` carrying exactly one of trip_update, vehicle or alert."""
    built: dict[str, object] = {"id": entity_id}
    if is_deleted is not None:
        built["is_deleted"] = is_deleted
    built.update(payload)
    return built


def trip(
    trip_id: str | None = None,
    *,
    route_id: str | None = None,
    direction_id: int | None = None,
    start_time: str | None = None,
    start_date: str | None = None,
    schedule_relationship: int | None = None,
) -> dict[str, object]:
    """A `TripDescriptor`. Every field is absent unless named."""
    built: dict[str, object] = {}
    for name, value in (
        ("trip_id", trip_id),
        ("route_id", route_id),
        ("direction_id", direction_id),
        ("start_time", start_time),
        ("start_date", start_date),
        ("schedule_relationship", schedule_relationship),
    ):
        if value is not None:
            built[name] = value
    return built


def stu(
    stop_sequence: int | None = None,
    stop_id: str | None = None,
    *,
    arrival: Mapping[str, object] | None = None,
    departure: Mapping[str, object] | None = None,
    schedule_relationship: int | None = None,
) -> dict[str, object]:
    """One `stop_time_update`.

    `arrival={}` is upstream's `StopTimeEvent.newBuilder().build()`: the field is
    present and carries neither a delay nor a time, which is what E044 fires on.
    `arrival=None` is no arrival at all, which is what E043 fires on.
    """
    built: dict[str, object] = {}
    if stop_sequence is not None:
        built["stop_sequence"] = stop_sequence
    if stop_id is not None:
        built["stop_id"] = stop_id
    if arrival is not None:
        built["arrival"] = dict(arrival)
    if departure is not None:
        built["departure"] = dict(departure)
    if schedule_relationship is not None:
        built["schedule_relationship"] = schedule_relationship
    return built


def trip_update(
    descriptor: Mapping[str, object],
    *updates: Mapping[str, object],
    vehicle_id: str | None = None,
    timestamp: int | None = None,
    delay: int | None = None,
) -> dict[str, object]:
    built: dict[str, object] = {"trip": dict(descriptor)}
    if vehicle_id is not None:
        built["vehicle"] = {"id": vehicle_id}
    if timestamp is not None:
        built["timestamp"] = timestamp
    if delay is not None:
        built["delay"] = delay
    if updates:
        built["stop_time_update"] = [dict(update) for update in updates]
    return built


def position(
    latitude: float,
    longitude: float,
    *,
    bearing: float | None = None,
    speed: float | None = None,
    odometer: float | None = None,
) -> dict[str, object]:
    """A `Position`. Both coordinates are `required`, the rest optional."""
    built: dict[str, object] = {"latitude": latitude, "longitude": longitude}
    if bearing is not None:
        built["bearing"] = bearing
    if speed is not None:
        built["speed"] = speed
    if odometer is not None:
        built["odometer"] = odometer
    return built


def vehicle_position(
    descriptor: Mapping[str, object] | None = None,
    *,
    vehicle_id: str | None = None,
    at: Mapping[str, object] | None = None,
    timestamp: int | None = None,
    stop_id: str | None = None,
    current_stop_sequence: int | None = None,
) -> dict[str, object]:
    built: dict[str, object] = {}
    if descriptor is not None:
        built["trip"] = dict(descriptor)
    if vehicle_id is not None:
        built["vehicle"] = {"id": vehicle_id}
    if at is not None:
        built["position"] = dict(at)
    if timestamp is not None:
        built["timestamp"] = timestamp
    if stop_id is not None:
        built["stop_id"] = stop_id
    if current_stop_sequence is not None:
        built["current_stop_sequence"] = current_stop_sequence
    return built


def alert(*informed: Mapping[str, object]) -> dict[str, object]:
    """An `Alert` over these `informed_entity` selectors.

    No selectors at all is E032; a selector that names nothing is E033. Both are
    states a builder with required arguments could not express, which is why
    this takes none.
    """
    return {"informed_entity": [dict(each) for each in informed]} if informed else {}
