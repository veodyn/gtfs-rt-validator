"""The three occurrence prefixes `StopValidator` builds, shared by E011 and E015.

`validation/rules/StopValidator.java:53-101` at
`7041fa3fcaf674bf730e17325c179d329cdff6f2` assembles these inline rather than
calling `util/GtfsUtils.java`, which is why they are not in `_shared/ids.py`:
that module is the port of `GtfsUtils` and holds the seven helpers that file
defines. These are the ones the validator writes itself.

Two of the three reach both rules. Upstream shares them by computing a `prefix`
local once per branch and reading it from both sites, except in the
VehiclePosition branch where it rebuilds the identical ternary a second time
(`:79` and `:85`). Splitting the two rules into two modules means the local
cannot be shared that way, and hand-writing the same ternary in each is exactly
the drift this package exists to prevent: a spacing difference would show up in
the differential for one rule and not the other, with nothing to say which of
the two was wrong.

The alert prefix has one caller, since E015 exempts alerts. It lives here
anyway, so that one file holds this validator's whole text contract.

Three details look like typos and are none of them:

- `tripUpdate.getTrip().getTripId()` is read with no `hasTripId()` guard
  (`:60`), so a trip descriptor carrying no trip_id gives `"trip_id  stop_id
  X"`, two spaces and all. Upstream's own `StopValidatorTest` builds precisely
  that descriptor, so that is the text the jar emits for its own test feed.
- The vehicle clause is a ternary yielding the empty string rather than a bare
  label, so a VehiclePosition with no vehicle id gives just `"stop_id X"`.
- `vehicle_id` here has an underscore, unlike the `vehicle.id` with a dot that
  `GtfsUtils.getVehicleId` produces for other rules.

Stdlib and the decoder only. Nothing here reads the static feed.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.decode import Msg


def trip_update_prefix(trip_update: Msg, stop_id: str) -> str:
    """StopValidator.java:60, read by the E011 and E015 sites in that branch."""
    return "trip_id " + trip_update.get("trip").get("trip_id") + " stop_id " + stop_id


def vehicle_prefix(position: Msg, stop_id: str) -> str:
    """StopValidator.java:79, rebuilt verbatim at :85 for the other rule."""
    vehicle = position.get("vehicle")
    if position.has("vehicle") and vehicle.has("id"):
        return "vehicle_id " + vehicle.get("id") + " stop_id " + stop_id
    return "stop_id " + stop_id


def alert_prefix(entity: Msg, stop_id: str) -> str:
    """StopValidator.java:95. `entityId` is the FeedEntity's own id.

    Not the informed_entity's, which has none: an `EntitySelector` carries
    agency, route, route type, trip and stop, and no id of its own.
    """
    return "alert entity ID " + entity.get("id") + " stop_id " + stop_id
