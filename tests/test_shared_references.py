"""A reference the pinned proto lets resolve two ways, and how it is reported.

Three cohort H rules resolve an id that may point either into the realtime feed
or into the static one, and all three have to say the same two things when it
resolves nowhere: which table and which entity type were searched, and whether
the value the producer wrote is the `FeedEntity.id` the clause warns against.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules._shared.feed_index import index
from gtfs_rt_validator.rules._shared.references import SHAPE, STOP, stop_resolves
from rulefixtures import minimal, static_context, stop_rows
from specfixtures import context, entity, message


def feed_index(*entities):
    return index(message(*entities), context())


def test_a_stop_resolves_through_stops_txt(tmp_path: Path):
    ctx = context(static=static_context(tmp_path, minimal(stops=stop_rows({"A": 0}))))

    assert stop_resolves("A", ctx, feed_index())
    assert not stop_resolves("B", ctx, feed_index())


def test_a_stop_resolves_through_a_stop_entity_of_the_same_feed(tmp_path: Path):
    """The whole reason S043 and S046 are not E011: `stops.txt` is not the only
    place a `stop_id` may be defined at this pin."""
    ctx = context(static=static_context(tmp_path, minimal()))

    assert stop_resolves("B", ctx, feed_index(entity("e", stop={"stop_id": "B"})))


def test_an_unresolved_reference_names_the_table_and_the_entity_it_searched():
    found = STOP.unresolved("B", feed_index())

    assert found == "stop_id B is in neither stops.txt nor a Stop entity of this feed"


def test_an_unresolved_reference_says_when_the_value_is_a_feed_entity_id():
    """`1202#1` and `1261#1` exist to warn against exactly this substitution, so
    a bare "unresolvable" would throw away the finding they were written for."""
    found = SHAPE.unresolved("e", feed_index(entity("e", shape={"shape_id": "S1"})))

    assert found == (
        "shape_id e is in neither shapes.txt nor a Shape entity of this feed, and is the id "
        "of a FeedEntity rather than the shape_id inside one"
    )
