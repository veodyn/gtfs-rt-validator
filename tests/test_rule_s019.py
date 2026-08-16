"""S019, and the band it occupies that E044 leaves open.

E044 accepts a StopTimeEvent carrying `delay` or `time`. The clause S019 cites
accepts only `time`, and only for the route-scoped descriptor shape, because a
delay is relative to a scheduled time that a route-scoped prediction never
names. The disjointness is the design: a fixture whose only defect is a `delay`
with no `time` leaves E044 satisfied, and the jar is asked in
`tests/test_spec_tier_does_not_shadow_the_jar.py`.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s019 import check
from specfixtures import context, entity, message


def found(*updates, **trip):
    feed = message(entity(trip_update={"trip": dict(trip), "stop_time_update": list(updates)}))
    return list(check(feed, context()) or ())


def prefixes(*updates, **trip):
    return [occurrence.prefix for occurrence in found(*updates, **trip)]


def test_a_route_scoped_arrival_with_only_a_delay_reports():
    """The band E044 accepts and the proto does not."""
    assert prefixes({"stop_id": "S1", "arrival": {"delay": 60}}, route_id="R1") == [
        "route_id R1 stop_time_update[0].arrival has no time"
    ]


def test_both_halves_of_one_update_report_separately():
    updates = ({"stop_id": "S1", "arrival": {"delay": 60}, "departure": {"delay": 90}},)

    assert prefixes(*updates, route_id="R1") == [
        "route_id R1 stop_time_update[0].arrival has no time",
        "route_id R1 stop_time_update[0].departure has no time",
    ]


def test_the_occurrence_locates_the_event_rather_than_the_update():
    (occurrence,) = found({"stop_id": "S1", "departure": {"delay": 0}}, route_id="R1")

    assert (
        occurrence.context[ENTITY_PATH_KEY] == "entity[0].trip_update.stop_time_update[0].departure"
    )


def test_an_absolute_time_satisfies_the_clause():
    """The satisfying fixture. A `time` alongside a `delay` is still a `time`."""
    arrival = {"time": 1_700_000_000, "delay": 60}

    assert prefixes({"stop_id": "S1", "arrival": arrival}, route_id="R1") == []


def test_an_absent_event_is_not_a_finding():
    """The clause constrains the times a producer provides. Whether an update
    has to carry one at all is E043's question, on a different antecedent."""
    assert prefixes({"stop_id": "S1"}, route_id="R1") == []


def test_a_trip_scoped_descriptor_is_out_of_scope():
    """With a trip_id there is a schedule for a delay to be relative to, which
    is the whole reason the clause is scoped to the route-only form."""
    assert prefixes({"stop_id": "S1", "arrival": {"delay": 60}}, trip_id="T1", route_id="R1") == []


def test_an_event_carrying_neither_reports_here_too():
    """A StopTimeEvent that was written and holds no time provides no absolute
    time either, so the clause is violated. E044 also fires on it, which is the
    overlap this rule declares, and neither rule is the other's duplicate."""
    assert prefixes({"stop_id": "S1", "arrival": {}}, route_id="R1") == [
        "route_id R1 stop_time_update[0].arrival has no time"
    ]
