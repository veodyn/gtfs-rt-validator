"""P012: an Alert that names every stop of a route instead of naming the route.

`:128`, "Do not apply the alert to every stop of the line." The fixture feed is
`minimal_tables()`, whose one route R1 is served by one trip T1 calling at S1 and
S2, so "every stop of the line" is exactly `{"S1", "S2"}` and a two-selector
alert is the whole violation.

Two claims here are worth more than the rest. `test_a_partial_list_is_silent` is
the conformant twin that stops this being a rule that fires on any alert naming a
stop, and it is the one that holds the rule to inventing no threshold of its
own: one stop short of the set is silence, not a lesser finding.
`test_a_route_whose_trips_serve_no_stops_is_not_covered_by_anything` is the
empty-subset trap from the rule's own side: every set contains the empty set, so
a route with no stops would otherwise make every alert in the feed a violation.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.practice.p012 import check
from specfixtures import entity, feed_context, message, minimal, prefixes


def alert(*selectors: dict[str, object]) -> dict[str, object]:
    return {"informed_entity": list(selectors)}


def stops(*stop_ids: str) -> list[dict[str, object]]:
    return [{"stop_id": stop_id} for stop_id in stop_ids]


def two_routes() -> dict[str, list[dict[str, str]]]:
    """R1 over S1 and S2, plus R2 over S2 and S3, so the two overlap at S2."""
    built = minimal(
        stops=[{"stop_id": "S3", "stop_name": "Third", "stop_lat": "28.1", "stop_lon": "-82.3"}],
        routes=[{"route_id": "R2", "agency_id": "A1", "route_short_name": "2", "route_type": "3"}],
        trips=[{"trip_id": "T2", "route_id": "R2", "service_id": "SVC1"}],
    )
    built["stop_times.txt"] += [
        {
            "trip_id": "T2",
            "arrival_time": "08:00:00",
            "departure_time": "08:00:00",
            "stop_id": stop_id,
            "stop_sequence": str(sequence),
            "pickup_type": "0",
        }
        for sequence, stop_id in enumerate(["S2", "S3"], start=1)
    ]
    return built


def run(tmp_path, *entities, tables=None):
    return check(message(*entities), feed_context(tmp_path, tables))


def reported(count: int, route_id: str) -> str:
    return (
        f"alert names all {count} stops served by route_id {route_id} as stop selectors and "
        f"does not name the route itself"
    )


def test_an_alert_naming_every_stop_of_a_route_is_reported(tmp_path):
    found = run(tmp_path, entity(alert=alert(*stops("S1", "S2"))))

    assert prefixes(found) == [reported(2, "R1")]


def test_a_partial_list_is_silent(tmp_path):
    """The conformant twin, and "invents no threshold of its own" as a test: one
    stop short of the route's set is not a lesser finding, it is silence."""
    assert prefixes(run(tmp_path, entity(alert=alert(*stops("S1"))))) == []


def test_naming_the_route_as_well_is_the_shape_the_clause_asks_for(tmp_path):
    """The clause's remedy is to apply the alert to the line. An alert that does
    that has told the consumer which line it is about, whatever else it lists."""
    found = run(tmp_path, entity(alert=alert({"route_id": "R1"}, *stops("S1", "S2"))))

    assert prefixes(found) == []


def test_naming_the_route_alone_is_the_conformant_shape(tmp_path):
    assert prefixes(run(tmp_path, entity(alert=alert({"route_id": "R1"})))) == []


def test_a_superset_of_the_routes_stops_still_covers_it(tmp_path):
    """Covering the line and then some is still covering the line. S3 here is a
    stop no trip calls at, so it belongs to no route and adds no second finding."""
    unrouted = minimal(
        stops=[{"stop_id": "S3", "stop_name": "Third", "stop_lat": "28.1", "stop_lon": "-82.3"}]
    )
    found = run(tmp_path, entity(alert=alert(*stops("S1", "S2", "S3"))), tables=unrouted)

    assert prefixes(found) == [reported(2, "R1")]


