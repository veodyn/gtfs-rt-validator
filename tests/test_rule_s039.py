"""S039: a `Shape` entity with no encoded_polyline.

The same sentence as S037 cites, on the other field. The two are separate clause
ids at separate lines, so they are separate rules and the citation gate resolves
each quote to the clause whose verdict names its rule.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s039 import check
from specfixtures import context, entity, message

LINE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


def found(*shapes):
    feed = message(*(entity(f"s{index}", shape=each) for index, each in enumerate(shapes)))
    return list(check(feed, context()) or ())


def prefixes(*shapes):
    return [occurrence.prefix for occurrence in found(*shapes)]


def test_a_shape_with_no_polyline_reports():
    assert prefixes({"shape_id": "RT1"}) == ["entity ID s0 shape has no encoded_polyline"]


def test_a_shape_that_carries_a_polyline_is_silent():
    """The satisfying fixture."""
    assert prefixes({"shape_id": "RT1", "encoded_polyline": LINE}) == []


def test_an_empty_polyline_was_still_written():
    """Presence. A polyline written as the empty string decodes to no points at
    all, which is S040's finding, and reporting it here as well would say the
    same thing twice about one shape."""
    assert prefixes({"shape_id": "RT1", "encoded_polyline": ""}) == []


def test_the_occurrence_locates_the_shape():
    (occurrence,) = found({"shape_id": "RT1"})

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].shape"


def test_a_shape_with_neither_field_reports_here_and_at_s037():
    """Two fields missing is two clauses violated, and each rule reports its
    own. The occurrences are distinguishable by id, not by text."""
    assert prefixes({}) == ["entity ID s0 shape has no encoded_polyline"]


def test_every_shape_in_a_feed_is_checked():
    assert len(prefixes({"shape_id": "A"}, {"shape_id": "B", "encoded_polyline": LINE}, {})) == 2
