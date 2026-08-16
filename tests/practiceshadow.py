"""The clean pieces every practice-tier jar fixture is built from.

`specshadow.py` is the same idea for the spec tier and the two are deliberately
not merged: a spec fixture is one message, and three of the practice rules are
about what changed *between* two, so a fixture here is a sequence of messages
written into a replay directory with its mtimes stamped. Sharing the dataclass
would have meant one of the two carrying a field it never uses.

**What a fixture has to be for the question to mean anything.** A run whose only
defect is the rule's, over a static feed the jar loads clean. So every entity
that is not the defect is built from `trip_update()` or `vehicle()`, each of
which was measured to produce no occurrence at all rather than assumed to.

Three details make "clean" reproducible, and all three are the same as
`specshadow.py`'s because they are facts about `BatchProcessor` rather than
about a tier:

- **The clock is each file's mtime**, `MTIME_BASE + index` in the order the
  fixture lists its messages, which `tools/run_jar.py` stamps and which
  `runner/clock.py:modern_reading` reads on a directory replay. So this
  project and the jar see the same clock for the same file.
- **`schedule_relationship` is stated explicitly** wherever the fixture is not
  about it, because W009 reports an absent one. P014 is the fixture that is
  about it, and W009 is what it measures.
- **`frequencies.txt` is dropped** from the static feed except where a rule is
  about it, because a trip in `frequencies.txt` with no `start_time` on its
  descriptor is E006's and E019's shape rather than a practice rule's.

The messages are encoded under `schema_current`: the jar parses them with the
2015 bindings and puts every field it does not know into its unknown-field set,
which is what a real modern-mode feed looks like to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gtfsfixtures import minimal_tables

__all__ = [
    "CLOCK",
    "DATED",
    "SCHEDULED",
    "UNSCHEDULED",
    "Fixture",
    "Message",
    "as_trip_update",
    "as_vehicle",
    "stop_time",
    "tables",
    "trip_update",
    "vehicle",
]

#: `tools/run_jar.py:MTIME_BASE`, which is the clock the first file of every run
#: here gets. File `n` of a fixture is stamped `CLOCK + n`.
CLOCK = 1_700_000_000

# `TripDescriptor.ScheduleRelationship`, by number, as `specshadow.py` does.
SCHEDULED, UNSCHEDULED = 0, 2

#: A descriptor's dated form, for the fixtures over a `frequencies.txt` trip
#: where E006 would otherwise report the missing start_date and start_time.
DATED = {"start_date": "20231114", "start_time": "09:50:00"}


def stop_time(sequence: int, stop_id: str, **rest: object) -> dict[str, object]:
    """One stop_time_update the jar has nothing to say about."""
    return {
        "stop_sequence": sequence,
        "stop_id": stop_id,
        "schedule_relationship": 0,
        "arrival": {"time": CLOCK + sequence * 60},
        "departure": {"time": CLOCK + sequence * 60 + 10},
        **rest,
    }


def trip_update(timestamp: int = CLOCK, **overrides: object) -> dict[str, object]:
    """A TripUpdate over `minimal_tables()`'s one trip, clean by measurement."""
    built: dict[str, object] = {
        "trip": {"trip_id": "T1", "schedule_relationship": SCHEDULED},
        "timestamp": timestamp,
        "vehicle": {"id": "1"},
        "stop_time_update": [stop_time(1, "S1"), stop_time(2, "S2")],
    }
    built.update(overrides)
    return built


def vehicle(timestamp: int = CLOCK, **overrides: object) -> dict[str, object]:
    """A VehiclePosition on the shape of that trip, clean by measurement."""
    built: dict[str, object] = {
        "trip": {"trip_id": "T1", "schedule_relationship": SCHEDULED},
        "vehicle": {"id": "1"},
        "timestamp": timestamp,
        "position": {"latitude": 27.95, "longitude": -82.45},
    }
    built.update(overrides)
    return built


def as_trip_update(entity_id: str = "a", **overrides: object) -> dict[str, object]:
    return {"id": entity_id, "trip_update": trip_update(**overrides)}


def as_vehicle(entity_id: str = "a", **overrides: object) -> dict[str, object]:
    return {"id": entity_id, "vehicle": vehicle(**overrides)}


def tables(exact_times: str | None = None) -> dict[str, list[dict[str, object]]]:
    """`minimal_tables()`, with `frequencies.txt` dropped unless asked for."""
    built = minimal_tables()
    if exact_times is None:
        del built["frequencies.txt"]
    else:
        built["frequencies.txt"][0]["exact_times"] = exact_times
    return built


@dataclass(frozen=True, slots=True)
class Message:
    """One file of a run: its header timestamp and its entities.

    `gtfs_realtime_version` is the header's, and it defaults to `"2.0"` because
    every fixture except P001's is about something else and `"2.0"` is what the
    jar and this project both read as a modern feed. P001 is the one rule whose
    whole subject is this field, so it states `"1.0"` and the default leaves
    every other fixture's bytes unchanged.
    """

    header_timestamp: int
    entities: list[dict[str, object]]
    gtfs_realtime_version: str = "2.0"


@dataclass(frozen=True, slots=True)
class Fixture:
    """One case of one rule, and what the jar was measured to say about it.

    A case is not always a violation. The band rules get four each, and the
    three that are not the violation are what stops a band split from being a
    paragraph: `fires` records which one this is, and a fixture with
    `fires=False` asserts that the practice rule is silent where the neighbour
    it borders on owns the ground.
    """

    rule_id: str
    #: What distinguishes this case from the rule's others, for the test id.
    case: str
    messages: tuple[Message, ...]
    #: Whether the practice rule itself fires, in modern mode, on the last
    #: message of the run.
    fires: bool = True
    #: The jar's ids over the whole run, recorded from a real run rather than
    #: predicted. Empty for most of them.
    jar_ids: frozenset[str] = frozenset()
    #: The upstream id this rule declares an overlap with, as `OVERLAP` in
    #: `tests/test_tier_overlap.py` records it, and which must **not** appear
    #: here. `None` where the rule declares no overlap at all.
    not_emitted: str | None = None
    #: `frequencies.txt`'s `exact_times`, or `None` for no `frequencies.txt`.
    exact_times: str | None = None
    note: str = field(default="")

    def name(self) -> str:
        return f"{self.rule_id} {self.case}"
