"""S027: `cause_detail` without `cause`.

`Alert.cause` carries `[default = UNKNOWN_CAUSE]`, so an alert that names no
cause still reads one back. Presence is what the clause is about, and these
tests pin that an explicit `UNKNOWN_CAUSE` satisfies it while an absent field
does not.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s027 import check
from specfixtures import context, entity, message

#: `Cause.UNKNOWN_CAUSE = 1`, which is also the field's declared default.
UNKNOWN_CAUSE = 1
STRIKE = 4

TEXT = {"translation": [{"text": "Drivers are on strike"}]}


def found(**alert):
    feed = message(entity("a0", alert=dict(alert)))
    return list(check(feed, context()) or ())


def prefixes(**alert):
    return [occurrence.prefix for occurrence in found(**alert)]


def test_a_cause_detail_with_no_cause_reports():
    assert prefixes(cause_detail=TEXT) == ["alert ID a0 sets cause_detail without cause"]


def test_a_cause_detail_beside_a_cause_is_silent():
    """The satisfying fixture."""
    assert prefixes(cause_detail=TEXT, cause=STRIKE) == []


def test_an_explicitly_written_default_counts_as_included():
    """`cause` defaults to UNKNOWN_CAUSE, so the value alone cannot tell the two
    apart. A producer that wrote it has included it, which is what the clause
    asks for, however uninformative the value is."""
    assert prefixes(cause_detail=TEXT, cause=UNKNOWN_CAUSE) == []


def test_a_cause_with_no_detail_is_silent():
    """The implication runs one way only."""
    assert prefixes(cause=STRIKE) == []


def test_an_alert_with_neither_is_silent():
    assert prefixes(header_text=TEXT) == []


def test_the_occurrence_locates_the_alert():
    (occurrence,) = found(cause_detail=TEXT)

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].alert"


def test_an_empty_cause_detail_is_still_included():
    """Presence, not content. A `cause_detail` written with no translations is
    S031's finding and is still a `cause_detail` for this clause."""
    assert prefixes(cause_detail={}) == ["alert ID a0 sets cause_detail without cause"]
