"""`_shared/alert_index.py`: every Alert of a message or a cycle, indexed once.

Three rules read it and a fourth already existed. P006 asks which effects name a
`trip_id`, P012 asks which stops one Alert's selectors name, P015 asks the same
DETOUR question E029 asks, and E029 is the one that was here first.

**So the sharpest tests here are the ones that say E029 did not move.**
`vehicle_bounds.has_detour_alert` is now this index asked one question, rather
than a second scan beside it, and its own behaviour is pinned in
`tests/test_shared_detour_alert.py`, which is unchanged and still passes. What
this file adds is the equivalence stated directly: for every alert shape that
file builds, the index answers what the loop answered, including the two
easy-to-lose details, that the route comparison reads the *selector's*
`trip.route_id` rather than its own `route_id`, and that it is guarded by the
caller's `route_id is not None` rather than by anything about the selector.
"""

from __future__ import annotations

from dataclasses import replace

from gtfs_rt_validator.rules._shared import alert_index
from gtfs_rt_validator.rules._shared.alert_index import cycle_index, index, index_of_entities
from gtfs_rt_validator.rules._shared.vehicle_bounds import DETOUR_EFFECT, has_detour_alert
from gtfs_rt_validator.runner.context import (
    ROLE_ALERTS,
    ROLE_TRIP_UPDATES,
    ROLE_VEHICLE_POSITIONS,
)
from rulefixtures import READING, context, entity, message
from specfixtures import cycle_of, sharing

NO_SERVICE = 1
UNKNOWN_EFFECT = 8


def alert(effect: int | None = DETOUR_EFFECT, *selectors: dict[str, object]) -> dict[str, object]:
    built: dict[str, object] = {"informed_entity": list(selectors)}
    if effect is not None:
        built["effect"] = effect
    return built


def entities_of(*built: dict[str, object]):
    return message(*built).get("entity")


def test_an_effect_is_indexed_under_every_trip_id_its_selectors_name():
    found = index_of_entities(
        entities_of(entity(alert=alert(NO_SERVICE, {"trip": {"trip_id": "T1"}})))
    )

    assert found.effects_for_trip("T1") == frozenset({NO_SERVICE})
    assert found.effects_for_trip("T2") == frozenset()


def test_two_alerts_naming_one_trip_pool_their_effects():
    """P006 asks whether *any* Alert of the cycle carries NO_SERVICE for a trip,
    so the answer is a set of effects rather than one Alert's."""
    found = index_of_entities(
        entities_of(
            entity(alert=alert(NO_SERVICE, {"trip": {"trip_id": "T1"}}), entity_id="a"),
            entity(alert=alert(DETOUR_EFFECT, {"trip": {"trip_id": "T1"}}), entity_id="b"),
        )
    )

    assert found.effects_for_trip("T1") == frozenset({NO_SERVICE, DETOUR_EFFECT})


def test_an_alert_with_no_effect_at_all_contributes_no_effect():
    """`hasEffect()` guards the read, so the proto default is never reached. The
    Alert is still in `alerts`, because P012 is about selectors and not effects."""
    found = index_of_entities(entities_of(entity(alert=alert(None, {"trip": {"trip_id": "T1"}}))))

    assert found.effects_for_trip("T1") == frozenset()
    assert [each.effect for each in found.alerts] == [None]
    assert [each.trip_ids for each in found.alerts] == [frozenset({"T1"})]


def test_a_selector_naming_a_stop_is_a_stop_selector():
    found = index_of_entities(
        entities_of(entity(alert=alert(NO_SERVICE, {"stop_id": "S1"}, {"stop_id": "S2"})))
    )

    assert found.alerts[0].stop_ids == frozenset({"S1", "S2"})
    assert found.stop_ids == frozenset({"S1", "S2"})


def test_a_selector_naming_a_route_directly_is_a_route_selector():
    """And it is a different set from the route a selector's *trip* names, which
    is the distinction `hasDetourAlert` turns on."""
    found = index_of_entities(
        entities_of(
            entity(alert=alert(NO_SERVICE, {"route_id": "R1"}, {"trip": {"route_id": "R2"}}))
        )
    )

    assert found.alerts[0].route_ids == frozenset({"R1"})
    assert found.alerts[0].trip_route_ids == frozenset({"R2"})
    assert found.route_ids == frozenset({"R1"})


