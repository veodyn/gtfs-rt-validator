"""S045: a selected trip that a REPLACEMENT TripUpdate has already taken.

The `TripModifications` is what replaces the trip, so a `TripUpdate` already
claiming `schedule_relationship=REPLACEMENT` for the same `trip_id` is two
producers of the same replacement, and the clause forbids it outright.

Only the REPLACEMENT relationship counts. A trip with an ordinary `TripUpdate`
is the normal case for a detour, since the modification changes the stops of a
trip that is otherwise running, and reporting that would fire on almost every
correct feed that carries both messages.

**The scope is the cycle.** "Already exist" is about the feed at an instant, and
this project's feed at an instant is one message per role, so every test here
runs the rule over a `CombinedFeed` the way the runner hands it one. A one-role
cycle is what a single-file run produces and is the shape most of these use; the
two-role tests at the bottom are the ones that would pass under a message-scoped
rule and say nothing.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import SOURCE_FILE_KEY
from gtfs_rt_validator.rules.spec.s045 import check
from specfixtures import cycle_of
from tripmodfixtures import context, entity, message, paths, prefixes, relationship
from tripmodfixtures import trip_modifications as tm

TAKEN = "trip_id {} already has a TripUpdate with schedule_relationship REPLACEMENT"


def trip_update(trip_id: str, name: str | None = None) -> dict[str, object]:
    trip: dict[str, object] = {"trip_id": trip_id}
    if name is not None:
        trip["schedule_relationship"] = relationship(name)
    return {"trip": trip}


def one_role(*entities):
    """A cycle of one message, which is what a single-file run produces."""
    feed = message(*entities)
    return feed, context(cycle=cycle_of({"rt": feed}))


def run(*entities):
    """Materialised, because `check` is a generator and every test reads it
    twice: once for the prefixes and once for the paths."""
    feed, ctx = one_role(*entities)
    return list(check(feed, ctx) or ())


def split(tu_entities, sa_entities):
    """One cycle, two role files. The rule is invoked on the host, `tu`."""
    tu_feed, sa_feed = message(*tu_entities), message(*sa_entities)
    cycle = cycle_of({"tu": tu_feed, "sa": sa_feed})
    return tu_feed, context(cycle=cycle, role="tu", source="tu.pb")


def test_a_selected_trip_with_a_replacement_trip_update_is_reported():
    found = run(entity("tu", trip_update=trip_update("T1", "REPLACEMENT")), tm(trip_ids=["T1"]))

    assert prefixes(found) == [TAKEN.format("T1")]


def test_the_occurrence_locates_the_selected_trip():
    found = run(entity("tu", trip_update=trip_update("T1", "REPLACEMENT")), tm(trip_ids=["T1"]))

    assert paths(found) == ["entity[1].trip_modifications.selected_trips[0].trip_ids[0]"]


def test_a_selected_trip_with_an_ordinary_trip_update_is_not_reported():
    """A detour modifies a trip that is running, so its `TripUpdate` is the
    normal case rather than the defect."""
    assert prefixes(run(entity("tu", trip_update=trip_update("T1")), tm(trip_ids=["T1"]))) == []


def test_a_selected_trip_with_no_trip_update_at_all_is_not_reported():
    assert prefixes(run(tm(trip_ids=["T1"]))) == []


def test_the_trip_update_may_follow_the_modification_that_selects_the_trip():
    """`FeedEntity` ordering is not specified, so "already exist" is about the
    cycle rather than about the order entities appear in it."""
    found = run(tm(trip_ids=["T1"]), entity("tu", trip_update=trip_update("T1", "REPLACEMENT")))

    assert prefixes(found) == [TAKEN.format("T1")]


def test_each_offending_trip_id_of_a_selected_trips_is_reported():
    found = run(
        entity("a", trip_update=trip_update("T1", "REPLACEMENT")),
        entity("b", trip_update=trip_update("T3", "REPLACEMENT")),
        tm(trip_ids=["T1", "T2", "T3"]),
    )

    assert prefixes(found) == [TAKEN.format("T1"), TAKEN.format("T3")]
    assert paths(found) == [
        "entity[2].trip_modifications.selected_trips[0].trip_ids[0]",
        "entity[2].trip_modifications.selected_trips[0].trip_ids[2]",
    ]


def test_a_conflict_split_across_two_role_files_of_one_cycle_is_reported():
    """The rule's scope is the cycle, not the message, and it means it. A producer
    publishing its `TripModifications` alongside its alerts and its REPLACEMENT
    `TripUpdate` in `-tu` has written exactly the feed the clause forbids, and a
    rule that indexed only the message it was handed would see neither half."""
    feed, ctx = split(
        [entity("tu", trip_update=trip_update("T1", "REPLACEMENT"))], [tm(trip_ids=["T1"])]
    )

    assert prefixes(check(feed, ctx)) == [TAKEN.format("T1")]


def test_a_finding_names_the_file_the_modification_is_in_and_not_the_host():
    """The rule fires once per cycle, on the host, so an occurrence stamped with
    the context's own source would send a reader to the wrong file."""
    feed, ctx = split(
        [entity("tu", trip_update=trip_update("T1", "REPLACEMENT"))], [tm(trip_ids=["T1"])]
    )
    (found,) = check(feed, ctx)

    assert found.context[SOURCE_FILE_KEY] == "sa.pb"


def test_only_the_host_of_a_cycle_reports_it():
    """`ctx.combined` is `None` on every message but the host's, so the cycle is
    checked once however many roles carry a `TripModifications`.

    The guest below is handed the *same* cycle the host is, which is the whole
    of the split: seeing the cycle and reporting for it are different questions,
    and a cross-feed rule is answered only on the second.
    """
    tu_feed, ctx = split(
        [entity("tu", trip_update=trip_update("T1", "REPLACEMENT"))], [tm(trip_ids=["T1"])]
    )
    guest = context(cycle=ctx.cycle, role="sa", source="sa.pb")

    assert guest.cycle is ctx.cycle
    assert check(message(tm(trip_ids=["T1"])), guest) is None
    assert ctx.combined is not None
    assert prefixes(check(tu_feed, ctx)) == [TAKEN.format("T1")]
