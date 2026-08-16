"""S030, and the band it occupies that E033 leaves open.

E033 asks whether a selector specifies *anything*, and `direction_id` is not on
its list of specifiers. So the two rules separate on a selector that carries
`direction_id` beside another specifier and no `route_id`: E033 is satisfied and
the proto is not. That fixture is the one
`tests/test_spec_tier_does_not_shadow_the_jar.py` runs the jar over.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s030 import check
from specfixtures import context, entity, message


def found(*selectors):
    feed = message(entity("a0", alert={"informed_entity": [dict(s) for s in selectors]}))
    return list(check(feed, context()) or ())


def prefixes(*selectors):
    return [occurrence.prefix for occurrence in found(*selectors)]


def test_a_direction_id_with_no_route_id_reports():
    assert prefixes({"stop_id": "S1", "direction_id": 1}) == [
        "alert ID a0 informed_entity[0] sets direction_id 1 without route_id"
    ]


def test_a_direction_id_beside_a_route_id_is_silent():
    """The satisfying fixture, and the shape the clause asks for."""
    assert prefixes({"route_id": "R1", "direction_id": 0}) == []


def test_direction_id_zero_is_a_value_like_any_other():
    """proto2 presence, so the zero counts. A rule reading truthiness would
    miss every inbound direction in every feed."""
    assert prefixes({"stop_id": "S1", "direction_id": 0}) == [
        "alert ID a0 informed_entity[0] sets direction_id 0 without route_id"
    ]


def test_a_selector_with_no_direction_id_is_out_of_scope():
    """ "If provided" is the antecedent."""
    assert prefixes({"stop_id": "S1"}) == []


def test_the_occurrence_locates_the_selector():
    (occurrence,) = found({"stop_id": "S1"}, {"stop_id": "S2", "direction_id": 1})

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].alert.informed_entity[1]"


def test_each_offending_selector_reports_once():
    assert (
        len(
            prefixes(
                {"direction_id": 1},
                {"route_id": "R1", "direction_id": 1},
                {"stop_id": "S2", "direction_id": 0},
            )
        )
        == 2
    )


def test_a_bare_direction_id_reports_here_and_at_e033_as_well():
    """A selector carrying only a direction_id specifies nothing E033 counts, so
    both rules fire. That is the overlap this rule declares; the band that
    separates them is the test above, where a companion specifier satisfies
    E033 and the missing route_id still violates this clause."""
    assert len(prefixes({"direction_id": 1})) == 1


def test_an_alert_with_no_informed_entity_is_silent():
    feed = message(entity("a0", alert={"cause": 3}))

    assert list(check(feed, context()) or ()) == []