def test_two_routes_covered_by_one_alert_report_separately(tmp_path):
    """Each covered route is its own instance of the shape the clause forbids,
    and the order is by route_id so it cannot depend on `trips.txt` row order."""
    found = run(tmp_path, entity(alert=alert(*stops("S1", "S2", "S3"))), tables=two_routes())

    assert prefixes(found) == [reported(2, "R1"), reported(2, "R2")]
    assert [one.context["entityPath"] for one in found] == ["entity[0].alert", "entity[0].alert"]


def test_naming_one_of_the_two_routes_leaves_only_the_other(tmp_path):
    found = run(
        tmp_path,
        entity(alert=alert(*stops("S1", "S2", "S3"), {"route_id": "R1"})),
        tables=two_routes(),
    )

    assert prefixes(found) == [reported(2, "R2")]


def test_a_stop_selector_carrying_a_route_still_names_the_stop(tmp_path):
    """`EntitySelector` may set several fields at once. A selector naming S1 on
    R1 names S1, and naming R1 that way is naming the route."""
    found = run(tmp_path, entity(alert=alert({"stop_id": "S1", "route_id": "R1"}, *stops("S2"))))

    assert prefixes(found) == []


def test_a_selector_with_an_explicitly_blank_stop_id_names_the_empty_string(tmp_path):
    """Presence, not the defaulted read. `alert_index` guards `stop_id` with
    `has()`, so a blank one puts `""` in the set rather than nothing, and `""`
    is a stop_id no route serves."""
    found = run(tmp_path, entity(alert=alert({"stop_id": ""}, *stops("S1", "S2"))))

    assert prefixes(found) == [reported(2, "R1")]


def test_a_selector_naming_a_trip_of_the_route_is_not_naming_the_route(tmp_path):
    """`EntitySelector.trip.route_id` scopes the alert to one run of the line,
    not to the line. The remedy the clause asks for is the route selector."""
    found = run(
        tmp_path,
        entity(alert=alert({"trip": {"trip_id": "T1", "route_id": "R1"}}, *stops("S1", "S2"))),
    )

    assert prefixes(found) == [reported(2, "R1")]


def test_an_alert_naming_no_stops_at_all_is_silent(tmp_path):
    assert prefixes(run(tmp_path, entity(alert=alert({"agency_id": "A1"})))) == []


def test_an_alert_with_no_informed_entity_at_all_is_silent(tmp_path):
    assert prefixes(run(tmp_path, entity(alert={"header_text": {"translation": []}}))) == []


def test_a_route_whose_trips_serve_no_stops_is_not_covered_by_anything(tmp_path):
    """The empty-subset trap. `_tables.build_route_stop_ids` leaves such a route
    out of the mapping rather than mapping it to an empty frozenset, because
    every alert names every stop of the empty set."""
    tables = minimal(
        routes=[{"route_id": "R9", "agency_id": "A1", "route_short_name": "9", "route_type": "3"}],
        trips=[{"trip_id": "T9", "route_id": "R9", "service_id": "SVC1"}],
    )
    found = run(tmp_path, entity(alert=alert(*stops("S1"))), tables=tables)

    assert prefixes(found) == []


def test_two_alerts_report_separately_and_are_located(tmp_path):
    found = run(
        tmp_path,
        entity("a", alert=alert(*stops("S1", "S2"))),
        entity("b", alert=alert(*stops("S2"))),
        entity("c", alert=alert(*stops("S2", "S1"))),
    )

    assert [one.context["entityPath"] for one in found] == ["entity[0].alert", "entity[2].alert"]
    assert [one.rule_id for one in found] == ["P012", "P012"]
    assert [one.context["routeId"] for one in found] == ["R1", "R1"]


def test_a_message_with_no_alerts_is_silent(tmp_path):
    found = run(tmp_path, entity(vehicle={"position": {"latitude": 27.95, "longitude": -82.45}}))

    assert prefixes(found) == []
