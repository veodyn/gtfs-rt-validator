"""The seven identifier-text helpers, against upstream's own assertions.

Every assertion below marked "upstream" is transcribed from the real
`UtilTest.java` in the checkout at `jar-build/upstream/`, not from the
reference's summary of it: `testGetVehicleAndTripId` and
`testGetVehicleAndRouteId` (UtilTest.java:352-381), `testGetTripIdText`
(384-406), `testGetStopTimeUpdateId` (409-420), `testGetVehicleId` (423-445),
and the two `expected = IllegalArgumentException` cases (547-557).

The rest are ours, and each one covers a branch or a trap upstream's tests
never reach: the `!hasTrip()` and `!hasVehicle()` shortcuts, the bare
`"stop_id "` with its trailing space, the empty interpolations that the
unguarded default reads in `vehicle_and_trip_id_text` produce, and the
explicitly present but empty `vehicle.id`, which is the only case that tells a
`hasId()` port apart from a truthiness one.

Messages go through the real encoder and decoder rather than being poked into
a `Msg` by hand, so a helper reading a field name the schema does not have
fails here rather than silently returning a default.
"""

import pytest

from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA
from gtfs_rt_validator.rules._shared import ids
from gtfs_rt_validator.runner.context import RuleContractError


def built(name: str, value: dict) -> Msg:
    return decode(encode(value, SCHEMA, name), SCHEMA, name)


def empty(name: str) -> Msg:
    """A message the decoder cannot produce, for the branches that need one.

    `TripUpdate.trip` is required at both pins, so a TripUpdate with no trip
    never survives `isInitialized` and cannot be reached through `decode`. The
    Java still branches on `hasTrip()`, so the branch still needs a subject.
    """
    return Msg(SCHEMA.message(name), SCHEMA)


# --- trip_id_text, both Java overloads -------------------------------------


def test_a_trip_with_no_trip_id_gives_the_entity_id():
    """Upstream, testGetTripIdText: `assertEquals("entity ID 1", id)`."""
    entity = built("FeedEntity", {"id": "1", "trip_update": {"trip": {}}})
    assert ids.trip_id_text(entity, entity.get("trip_update")) == "entity ID 1"


def test_a_trip_id_reaches_the_text_through_both_overloads():
    """Upstream, testGetTripIdText: `assertEquals("trip_id 20", id)`, twice."""
    entity = built("FeedEntity", {"id": "1", "trip_update": {"trip": {"trip_id": "20"}}})
    trip_update = entity.get("trip_update")
    assert ids.trip_id_text(entity, trip_update) == "trip_id 20"
    assert ids.trip_descriptor_id_text(entity, trip_update.get("trip")) == "trip_id 20"


def test_a_trip_update_carrying_no_trip_at_all_gives_the_entity_id():
    """Ours. Upstream always sets the trip, so its `!hasTrip()` shortcut at
    GtfsUtils.java:184 is never exercised by its own tests."""
    entity = built("FeedEntity", {"id": "1"})
    assert ids.trip_id_text(entity, empty("TripUpdate")) == "entity ID 1"


# --- vehicle_id_text, both Java overloads -----------------------------------


def test_a_vehicle_with_no_id_gives_the_entity_id():
    """Upstream, testGetVehicleId: `assertEquals("entity ID 1", id)`."""
    entity = built("FeedEntity", {"id": "1", "vehicle": {"vehicle": {}}})
    assert ids.vehicle_id_text(entity, entity.get("vehicle")) == "entity ID 1"


def test_a_vehicle_id_reaches_the_text_through_both_overloads():
    """Upstream, testGetVehicleId: `assertEquals("vehicle.id 20", id)`, twice.

    The dot is upstream's. The rule titles say `vehicle_id`; this text says
    `vehicle.id`, and it is the text that reaches output bytes.
    """
    entity = built("FeedEntity", {"id": "1", "vehicle": {"vehicle": {"id": "20"}}})
    position = entity.get("vehicle")
    assert ids.vehicle_id_text(entity, position) == "vehicle.id 20"
    assert ids.vehicle_descriptor_id_text(entity, position.get("vehicle")) == "vehicle.id 20"


def test_an_explicitly_empty_vehicle_id_is_present_and_never_falls_back():
    """Ours, measured, and the one case that separates `has` from truthiness.

    GtfsUtils.java:226 is `vehicleDescriptor.hasId() ? ... : ...`. It branches
    on *presence*, so a descriptor that sets `id = ""` takes the first arm and
    the text keeps its label with nothing after it. Every other case in this
    module sets a non-empty id or no id at all, so a port that asked
    `if vehicle.get("id")` instead of `if vehicle.has("id")` would pass all of
    them and only differ here.

    Measured: over an entity carrying this descriptor, a valid position and a
    speed of 31, the pinned jar writes W002 `entity ID <id>` and W004
    `vehicle.id  speed of 31.0 m/s (69.35 mph)`, double space included.
    """
    entity = built("FeedEntity", {"id": "1", "vehicle": {"vehicle": {"id": ""}}})
    position = entity.get("vehicle")

    assert position.get("vehicle").has("id") is True
    assert ids.vehicle_id_text(entity, position) == "vehicle.id "
    assert ids.vehicle_descriptor_id_text(entity, position.get("vehicle")) == "vehicle.id "


