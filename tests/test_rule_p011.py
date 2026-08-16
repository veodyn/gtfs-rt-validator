"""P011: an Alert naming an exact_times=1 trip whose start_time is off the headway.

The predicate is E019's, applied at the third site E019 does not have: an
`Alert.informed_entity[].trip`. `rules/upstream/e019.py:check` reads
`entity.has("trip_update")` and `entity.has("vehicle")` and nothing else, which
is why P011 declares no upstream overlap, and one test below asserts that this
rule stays off both of E019's sites.

The two tests that matter most are `test_the_occurrence_names_the_declared_start_time`
and `test_the_candidate_rendering_is_not_e019s_inlined_typo`. Both pin a
deliberate divergence from E019, whose two compat artefacts P011 must not
reproduce: reporting the last candidate tried, and the `% 360` in the inlined
`String.format`. Each test says which E019 behaviour it is refusing.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.rules.practice.p011 import check
from gtfs_rt_validator.rules.upstream.e019 import vehicle_position_clock
from specfixtures import entity, feed_context, message, minimal, prefixes

#: One `frequencies.txt` row, as the fixture feed's own table writes them.
PERIOD = {
    "trip_id": "T1",
    "start_time": "06:00:00",
    "end_time": "10:00:00",
    "headway_secs": "600",
    "exact_times": "1",
}


def period(start: str, end: str = "10:00:00", headway: str = "600") -> dict[str, str]:
    return {**PERIOD, "start_time": start, "end_time": end, "headway_secs": headway}


def tables(periods: tuple[dict[str, str], ...], exact_times: str):
    built = minimal()
    rows = list(periods) if periods else [dict(PERIOD)]
    built["frequencies.txt"] = [{**row, "exact_times": exact_times} for row in rows]
    return built


def alert(trip_id: str = "T1", start_time: str | None = "06:05:00") -> dict[str, object]:
    trip: dict[str, object] = {"trip_id": trip_id}
    if start_time is not None:
        trip["start_time"] = start_time
    return {"informed_entity": [{"trip": trip}]}


def run(tmp_path, *entities, periods: tuple[dict[str, str], ...] = (), exact_times: str = "1"):
    context = feed_context(tmp_path, tables(periods, exact_times))
    return check(message(*entities), context)


def reported(start_time: str, declared: str) -> str:
    """The one occurrence text, so every assertion below spells it once."""
    return (
        f"trip_id T1 start_time {start_time} is not an exact multiple of headway_secs after "
        f"the start of any exact_times=1 period; frequencies.txt declares {declared}"
    )


def test_a_start_time_off_the_headway_is_reported(tmp_path):
    found = run(tmp_path, entity(alert=alert(start_time="06:05:00")))

    assert prefixes(found) == [reported("06:05:00", "06:00:00 every 600 seconds")]


def test_a_start_time_on_the_headway_is_silent(tmp_path):
    """The conformant twin: the same alert, five minutes later."""
    assert prefixes(run(tmp_path, entity(alert=alert(start_time="06:10:00")))) == []


def test_the_periods_own_start_time_is_a_multiple_of_zero_headways(tmp_path):
    assert prefixes(run(tmp_path, entity(alert=alert(start_time="06:00:00")))) == []


def test_the_end_of_the_period_is_exclusive(tmp_path):
    """`for (int t = start; t < end; t += headway)`, which
    `_shared/frequencies.start_times` is. 10:00:00 is a multiple of the headway
    and is still not a candidate, because the period ended."""
    assert len(run(tmp_path, entity(alert=alert(start_time="10:00:00")))) == 1


def test_a_trip_absent_from_frequencies_txt_is_out_of_scope(tmp_path):
    assert prefixes(run(tmp_path, entity(alert=alert(trip_id="T2")))) == []


def test_an_exact_times_zero_trip_is_out_of_scope(tmp_path):
    """The clause is about the `exact_time=1` interval. A trip with
    `exact_times=0` has no fixed departure to be a multiple of."""
    assert prefixes(run(tmp_path, entity(alert=alert()), exact_times="0")) == []


def test_a_selector_stating_no_start_time_is_out_of_scope(tmp_path):
    """The clause's antecedent is "when `trip_id` and `start_time` are within"
    the interval, so a descriptor naming no start_time is outside it. E019 reads
    `getStartTime()` unguarded and reports such a descriptor against every
    candidate; that is point 4 of `e019.py`'s docstring and P011 does not
    reproduce it."""
    assert prefixes(run(tmp_path, entity(alert=alert(start_time=None)))) == []


def test_a_selector_with_no_trip_at_all_is_out_of_scope(tmp_path):
    found = run(tmp_path, entity(alert={"informed_entity": [{"route_id": "R1"}]}))

    assert prefixes(found) == []


def test_the_occurrence_names_the_declared_start_time(tmp_path):
    """**Divergence from E019, one of two.** `e019._search` reports whatever
    candidate its loop last assigned, so over this period it would say
    09:50:00. P011 reports the period's own declared start_time."""
    (found,) = run(tmp_path, entity(alert=alert(start_time="06:05:00")))

    assert "06:00:00 every 600 seconds" in found.prefix
    assert "09:50:00" not in found.prefix


