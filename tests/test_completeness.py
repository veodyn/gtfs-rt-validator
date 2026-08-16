"""The registry, the manifest and the tree on disk must agree.

Two correspondences, each of which fails a different way:

- **Registry against manifest.** A rule module with no manifest entry cannot
  register at all; a manifest entry with no module is caught here.
- **Registry against the tree.** One module per reported id, named exactly
  after the id, so a code in a report opens a file without a grep.

The third gate that used to live here, "no rule body branches on mode", is a
source scanner rather than a registry check and is now
`tests/test_no_mode_branch.py`.

**How the first one behaves as rules land.** The 56 batch-reachable rules
landed over four commits, so for three of them the tree was partly written, and
that was the intended build order rather than an accident.

Nothing on disk can tell "not written yet" from "written and then deleted".
Once the 56 have landed, removing every rule module, or breaking `discover()`
so that nothing registers, returns the tree to empty and the suite to green,
and nothing left would remember that 56 rules ever existed. So the gate needs
something committed that does: `WRITTEN_COMPAT_RULES`, which the commit that
lands rules raises in the same diff. It and the two cited-tier ratchets live in
`tests/writtenrules.py`, along with the paragraph beside each explaining why the
number is what it is; two of the three now carry a retired id, `S022` and
`P014`, and those are the paragraphs a reader hunting a gap in an id range
needs.

The gate is then a single equality between that number and what
`Registry.compat()` reports, which pins the count at *every* value rather than
only at 0 and 56. `test_the_gate_passes_at_every_count_the_marker_agrees_with`
and `test_a_partly_written_tree_passes_when_the_marker_says_so` walk it through
every state rather than trusting this paragraph. An earlier version also
asserted *empty or complete, never partial*; `gate` records why that half was
removed and what was checked before removing it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.rules import registry
from gtfs_rt_validator.rules.registry import Registry
from writtenrules import (
    WRITTEN_CITED_RULES,
    WRITTEN_COMPAT_RULES,
)

RULES_DIR = Path(registry.__file__).resolve().parent
#: The two modules under `rules/` that are not rule bodies. Mode selection is
#: the registry's whole job, so it is the one place allowed to say "compat".
EXCUSED = (RULES_DIR / "__init__.py", RULES_DIR / "registry.py")


def rule_modules() -> list[Path]:
    return [path for path in sorted(RULES_DIR.rglob("*.py")) if path not in EXCUSED]


def modules_in(tier: str, directory: Path | None = None) -> dict[str, list[str]]:
    """Module basename under `rules/<tier>/` to the ids that module registers.

    Seeded from the tree and filled from the registry, so the three ways of
    breaking the constraint all show up in one dict: a module that registers
    nothing keeps its empty list, a module that registers two ids has both, and
    a module whose name is not its id has a list that does not match its stem.

    `directory` exists for `tests/test_cited_tier_naming.py`, which plants a
    real module outside the source tree to give this gate teeth while
    `rules/spec/` and `rules/practice/` are still empty. It defaults to the
    tier's own directory, which is what every assertion over the real tree uses.
    """
    registry.discover()
    directory = RULES_DIR / tier if directory is None else directory
    claimed: dict[str, list[str]] = {
        path.stem: [] for path in sorted(directory.glob("*.py")) if not path.stem.startswith("_")
    }
    for registered in Registry.modern():
        if registered.tier == tier:
            claimed.setdefault(registered.module.rsplit(".", 1)[-1], []).append(registered.rule_id)
    return claimed


def misnamed(claimed: dict[str, list[str]]) -> dict[str, list[str]]:
    """Every module that is not named for the one id it registers, or `{}`."""
    return {stem: ids for stem, ids in claimed.items() if ids != [stem.upper()]}


@pytest.mark.parametrize("tier", registry.TIERS)
def test_every_module_is_named_for_the_one_id_it_registers(tier):
    """One module per reported id is a hard constraint for *all* tiers, and
    until 2026-08-15 the collector was scoped to `upstream`, so it was unenforced for
    the two cited ones. Parametrised off `registry.TIERS` rather than a literal
    list, so narrowing it again means deleting a tier from the registry."""
    assert misnamed(modules_in(tier)) == {}


def test_shared_helpers_register_nothing():
    """`rules/_shared/` is factored-out logic, not a tier. A rule there would
    be a rule with no id and no manifest entry."""
    decorated = [
        path.relative_to(RULES_DIR).as_posix()
        for path in rule_modules()
        if path.parent.name == "_shared" and "@rule" in path.read_text(encoding="utf-8")
    ]
    assert decorated == []


def test_every_registered_rule_is_a_manifest_entry_or_cites_and_declares():
    """Half of the set equality: nothing registers that the manifest does not
    declare, unless it is a `spec` or `practice` rule, which cites its source
    and declares its severity instead, those being the two things the packed
    manifest cannot hold for it. Enforced at registration too; asserted here
    over the real tree, where a rule reaches the registry by being imported."""
    registry.discover()
    for registered in Registry.modern():
        if registered.tier == "upstream":
            assert registered.rule_id in manifest.all_ids()
            assert registered.source is None
            assert registered.severity is None
        else:
            assert registered.source is not None
            assert isinstance(registered.severity, manifest.Severity)
            assert registered.rule_id not in manifest.all_ids()


def missing_ids(registered: set[str]) -> tuple[str, ...]:
    return tuple(rule_id for rule_id in manifest.batch_reachable_ids() if rule_id not in registered)


def gate(registered: set[str], written: int) -> tuple[str, ...]:
    """Every reason this tree fails the completeness gate, or `()`.

    A pure function of the two numbers so that the states the real tree cannot
    be put into can still be asserted. `written` is the committed
    `WRITTEN_COMPAT_RULES`; `registered` is what `Registry.compat()` reports.

    The gate is one equality: the count on disk is the count committed. It used
    to be that plus "empty or complete, never partial", which forbade every
    state between 0 and 56. That half was written before the build order was,
    and the 56 rules landed over four commits, so the tree is legitimately
    partial for three of them. Removing it loses nothing the
    equality does not already cover, and the equality covers strictly more:
    "empty or complete" is silent at 5 registered and 5 committed, while the
    equality fails the moment either number moves without the other, at every
    count rather than only at the ends. The missing ids stay in the message,
    because "which ones?" is the first thing anyone asks.
    """
    reasons = []
    if len(registered) < written:
        reasons.append(
            f"{written} compat rules are committed and {len(registered)} registered, "
            f"no module for {missing_ids(registered)}: rule modules were deleted, or "
            "discover() stopped finding them"
        )
    if len(registered) > written:
        reasons.append(
            f"{len(registered)} compat rules registered and {written} committed: "
            "raise WRITTEN_COMPAT_RULES in the commit that lands them"
        )
    return tuple(reasons)


def test_the_gate_passes_at_every_count_the_marker_agrees_with():
    """Every state the tree can be in, including the one no assertion over the
    real tree could reach: 56 rules landed and then deleted, which looks exactly
    like "none written yet" to anything that only reads the tree."""
    reachable = manifest.batch_reachable_ids()
    assert gate(set(), 0) == ()
    assert gate(set(reachable), 56) == ()
    assert gate(set(), 56) != (), "56 committed, none registered: deletion must fail the gate"
    assert gate(set(reachable[:30]), 56) != ()
    assert gate(set(reachable[:30]), 0) != ()
    assert gate(set(reachable), 0) != (), "landing rules without ratcheting the marker must fail"
    assert len(missing_ids(set(reachable[:30]))) == 26
    assert missing_ids(set(reachable)) == ()


def test_a_partly_written_tree_passes_when_the_marker_says_so():
    """The 56 rules landed in four commits, so the tree was partial for three of
    them, and that was the intended build order rather than an accident. An
    earlier version of this gate forbade every intermediate state outright; it
    was written before the build order was, and it made the first of those four
    commits impossible to finish.

    What replaces it is the ratchet below, which is strictly stronger: it pins
    the count at *every* number rather than only at 0 and 56, so a rule that
    quietly stops registering fails the gate at 5 exactly as it would at 56.
    """
    reachable = manifest.batch_reachable_ids()
    for count in (1, 5, 30, 55):
        assert gate(set(reachable[:count]), count) == (), f"{count} written and {count} committed"
        assert gate(set(reachable[:count]), count - 1) != (), "one more registered than committed"
        assert gate(set(reachable[:count]), count + 1) != (), "one fewer registered than committed"


def test_the_failure_names_the_ids_that_have_no_module():
    """The diagnostic `partially_filled` used to carry. Losing the assertion
    should not mean losing the list, because "which 26?" is the first question
    anyone reading the failure asks."""
    reachable = manifest.batch_reachable_ids()

    (reason,) = gate(set(reachable[:30]), 56)

    assert reachable[30] in reason
    assert reachable[55] in reason


def test_the_batch_reachable_rules_are_all_written_or_none_of_them_are():
    """The other half of the set equality: a manifest entry with no module.
    Reads `Registry.compat()`, because a batch-reachable id that registered but
    did not reach compat would be a construction bug, not a missing module."""
    assert gate(set(Registry.compat().ids()), WRITTEN_COMPAT_RULES) == ()


@pytest.mark.parametrize("tier", sorted(WRITTEN_CITED_RULES))
def test_the_cited_tier_count_is_the_count_committed(tier):
    """The `WRITTEN_COMPAT_RULES` ratchet, for the tiers the manifest cannot
    bound. An equality, not a floor, for the same reason: landing rules without
    raising the marker fails, and raising it without landing them fails too."""
    registered = sorted(r.rule_id for r in Registry.modern() if r.tier == tier)
    assert len(registered) == WRITTEN_CITED_RULES[tier], (
        f"{tier} has {len(registered)} rules registered and "
        f"{WRITTEN_CITED_RULES[tier]} committed: {registered}"
    )


def test_every_cited_tier_is_ratcheted():
    """A cited tier with no marker would be a tier whose rules could all be
    deleted without a red test, which is the one thing the marker exists for."""
    assert set(WRITTEN_CITED_RULES) == set(registry.CITED_TIERS)
    assert all(count >= 0 for count in WRITTEN_CITED_RULES.values())


def test_the_committed_marker_is_a_count_of_the_rules_that_exist_to_write():
    """A marker above 56 would make the gate unsatisfiable and a negative one
    would make it meaningless, and either would be a typo nothing else catches.
    """
    assert 0 <= WRITTEN_COMPAT_RULES <= len(manifest.batch_reachable_ids())


def test_the_three_way_split_the_registry_targets():
    """61 declared, 57 emitted, 56 batch-reachable. Compat targets the 56."""
    assert len(manifest.all_ids()) == 61
    assert len(manifest.emitted_ids()) == 57
    assert len(manifest.batch_reachable_ids()) == 56


def test_e010_is_emitted_only_by_a_validator_batchprocessor_never_registers():
    """The one rule between "emitted" and "reachable". Emitting it under
    `--compat` would itself be a parity failure."""
    e010 = manifest.rule("E010")
    assert e010.emitters == ("StopLocationTypeValidator",)
    assert "StopLocationTypeValidator" not in manifest.registration_order()
    assert not e010.batch_reachable
    assert "E010" not in manifest.batch_reachable_ids()


def test_four_declared_constants_are_emitted_by_nothing():
    dead = tuple(rule_id for rule_id in manifest.all_ids() if not manifest.rule(rule_id).emitters)
    assert dead == ("E005", "E007", "E008", "E014")
    assert not any(manifest.rule(rule_id).batch_reachable for rule_id in dead)