def test_a_vehicle_position_carrying_no_vehicle_at_all_gives_the_entity_id():
    """Ours. Upstream always sets the descriptor, so its `!hasVehicle()`
    shortcut at GtfsUtils.java:211 is never exercised by its own tests."""
    entity = built("FeedEntity", {"id": "1", "vehicle": {}})
    assert ids.vehicle_id_text(entity, entity.get("vehicle")) == "entity ID 1"


# --- stop_time_update_id_text ----------------------------------------------


def test_a_stop_time_update_with_only_a_stop_id_gives_the_stop_id():
    """Upstream, testGetStopTimeUpdateId: `assertEquals("stop_id 1000", id)`."""
    update = built("TripUpdate.StopTimeUpdate", {"stop_id": "1000"})
    assert ids.stop_time_update_id_text(update) == "stop_id 1000"


def test_a_stop_sequence_beats_a_stop_id():
    """Upstream, testGetStopTimeUpdateId: with stop_id 1000 still set, adding
    stop_sequence 5 gives `assertEquals("stop_sequence 5", id)`."""
    update = built("TripUpdate.StopTimeUpdate", {"stop_id": "1000", "stop_sequence": 5})
    assert ids.stop_time_update_id_text(update) == "stop_sequence 5"


def test_a_stop_time_update_with_neither_gives_a_bare_stop_id_and_a_trailing_space():
    """Ours. The `stop_id` arm at GtfsUtils.java:240 is unguarded: it reads the
    default rather than falling back, so the text ends in a space. Trailing
    whitespace in an occurrence is a parity detail, hence the explicit repr."""
    assert ids.stop_time_update_id_text(empty("TripUpdate.StopTimeUpdate")) == "stop_id "


# --- vehicle_and_trip_id_text and vehicle_and_route_id_text -----------------


def test_a_trip_update_gives_only_its_trip_id():
    """Upstream, testGetVehicleAndTripId: `assertEquals(text, "trip_id 1")`."""
    trip_update = built("TripUpdate", {"trip": {"trip_id": "1"}})
    assert ids.vehicle_and_trip_id_text(trip_update) == "trip_id 1"


def test_a_vehicle_position_gives_its_vehicle_and_its_trip_id():
    """Upstream, testGetVehicleAndTripId:
    `assertEquals(text, "vehicle_id A trip_id 1")`."""
    position = built("VehiclePosition", {"vehicle": {"id": "A"}, "trip": {"trip_id": "1"}})
    assert ids.vehicle_and_trip_id_text(position) == "vehicle_id A trip_id 1"


def test_a_trip_update_gives_only_its_route_id():
    """Upstream, testGetVehicleAndRouteId: `assertEquals(text, "route_id 1")`."""
    trip_update = built("TripUpdate", {"trip": {"route_id": "1"}})
    assert ids.vehicle_and_route_id_text(trip_update) == "route_id 1"


def test_a_vehicle_position_gives_its_vehicle_and_its_route_id():
    """Upstream, testGetVehicleAndRouteId:
    `assertEquals(text, "vehicle_id A route_id 1")`."""
    position = built("VehiclePosition", {"vehicle": {"id": "A"}, "trip": {"route_id": "1"}})
    assert ids.vehicle_and_route_id_text(position) == "vehicle_id A route_id 1"


def test_absent_fields_interpolate_as_nothing_rather_than_falling_back():
    """Ours. GtfsUtils.java:101 and :122 chain through `getVehicle()` and
    `getTrip()` with no `has` guard, so an absent one yields its default
    instance and an empty id. There is no "entity ID" fallback on this path,
    and the result keeps both literal labels and the double space between
    them."""
    position = empty("VehiclePosition")
    assert ids.vehicle_and_trip_id_text(position) == "vehicle_id  trip_id "
    assert ids.vehicle_and_route_id_text(position) == "vehicle_id  route_id "
    trip_update = empty("TripUpdate")
    assert ids.vehicle_and_trip_id_text(trip_update) == "trip_id "
    assert ids.vehicle_and_route_id_text(trip_update) == "route_id "


def test_any_other_message_is_a_caller_bug_not_a_finding():
    """Upstream, testAssertVehicleAndTripIdThrowException and
    testAssertVehicleAndRouteIdThrowException: both pass a TripDescriptor and
    expect IllegalArgumentException."""
    trip = built("TripDescriptor", {"trip_id": "1", "route_id": "1"})
    with pytest.raises(RuleContractError, match="TripDescriptor"):
        ids.vehicle_and_trip_id_text(trip)
    with pytest.raises(RuleContractError, match="TripDescriptor"):
        ids.vehicle_and_route_id_text(trip)
