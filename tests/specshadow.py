"""The fixtures the jar is asked about, one per spec-tier rule of cohorts A to C.

Kept beside `test_spec_tier_does_not_shadow_the_jar.py` rather than inside it,
because two modules need them: the jar test, which is slow and skips without a
jar, and the compat test, which runs everywhere and asks the same question of
this project's own byte-for-byte reproduction of it.

The fixtures themselves are next door in `specshadowfeeds.py`, which the file
size hook split this module at; what is left here is the shape of one and the
clean pieces every one of them is built from.

**What a fixture has to be for the question to mean anything.** One message
whose *only* defect is the rule's, over a static feed the jar loads clean. So
every entity that is not the defect is built from `trip_update()`,
`vehicle()` or `CLEAN_ALERT`, each of which was measured to produce no
occurrence at all rather than assumed to.

Three details make "clean" reproducible:

- **The clock is the file's mtime.** `BatchProcessor.java:223` uses it as
  "current" for every timestamp rule, and `tools/run_jar.py` stamps it at
  `MTIME_BASE`. `CLOCK` is that instant, and every header and every event time
  in these fixtures is at or after it, so W008, E012, E048 and E050 are silent.
- **`schedule_relationship` is stated explicitly** wherever the fixture is not
  about it, because W009 reports an absent one.
- **`frequencies.txt` is dropped** from the static feed except where a rule is
  about it, because a trip in `frequencies.txt` with no `start_time` on its
  descriptor is E006's and E019's shape rather than anything a spec rule is
  saying.

The messages are encoded under `schema_current`, which is the whole point: the
jar parses them with the 2015 bindings and puts every field it does not know
into its unknown-field set. That is what a real modern-mode feed looks like to
it.
"""

from __future__ import annotations

from dataclasses import KW_ONLY, dataclass, field

from gtfsfixtures import minimal_tables

__all__ = [
    "CLEAN_ALERT",
    "CLOCK",
    "DATED",
    "DUPLICATED",
    "MANY_SEATS",
    "NEW",
    "SCHEDULED",
    "STU_SCHEDULED",
    "STU_SKIPPED",
    "STU_UNSCHEDULED",
    "UNSCHEDULED",
    "Fixture",
    "as_trip_update",
    "as_vehicle",
    "stop_time",
    "tables",
    "trip_update",
    "vehicle",
]

#: `tools/run_jar.py:MTIME_BASE`, which is the clock every jar run here uses.
CLOCK = 1_700_000_000

# `TripDescriptor.ScheduleRelationship`, by number rather than by name, because
# the point of several fixtures is a number the 2015 enum has no member for.
SCHEDULED, UNSCHEDULED, DUPLICATED, NEW = 0, 2, 6, 8

# `TripUpdate.StopTimeUpdate.ScheduleRelationship`. `UNSCHEDULED = 3` is the
# member the 2015 enum lacks, which is S007's and S008's whole subject.
STU_SCHEDULED, STU_SKIPPED, STU_UNSCHEDULED = 0, 1, 3

#: An `OccupancyStatus`, for the one fixture that needs one.
MANY_SEATS = 1

#: A trip descriptor's dated form, for the fixtures over a `frequencies.txt`
#: trip where E006 would otherwise report the missing start_date and start_time.
DATED = {"start_date": "20231114", "start_time": "09:50:00"}

CLEAN_ALERT: dict[str, object] = {"informed_entity": [{"route_id": "R1"}]}


def stop_time(sequence: int, stop_id: str, **rest: object) -> dict[str, object]:
    """One stop_time_update the jar has nothing to say about."""
    return {
        "stop_sequence": sequence,
        "stop_id": stop_id,
        "schedule_relationship": STU_SCHEDULED,
        "arrival": {"time": CLOCK + sequence * 60},
        "departure": {"time": CLOCK + sequence * 60 + 10},
        **rest,
    }


def trip_update(**overrides: object) -> dict[str, object]:
    """A TripUpdate over `minimal_tables()`'s one trip, clean by measurement."""
    built: dict[str, object] = {
        "trip": {"trip_id": "T1", "schedule_relationship": SCHEDULED},
        "timestamp": CLOCK,
        "vehicle": {"id": "1"},
        "stop_time_update": [stop_time(1, "S1"), stop_time(2, "S2")],
    }
    built.update(overrides)
    return built