def test_a_selector_that_names_no_stop_does_not_name_the_empty_stop():
    """Presence, not the defaulted read. P012 asks whether an Alert names every
    stop of a route; a selector with no `stop_id` naming `""` would put the
    empty string in every alert's stop set and make that question meaningless."""
    found = index_of_entities(entities_of(entity(alert=alert(NO_SERVICE, {"route_id": "R1"}))))

    assert found.alerts[0].stop_ids == frozenset()


def test_a_selector_whose_trip_names_nothing_still_names_the_defaulted_trip_id():
    """The deliberate asymmetry with the test above, and it is E029's.

    `hasDetourAlert` compares `tripId.equals(entitySelector.getTrip().getTripId())`
    with no `hasTripId()` guard, so a selector carrying an empty `trip`
    submessage matches a vehicle whose own trip_id is the empty string. That is
    upstream's behaviour, it is reachable, and this index has to reproduce it
    because `has_detour_alert` is now this index asked a question.
    """
    found = index_of_entities(entities_of(entity(alert=alert(DETOUR_EFFECT, {"trip": {}}))))

    assert found.alerts[0].trip_ids == frozenset({""})
    assert found.has_effect(DETOUR_EFFECT, "") is True
    assert found.has_effect(DETOUR_EFFECT, "T1") is False


def test_has_effect_reads_the_route_only_when_the_caller_named_one():
    found = index_of_entities(
        entities_of(entity(alert=alert(DETOUR_EFFECT, {"trip": {"route_id": "A"}})))
    )

    assert found.has_effect(DETOUR_EFFECT, "T1", "A") is True
    assert found.has_effect(DETOUR_EFFECT, "T1", None) is False
    assert found.has_effect(DETOUR_EFFECT, "T1") is False


def test_has_effect_ignores_a_route_named_by_the_selector_itself():
    """`:254` is `entitySelector.getTrip().getRouteId()`. A selector naming a
    route directly fails `hasTrip()` at `:249` and is skipped."""
    found = index_of_entities(entities_of(entity(alert=alert(DETOUR_EFFECT, {"route_id": "A"}))))

    assert found.has_effect(DETOUR_EFFECT, "T1", "A") is False


def test_an_entity_carrying_no_alert_contributes_nothing():
    found = index_of_entities(entities_of(entity(trip_update={"trip": {"trip_id": "T1"}})))

    assert found.alerts == ()
    assert found.effects_for_trip("T1") == frozenset()


def test_the_path_locates_the_alert_for_an_occurrence():
    found = index_of_entities(
        entities_of(
            entity(trip_update={"trip": {"trip_id": "T1"}}, entity_id="one"),
            entity(alert=alert(NO_SERVICE, {"stop_id": "S1"}), entity_id="two"),
        ),
        role=ROLE_ALERTS,
    )

    assert [(each.role, each.path) for each in found.alerts] == [(ROLE_ALERTS, "entity[1].alert")]


DETOUR_SHAPES = (
    ("the trip_id matches", alert(DETOUR_EFFECT, {"trip": {"trip_id": "2"}}), "2", None, True),
    ("a different trip_id", alert(DETOUR_EFFECT, {"trip": {"trip_id": "10"}}), "2", None, False),
    ("the route via the trip", alert(DETOUR_EFFECT, {"trip": {"route_id": "A"}}), "2", "A", True),
    ("no route given", alert(DETOUR_EFFECT, {"trip": {"route_id": "A"}}), "2", None, False),
    ("a bare route selector", alert(DETOUR_EFFECT, {"route_id": "A"}), "2", "A", False),
    ("another effect", alert(UNKNOWN_EFFECT, {"trip": {"trip_id": "2"}}), "2", None, False),
    ("no effect at all", alert(None, {"trip": {"trip_id": "2"}}), "2", None, False),
    (
        "any selector of the alert",
        alert(DETOUR_EFFECT, {"trip": {"trip_id": "10"}}, {"trip": {"trip_id": "2"}}),
        "2",
        None,
        True,
    ),
)


def test_the_index_answers_e029s_question_exactly_as_the_scan_did():
    """The equivalence, over every shape `test_shared_detour_alert.py` builds.

    E029 is a compat byte contract, so the claim that matters about this module
    is not what it adds but that it subtracted nothing.
    """
    for name, built, trip_id, route_id, expected in DETOUR_SHAPES:
        found = entities_of(entity(alert=built))
        assert has_detour_alert(found, trip_id, route_id) is expected, name
        assert index_of_entities(found).has_effect(DETOUR_EFFECT, trip_id, route_id) is expected, (
            name
        )


