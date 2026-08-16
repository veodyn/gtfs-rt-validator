"""S028: `effect_detail` without `effect`.

`Alert.effect` carries `[default = UNKNOWN_EFFECT]`, so an alert that names no
effect still reads one back. Presence is what the clause is about, and these
tests pin that an explicit `UNKNOWN_EFFECT` satisfies it while an absent field
does not.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s028 import check
from specfixtures import context, entity, message

#: `Effect.UNKNOWN_EFFECT = 8`, which is also the field's declared default.
UNKNOWN_EFFECT = 8
DETOUR = 4

TEXT = {"translation": [{"text": "Buses are running via Elm Street"}]}


def found(**alert):
    feed = message(entity("a0", alert=dict(alert)))
    return list(check(feed, context()) or ())


def prefixes(**alert):
    return [occurrence.prefix for occurrence in found(**alert)]


def test_an_effect_detail_with_no_effect_reports():
    assert prefixes(effect_detail=TEXT) == ["alert ID a0 sets effect_detail without effect"]


def test_an_effect_detail_beside_an_effect_is_silent():
    """The satisfying fixture."""
    assert prefixes(effect_detail=TEXT, effect=DETOUR) == []


def test_an_explicitly_written_default_counts_as_included():
    """`effect` defaults to UNKNOWN_EFFECT, so the value alone cannot tell the two
    apart. A producer that wrote it has included it, which is what the clause
    asks for, however uninformative the value is."""
    assert prefixes(effect_detail=TEXT, effect=UNKNOWN_EFFECT) == []


def test_an_effect_with_no_detail_is_silent():
    """The implication runs one way only."""
    assert prefixes(effect=DETOUR) == []


def test_an_alert_with_neither_is_silent():
    assert prefixes(header_text=TEXT) == []


def test_the_occurrence_locates_the_alert():
    (occurrence,) = found(effect_detail=TEXT)

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].alert"


def test_an_empty_effect_detail_is_still_included():
    """Presence, not content. A `effect_detail` written with no translations is
    S031's finding and is still an `effect_detail` for this clause."""
    assert prefixes(effect_detail={}) == ["alert ID a0 sets effect_detail without effect"]
