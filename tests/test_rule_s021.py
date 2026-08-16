"""S021, the one rule in the spec tier that reads `ctx.previous`.

What `ctx.previous` means is settled by `runner/context.py` and enforced by
`tests/test_runner_rules.py::test_previous_is_per_role_rather_than_global`: it
is the previous message **of the same role**, never whatever the runner read
last, and it is `None` until a second message of that role has been validated.
So S021 compares a TripUpdates snapshot against the TripUpdates snapshot before
it, and never against a VehiclePositions one that happened to arrive between
them. Nothing here re-tests the runner; these tests exercise the rule's own
predicate over a context whose `previous` is set the way the runner sets it.

The static feed is built with `frequencies.txt` giving T1 `exact_times=0`, which
is the clause's antecedent, and the first test asserts that precondition rather
than trusting it.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s021 import check
from gtfsfixtures import minimal_tables
from rulefixtures import static_context
from specfixtures import context, entity, message

#: `T1` is the fixture feed's one trip and `T2` is not in `trips.txt` at all;
#: only the exact_times value distinguishes the two frequency rows.
FREQUENCY_ZERO = {
    "trip_id": "T1",
    "start_time": "06:00:00",
    "end_time": "10:00:00",
    "headway_secs": "600",
    "exact_times": "0",
}


def frequency_static(tmp_path: Path):
    tables = minimal_tables()
    tables["frequencies.txt"] = [dict(FREQUENCY_ZERO)]
    return static_context(tmp_path, tables)


#: Two runs of the one frequency-based trip on one service date. This is what
#: exact_times=0 describes: `TripDescriptor.trip_id`'s own comment says that for
#: a frequency-based trip `start_time` and `start_date` "might also be
#: necessary" to identify the trip, so these are two instances rather than one
#: instance described twice.
EIGHT = {"trip_id": "T1", "start_date": "20260815", "start_time": "08:00:00"}
TEN_PAST = {"trip_id": "T1", "start_date": "20260815", "start_time": "08:10:00"}
TWENTY_PAST = {"trip_id": "T1", "start_date": "20260815", "start_time": "08:20:00"}


def feed(**trip):
    return message(entity(trip_update={"trip": dict(trip)}))


def feed_of(*trips):
    """One message carrying a descriptor per mapping, each in its own entity."""
    return message(
        *[entity(f"e{index}", trip_update={"trip": dict(trip)}) for index, trip in enumerate(trips)]
    )


def found(tmp_path: Path, before, now):
    ctx = context(static=frequency_static(tmp_path), previous=before)
    return list(check(now, ctx) or ())


def prefixes(tmp_path: Path, before, now):
    return [occurrence.prefix for occurrence in found(tmp_path, before, now)]


def test_the_fixture_really_makes_the_trip_frequency_based(tmp_path: Path):
    """The clause's antecedent is exact_times=0, so a feed that did not make T1
    frequency-based would leave every test below vacuously green."""
    assert frequency_static(tmp_path).exact_times_zero_trip_ids == frozenset({"T1"})


def test_a_start_time_that_moved_between_two_messages_reports(tmp_path: Path):
    before = feed(trip_id="T1", start_date="20260814", start_time="06:10:00")
    now = feed(trip_id="T1", start_date="20260814", start_time="06:20:00")

    assert prefixes(tmp_path, before, now) == [
        "trip_id T1 start_date 20260814 start_time changed from 06:10:00 to 06:20:00"
    ]


def test_the_occurrence_locates_the_descriptor_that_moved(tmp_path: Path):
    before = feed(trip_id="T1", start_time="06:10:00")
    now = feed(trip_id="T1", start_time="06:20:00")

    (occurrence,) = found(tmp_path, before, now)

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].trip_update.trip"


def test_a_start_time_that_did_not_move_is_silent(tmp_path: Path):
    """The satisfying fixture."""
    before = feed(trip_id="T1", start_date="20260814", start_time="06:10:00")
    now = feed(trip_id="T1", start_date="20260814", start_time="06:10:00")

    assert prefixes(tmp_path, before, now) == []


def test_the_first_message_of_a_role_has_no_previous_and_reports_nothing(tmp_path: Path):
    """`ctx.previous` is `None` until a second message of the same role has been
    validated, which is the runner's contract rather than this rule's choice."""
    now = feed(trip_id="T1", start_time="06:20:00")

    assert list(check(now, context(static=frequency_static(tmp_path))) or ()) == []


def test_a_different_start_date_is_a_different_trip_instance(tmp_path: Path):
    """The clause is about "this frequency-based trip", which is one instance.
    Two service dates are two instances and their start_times are unrelated."""
    before = feed(trip_id="T1", start_date="20260814", start_time="06:10:00")
    now = feed(trip_id="T1", start_date="20260815", start_time="06:20:00")

    assert prefixes(tmp_path, before, now) == []


def test_two_instances_of_one_trip_that_both_stood_still_are_silent(tmp_path: Path):
    """Two runs of one exact_times=0 trip on one date, unchanged between the two
    messages. Nothing moved, so nothing is reported. `(trip_id, start_date)`
    alone does not name one of the two, which is why the second descriptor must
    not be compared against the first descriptor's value."""
    before = feed_of(EIGHT, TEN_PAST)
    now = feed_of(EIGHT, TEN_PAST)

    assert prefixes(tmp_path, before, now) == []


