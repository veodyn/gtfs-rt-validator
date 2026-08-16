"""W009, against upstream's own `testW009TripDescriptor` and `testW009StopTimeUpdate`.

Upstream asserts counts only; the prefixes are ours, read off
`TripDescriptorValidator.java:472` and `:485`.

Three things are pinned here that upstream's two tests do not reach, because
neither of them puts two entities in one feed:

- **the whole-feed suppression list**, `errorListW009`, which is never reset, so
  a W009 anywhere silences the second and later stop_time_updates of every later
  TripUpdate;
- **the ordering** of a TripUpdate's stop_time_update warnings against its
  trip-level one;
- **the enum gap**, which fires this rule for any post-2015
  schedule_relationship because `hasScheduleRelationship()` is false for one.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.upstream.w009 import check
from rulefixtures import entity, prefixes
from tripfixtures import DUPLICATED, SCHEDULED, alert, run, selector, td

#: `StopTimeUpdate.ScheduleRelationship.SCHEDULED`, which is 0 in both schemas.
STU_SCHEDULED = 0

#: The trip every stop_time_update case hangs off, already warned about or not.
KNOWN_TRIP = td(trip_id="1.1", schedule_relationship=SCHEDULED)


def found(tmp_path: Path, *entities) -> list[str]:
    return prefixes(run(check, tmp_path, *entities))


def a_trip_update(*stop_time_updates, entity_id: str = "TEST_ENTITY") -> dict[str, object]:
    return entity(
        trip_update={"trip": KNOWN_TRIP, "stop_time_update": list(stop_time_updates)},
        entity_id=entity_id,
    )


# --- upstream's own cases ---------------------------------------------------


def test_a_trip_with_no_schedule_relationship_warns_from_all_three_halves(
    tmp_path: Path,
) -> None:
    """Upstream, testW009TripDescriptor: one entity carrying an alert, a
    TripUpdate and a VehiclePosition all with trip_id `1` and no
    schedule_relationship, `expected.put(W009, 3)`."""
    trip = td(trip_id="1")
    everywhere = entity(
        trip_update={"trip": trip},
        vehicle={"trip": trip},
        alert=alert(selector(trip=trip)),
    )

    assert found(tmp_path, everywhere) == ["trip_id 1"] * 3


def test_a_trip_with_scheduled_warns_about_nothing(tmp_path: Path) -> None:
    """Upstream, testW009TripDescriptor's second stage, `expected.clear()`."""
    trip = td(trip_id="1", schedule_relationship=SCHEDULED)
    everywhere = entity(
        trip_update={"trip": trip},
        vehicle={"trip": trip},
        alert=alert(selector(trip=trip)),
    )

    assert found(tmp_path, everywhere) == []


def test_one_bare_stop_time_update_warns_once(tmp_path: Path) -> None:
    """Upstream, testW009StopTimeUpdate: stop_id `1000` and no
    schedule_relationship, `expected.put(W009, 1)`. The prefix is ours."""
    assert found(tmp_path, a_trip_update({"stop_id": "1000"})) == [
        "trip_id 1.1 stop_id 1000 (and potentially more for this trip)"
    ]


def test_a_second_bare_stop_time_update_still_warns_once(tmp_path: Path) -> None:
    """Upstream, testW009StopTimeUpdate: adding stop_id `2000` keeps the count
    at 1. This is the half of the suppression that is deliberate, and upstream's
    own comment at `:130` says why."""
    both_bare = a_trip_update({"stop_id": "1000"}, {"stop_id": "2000"})

    assert len(found(tmp_path, both_bare)) == 1


def test_stop_time_updates_that_declare_scheduled_warn_about_nothing(tmp_path: Path) -> None:
    """Upstream, testW009StopTimeUpdate's last stage: two stop_time_updates with
    stop_sequence 4 and 5 and SCHEDULED, `expected.clear()`."""
    scheduled = a_trip_update(
        {"stop_sequence": 4, "stop_id": "1000", "schedule_relationship": STU_SCHEDULED},
        {"stop_sequence": 5, "stop_id": "2000", "schedule_relationship": STU_SCHEDULED},
    )

    assert found(tmp_path, scheduled) == []