def vehicle(**overrides: object) -> dict[str, object]:
    """A VehiclePosition on the shape of that trip, clean by measurement."""
    built: dict[str, object] = {
        "trip": {"trip_id": "T1", "schedule_relationship": SCHEDULED},
        "vehicle": {"id": "1"},
        "timestamp": CLOCK,
        "position": {"latitude": 27.95, "longitude": -82.45},
    }
    built.update(overrides)
    return built


def as_trip_update(entity_id: str = "a", **overrides: object) -> dict[str, object]:
    """One entity carrying that TripUpdate, which is most fixtures' whole feed."""
    return {"id": entity_id, "trip_update": trip_update(**overrides)}


def as_vehicle(entity_id: str = "a", **overrides: object) -> dict[str, object]:
    """The same, for the VehiclePosition fixtures."""
    return {"id": entity_id, "vehicle": vehicle(**overrides)}


def tables(
    exact_times: str | None = None,
    shape_points: int | None = None,
    extra_stops: tuple[dict[str, object], ...] = (),
) -> dict[str, list[dict[str, object]]]:
    """`minimal_tables()`, with `frequencies.txt` dropped unless asked for.

    `shape_points` trims `shapes.txt` to its first n rows, which only S038's
    small-shape fixture asks for. Four points is what `minimal_tables()` writes
    and what clears `GtfsMetadata.java:127`'s feed-wide `shapePoints.size() > 3`
    gate; three is the case that gate empties, so `StaticContext.shape_points`
    is empty there and `shape_ids` is not.

    `extra_stops` appends rows to `stops.txt`, which only S047's fixture asks
    for. Both stops `minimal_tables()` writes are `location_type=0`, and S047
    fires on a replacement stop whose static row says otherwise, so that rule is
    the one fixture here whose defect cannot be stated in the realtime feed
    alone. The rows are appended rather than substituted, so every other rule's
    `S1` and `S2` are untouched.
    """
    built = minimal_tables()
    if exact_times is None:
        del built["frequencies.txt"]
    else:
        built["frequencies.txt"][0]["exact_times"] = exact_times
    if shape_points is not None:
        built["shapes.txt"] = built["shapes.txt"][:shape_points]
    built["stops.txt"].extend(dict(row) for row in extra_stops)
    return built


@dataclass(frozen=True, slots=True)
class Fixture:
    """One rule, one feed, and what the jar was measured to say about it."""

    rule_id: str
    entities: list[dict[str, object]]
    # Everything past the feed is keyword-only, and that is a scar rather than a
    # style. Two cohorts landing fixtures in parallel each inserted a field
    # ahead of `jar_ids`, which silently rebound the positional constructions:
    # S008 and S009 went on passing their measured jar verdict into whatever
    # field had taken third place, and failed the compat and jar assertions for
    # a reason neither cohort had touched. The first fix was a comment saying
    # `jar_ids` stays third, which is a rule the next person has to read and
    # obey. This is the same rule enforced by the interpreter: an inserted
    # field is now a TypeError at import, not a fixture quietly asserting the
    # wrong thing.
    _: KW_ONLY
    #: The jar's ids, recorded from a real run. Empty for most of them.
    jar_ids: frozenset[str] = frozenset()
    #: Entities of the messages that run *before* `entities`, under the same
    #: role, one list per message. Empty for every fixture but S021's, which is
    #: the only spec rule that reads `ctx.previous` and therefore the only one
    #: whose defect is a change between two messages. A fixture that states one
    #: is staged as a run of that many files, and its message `n` carries header
    #: timestamp `CLOCK + n`: two messages sharing a header timestamp are E017's
    #: shape rather than any spec rule's.
    preceding: tuple[list[dict[str, object]], ...] = ()
    #: The upstream id this rule declares an overlap with, as `OVERLAP` in
    #: `tests/test_tier_overlap.py` records it, and which must **not** appear
    #: here. `None` where the rule declares no overlap at all.
    not_emitted: str | None = None
    #: `frequencies.txt`'s `exact_times`, or `None` for no `frequencies.txt`.
    exact_times: str | None = None
    #: How many rows of `shapes.txt` the static feed keeps, or `None` for all
    #: four. See `tables()`.
    shape_points: int | None = None
    #: Rows appended to `stops.txt`, which only S047's fixture states. See
    #: `tables()`.
    extra_stops: tuple[dict[str, object], ...] = ()
    note: str = field(default="")

    def messages(self) -> tuple[list[dict[str, object]], ...]:
        """Every message of the run, the one the rule is about last.

        One element for all but S021's fixture, so a reader of the common case
        sees `(entities,)` and nothing else.
        """
        return (*self.preceding, self.entities)
