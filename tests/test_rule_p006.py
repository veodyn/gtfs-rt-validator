"""P006: a trip cancelled over several days with no NO_SERVICE Alert for it.

The violating feed is two CANCELED TripUpdates for one trip on two
`start_date`s. Its conformant twin is the same feed with the Alert the clause
asks for, and the interesting form of that twin is the one where the Alert is in
**another role's file of the same cycle**: an agency publishes TripUpdates and
Alerts separately, so a rule that only looked in the message it was handed would
report every correctly-alerted cancellation in a real deployment.

**Off the cycle host the rule reads the cycle anyway**, because reading is not
reporting: `ctx.cycle` reaches every role and only the host token `ctx.combined`
is withheld. The one case that is genuinely different is a context carrying no
cycle at all, where the message is the whole scope and its own Alerts are every
Alert there is. Both are tested below.

`Alert.Effect.NO_SERVICE` is 1 under the 2015 schema and the current one alike,
which is asserted below rather than assumed: the number is written as a literal
in the rule, exactly as `_shared/vehicle_bounds.DETOUR_EFFECT` is, and that is
only legitimate while the two schemas agree.
"""

from __future__ import annotations

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.proto.schema_current import SCHEMA
from gtfs_rt_validator.rules.practice.p006 import NO_SERVICE_EFFECT, check
from gtfs_rt_validator.runner.context import CombinedFeed
from specfixtures import context, cycle_of, entity, message, occurrences, prefixes

TRIP = SCHEMA.enums["TripDescriptor.ScheduleRelationship"]
EFFECT = SCHEMA.enums["Alert.Effect"]

DAY, NEXT_DAY = "20231114", "20231115"


def trip_update(
    start_date: str | None = DAY, trip_id: str = "T1", relationship: str = "CANCELED"
) -> dict[str, object]:
    trip: dict[str, object] = {"trip_id": trip_id, "schedule_relationship": TRIP[relationship]}
    if start_date is not None:
        trip["start_date"] = start_date
    return {"trip": trip}


def alert(effect: str | None = "NO_SERVICE", trip_id: str = "T1") -> dict[str, object]:
    built: dict[str, object] = {"informed_entity": [{"trip": {"trip_id": trip_id}}]}
    if effect is not None:
        built["effect"] = EFFECT[effect]
    return built


def cycle(**messages: Msg) -> CombinedFeed:
    """One cycle, one message per role, built the way the runner builds one."""
    return cycle_of(messages)


def run(*entities: dict[str, object], alerts: object = None):
    """The rule over one TripUpdates message, hosting a cycle of one or two."""
    now = message(*entities)
    roles: dict[str, object] = {"tu": now}
    if alerts is not None:
        roles["sa"] = alerts
    return check(now, context(role="tu", source="tu.pb", cycle=cycle(**roles)))


def reported(trip_id: str = "T1", dates: str = f"{DAY}, {NEXT_DAY}") -> str:
    return (
        f"trip_id {trip_id} is CANCELED on 2 start_dates ({dates}) and no Alert in this "
        f"feed cycle names it with effect NO_SERVICE"
    )


def test_the_effect_number_is_the_same_under_both_schemas():
    """Which is what lets the rule spell it as a literal, the way E029 spells
    DETOUR. The day a pin disagrees, this is the test that says so."""
    assert V2015.enums["Alert.Effect"]["NO_SERVICE"] == NO_SERVICE_EFFECT
    assert SCHEMA.enums["Alert.Effect"]["NO_SERVICE"] == NO_SERVICE_EFFECT


def test_a_trip_canceled_on_two_days_with_no_alert_is_reported():
    found = run(
        entity(trip_update=trip_update(DAY), entity_id="a"),
        entity(trip_update=trip_update(NEXT_DAY), entity_id="b"),
    )

    assert prefixes(found) == [reported()]