def test_the_scan_covers_every_entity_of_the_message():
    found = entities_of(
        entity(trip_update={"trip": {"trip_id": "2"}}, entity_id="one"),
        entity(alert=alert(DETOUR_EFFECT, {"trip": {"trip_id": "2"}}), entity_id="two"),
    )

    assert has_detour_alert(found, "2", None) is True


def test_two_rules_reading_one_message_index_it_once(tmp_path, monkeypatch):
    runs = sharing(monkeypatch, alert_index, "_build")
    feed = message(entity(alert=alert(NO_SERVICE, {"trip": {"trip_id": "T1"}})))
    ctx = context(tmp_path)

    index(feed, ctx)
    index(feed, ctx)

    assert len(runs) == 1


def combined_context(tmp_path, *, role: str | None = None, **roles):
    """A context over a cycle of named roles, the way the runner builds one.

    `role` names which of them this context belongs to and defaults to the host.
    Passing a non-host one is how a test says "this message does not report for
    the cycle", which is no longer the same claim as "cannot see it"."""
    view = cycle_of(roles)
    mine = view.host_role if role is None else role
    return replace(context(tmp_path), clock=READING, source=f"{mine}.pb", role=mine, cycle=view)


def test_the_cycle_index_spans_every_role(tmp_path):
    """P006 runs on a TripUpdates message and the Alert it needs is in the
    Service Alerts feed, which is a different file of the same cycle."""
    ctx = combined_context(
        tmp_path,
        tu=message(entity(trip_update={"trip": {"trip_id": "T1"}})),
        sa=message(entity(alert=alert(NO_SERVICE, {"trip": {"trip_id": "T1"}}))),
    )

    found = cycle_index(ctx)

    assert found is not None
    assert found.effects_for_trip("T1") == frozenset({NO_SERVICE})
    assert [each.role for each in found.alerts] == [ROLE_ALERTS]


def test_the_cycle_index_is_none_only_when_there_is_no_cycle(tmp_path):
    """A context with no cycle is one message standing alone, and `None` says
    so. `crossfeed` reads the other view, `ctx.combined`, which a non-host
    message does not get, because reporting fires once per cycle."""
    assert cycle_index(context(tmp_path)) is None


def test_the_cycle_index_spans_every_role_from_every_role(tmp_path):
    """Read from the VehiclePositions message of a cycle `-tu` hosts. This
    answered `None` before the split, so P015 fell back to the alerts of a file
    that by construction carries none."""
    ctx = combined_context(
        tmp_path,
        role=ROLE_VEHICLE_POSITIONS,
        tu=message(entity(trip_update={"trip": {"trip_id": "T1"}})),
        sa=message(entity(alert=alert(NO_SERVICE, {"trip": {"trip_id": "T1"}}))),
    )

    assert ctx.combined is None
    assert cycle_index(ctx).effects_for_trip("T1") == frozenset({NO_SERVICE})


def test_the_cycle_index_is_built_once_for_the_whole_cycle(tmp_path, monkeypatch):
    runs = sharing(monkeypatch, alert_index, "_build_cycle")
    ctx = combined_context(
        tmp_path,
        tu=message(entity(trip_update={"trip": {"trip_id": "T1"}})),
        sa=message(entity(alert=alert(NO_SERVICE, {"trip": {"trip_id": "T1"}}))),
    )

    cycle_index(ctx)
    cycle_index(ctx)

    assert len(runs) == 1


def test_a_compat_run_sees_its_one_role_as_the_whole_cycle(tmp_path):
    """One unnamed role, so the cycle index and the message index agree, which
    is what makes the cycle reading safe to share with a compat-reachable one."""
    feed = message(entity(alert=alert(DETOUR_EFFECT, {"trip": {"trip_id": "T1"}})))
    ctx = combined_context(tmp_path, rt=feed)

    assert cycle_index(ctx).has_effect(DETOUR_EFFECT, "T1") is True
    assert index(feed, ctx).has_effect(DETOUR_EFFECT, "T1") is True


def test_the_message_index_carries_the_contexts_own_role(tmp_path):
    feed = message(entity(alert=alert(NO_SERVICE, {"stop_id": "S1"})))
    ctx = combined_context(tmp_path, tu=feed)

    assert [each.role for each in index(feed, ctx).alerts] == [ROLE_TRIP_UPDATES]