def test_the_candidate_rendering_is_not_e019s_inlined_typo(tmp_path):
    """**Divergence from E019, two of two.** `e019.vehicle_position_clock`
    inlines `startTime % 360` where the minutes belong, so it renders a period
    starting at 06:01:00 as 06:60:00 and that period's 06:11:00 candidate as
    06:300:00. P011 renders with `_shared/times.seconds_after_midnight_to_clock`,
    so 06:11:00 matches its candidate and is silent."""
    assert vehicle_position_clock(6 * 3600 + 60) == "06:60:00"

    found = run(tmp_path, entity(alert=alert(start_time="06:11:00")), periods=(period("06:01:00"),))

    assert prefixes(found) == []


def test_a_period_start_that_e019_would_misrender_is_named_correctly(tmp_path):
    found = run(tmp_path, entity(alert=alert(start_time="06:05:00")), periods=(period("06:01:00"),))

    assert prefixes(found) == [reported("06:05:00", "06:01:00 every 600 seconds")]


def test_every_declared_period_is_named(tmp_path):
    """E019 keeps one pair of locals across every period. This names them all,
    so a two-period trip says what both periods were."""
    found = run(
        tmp_path,
        entity(alert=alert(start_time="13:05:00")),
        periods=(period("06:00:00", "10:00:00", "600"), period("12:00:00", "16:00:00", "900")),
    )

    assert prefixes(found) == [
        reported("13:05:00", "06:00:00 every 600 seconds, 12:00:00 every 900 seconds")
    ]


def test_matching_any_period_is_enough(tmp_path):
    found = run(
        tmp_path,
        entity(alert=alert(start_time="13:00:00")),
        periods=(period("06:00:00", "10:00:00", "600"), period("12:00:00", "16:00:00", "900")),
    )

    assert prefixes(found) == []


@pytest.mark.parametrize("payload", ["trip_update", "vehicle"])
def test_e019s_two_sites_are_not_this_rules(tmp_path, payload):
    """E019 owns both, byte for byte, under `--compat`. P011 covering them too
    would report one entity twice in modern mode."""
    payloads = {payload: {"trip": {"trip_id": "T1", "start_time": "06:05:00"}}}

    assert prefixes(run(tmp_path, entity(**payloads))) == []


def test_the_occurrence_locates_the_selector_and_carries_this_rules_id(tmp_path):
    found = run(
        tmp_path,
        entity(
            alert={
                "informed_entity": [
                    {"route_id": "R1"},
                    {"trip": {"trip_id": "T1", "start_time": "06:05:00"}},
                ]
            }
        ),
    )

    assert [one.context["entityPath"] for one in found] == [
        "entity[0].alert.informed_entity[1].trip"
    ]
    assert [one.rule_id for one in found] == ["P011"]
    assert [one.context["startTime"] for one in found] == ["06:05:00"]


def test_two_selectors_report_separately(tmp_path):
    found = run(
        tmp_path,
        entity(
            alert={
                "informed_entity": [
                    {"trip": {"trip_id": "T1", "start_time": "06:05:00"}},
                    {"trip": {"trip_id": "T1", "start_time": "06:10:00"}},
                    {"trip": {"trip_id": "T1", "start_time": "06:15:00"}},
                ]
            }
        ),
    )

    assert [one.context["entityPath"] for one in found] == [
        "entity[0].alert.informed_entity[0].trip",
        "entity[0].alert.informed_entity[2].trip",
    ]