def test_the_same_feed_carrying_the_alert_the_clause_asks_for_is_silent():
    """The conformant twin, with the Alert in the same message."""
    found = run(
        entity(trip_update=trip_update(DAY), entity_id="a"),
        entity(trip_update=trip_update(NEXT_DAY), entity_id="b"),
        entity(alert=alert(), entity_id="c"),
    )

    assert prefixes(found) == []


def test_an_alert_in_another_role_of_the_same_cycle_is_the_same_answer():
    """The twin that matters: an agency publishing `-tu` and `-sa` separately
    satisfies the clause across two files, and the cycle is what sees both."""
    found = run(
        entity(trip_update=trip_update(DAY), entity_id="a"),
        entity(trip_update=trip_update(NEXT_DAY), entity_id="b"),
        alerts=message(entity(alert=alert(), entity_id="c")),
    )

    assert prefixes(found) == []


def test_an_alert_naming_another_trip_does_not_cover_this_one():
    found = run(
        entity(trip_update=trip_update(DAY), entity_id="a"),
        entity(trip_update=trip_update(NEXT_DAY), entity_id="b"),
        alerts=message(entity(alert=alert(trip_id="T9"), entity_id="c")),
    )

    assert prefixes(found) == [reported()]


def test_an_alert_with_another_effect_does_not_cover_the_cancellation():
    """The clause names `NO_SERVICE`, and a DETOUR alert describes a different
    service change."""
    found = run(
        entity(trip_update=trip_update(DAY), entity_id="a"),
        entity(trip_update=trip_update(NEXT_DAY), entity_id="b"),
        alerts=message(entity(alert=alert(effect="DETOUR"), entity_id="c")),
    )

    assert prefixes(found) == [reported()]


def test_an_alert_declaring_no_effect_at_all_covers_nothing():
    """`alert_index` leaves an Alert with no `effect` out of the effect lookup
    rather than defaulting it, so it cannot answer for NO_SERVICE."""
    found = run(
        entity(trip_update=trip_update(DAY), entity_id="a"),
        entity(trip_update=trip_update(NEXT_DAY), entity_id="b"),
        alerts=message(entity(alert=alert(effect=None), entity_id="c")),
    )

    assert prefixes(found) == [reported()]


def test_one_canceled_day_is_not_canceling_over_a_number_of_days():
    """ "When canceling trips over a number of days" is the antecedent, so a
    single cancelled instance is out of scope however cancelled it is."""
    assert prefixes(run(entity(trip_update=trip_update(DAY), entity_id="a"))) == []


def test_two_trip_updates_naming_one_day_are_one_day():
    """The count is of distinct `start_date` values. Two TripUpdates for one
    instance is S003's finding and not a multi-day cancellation."""
    found = run(
        entity(trip_update=trip_update(DAY), entity_id="a"),
        entity(trip_update=trip_update(DAY), entity_id="b"),
    )

    assert prefixes(found) == []


def test_a_trip_that_still_runs_on_one_of_the_days_is_silent():
    """ "as `CANCELED`" is part of the antecedent: a trip running some days and
    cancelled on others is not the shape the clause describes."""
    found = run(
        entity(trip_update=trip_update(DAY), entity_id="a"),
        entity(trip_update=trip_update(NEXT_DAY, relationship="SCHEDULED"), entity_id="b"),
    )

    assert prefixes(found) == []


def test_an_undeclared_relationship_resolves_to_scheduled_and_is_not_a_cancellation():
    found = run(
        entity(trip_update=trip_update(DAY), entity_id="a"),
        entity(trip_update={"trip": {"trip_id": "T1", "start_date": NEXT_DAY}}, entity_id="b"),
    )

    assert prefixes(found) == []


def test_a_trip_update_naming_no_start_date_names_no_day():
    """It is neither one of the days counted nor a day that could break the
    cancellation, because the clause counts `start_dates` and this one has
    none. The two cancelled days beside it are still two."""
    found = run(
        entity(trip_update=trip_update(DAY), entity_id="a"),
        entity(trip_update=trip_update(NEXT_DAY), entity_id="b"),
        entity(trip_update=trip_update(None, relationship="SCHEDULED"), entity_id="c"),
    )

    assert prefixes(found) == [reported()]