def test_a_move_inside_a_two_instance_message_is_not_attributed(tmp_path: Path):
    """The narrowing's cost, stated rather than hidden. One of the two runs is
    now at 08:20 and the descriptors do not say which: the 08:10 run may have
    moved, or it may have ended and an 08:20 run begun. The clause constrains an
    established instance's value, and this message establishes which instance is
    which nowhere, so the rule declines to guess."""
    before = feed_of(EIGHT, TEN_PAST)
    now = feed_of(EIGHT, TWENTY_PAST)

    assert prefixes(tmp_path, before, now) == []


def test_a_second_instance_appearing_is_not_a_move(tmp_path: Path):
    """A frequency-based trip runs repeatedly, so a message may state a run the
    message before it did not. A start_time nothing established is not one that
    changed."""
    before = feed_of(EIGHT)
    now = feed_of(EIGHT, TEN_PAST)

    assert prefixes(tmp_path, before, now) == []


def test_one_instance_stated_twice_with_one_value_reports_once(tmp_path: Path):
    """Two descriptors agreeing on the start_time describe one instance twice,
    not two instances, so the move they agree on is one finding. The duplicate
    descriptor itself is S003's finding, not this rule's."""
    before = feed_of(EIGHT)
    now = feed_of(TWENTY_PAST, TWENTY_PAST)

    assert prefixes(tmp_path, before, now) == [
        "trip_id T1 start_date 20260815 start_time changed from 08:00:00 to 08:20:00"
    ]


def test_a_trip_that_is_not_frequency_based_is_out_of_scope(tmp_path: Path):
    """T2 is in no frequencies row, so nothing established its start_time and
    the clause's "this frequency-based trip" does not name it."""
    before = feed(trip_id="T2", start_time="06:10:00")
    now = feed(trip_id="T2", start_time="06:20:00")

    assert prefixes(tmp_path, before, now) == []


def test_an_exact_times_one_trip_is_out_of_scope(tmp_path: Path):
    """The fixture feed's own frequencies row, unaltered, gives T1
    exact_times=1, where E019 constrains start_time instead."""
    before = feed(trip_id="T1", start_time="06:10:00")
    now = feed(trip_id="T1", start_time="06:20:00")
    ctx = context(static=static_context(tmp_path), previous=before)

    assert list(check(now, ctx) or ()) == []


def test_a_start_time_that_was_never_established_is_not_a_change(tmp_path: Path):
    """ "Once established" is the clause's own precondition. A producer that
    omitted start_time and then supplied one has established it, not moved it."""
    before = feed(trip_id="T1")
    now = feed(trip_id="T1", start_time="06:20:00")

    assert prefixes(tmp_path, before, now) == []


def test_dropping_the_start_time_is_not_reported_here(tmp_path: Path):
    """The clause constrains the value, and a message that carries none states
    no value to compare. E006 is where a missing start_time is reported."""
    before = feed(trip_id="T1", start_time="06:10:00")
    now = feed(trip_id="T1")

    assert prefixes(tmp_path, before, now) == []


def test_a_vehicle_position_descriptor_is_compared_too(tmp_path: Path):
    """A TripDescriptor rides on three messages and the clause is about the
    descriptor's field, not about TripUpdates."""
    before = message(entity(vehicle={"trip": {"trip_id": "T1", "start_time": "06:10:00"}}))
    now = message(entity(vehicle={"trip": {"trip_id": "T1", "start_time": "06:20:00"}}))

    assert prefixes(tmp_path, before, now) == [
        "trip_id T1 start_time changed from 06:10:00 to 06:20:00"
    ]


def test_the_two_messages_are_resolved_separately_rather_than_twice_over_one(tmp_path: Path):
    """The memo trap this rule is the only one to meet: both walks run in one
    context, so the second needs a scope of its own or it is handed the first
    message's records and every comparison is a value against itself."""
    before = feed(trip_id="T1", start_time="06:10:00")
    now = feed(trip_id="T1", start_time="06:20:00")
    ctx = context(static=frequency_static(tmp_path), previous=before)

    assert len(list(check(now, ctx) or ())) == 1
    assert len(ctx.memo) == 2
