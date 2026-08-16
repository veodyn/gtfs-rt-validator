"""E039, a FULL_DATASET feed carrying `entity.is_deleted`.

Six of the assertions below are upstream's own, ported case by case from the
checkout at `jar-build/upstream/`, `gtfs-realtime-validator-lib/src/test/java/
edu/usf/cutr/gtfsrtvalidator/lib/test/rules/HeaderValidatorTest.java:97-155`
(`testE039`), rather than from a second-hand summary of it. The
summary describes the first two cases as "no entities", and they are not: the
`FeedMessageTest` base class leaves one entity, id `TEST_ENTITY` and no
`is_deleted`, in `feedMessageBuilder` before any test runs, and `testE039` only
clears it before its last case. Upstream's six messages therefore carry 1, 1, 2,
3, 4 and 1 entities, which is what `UPSTREAM_CASES` states. The counts come out
the same either way, but a port that believed the summary would be testing a
different feed than the jar was.

Upstream counts occurrences and never looks at a prefix, so every prefix
assertion here is ours, as are the three cases below `UPSTREAM_CASES`: an absent
`incrementality`, which is the whole trap in this rule, `is_deleted=false`,
and more than one entity carrying the field.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from gtfs_rt_validator.proto.decode import Msg, decode
from gtfs_rt_validator.proto.encode import encode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.proto.schema_current import SCHEMA as CURRENT
from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.upstream.e039 import RULE_ID, check

#: `FeedMessageTest.ENTITY_ID`.
ENTITY_ID = "TEST_ENTITY"

#: `FeedHeader.Incrementality`, as both schemas declare it.
FULL_DATASET = 0
DIFFERENTIAL = 1

#: One entity as upstream's `feedEntityBuilder` leaves it, with and without the
#: field this rule is about.
PLAIN: dict[str, object] = {"id": ENTITY_ID}
DELETED: dict[str, object] = {"id": ENTITY_ID, "is_deleted": True}

#: `testE039` in order: incrementality, the entity list built so far, and the
#: number of E039 occurrences upstream asserts.
UPSTREAM_CASES: tuple[tuple[int, tuple[dict[str, object], ...], int], ...] = (
    (FULL_DATASET, (PLAIN,), 0),
    (DIFFERENTIAL, (PLAIN,), 0),
    (FULL_DATASET, (PLAIN, PLAIN), 0),
    (DIFFERENTIAL, (PLAIN, PLAIN, PLAIN), 0),
    (FULL_DATASET, (PLAIN, PLAIN, PLAIN, DELETED), 1),
    (DIFFERENTIAL, (DELETED,), 0),
)


def feed(
    header: dict[str, object],
    entities: Sequence[dict[str, object]] = (),
    schema: object = V2015,
) -> Msg:
    """One decoded `FeedMessage`, through the real encoder and decoder.

    The 2015 schema by default, which is the one upstream compiles against and
    the one `--compat` decodes with. `schema` is a parameter only so that one
    test below can hand the same rule a message decoded the other way.
    """
    return decode(encode({"header": header, "entity": list(entities)}, schema), schema)


def occurrences(message: Msg) -> list:
    """What the rule found, as a list. `None` is the legal "nothing" too."""
    return list(check(message, None) or ())


def a_feed(entities: Sequence[dict[str, object]], **header: object) -> Msg:
    return feed({"gtfs_realtime_version": "1.0", **header}, entities)


@pytest.mark.parametrize(("incrementality", "entities", "expected"), UPSTREAM_CASES)
def test_upstream_cases(
    incrementality: int, entities: Sequence[dict[str, object]], expected: int
) -> None:
    assert len(occurrences(a_feed(entities, incrementality=incrementality))) == expected


def test_an_absent_incrementality_is_scanned_too() -> None:
    """`getIncrementality()` is read with no `has` test at `HeaderValidator.java:64`
    and FULL_DATASET is the protobuf default, so a header that never mentions
    incrementality takes the same branch a FULL_DATASET one does. Upstream's own
    test has to set DIFFERENTIAL explicitly to get zero, which is the tell."""
    found = occurrences(a_feed([DELETED]))

    assert len(found) == 1
    assert found[0].rule_id == RULE_ID


def test_the_prefix_names_the_entity_and_renders_the_boolean_java_style() -> None:
    """`"entity ID " + getId() + " has is_deleted=" + getIsDeleted()`,
    `HeaderValidator.java:68`. Java concatenates a `boolean` as lower-case
    `true`, where Python's `str(True)` would put a capital there."""
    (found,) = occurrences(a_feed([DELETED], incrementality=FULL_DATASET))

    assert found.prefix == "entity ID TEST_ENTITY has is_deleted=true"


def test_is_deleted_false_is_still_reported() -> None:
    """The condition is `hasIsDeleted()`, not `getIsDeleted()`. A FULL_DATASET
    feed that sets the field to false has still included a field it should not
    have, and the value goes into the prefix as Java renders it."""
    entity: dict[str, object] = {"id": "E1", "is_deleted": False}

    (found,) = occurrences(a_feed([entity], incrementality=FULL_DATASET))

    assert found.prefix == "entity ID E1 has is_deleted=false"


def test_one_occurrence_per_entity_in_entity_order() -> None:
    entities: list[dict[str, object]] = [
        {"id": "first", "is_deleted": True},
        {"id": "quiet"},
        {"id": "second", "is_deleted": False},
    ]

    found = occurrences(a_feed(entities, incrementality=FULL_DATASET))

    assert [each.prefix for each in found] == [
        "entity ID first has is_deleted=true",
        "entity ID second has is_deleted=false",
    ]
    assert [each.context[ENTITY_PATH_KEY] for each in found] == ["entity[0]", "entity[2]"]


def test_the_occurrence_carries_the_entity_id_and_the_value() -> None:
    """Ours, and modern-mode only: `--compat` writes the prefix alone."""
    (found,) = occurrences(a_feed([DELETED], incrementality=FULL_DATASET))

    assert found.context["entityId"] == ENTITY_ID
    assert found.context["isDeleted"] is True


def test_the_rule_reads_the_same_fields_under_either_schema() -> None:
    """Mode is the descriptor the message was decoded with, never a branch in
    here: both schemas declare `incrementality` and `is_deleted` at the same
    numbers, so the rule cannot tell which one it was handed."""
    message = feed(
        {"gtfs_realtime_version": "2.0", "incrementality": FULL_DATASET}, [DELETED], CURRENT
    )

    assert [each.prefix for each in occurrences(message)] == [
        "entity ID TEST_ENTITY has is_deleted=true"
    ]