def test_a_descriptor_with_no_trip_id_is_not_grouped_with_anything():
    found = run(
        entity(
            trip_update={"trip": {"start_date": DAY, "schedule_relationship": TRIP["CANCELED"]}}
        ),
        entity(
            trip_update={
                "trip": {"start_date": NEXT_DAY, "schedule_relationship": TRIP["CANCELED"]}
            },
            entity_id="b",
        ),
    )

    assert prefixes(found) == []


def test_a_vehicle_position_is_not_a_trip_update():
    """The clause asks producers to provide *TripUpdates*, and a VehiclePosition
    carrying a cancelled descriptor is not one."""
    found = run(
        entity(vehicle=trip_update(DAY), entity_id="a"),
        entity(vehicle=trip_update(NEXT_DAY), entity_id="b"),
    )

    assert prefixes(found) == []


def cancelled_twice():
    return message(
        entity(trip_update=trip_update(DAY), entity_id="a"),
        entity(trip_update=trip_update(NEXT_DAY), entity_id="b"),
    )


def test_off_the_cycle_host_the_alerts_are_still_read_from_the_cycle():
    """Reading is not reporting. TripUpdates arriving under `-vp` while a `-tu`
    feed is present are examined, and the Alert covering them is found even
    though this message does not host the cycle's cross-feed rules."""
    now = cancelled_twice()
    alerts = message(entity(alert=alert(), entity_id="c"))
    ctx = context(role="vp", source="vp.pb", cycle=cycle(tu=message(), vp=now, sa=alerts))

    assert prefixes(check(now, ctx)) == []


def test_off_the_cycle_host_a_cancellation_no_alert_covers_is_still_reported():
    """The other half of the pair: the non-host message is not silenced, it is
    answered. Silence there would have been "I was not shown the Alerts"."""
    now = cancelled_twice()
    ctx = context(role="vp", source="vp.pb", cycle=cycle(tu=message(), vp=now))

    assert prefixes(check(now, ctx)) == [reported()]


def test_with_no_cycle_at_all_the_message_is_the_whole_scope():
    """A context carrying no cycle is one message standing alone, so its own
    Alerts are every Alert there is. That is a complete answer, and it is what
    makes "no cycle" different from "not this cycle's host"."""
    alone = message(
        entity(trip_update=trip_update(DAY), entity_id="a"),
        entity(trip_update=trip_update(NEXT_DAY), entity_id="b"),
        entity(alert=alert(), entity_id="c"),
    )

    assert prefixes(check(alone, context())) == []
    assert prefixes(check(cancelled_twice(), context())) == [reported()]


def test_every_trip_is_reported_once_in_first_appearance_order():
    found = run(
        entity(trip_update=trip_update(DAY, trip_id="T2"), entity_id="a"),
        entity(trip_update=trip_update(DAY, trip_id="T1"), entity_id="b"),
        entity(trip_update=trip_update(NEXT_DAY, trip_id="T1"), entity_id="c"),
        entity(trip_update=trip_update(NEXT_DAY, trip_id="T2"), entity_id="d"),
    )

    assert prefixes(found) == [reported("T2"), reported("T1")]


def test_the_occurrence_locates_the_first_trip_update_and_lists_the_days():
    found = occurrences(
        run(
            entity(vehicle={"trip": {"trip_id": "T9"}}, entity_id="other"),
            entity(trip_update=trip_update(DAY), entity_id="a"),
            entity(trip_update=trip_update(NEXT_DAY), entity_id="b"),
        )
    )

    assert [one.rule_id for one in found] == ["P006"]
    assert [one.context["entityPath"] for one in found] == ["entity[1].trip_update"]
    assert [one.context["tripId"] for one in found] == ["T1"]
    assert [one.context["startDates"] for one in found] == [[DAY, NEXT_DAY]]
    assert [one.context["entityIndexes"] for one in found] == [[1, 2]]
