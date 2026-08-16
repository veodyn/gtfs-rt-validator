"""Tier 1 feeds about VehiclePositions, the two feeds compared, and the header.

Files 18 to 27 of the `bullrunner` sequence. `tools/conf_common.py` explains the
timeline and the archive.

**22-crossfeed-many.pb is the one file that could not be a smaller file.**
`CrossFeedDescriptorValidator` is the only validator whose output order depends
on Java `HashMap` iteration, and no committed golden exercised it before this
corpus: `tests/fixtures/jar/04-combined-feed.pb` puts at most one key in every
iterated container, so its four W003 occurrences are ordered by the loop alone
and any hash simulation at all would reproduce them.

**What the iterated containers hold here, counted rather than claimed.** Sixty
TripUpdates against sixty VehiclePositions, with `CROSSFEED_ENTITIES` vehicle ids
and the fifteen trip ids `bullrunner-gtfs.zip` actually defines:

    tripUpdatesTripIdToVehicleId       15 keys, table capacity 32
    vehiclePositionsVehicleIdToTripId  60 keys, table capacity 128
    tripsWithoutVehicles / vehiclesWithoutTrips   empty, every entity has both

The trip-keyed maps cannot grow past fifteen against this archive, because a
trip id outside `trips.txt` is E003 and a different file's job. The vehicle-keyed
one carries the table past `MIN_TREEIFY_CAPACITY`: sixty keys resize
16 -> 32 -> 64 -> 128, so `javahash.capacity_for`'s treeify branch is live in
this differential rather than only in unit tests, and sixty W003 occurrences come
out in the order a 128-bucket table iterates.

**The refusal itself is still not here, and cannot be.** `javahash` raises rather
than guessing once a bin would hold nine entries, which needs ids that collide
completely under `String.hashCode`. The jar emits a red-black tree's order for
those and this project refuses, so a feed built to reach it would be a deliberate
red diff rather than a passing comparison. `tests/test_shared_javahash.py` covers
that boundary, and `tests/test_conformance_differential.py` records the gap.

The pairings rotate by seven so that most vehicles appear in both halves under
different trips, which is E047, while the ends of the rotation appear in only
one, which is W003.
"""

from __future__ import annotations

from conf_common import DELAYED, STU_SCHEDULED, clock, quiet_trip
from feedbuild import (
    Feed,
    entity,
    header,
    message,
    pb,
    position,
    stu,
    trip_update,
    vehicle_position,
)

#: shapes.txt row 1 of shape `0`, which trips `1` and `2` both follow. A vehicle
#: here is on its own shape, so E029 stays quiet and the file is about the field
#: it names.
ON_SHAPE_ZERO = (28.0638055258, -82.4189883471)

#: Inside the coverage buffer of the whole feed but off every individual shape.
OFF_SHAPE = (28.07, -82.40)

#: Somewhere in the Atlantic off New Jersey, 1,500 km from Tampa.
OUTSIDE_COVERAGE = (40.0, -73.0)

#: How many TripUpdates and how many VehiclePositions 22-crossfeed-many.pb
#: carries, which is also how many distinct vehicle ids each half contributes.
#: Sixty is past the 48 a `HashMap` holds at capacity 64, so the iterated
#: vehicle-keyed map lands at 128 and the differential covers a table longer
#: than `MIN_TREEIFY_CAPACITY`. Twenty put every container at 32.
CROSSFEED_ENTITIES = 60

#: How far the vehicle-to-trip pairing rotates between the two halves.
CROSSFEED_ROTATION = 7


def _invalid_positions() -> bytes:
    """A latitude outside WGS84, a bearing outside 0-360, and 90 m/s."""
    return pb(
        message(
            header(clock(-13)),
            entity(
                "off-the-globe",
                vehicle=vehicle_position(
                    quiet_trip("1"),
                    vehicle_id="pos-1",
                    at=position(100.0, ON_SHAPE_ZERO[1]),
                    timestamp=clock(-13),
                ),
            ),
            entity(
                "impossible-bearing",
                vehicle=vehicle_position(
                    quiet_trip("2"),
                    vehicle_id="pos-2",
                    at=position(*ON_SHAPE_ZERO, bearing=400.0),
                    timestamp=clock(-13),
                ),
            ),
            entity(
                "too-fast",
                vehicle=vehicle_position(
                    quiet_trip("1"),
                    vehicle_id="pos-3",
                    at=position(*ON_SHAPE_ZERO, speed=90.0),
                    timestamp=clock(-13),
                ),
            ),
        )
    )


def _outside_coverage() -> bytes:
    """A vehicle 1,500 km from every shape point in the feed."""
    return pb(
        message(
            header(clock(-12)),
            entity(
                "at-sea",
                vehicle=vehicle_position(
                    quiet_trip("1"),
                    vehicle_id="coverage-1",
                    at=position(*OUTSIDE_COVERAGE),
                    timestamp=clock(-12),
                ),
            ),
        )
    )


