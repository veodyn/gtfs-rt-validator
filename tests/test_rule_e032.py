"""E032, against upstream's own `testE032`.

Upstream asserts counts only; the prefix is ours, read off
`TripDescriptorValidator.java:196`. There is no `checkE032` to point at: the
condition and the text are inline in the `else` of the informed_entity test that
opens the alert half.
"""

from __future__ import annotations

from pathlib import Path

from gtfs_rt_validator.rules.upstream.e032 import check
from rulefixtures import entity, prefixes
from tripfixtures import alert, run, selector


def found(tmp_path: Path, *entities) -> list[str]:
    return prefixes(run(check, tmp_path, *entities))


def test_an_alert_with_no_informed_entity_reports_once(tmp_path: Path) -> None:
    """Upstream, testE032's first stage, `expected.put(E032, 1)`. The prefix is
    ours."""
    assert found(tmp_path, entity(alert=alert())) == [
        "alert ID TEST_ENTITY does not have an informed_entity"
    ]


def test_an_alert_with_one_specifier_reports_nothing(tmp_path: Path) -> None:
    """Upstream, testE032: one informed_entity carrying route_id `A`,
    `expected.clear()`."""
    assert found(tmp_path, entity(alert=alert(selector(route_id="A")))) == []


# --- ours ----------------------------------------------------------------


def test_the_prefix_names_the_feed_entitys_own_id(tmp_path: Path) -> None:
    """Ours. `entity.getId()`, not anything from the alert."""
    assert found(tmp_path, entity(alert=alert(), entity_id="ALERT_1")) == [
        "alert ID ALERT_1 does not have an informed_entity"
    ]


def test_an_entity_with_no_alert_reports_nothing(tmp_path: Path) -> None:
    """Ours. The whole half is gated on `hasAlert()` at `:177`, so an entity
    carrying only a TripUpdate is not an alert with no informed_entity."""
    assert found(tmp_path, entity(trip_update={"trip": {}})) == []


def test_one_occurrence_per_alert_and_one_alert_per_entity(tmp_path: Path) -> None:
    """Ours. `FeedEntity.alert` is singular, so two empty alerts need two
    entities, and each reports once."""
    found_prefixes = found(
        tmp_path, entity(alert=alert(), entity_id="one"), entity(alert=alert(), entity_id="two")
    )

    assert found_prefixes == [
        "alert ID one does not have an informed_entity",
        "alert ID two does not have an informed_entity",
    ]
