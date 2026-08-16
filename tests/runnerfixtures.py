"""Feeds, rules and registries small enough to state inline, for the runner tests.

A module of plain functions rather than a `conftest.py`, matching
`gtfsfixtures.py`: every runner test wants a *different* registry, so a fixture
would be a factory-fixture and the indirection would buy nothing.

The realtime bytes go through `proto/encode.py`, which is what it exists for.
The static feed goes through the real sibling loader, because the gate's two
decisions are about what that loader accepts and a hand-built `StaticContext`
would assert nothing about them.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.rules.registry import RegisteredRule, Registry
from gtfs_rt_validator.runner.mode import Mode
from gtfs_rt_validator.runner.run import RunConfig, prepare
from gtfsfixtures import build_feed, minimal_tables

AGENCY_COLUMNS = ["agency_id", "agency_name", "agency_url", "agency_timezone"]

#: Where a fake rule pretends to live. `tier_of` reads the dotted name, so a
#: rule that claims another tier would have to cite a source.
UPSTREAM = "gtfs_rt_validator.rules.upstream"

#: The header timestamp a "clean feed" carries, and the instant a caller who
#: wants a clean run has to pin its clock to. 2023-11-14T22:13:20Z, which is
#: `rulefixtures.READING` expressed in seconds.
#:
#: A fixed value rather than the wall clock, because several callers assert that
#: two `feed()` calls produce identical bytes and a clock read twice does not.
#: That is what makes pinning the run's clock the caller's job: `TimestampValidator`
#: gives W008 65 seconds and E050 60 either side of "now", so no fixed timestamp
#: can be clean against an unpinned one. `--at` and `api.Request.at` exist for
#: exactly this, and a clean run that depends on when the suite is executed was
#: never a run worth asserting on.
CLEAN_HEADER_TIMESTAMP = 1_700_000_000

#: What every entity `feed()` builds carries, so that "exactly one payload" is
#: true of it. `R1` is `gtfsfixtures.minimal_tables`'s one route, which is what
#: `static_feed` below builds, so E032 and E035 have nothing to say either.
PAYLOAD: dict[str, object] = {"alert": {"informed_entity": [{"route_id": "R1"}]}}

#: The same instant, as `--at` spells it and as `api.Request.at` takes it.
CLEAN_CLOCK_TEXT = "2023-11-14T22:13:20Z"
CLEAN_CLOCK = dt.datetime.fromtimestamp(CLEAN_HEADER_TIMESTAMP, tz=dt.UTC)


def feed(
    *entity_ids: str, version: str = "2.0", timestamp: int | None = CLEAN_HEADER_TIMESTAMP
) -> bytes:
    """A valid `FeedMessage` under the 2015 schema, one entity per id.

    `incrementality` is set because several callers use this to mean "a clean
    feed" and assert that a run over it reports nothing. It was absent while no
    rule existed, which made "clean" vacuously true; E049 fires on exactly this
    shape, a version of 2.0 or higher with no incrementality, so the day that
    rule landed the fixture stopped being clean. The fixture was stale, not the
    rule. `FULL_DATASET` is the protobuf default and so is what an absent field
    already meant to every reader; stating it changes no other rule's view of
    this feed, and E039, the only rule that keys on FULL_DATASET, needs an
    entity carrying `is_deleted` and none here does.

    `timestamp` is populated for the same reason and by the same argument.
    `TimestampValidator` landed after that paragraph was written, and a v2.0
    header with no timestamp is E048's exact shape, so "clean" went stale a
    second time. Passing `timestamp=None` gets the old bytes back for a caller
    that wants that shape.

    `PAYLOAD` is on every entity for the third turn of the same wheel. An entity
    carrying no payload at all is exactly what proto `:106` forbids and what
    S001 reports, so the day the spec tier's first cohort landed the fixture
    went stale again. The payload is the smallest one the whole modern registry
    is silent about, measured rather than guessed: a bare `alert` naming a route
    the static fixture has. A TripUpdate would have brought E041 and W009 and a
    VehiclePosition W002, none of which is anything this fixture is about.
    """
    header: dict[str, object] = {"gtfs_realtime_version": version, "incrementality": 0}
    if timestamp is not None:
        header["timestamp"] = timestamp
    entities = [{"id": each, **PAYLOAD} for each in entity_ids]
    return encode({"header": header, "entity": entities}, V2015)


def written_feed(directory: Path, name: str, *entity_ids: str) -> Path:
    path = directory / name
    path.write_bytes(feed(*entity_ids))
    return path


def a_rule(rule_id: str, check: Callable[..., object]) -> RegisteredRule:
    """One registered rule, built directly rather than through the decorator.

    The decorator writes into the process-wide `_REGISTERED`, which would leak
    a test's fake rule into every later `Registry.modern()`.
    """
    return RegisteredRule(rule_id, "upstream", f"{UPSTREAM}.{rule_id.lower()}", check, None)


def registry_of(*rules: RegisteredRule) -> Registry:
    return Registry(tuple(rules))


def per_entity(rule_id: str) -> RegisteredRule:
    """A rule that fires once per entity, returning a list."""

    def check(message: object, ctx: object) -> list[Occurrence]:
        return [Occurrence(rule_id, f"entity {each.get('id')}") for each in message.get("entity")]

    return a_rule(rule_id, check)


def yielding(rule_id: str) -> RegisteredRule:
    """The same rule written as a generator, which is the other legal shape."""

    def check(message: object, ctx: object) -> Iterator[Occurrence]:
        for each in message.get("entity"):
            yield Occurrence(rule_id, f"entity {each.get('id')}")

    return a_rule(rule_id, check)


def silent(rule_id: str) -> RegisteredRule:
    """A rule that found nothing and fell off its own end, returning `None`."""

    def check(message: object, ctx: object) -> None:
        return None

    return a_rule(rule_id, check)


def static_feed(directory: Path, tables: dict[str, list[dict[str, object]]] | None = None) -> Path:
    return build_feed(directory, minimal_tables() if tables is None else tables)


def a_config(
    directory: Path,
    mode: Mode = Mode.MODERN,
    registry: Registry | None = None,
    **kwargs: object,
) -> RunConfig:
    """A prepared run over the minimal static feed.

    `registry` replaces the mode's own, so a caller can drive the runner with a
    handful of rules rather than all of them. `replace` rather than a `prepare`
    argument, so the shipped entry point does not grow a test-only door.
    """
    config = prepare(mode, static_feed(directory), **kwargs)
    return config if registry is None else replace(config, registry=registry)
