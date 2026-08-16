"""S037: a `Shape` entity with no shape_id.

The clause is the clearest case in the proto of a comment being the normative
source *because* the wire format cannot be: the field is declared `optional`
and the comment on it says, in the same breath, that proto2's "Required is
Forever" rule is the only reason. A validator that took the wire cardinality as
the spec would enforce the opposite of what the file says.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s037 import check
from specfixtures import context, entity, message

LINE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


def found(*shapes):
    feed = message(*(entity(f"s{index}", shape=each) for index, each in enumerate(shapes)))
    return list(check(feed, context()) or ())


def prefixes(*shapes):
    return [occurrence.prefix for occurrence in found(*shapes)]


def test_a_shape_with_no_shape_id_reports():
    assert prefixes({"encoded_polyline": LINE}) == ["entity ID s0 shape has no shape_id"]


def test_a_shape_that_names_itself_is_silent():
    """The satisfying fixture."""
    assert prefixes({"shape_id": "RT1", "encoded_polyline": LINE}) == []


def test_an_empty_shape_id_was_still_written():
    """Presence, as everywhere else in the tier. A producer that wrote an empty
    id has specified the field, badly, and nothing here can tell that from a
    shape whose id genuinely is the empty string."""
    assert prefixes({"shape_id": "", "encoded_polyline": LINE}) == []


def test_the_occurrence_locates_the_shape():
    (occurrence,) = found({"encoded_polyline": LINE})

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].shape"


def test_an_entity_that_is_not_a_shape_is_out_of_scope():
    feed = message(entity("a0", alert={"cause": 3}))

    assert list(check(feed, context()) or ()) == []


def test_every_shape_in_a_feed_is_checked():
    assert prefixes({"encoded_polyline": LINE}, {"shape_id": "RT1"}, {}) == [
        "entity ID s0 shape has no shape_id",
        "entity ID s2 shape has no shape_id",
    ]
