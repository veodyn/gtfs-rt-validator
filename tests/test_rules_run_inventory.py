"""`summary.rulesRun`: the ids the run's registry actually held.

A consumer that will not accept a verdict from an empty rule set needs the
report to name what ran, and the whole value of that field is that it can be
*wrong in the same direction as the run*. So what is pinned here is the
derivation and not the number: every assertion drives a run whose registry was
deliberately built short and reads the field back out.

A test that asserted `len(rulesRun) == 121` would pass against a literal list in
the writer, which is exactly the shape of claim this project spends its effort
deleting: green long after the thing it describes stopped being true. The one
assertion below that mentions the real registry compares against
`Registry.modern().ids()` rather than a count, and it is a cross-check on top of
the derivation tests rather than the thing being proved.

The chain is `RunConfig.registry` -> `RunResult.rules_run` -> `RunSummary` ->
`report.json`, and the last test walks all of it by reading the written bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

from gtfs_rt_validator import api
from gtfs_rt_validator.report.summary import build_summary
from gtfs_rt_validator.rules.registry import Registry
from gtfs_rt_validator.runner.mode import Mode
from gtfs_rt_validator.runner.run import RunConfig, file_cycles, run
from runnerfixtures import CLEAN_CLOCK, a_config, registry_of, silent, static_feed, written_feed


def archive(tmp_path: Path, *names: str) -> Path:
    directory = tmp_path / "archive"
    directory.mkdir()
    for name in names:
        written_feed(directory, name, "a")
    return directory


def result_of(config: RunConfig, directory: Path) -> api.Result:
    """One real run, wrapped in the `Result` the writer and the summary take."""
    return api.Result(
        mode=config.mode,
        gtfs_input="feed.zip",
        run=run(config, file_cycles(directory, config.sort_by)),
        validated_at="2026-08-14T09:00:00Z",
        validation_time_seconds=0.5,
    )


def rules_run(config: RunConfig, directory: Path) -> list[str]:
    return build_summary(result_of(config, directory).summary())["rulesRun"]


def test_the_inventory_is_the_short_registry_the_run_was_given(tmp_path):
    """Two rules configured, two rules reported, and nothing about the tiers.

    The rules are `silent`, so nothing fired: `rulesRun` is what *ran*, not what
    found something, and a clean feed still has to be able to say what checked
    it. That is the whole point for a consumer deciding whether "no notices"
    means anything.
    """
    config = a_config(tmp_path, registry=registry_of(silent("E001"), silent("W002")))

    assert rules_run(config, archive(tmp_path, "one.pb")) == ["E001", "W002"]


def test_a_rule_missing_from_the_registry_is_missing_from_the_inventory(tmp_path):
    """The failure this field exists to report, run end to end.

    Same feed, same code path, one rule taken away: if `rulesRun` came from a
    constant, from `Registry.modern()` at write time, or from anything other
    than the registry this run walked, both runs would report the same list.
    """
    directory = archive(tmp_path, "one.pb")
    both = a_config(tmp_path, registry=registry_of(silent("E001"), silent("W002")))
    short = a_config(tmp_path, registry=registry_of(silent("E001")))

    full_inventory = rules_run(both, directory)
    lost_a_module = rules_run(short, directory)

    assert lost_a_module == ["E001"]
    assert set(full_inventory) - set(lost_a_module) == {"W002"}


def test_an_empty_registry_reports_an_empty_inventory_rather_than_omitting_it(tmp_path):
    """The case the consumer refuses on, and it has to be visible.

    A run that walked no rules says so with `[]`. The key going absent instead
    would leave "nothing ran" indistinguishable from "an older writer that did
    not record it", which is the distinction `RunSummary.rules_run` defaults to
    `None` to keep.
    """
    config = a_config(tmp_path, registry=registry_of())

    assert rules_run(config, archive(tmp_path, "one.pb")) == []


def test_the_written_report_carries_the_inventory_and_the_mode(tmp_path):
    """The bytes on disk, not the dict on the way there.

    `mode` rides beside it because 121 ids and 56 are different assurance
    claims and a stored file should not need its name to say which it is.
    """
    config = a_config(tmp_path, registry=registry_of(silent("E001")))
    result = result_of(config, archive(tmp_path, "one.pb"))

    written = result.write(tmp_path / "out")

    summary = json.loads(written.report.read_text(encoding="utf-8"))["summary"]
    assert summary["rulesRun"] == ["E001"]
    assert summary["mode"] == "modern"


def test_a_real_modern_run_reports_the_registry_modern_mode_builds(tmp_path):
    """The cross-check: the real thing, still read off the run rather than
    counted. Compared against `Registry.modern().ids()` rather than a number,
    so the day a rule is added or removed this test moves with it instead of
    having to be edited.
    """
    gtfs = static_feed(tmp_path)
    directory = archive(tmp_path, "one.pb")
    request = api.Request(
        mode=Mode.MODERN, gtfs=gtfs, inputs=api.resolve(str(directory)), at=CLEAN_CLOCK
    )

    result = api.validate(request)

    assert result.run.rules_run == Registry.modern().ids()
    assert build_summary(result.summary())["rulesRun"] == list(Registry.modern().ids())
