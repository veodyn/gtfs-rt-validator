"""S026: impact_period intervals outside every communication_period interval.

The boundary that had to be settled is here: an impact interval sharing an
endpoint with a communication interval is contained, because `TimeRange`'s own
comment makes the interval `start <= t < end`, and containment of one closed
pair in another is `start <= start` and `end <= end`. An absent bound is an infinite one, which the
proto says in as many words, so the tests below exercise both.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s026 import check
from specfixtures import context, entity, message


def alert(impact, communication=None):
    built = {"impact_period": list(impact)}
    if communication is not None:
        built["communication_period"] = list(communication)
    return built


def found(impact, communication=None):
    feed = message(entity("a0", alert=alert(impact, communication)))
    return list(check(feed, context()) or ())


def prefixes(impact, communication=None):
    return [occurrence.prefix for occurrence in found(impact, communication)]


def test_an_impact_interval_outside_every_communication_interval_reports():
    assert prefixes([{"start": 300, "end": 400}], [{"start": 100, "end": 200}]) == [
        (
            "alert ID a0 impact_period[0] (300 to 400) "
            "is not fully contained in any communication_period"
        )
    ]


def test_an_impact_interval_inside_one_of_several_is_silent():
    """The satisfying fixture. "At least one" is the clause's own word."""
    communication = [{"start": 100, "end": 200}, {"start": 300, "end": 500}]

    assert prefixes([{"start": 350, "end": 400}], communication) == []


def test_shared_endpoints_are_contained():
    """The boundary. Equal bounds are containment, not an off-by-one."""
    assert prefixes([{"start": 100, "end": 200}], [{"start": 100, "end": 200}]) == []


def test_an_interval_straddling_two_adjacent_communication_intervals_reports():
    """ "Fully contained within at least one" is not "covered by the union", and
    the clause says the first. Two touching windows do not merge."""
    communication = [{"start": 100, "end": 200}, {"start": 200, "end": 300}]

    assert len(prefixes([{"start": 150, "end": 250}], communication)) == 1


def test_an_absent_communication_bound_is_infinite():
    """ "If missing, the interval starts at minus infinity", `:745`."""
    assert prefixes([{"start": 0, "end": 10}], [{"end": 200}]) == []
    assert prefixes([{"start": 900}], [{"start": 100}]) == []


def test_an_absent_impact_bound_is_infinite_too():
    """An unbounded impact fits in nothing but an unbounded communication."""
    assert len(prefixes([{"end": 200}], [{"start": 100, "end": 200}])) == 1
    assert prefixes([{"end": 200}], [{"end": 300}]) == []


def test_an_unbounded_interval_is_rendered_as_the_proto_describes_it():
    assert prefixes([{}], [{"start": 100, "end": 200}]) == [
        (
            "alert ID a0 impact_period[0] (minus infinity to plus infinity) "
            "is not fully contained in any communication_period"
        )
    ]


def test_each_offending_interval_reports_once():
    impact = [{"start": 150, "end": 160}, {"start": 300, "end": 400}, {"start": 500, "end": 600}]

    assert len(prefixes(impact, [{"start": 100, "end": 200}])) == 2


def test_the_occurrence_locates_the_interval():
    (occurrence,) = found([{"start": 300, "end": 400}], [{"start": 100, "end": 200}])

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].alert.impact_period[0]"


def test_no_communication_period_means_no_constraint():
    """ "If communication_period is specified" is the antecedent, and an alert
    that specifies none has said nothing this clause can contradict."""
    assert prefixes([{"start": 300, "end": 400}]) == []


def test_an_empty_communication_period_list_is_not_specified_either():
    """A repeated field with no occurrences is absent on the wire, so this is
    the same feed as the one above and must give the same answer."""
    assert prefixes([{"start": 300, "end": 400}], []) == []


def test_an_alert_with_no_impact_period_is_silent():
    assert prefixes([], [{"start": 100, "end": 200}]) == []
