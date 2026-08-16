"""Tier 1 feeds about the TripDescriptor: what it names and how it spells it.

Files 01 to 04 of the `bullrunner` sequence, plus the two alert files, which
belong here because `TripDescriptorValidator` is what emits E030 to E034 as well.
`tools/conf_common.py` explains the timeline and the archive.
"""

from __future__ import annotations

from conf_common import ADDED, DELAYED, SCHEDULED, STU_SCHEDULED, clock, quiet_trip
from feedbuild import Feed, alert, entity, header, message, pb, stu, trip, trip_update


def _empty_trip() -> bytes:
    """A TripUpdate with no stop_time_updates, no vehicle and no trip_id.

    Four rules at once because they are four different fields nobody set: E041
    for the empty update list, W006 for the missing trip_id, W002 for the
    missing vehicle_id and W009 for the missing schedule_relationship. The
    second entity is the control: CANCELED is the one schedule_relationship
    that makes an empty update list legitimate, so E041 must not name it.
    """
    return pb(
        message(
            header(clock(-30)),
            entity("empty", trip_update=trip_update(trip(), timestamp=clock(-30))),
            entity(
                "cancelled",
                trip_update=trip_update(quiet_trip("2", schedule_relationship=3)),
            ),
        )
    )


def _unknown_ids() -> bytes:
    """A trip_id, a route_id and a stop_id none of which GTFS has: E003, E004, E011."""
    return pb(
        message(
            header(clock(-29)),
            entity(
                "unknown",
                trip_update=trip_update(
                    trip("not-in-gtfs", route_id="ZZ", schedule_relationship=SCHEDULED),
                    stu(1, "no-such-stop", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="unknown-1",
                    timestamp=clock(-29),
                ),
            ),
        )
    )


def _route_mismatch() -> bytes:
    """Trip `1` under route `B` when GTFS says route `A`, and the three
    frequency-type-zero rules a descriptor with no frequency fields brings."""
    return pb(
        message(
            header(clock(-28)),
            entity(
                "wrong-route",
                trip_update=trip_update(
                    quiet_trip("1", route_id="B"),
                    stu(1, "222", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="route-1",
                    timestamp=clock(-28),
                ),
            ),
            entity(
                "no-frequency-fields",
                trip_update=trip_update(
                    trip("3", schedule_relationship=SCHEDULED),
                    stu(1, "426", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    timestamp=clock(-28),
                ),
            ),
        )
    )


def _added_and_formats() -> bytes:
    """ADDED over a trip GTFS already has, and two malformed date fields."""
    return pb(
        message(
            header(clock(-27)),
            entity(
                "already-there",
                trip_update=trip_update(
                    quiet_trip("2", schedule_relationship=ADDED),
                    stu(1, "222", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="added-1",
                    timestamp=clock(-27),
                ),
            ),
            entity(
                "bad-formats",
                trip_update=trip_update(
                    quiet_trip("4", start_time="7:0:0", start_date="2016-01-01"),
                    stu(1, "418", arrival=DELAYED, schedule_relationship=STU_SCHEDULED),
                    vehicle_id="added-2",
                    timestamp=clock(-27),
                ),
            ),
        )
    )


def _alerts_without_specifiers() -> bytes:
    """An alert with no informed_entity, and one whose selector names nothing."""
    return pb(
        message(
            header(clock(-15)),
            entity("no-informed-entity", alert=alert()),
            entity("selector-names-nothing", alert=alert({})),
        )
    )


def _alerts_that_disagree() -> bytes:
    """A trip that does not belong to the named route, a route the trip's own
    descriptor contradicts, and an agency_id GTFS does not have."""
    return pb(
        message(
            header(clock(-14)),
            entity("unknown-agency", alert=alert({"agency_id": "no-such-agency"})),
            entity(
                "trip-not-on-route",
                alert=alert({"route_id": "B", "trip": trip("1", schedule_relationship=SCHEDULED)}),
            ),
            entity(
                "route-contradicts-trip",
                alert=alert(
                    {
                        "route_id": "A",
                        "trip": trip("1", route_id="B", schedule_relationship=SCHEDULED),
                    }
                ),
            ),
        )
    )


TRIP_FEEDS: tuple[Feed, ...] = (
    Feed("01-empty-trip.pb", "no stop_time_updates, no trip_id, no vehicle", _empty_trip()),
    Feed("02-unknown-ids.pb", "a trip, a route and a stop GTFS does not have", _unknown_ids()),
    Feed(
        "03-route-mismatch.pb",
        "a trip under the wrong route, and one with no frequency fields",
        _route_mismatch(),
    ),
    Feed(
        "04-added-and-formats.pb",
        "ADDED over an existing trip, and two malformed date fields",
        _added_and_formats(),
    ),
)

ALERT_FEEDS: tuple[Feed, ...] = (
    Feed(
        "16-alerts-without-specifiers.pb",
        "an alert with nothing to inform",
        _alerts_without_specifiers(),
    ),
    Feed(
        "17-alerts-that-disagree.pb",
        "alerts whose route, trip and agency disagree",
        _alerts_that_disagree(),
    ),
)
