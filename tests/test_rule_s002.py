"""S002: two `FeedEntity` values in one `FeedMessage` sharing an `id`.

The clause is a `should`, so this is a WARNING, and the reason it is not an
error is written into the sentence after it: "Consequent FeedMessages may
contain FeedEntities with the same id", which is how a DIFFERENTIAL update
replaces one. Within a single message there is no such reading.

Not E052. That rule is about `VehicleDescriptor.id` being unique per vehicle,
a different field on a different message, and a feed can violate either without
the other. The overlap test next to this one shows it.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.spec.s002 import check
from specfixtures import context, entity, message, prefixes

TRIP_UPDATE = {"trip": {"trip_id": "T1"}}


def run(*entities):
    return check(message(*entities), context())


def test_distinct_ids_are_not_a_finding():
    found = run(entity("one", trip_update=TRIP_UPDATE), entity("two", trip_update=TRIP_UPDATE))

    assert prefixes(found) == []


def test_one_entity_is_never_a_finding():
    assert prefixes(run(entity("only", trip_update=TRIP_UPDATE))) == []


def test_two_entities_sharing_an_id_report_once():
    """Once per repeated id, not once per entity: the defect is the collision,
    and a feed with the same id on forty entities is one mistake."""
    found = run(entity("same", trip_update=TRIP_UPDATE), entity("same", trip_update=TRIP_UPDATE))

    assert prefixes(found) == ["entity ID same is claimed by 2 entities"]


def test_three_entities_sharing_an_id_still_report_once_and_count_them():
    found = run(*(entity("same", trip_update=TRIP_UPDATE) for _ in range(3)))

    assert prefixes(found) == ["entity ID same is claimed by 3 entities"]


def test_two_repeated_ids_report_in_first_seen_order():
    found = run(
        entity("b", trip_update=TRIP_UPDATE),
        entity("a", trip_update=TRIP_UPDATE),
        entity("b", trip_update=TRIP_UPDATE),
        entity("a", trip_update=TRIP_UPDATE),
    )

    assert prefixes(found) == [
        "entity ID b is claimed by 2 entities",
        "entity ID a is claimed by 2 entities",
    ]


def test_the_occurrence_names_every_entity_index_that_claimed_the_id():
    found = run(
        entity("same", trip_update=TRIP_UPDATE),
        entity("other", trip_update=TRIP_UPDATE),
        entity("same", trip_update=TRIP_UPDATE),
    )

    assert [occurrence.context["entityIndexes"] for occurrence in found] == [[0, 2]]


def test_every_occurrence_carries_this_rules_id():
    found = run(entity("same", trip_update=TRIP_UPDATE), entity("same", trip_update=TRIP_UPDATE))

    assert [occurrence.rule_id for occurrence in found] == ["S002"]