def _off_shape() -> bytes:
    """Inside the agency's coverage area but off the shape of its own trip."""
    return pb(
        message(
            header(clock(-11)),
            entity(
                "wandered",
                vehicle=vehicle_position(
                    quiet_trip("1"),
                    vehicle_id="shape-1",
                    at=position(*OFF_SHAPE),
                    timestamp=clock(-11),
                ),
            ),
        )
    )


def _duplicate_vehicle() -> bytes:
    """Two VehiclePositions in one message claiming the same vehicle.id."""
    return pb(
        message(
            header(clock(-10)),
            entity(
                "first-claim",
                vehicle=vehicle_position(
                    quiet_trip("1"),
                    vehicle_id="claimed",
                    at=position(*ON_SHAPE_ZERO),
                    timestamp=clock(-10),
                ),
            ),
            entity(
                "second-claim",
                vehicle=vehicle_position(
                    quiet_trip("2"),
                    vehicle_id="claimed",
                    at=position(*ON_SHAPE_ZERO),
                    timestamp=clock(-10),
                ),
            ),
        )
    )


def _crossfeed_many() -> bytes:
    """`CROSSFEED_ENTITIES` TripUpdates against as many VehiclePositions."""
    when = clock(-9)
    entities = [
        entity(
            f"tu{index}",
            trip_update=trip_update(
                quiet_trip(str(index % 15 + 1)),
                stu(1, "222", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                vehicle_id=f"tuVeh{index}",
                timestamp=when,
            ),
        )
        for index in range(CROSSFEED_ENTITIES)
    ]
    entities += [
        entity(
            f"vp{index}",
            vehicle=vehicle_position(
                quiet_trip(str((index + CROSSFEED_ROTATION) % 15 + 1)),
                vehicle_id=f"vpVeh{index}",
                at=position(*ON_SHAPE_ZERO),
                timestamp=when,
            ),
        )
        for index in range(CROSSFEED_ENTITIES)
    ]
    return pb(message(header(when), *entities))


def _one_vehicle(offset: int, vehicle_id: str) -> bytes:
    """A minimal well-formed message, so the file is only about its header."""
    return pb(
        message(
            header(clock(offset)),
            entity(
                vehicle_id,
                vehicle=vehicle_position(
                    quiet_trip("1"),
                    vehicle_id=vehicle_id,
                    at=position(*ON_SHAPE_ZERO),
                    timestamp=clock(offset),
                ),
            ),
        )
    )


def _header_v2() -> bytes:
    """A 2.0 header with neither timestamp nor incrementality, and is_deleted.

    `HeaderValidator` reads the version first and both E048 and E049 are inside
    that branch, so a 1.0 feed missing the same two fields reports neither. The
    entity's own missing timestamp is W001, and `is_deleted` on a feed that
    defaults to FULL_DATASET is E039.
    """
    return pb(
        message(
            header(None, version="2.0", incrementality=None),
            entity(
                "deleted",
                is_deleted=True,
                trip_update=trip_update(
                    quiet_trip("1"),
                    stu(1, "222", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="v2-1",
                ),
            ),
        )
    )


def _stale_unknown_version() -> bytes:
    """A version upstream does not know, on a header 126 seconds old."""
    return pb(
        message(
            header(clock(-100), version="3.0"),
            entity(
                "old",
                vehicle=vehicle_position(
                    quiet_trip("1"),
                    vehicle_id="stale-1",
                    at=position(*ON_SHAPE_ZERO),
                    timestamp=clock(-100),
                ),
            ),
        )
    )


_CROSSFEED = _crossfeed_many()

VEHICLE_FEEDS: tuple[Feed, ...] = (
    Feed(
        "18-invalid-positions.pb", "a bad latitude, a bad bearing and 90 m/s", _invalid_positions()
    ),
    Feed("19-outside-coverage.pb", "1,500 km from every shape point", _outside_coverage()),
    Feed("20-off-shape.pb", "inside coverage but off its own trip's shape", _off_shape()),
    Feed("21-duplicate-vehicle.pb", "two positions claiming one vehicle.id", _duplicate_vehicle()),
    Feed(
        "22-crossfeed-many.pb",
        "60 vehicle ids in one iterated map, so hash order is observable at capacity 128",
        _CROSSFEED,
    ),
    Feed(
        "23-duplicate-of-22.pb",
        "byte-identical to 22, a second dedupe skip",
        _CROSSFEED,
        "duplicate",
    ),
    Feed(
        "24-refresh-gap.pb", "64 seconds after the last header timestamp", _one_vehicle(55, "gap-1")
    ),
    Feed(
        "25-header-went-back.pb",
        "a header timestamp lower than the last",
        _one_vehicle(50, "back-1"),
    ),
    Feed("26-header-v2.pb", "2.0 with no timestamp, no incrementality, is_deleted", _header_v2()),
    Feed(
        "27-stale-unknown-version.pb",
        "version 3.0 on a 126-second-old header",
        _stale_unknown_version(),
    ),
)
