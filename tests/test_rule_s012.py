"""S012: an `assigned_stop_id` that `stops.txt` does not define.

**The clause is definitional, not normative**, and the verdict file records it
that way: `272#1`, "Refers to a stop_id defined in the GTFS stops.txt.", has no
modal verb and its severity is pinned ERROR by the kind rather than derived from
a verb. There is no advisory reading of a value domain: a real-time stop
assignment naming a stop nobody defined cannot be applied at all.

Not E011, which reads `StopTimeUpdate.stop_id`. This reads a different field on
the same message, and the two can disagree, which is what S011 is about.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.spec.s012 import check
from gtfs_rt_validator.rules.upstream.e011 import check as e011
from specfixtures import entity, feed_context, message, prefixes


def update(stop_id: str | None = None, assigned: str | None = None) -> dict[str, object]:
    built: dict[str, object] = {}
    if stop_id is not None:
        built["stop_id"] = stop_id
    if assigned is not None:
        built["stop_time_properties"] = {"assigned_stop_id": assigned}
    return built


def trip_update(*updates: dict[str, object]) -> dict[str, object]:
    return {"trip": {"trip_id": "T1"}, "stop_time_update": list(updates)}


def run(tmp_path, *entities):
    return check(message(*entities), feed_context(tmp_path))


def test_a_stop_id_stops_txt_defines_resolves(tmp_path):
    """S1 and S2 are `minimal_tables()`'s two stops."""
    assert prefixes(run(tmp_path, entity(trip_update=trip_update(update(assigned="S2"))))) == []


def test_a_stop_id_stops_txt_does_not_define_is_reported(tmp_path):
    found = run(tmp_path, entity(trip_update=trip_update(update(assigned="DUMMY"))))

    assert prefixes(found) == [
        "trip_id T1 stop_time_update[0] assigned_stop_id DUMMY is not in stops.txt"
    ]


def test_an_update_with_no_assigned_stop_id_is_not_a_finding(tmp_path):
    assert prefixes(run(tmp_path, entity(trip_update=trip_update(update("S1"))))) == []


def test_each_offending_update_reports_once(tmp_path):
    found = run(
        tmp_path,
        entity(
            trip_update=trip_update(
                update(assigned="S1"), update(assigned="X"), update(assigned="Y")
            )
        ),
    )

    assert [occurrence.context["entityPath"] for occurrence in found] == [
        "entity[0].trip_update.stop_time_update[1]",
        "entity[0].trip_update.stop_time_update[2]",
    ]
    assert [occurrence.rule_id for occurrence in found] == ["S012", "S012"]


# --- the boundary with E011, which owns the other field ----------------------


def test_a_bad_assigned_stop_id_beside_a_good_stop_id_is_this_rules_alone(tmp_path):
    feed = message(entity(trip_update=trip_update(update("S1", "DUMMY"))))

    assert len(list(check(feed, feed_context(tmp_path)))) == 1
    assert list(e011(feed, feed_context(tmp_path))) == []


def test_a_bad_stop_id_beside_a_good_assigned_stop_id_is_e011s_alone(tmp_path):
    feed = message(entity(trip_update=trip_update(update("DUMMY", "S1"))))

    assert list(check(feed, feed_context(tmp_path))) == []
    assert len(list(e011(feed, feed_context(tmp_path)))) == 1
