"""S025: the deprecated `Alert.active_period`.

The clause and the `[deprecated = true]` option say the same thing at the same
site, so the rule reads the option rather than trusting the sentence, and the
first test asserts the pin still carries it. A field that stopped being
deprecated would otherwise leave a rule quietly firing on a supported field.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s025 import DEPRECATED_FIELD, check
from specfixtures import context, entity, message

RANGE = {"start": 1_700_000_000, "end": 1_700_003_600}


def found(*alerts):
    feed = message(*(entity(f"a{index}", alert=each) for index, each in enumerate(alerts)))
    return list(check(feed, context()) or ())


def prefixes(*alerts):
    return [occurrence.prefix for occurrence in found(*alerts)]


def test_the_pin_still_marks_the_field_deprecated():
    """`repeated TimeRange active_period = 1 [deprecated = true]` at `:629`."""
    assert DEPRECATED_FIELD == "active_period"


def test_an_alert_that_sets_active_period_reports():
    assert prefixes({"active_period": [RANGE]}) == [
        "alert ID a0 sets active_period, which this pin deprecates"
    ]


def test_an_alert_with_two_ranges_reports_once():
    """The defect is using the field, not each range in it."""
    assert prefixes({"active_period": [RANGE, RANGE]}) == [
        "alert ID a0 sets active_period, which this pin deprecates"
    ]


def test_the_occurrence_locates_the_alert():
    (occurrence,) = found({"active_period": [RANGE]})

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].alert"


def test_the_replacement_fields_are_silent():
    """The satisfying fixture. `communication_period` and `impact_period` are
    what the deprecation points at."""
    assert prefixes({"communication_period": [RANGE], "impact_period": [RANGE]}) == []


def test_an_alert_with_no_periods_at_all_is_silent():
    assert prefixes({"cause": 3}) == []


def test_every_alert_in_a_feed_is_checked():
    assert prefixes({"active_period": [RANGE]}, {"cause": 3}, {"active_period": [RANGE]}) == [
        "alert ID a0 sets active_period, which this pin deprecates",
        "alert ID a2 sets active_period, which this pin deprecates",
    ]
