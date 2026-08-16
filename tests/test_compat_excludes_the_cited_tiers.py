"""An `S` or `P` rule is unreachable under `--compat`, asserted over the real tree.

A spec rule that ran under `--compat` would change output bytes and break the
byte-for-byte parity this project exists to hold, silently, in whichever feed
happened to trip it. Four independent things would each have to fail first.
Three of them were already here on 2026-08-15; this file is the one that was
not, and what it adds is *scope*.

- **Construction.** `Registry.compat()` builds from `manifest.batch_reachable_ids()`
  and looks each id up, rather than walking what registered and dropping what
  does not belong, so an id outside the 56 is never in the object.
  `tests/test_registry.py` holds that, but it holds it with a synthetic rule in
  a cleared registration table. Once `rules/spec/` has real modules that is no
  longer the same claim, which is why the assertions here run against whatever
  `discover()` actually imported.
- **The writer.** `report/compat.py:_validation_rule` calls `manifest.rule()`
  for the five strings it emits inline, so an `S` id raises `KeyError` there
  rather than producing a bean of empty strings. Defence in depth: a rule that
  never ran never reaches it.
- **The differential.** `tools/diff_compat_against_jar.py` is the backstop and
  needs no code here. It is also the slow one, which is why the three cheap
  gates exist.

The one thing that is true and is deliberately *not* counted as a guard: under
`--compat` the 2015 descriptor reads `TripModifications`, `Shape`, `Stop`,
`TripProperties`, `StopTimeProperties`, `TranslatedImage` and `CarriageDetails`
as unknown fields, so most spec rules would find nothing even if they ran. Most
is not all: S001, S002, S003, S018, S019, S029 and S030 read fields the
2015 schema decodes perfectly well. The descriptor is not a substitute for the
registry, and this file is what says so in code.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.rules import registry
from gtfs_rt_validator.rules.registry import Registry
from test_cited_tier_naming import a_module, planted
from test_registry import isolated

#: The id prefixes the two cited tiers own, which is exactly what must never
#: appear in a compat registry. Read from the registry rather than spelled, so
#: a third cited tier is covered the day it is added.
CITED_PREFIXES = tuple(registry.CITED_TIERS.values())


def test_compat_is_exactly_the_manifests_batch_reachable_ids():
    """Set *and* order, over the real tree. `tests/test_completeness.py` gates
    the count and names what is missing; this gates the membership, which is
    what a leaked rule would change without changing the count."""
    assert Registry.compat().ids() == manifest.batch_reachable_ids()


def test_no_compat_id_belongs_to_a_cited_tier():
    for rule_id in Registry.compat().ids():
        assert not rule_id.startswith(CITED_PREFIXES), f"{rule_id} reached a compat registry"
        assert Registry.modern().get(rule_id).tier == "upstream"


def test_every_registered_cited_tier_rule_is_absent_from_compat():
    """Written while `rules/spec/` was still empty, and vacuous then, which was
    the point: the assertion was in place before the modules it is about, so no
    cohort commit was the one that had to remember to add it."""
    compat = Registry.compat()
    cited = [r.rule_id for r in Registry.modern() if r.tier in registry.CITED_TIERS]
    assert [rule_id for rule_id in cited if rule_id in compat] == []


@pytest.mark.parametrize("tier", sorted(registry.CITED_TIERS))
def test_a_real_cited_tier_module_on_disk_does_not_reach_compat(tier, tmp_path):
    """The teeth, and the reason this file is not vacuous today.

    A real module in a real rule tier, imported by the real `discover()`, so
    what is under test is the construction of `Registry.compat()` and not a
    stub. `isolated()` is entered first, so the planted id is dropped from the
    registration table on the way out and no later test sees a tier that does
    not match the tree.
    """
    # `999` rather than `001`: a planted module sharing a name with a real
    # rule would be popped out of `sys.modules` by the cleanup, and the real
    # one would then re-register inside a later `isolated()` block.
    rule_id = f"{registry.CITED_TIERS[tier]}999"
    stem = rule_id.lower()
    with isolated(), planted(tier, stem, a_module(tier, stem, (rule_id,)), tmp_path):
        assert Registry.modern().get(rule_id) is not None
        compat = Registry.compat()
        assert rule_id not in compat
        assert not any(one.startswith(CITED_PREFIXES) for one in compat.ids())


def test_the_writer_refuses_a_cited_tier_id_rather_than_emitting_an_empty_bean():
    """The second guard, exercised rather than described. `_validation_rule`
    resolves five strings through the packed manifest, which has no `S` row, so
    the failure is loud at the point of writing instead of a results file with
    an empty title that diffs clean against nothing."""
    from gtfs_rt_validator.report import compat

    with pytest.raises(KeyError):
        compat._validation_rule("S001")
    assert compat._validation_rule("E001")["errorId"] == manifest.rule("E001").error_id