# --- the prefixes, which upstream's tests never look at ---------------------


def test_the_trip_prefix_falls_back_to_the_entity_id(tmp_path: Path) -> None:
    """Ours. `GtfsUtils.getTripId` gives `trip_id X` or `entity ID Y`, and a
    TripUpdate with no trip_id reports both W006 and this."""
    assert found(tmp_path, entity(trip_update={"trip": {}}, entity_id="E1")) == ["entity ID E1"]


def test_the_stop_time_update_prefix_prefers_the_stop_sequence(tmp_path: Path) -> None:
    """Ours, `GtfsUtils.getStopTimeUpdateId`: stop_sequence wins when present,
    even alongside a stop_id, and the `else` arm reads `getStopId()` unguarded,
    so an update carrying neither gives `stop_id ` and a trailing space."""
    sequenced = a_trip_update({"stop_sequence": 4, "stop_id": "1000"})
    neither = a_trip_update({})

    assert found(tmp_path, sequenced) == [
        "trip_id 1.1 stop_sequence 4 (and potentially more for this trip)"
    ]
    assert found(tmp_path, neither) == ["trip_id 1.1 stop_id  (and potentially more for this trip)"]


def test_a_trips_stop_time_update_warnings_come_before_its_own(tmp_path: Path) -> None:
    """Ours, `:129-140`: the stop_time_update loop runs before the trip-level
    call, so a TripUpdate warned about on both counts reports in that order."""
    unscheduled = entity(
        trip_update={"trip": td(trip_id="1.1"), "stop_time_update": [{"stop_id": "1000"}]}
    )

    assert found(tmp_path, unscheduled) == [
        "trip_id 1.1 stop_id 1000 (and potentially more for this trip)",
        "trip_id 1.1",
    ]


# --- the whole-feed suppression list ----------------------------------------


def test_a_later_trips_second_stop_time_update_goes_unchecked(tmp_path: Path) -> None:
    """Ours, and the bug. `errorListW009` is the feed's list, not the trip's, so
    the first stop_time_update of the second TripUpdate sets `foundW009` because
    the list is already non-empty rather than because it added anything, and the
    second stop_time_update is never examined.

    The two runs differ only in whether an earlier entity warned."""
    silenced = a_trip_update(
        {"stop_id": "1000", "schedule_relationship": STU_SCHEDULED},
        {"stop_id": "2000"},
        entity_id="second",
    )
    earlier = a_trip_update({"stop_id": "1"}, entity_id="first")

    assert found(tmp_path, silenced) == [
        "trip_id 1.1 stop_id 2000 (and potentially more for this trip)"
    ]
    assert found(tmp_path, earlier, silenced) == [
        "trip_id 1.1 stop_id 1 (and potentially more for this trip)"
    ]


def test_a_trip_descriptors_warning_silences_a_later_trip_too(tmp_path: Path) -> None:
    """Ours. The list is filled by both overloads, so a VehiclePosition whose
    trip has no schedule_relationship is enough on its own. That is why the
    suppression cannot be modelled per trip even as a cache."""
    silenced = a_trip_update(
        {"stop_id": "1000", "schedule_relationship": STU_SCHEDULED},
        {"stop_id": "2000"},
        entity_id="second",
    )
    earlier = entity(vehicle={"trip": td(trip_id="1")}, entity_id="first")

    assert found(tmp_path, earlier, silenced) == ["trip_id 1"]


# --- the schedule_relationship enum gap -------------------------------------


def test_a_post_2015_schedule_relationship_warns_as_though_it_were_absent(
    tmp_path: Path,
) -> None:
    """Ours. DUPLICATED is not in the 2015 enum, so protobuf 2.6.1 files it in
    the unknown-field set and `hasScheduleRelationship()` is false. Under
    `--compat` a feed that populates the field with a modern value is warned
    about as though it had left it empty."""
    duplicated = entity(trip_update={"trip": td(trip_id="1.1", schedule_relationship=DUPLICATED)})
    scheduled = entity(trip_update={"trip": td(trip_id="1.1", schedule_relationship=SCHEDULED)})

    assert found(tmp_path, duplicated) == ["trip_id 1.1"]
    assert found(tmp_path, scheduled) == []
