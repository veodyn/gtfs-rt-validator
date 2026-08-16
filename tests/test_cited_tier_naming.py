"""The one-module-per-id gate, given teeth against real `spec` and `practice` modules.

"One rule module per reported id, named exactly after the id" is a hard
constraint of this project, for all three tiers, so that a code in a report
opens a file without a grep. The gate itself lives in
`tests/test_completeness.py`, which asserts it over the real tree; but
`rules/spec/` and `rules/practice/` were empty while the gate was being written,
and an assertion over an empty directory passes whether the gate works or not.

Until 2026-08-15 it did not work. The collector was scoped to
`path.parent.name == "upstream"` on the disk half and to
`registered.tier == "upstream"` on the registration half, so a module named
`s0001.py` registering `S001` registered successfully and the gate reported
nothing at all. Measured rather than argued: a probe planted exactly that module
and the gate answered `{}`. The first test below is that probe, kept.

So the teeth are here rather than there, and they bite on real modules. Each
test writes a rule module into a temp directory, appends that directory to the
tier package's `__path__`, and lets the real `discover()` import it through the
real decorator. Nothing is stubbed and nothing is written into the source tree,
which matters because the failure being guarded against is precisely a gate
that agrees with a mock while disagreeing with the tree.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from gtfs_rt_validator.rules import registry
from test_completeness import misnamed, modules_in
from test_registry import isolated

# The real tree is imported once, here, outside any `isolated()` block. A rule
# module that first registered *inside* one would be wiped when the block
# restored the table, and `discover()` could never bring it back, because the
# module is already in `sys.modules` and importing it again runs no decorator.
registry.discover()

#: A rule module as a cohort would write one. The body finds nothing; what is
#: under test is the decorator line and the file it sits in.
ONE_RULE = '''"""{stem}: one id, registered once."""

from gtfs_rt_validator.report.manifest import Severity
from gtfs_rt_validator.rules import rule


@rule("{first}", source="{tier}: a clause of the pinned source", severity=Severity.WARNING)
def check(message, ctx):
    return None
'''

#: Two ids from one file, which is the constraint's other half: a reader who
#: has a code in a report must be able to open the file it names.
SECOND_RULE = """

@rule("{second}", source="{tier}: a second clause", severity=Severity.WARNING)
def check_again(message, ctx):
    return None
"""

#: A file in a rule tier that registers nothing. Indistinguishable on disk from
#: a rule whose decorator was deleted, or whose import raised before reaching it.
SILENT = '"""A module in a rule tier that registers no id at all."""\n'


def a_module(tier: str, stem: str, ids: tuple[str, ...]) -> str:
    body = ONE_RULE.format(stem=stem, first=ids[0], tier=tier)
    for extra in ids[1:]:
        body += SECOND_RULE.format(second=extra, tier=tier)
    return body


@contextmanager
def planted(tier: str, stem: str, body: str, directory: Path) -> Iterator[Path]:
    """One module file, importable as `rules.<tier>.<stem>`, then gone again."""
    (directory / f"{stem}.py").write_text(body, encoding="utf-8")
    package = importlib.import_module(f"{registry.PACKAGE}.{tier}")
    package.__path__.append(str(directory))
    importlib.invalidate_caches()
    try:
        yield directory
    finally:
        package.__path__.remove(str(directory))
        sys.modules.pop(f"{registry.PACKAGE}.{tier}.{stem}", None)
        importlib.invalidate_caches()


def prefixed(tier: str, *suffixes: str) -> tuple[str, ...]:
    """`("S999", "S998")` for `spec`, `("P999", "P998")` for `practice`.

    The suffixes every caller passes are `999` and `998`, which no real rule
    claims: the spec tier stops at S052 and the practice tier at P015. A planted
    `s001` would share a module name with a real rule, and `planted`'s cleanup pops that name
    out of `sys.modules`, so the real module would be re-imported and
    re-registered inside the next `isolated()` block. The synthetic ids are out
    of range on purpose.
    """
    return tuple(f"{registry.CITED_TIERS[tier]}{suffix}" for suffix in suffixes)


CITED = sorted(registry.CITED_TIERS)


@pytest.mark.parametrize("tier", CITED)
def test_a_module_named_for_no_id_it_registers_fails_the_gate(tier, tmp_path):
    """The regression, and the shape the defect was found with: a four-digit
    stem for a three-digit id, which registers happily and cannot be opened
    from a report code."""
    (first,) = prefixed(tier, "999")
    with isolated(), planted(tier, "x0001", a_module(tier, "x0001", (first,)), tmp_path):
        assert misnamed(modules_in(tier, tmp_path)) == {"x0001": [first]}


@pytest.mark.parametrize("tier", CITED)
def test_a_module_that_registers_nothing_fails_the_gate(tier, tmp_path):
    """Missing, in the only sense the tree can express it. The id is claimed by
    the filename and by nothing else, so a report can never carry it."""
    stem = registry.CITED_TIERS[tier].lower() + "999"
    with isolated(), planted(tier, stem, SILENT, tmp_path):
        assert misnamed(modules_in(tier, tmp_path)) == {stem: []}


@pytest.mark.parametrize("tier", CITED)
def test_a_module_that_registers_two_ids_fails_the_gate(tier, tmp_path):
    stem = registry.CITED_TIERS[tier].lower() + "999"
    first, second = prefixed(tier, "999", "998")
    with isolated(), planted(tier, stem, a_module(tier, stem, (first, second)), tmp_path):
        assert misnamed(modules_in(tier, tmp_path)) == {stem: [first, second]}


@pytest.mark.parametrize("tier", CITED)
def test_a_module_named_for_the_one_id_it_registers_passes(tier, tmp_path):
    """The negative direction, which is the one that ships if it is skipped: a
    gate that reports every module is exactly as useless as one that reports
    none, and both of them pass a positive-only test."""
    stem = registry.CITED_TIERS[tier].lower() + "999"
    (first,) = prefixed(tier, "999")
    with isolated(), planted(tier, stem, a_module(tier, stem, (first,)), tmp_path):
        assert modules_in(tier, tmp_path) == {stem: [first]}
        assert misnamed(modules_in(tier, tmp_path)) == {}


def test_the_planting_leaves_no_trace_in_the_tiers_it_borrowed(tmp_path):
    """The tests above reach into a real package's `__path__`. If one leaked, a
    later test would see a rule tier that does not match the tree, so the
    cleanup is asserted rather than trusted."""
    package = importlib.import_module(f"{registry.PACKAGE}.spec")
    before = list(package.__path__)
    with isolated(), planted("spec", "s999", a_module("spec", "s999", ("S999",)), tmp_path):
        modules_in("spec", tmp_path)
    assert list(package.__path__) == before
    assert f"{registry.PACKAGE}.spec.s999" not in sys.modules
    # The planted module is gone, and the tier's real modules are untouched.
    # An equality against `{}` held only while `rules/spec/` was empty, which
    # was true for exactly as long as it took the first cohort to land.
    assert "s999" not in modules_in("spec")
