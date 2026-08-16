"""What the loop hands a rule, and what it does with what comes back.

The contract itself is pinned in `tests/test_rule_context.py`; this is the same
contract seen from inside a run, where the context is built rather than
constructed by hand.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.report.occurrence import SOURCE_FILE_KEY, Occurrence
from gtfs_rt_validator.runner.clock import SortBy
from gtfs_rt_validator.runner.context import DEFAULT_ROLE, RuleContractError
from gtfs_rt_validator.runner.run import MessageResult, file_cycles, role_cycle, run
from runnerfixtures import (
    a_config,
    a_rule,
    per_entity,
    registry_of,
    silent,
    written_feed,
    yielding,
)


def one_file(tmp_path: Path, *entity_ids: str) -> Path:
    directory = tmp_path / "archive"
    directory.mkdir(exist_ok=True)
    return written_feed(directory, "one.pb", *entity_ids)


def contexts(rule_id: str = "E001") -> tuple[list, object]:
    """A rule that records the context it was given and finds nothing."""
    seen: list = []

    def check(message, ctx):
        seen.append(ctx)
        return ()

    return seen, a_rule(rule_id, check)


def replay(config, directory: Path) -> list[MessageResult]:
    written: list[MessageResult] = []
    run(config, file_cycles(directory, config.sort_by), sink=written.append)
    return written


def test_a_rule_that_raises_is_not_caught(tmp_path):
    """A rule that raises is a bug in this project, not a malformed feed.

    Swallowing it would turn a broken rule into a rule that silently finds
    nothing, which is indistinguishable from a clean feed in the report.
    """

    def boom(message, ctx):
        raise ZeroDivisionError("the rule is wrong, not the feed")

    config = a_config(tmp_path, registry=registry_of(a_rule("E001", boom)))
    path = one_file(tmp_path, "a")

    with pytest.raises(ZeroDivisionError, match="the rule is wrong"):
        run(config, file_cycles(path.parent, config.sort_by))


def test_the_three_return_shapes_all_reach_the_container(tmp_path):
    config = a_config(
        tmp_path, registry=registry_of(per_entity("E001"), yielding("E002"), silent("E003"))
    )
    path = one_file(tmp_path, "a", "b")

    result = run(config, file_cycles(path.parent, config.sort_by))

    assert result.notices.count_for("E001") == 2
    assert result.notices.count_for("E002") == 2
    assert result.notices.count_for("E003") == 0


def test_every_occurrence_is_stamped_with_the_file_it_came_from(tmp_path):
    config = a_config(tmp_path, registry=registry_of(per_entity("E001")))
    path = one_file(tmp_path, "a")

    result = run(config, file_cycles(path.parent, config.sort_by))

    assert result.notices.in_order()[0].context[SOURCE_FILE_KEY] == str(path)


def test_a_rule_emitting_another_rules_id_stops_the_run(tmp_path):
    config = a_config(
        tmp_path, registry=registry_of(a_rule("E001", lambda m, c: [Occurrence("W1")]))
    )
    path = one_file(tmp_path, "a")

    with pytest.raises(RuleContractError):
        run(config, file_cycles(path.parent, config.sort_by))


def test_rules_run_in_registry_order(tmp_path):
    """Registration order is output order under compat, so the loop preserves it."""
    order: list[str] = []

    def watcher(rule_id):
        def check(message, ctx):
            order.append(rule_id)
            return ()

        return a_rule(rule_id, check)

    config = a_config(tmp_path, registry=registry_of(watcher("W003"), watcher("E001")))
    path = one_file(tmp_path, "a")

    run(config, file_cycles(path.parent, config.sort_by))

    assert order == ["W003", "E001"]


def test_the_previous_message_is_none_on_the_first_file_and_set_after(tmp_path):
    seen, rule = contexts()
    config = a_config(tmp_path, registry=registry_of(rule), sort_by=SortBy.NAME)
    directory = tmp_path / "archive"
    directory.mkdir()
    written_feed(directory, "1.pb", "a")
    written_feed(directory, "2.pb", "b")

    replay(config, directory)

    assert seen[0].previous is None
    assert seen[0].previous_clock is None
    assert [each.get("id") for each in seen[1].previous.get("entity")] == ["a"]
    assert seen[1].previous_clock == seen[0].clock


def test_previous_is_per_role_rather_than_global(tmp_path):
    """Otherwise a VehiclePositions message's "previous" is a TripUpdates one,
    which compares two snapshots that have nothing to do with each other."""
    seen, rule = contexts()
    config = a_config(tmp_path, registry=registry_of(rule))
    first = {
        "tu": written_feed(tmp_path, "tu-1.pb", "t1"),
        "vp": written_feed(tmp_path, "vp-1.pb", "v1"),
    }
    second = {
        "tu": written_feed(tmp_path, "tu-2.pb", "t2"),
        "vp": written_feed(tmp_path, "vp-2.pb", "v2"),
    }

    run(config, [role_cycle(first), role_cycle(second)])

    by_role = {(ctx.role, index // 2): ctx for index, ctx in enumerate(seen)}
    assert by_role[("tu", 0)].previous is None
    assert by_role[("vp", 0)].previous is None
    assert by_role[("vp", 1)].previous is not None
    assert [each.get("id") for each in by_role[("vp", 1)].previous.get("entity")] == ["v1"]


def test_the_combined_view_reaches_the_host_role_only(tmp_path):
    seen, rule = contexts()
    config = a_config(tmp_path, registry=registry_of(rule))
    tu = written_feed(tmp_path, "tu.pb", "t1")
    vp = written_feed(tmp_path, "vp.pb", "v1")

    run(config, [role_cycle({"vp": vp, "tu": tu})])

    hosted = [ctx for ctx in seen if ctx.combined is not None]
    assert [ctx.role for ctx in hosted] == ["tu"]
    assert [entity.get("id") for _, _, entity in hosted[0].combined.entities()] == ["t1", "v1"]


def test_a_role_whose_file_failed_to_decode_is_absent_from_the_cycle(tmp_path):
    """A cross-feed rule must not compare against a snapshot that never loaded."""
    seen, rule = contexts()
    config = a_config(tmp_path, registry=registry_of(rule))
    tu = written_feed(tmp_path, "tu.pb", "t1")
    vp = tmp_path / "vp.pb"
    vp.write_bytes(b"\xff\xff\xff\xff")

    run(config, [role_cycle({"tu": tu, "vp": vp})])

    assert len(seen) == 1
    assert seen[0].combined.roles() == ("tu",)


def test_a_compat_message_is_its_own_combined_view(tmp_path):
    seen, rule = contexts()
    config = a_config(tmp_path, registry=registry_of(rule))
    path = one_file(tmp_path, "a")

    run(config, file_cycles(path.parent, config.sort_by))

    assert seen[0].role == DEFAULT_ROLE
    assert seen[0].combined.roles() == (DEFAULT_ROLE,)
    assert seen[0].timezone == "America/New_York"
    assert seen[0].static.stop_ids == frozenset({"S1", "S2"})


def memos_from(tmp_path: Path, *rule_ids: str, files: int = 1) -> list[tuple[dict, dict]]:
    """Run `rule_ids` over `files` messages, recording each memo and its state.

    The pair is the dict itself and a snapshot of what it held on arrival: the
    rule then writes to it, and the object cannot say afterwards what was in it
    when it was handed over.
    """
    seen: list[tuple[dict, dict]] = []

    def check(message, ctx):
        seen.append((ctx.memo, dict(ctx.memo)))
        ctx.memo["walk:x"] = ["event"]
        return ()

    directory = tmp_path / "archive"
    directory.mkdir()
    for index in range(files):
        written_feed(directory, f"{index}.pb", f"e{index}")
    config = a_config(tmp_path, registry=registry_of(*(a_rule(r, check) for r in rule_ids)))
    run(config, file_cycles(directory, config.sort_by))
    return seen


def test_every_rule_that_sees_one_message_sees_one_scratch_dict(tmp_path):
    """The point of the field: twelve rules sharing one walk share its result."""
    seen = memos_from(tmp_path, "E001", "E002")

    assert len(seen) == 2
    assert seen[0][0] is seen[1][0]
    assert seen[1][1] == {"walk:x": ["event"]}


def test_the_runner_hands_every_message_a_fresh_scratch_dict(tmp_path):
    """Built per message by the loop, not taken from the field's own default,
    which would be one dict for every message in the process."""
    seen = memos_from(tmp_path, "E001", files=2)

    assert seen[0][0] is not seen[1][0]


def test_nothing_a_rule_memoised_leaks_into_the_next_message(tmp_path):
    """A walk memoised against one message must never answer for another."""
    seen = memos_from(tmp_path, "E001", files=2)

    assert [arrived for _, arrived in seen] == [{}, {}]
