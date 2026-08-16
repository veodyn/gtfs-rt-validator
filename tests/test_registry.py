"""Registration, the two gates on it, and how a mode picks its rules.

The load-bearing claim here is this project's central one: **mode selection is
registry construction, not a call-time filter**. An earlier draft
argued `spec` and `practice` rules need no filtering under `--compat` because
upstream's format could not carry them. It is wrong on both halves: the bean
format carries any `ValidationRule` value, and running a rule has effects
beyond its output. So `Registry.compat()` is *built* from the manifest's
batch-reachable ids and a rule outside that set never enters the object at all.
The tests below assert that structurally rather than behaviourally: the walk
takes no predicate, and the object carries no mode to branch on.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest

from gtfs_rt_validator import rules
from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.rules import registry
from gtfs_rt_validator.rules.registry import RegistrationError, Registry

CITATION = "spec: gtfs-realtime.proto, message FeedHeader, field gtfs_realtime_version"
#: What the packed manifest cannot hold for a cited tier, alongside the
#: citation: its severity. The gate on it is `tests/test_declared_severity.py`;
#: here it is just the other half of a legal `spec` registration.
SEVERITY = manifest.Severity.WARNING


@contextmanager
def isolated() -> Iterator[None]:
    """An empty registration table, restored afterwards.

    Reaches into the module's private table deliberately: registration is a
    process-wide side effect of importing a rule module, so a test that wants a
    known population has to swap the table rather than construct its own.
    `discover()` stays a no-op inside this block because Python caches the rule
    modules it has already imported, which is what makes the swap safe.
    """
    saved = dict(registry._REGISTERED)
    registry._REGISTERED.clear()
    try:
        yield
    finally:
        registry._REGISTERED.clear()
        registry._REGISTERED.update(saved)


def probe(module: str) -> Callable[[object, object], None]:
    """A rule body that finds nothing, attributed to `module`.

    The tier comes from where a rule is written, never from an argument, so a
    test that wants a tier writes a function that claims to live in it.
    """

    def check(message: object, ctx: object) -> None:
        return None

    check.__module__ = module
    return check


def test_the_decorator_registers_the_id_and_returns_the_function_untouched():
    with isolated():
        check = probe("gtfs_rt_validator.rules.upstream.e001")
        assert rules.rule("E001")(check) is check
        registered = Registry.modern().get("E001")
        assert registered is not None
        assert (registered.tier, registered.check, registered.source) == ("upstream", check, None)


def test_a_rule_takes_message_and_ctx_and_the_registry_says_nothing_more_about_ctx():
    """`ctx` is one opaque positional argument here. Its type is
    `runner.context.RuleContext`, and naming it in this package would couple the
    registry to the runner layer."""
    with isolated():
        rules.rule("E001")(probe("gtfs_rt_validator.rules.upstream.e001"))
        check = Registry.modern().get("E001").check
        assert [p.name for p in inspect.signature(check).parameters.values()] == ["message", "ctx"]


def test_a_spec_tier_rule_without_a_citation_does_not_register():
    with isolated():
        with pytest.raises(RegistrationError, match="cite"):
            rules.rule("S001")(probe("gtfs_rt_validator.rules.spec.s001"))
        assert Registry.modern().ids() == ()


def test_a_cited_spec_tier_rule_registers_and_keeps_its_citation():
    with isolated():
        decorate = rules.rule("S001", source=CITATION, severity=SEVERITY)
        decorate(probe("gtfs_rt_validator.rules.spec.s001"))
        assert Registry.modern().get("S001").source == CITATION


def test_only_the_two_permitted_sources_count_as_a_citation():
    """`spec:` a clause of the pinned proto, `practice:` a clause of the pinned
    Best Practices. The 52 open upstream "new rule" proposals are candidates
    against those two, not a third source."""
    with isolated():
        for bad in ("issue: mobilitydata/gtfs-realtime-validator#332", "spec:", "  ", ""):
            with pytest.raises(RegistrationError, match="cite"):
                rules.rule("S001", source=bad)(probe("gtfs_rt_validator.rules.spec.s001"))
        with pytest.raises(RegistrationError, match="cite"):
            rules.rule("P001", source=CITATION)(probe("gtfs_rt_validator.rules.practice.p001"))
        assert Registry.modern().ids() == ()


def test_an_upstream_rule_may_not_carry_a_citation():
    """Its source is the pinned Java, which the manifest already records. A
    `spec:` string on an upstream rule would claim it enforces the proto."""
    with isolated(), pytest.raises(RegistrationError, match="citation"):
        rules.rule("E001", source=CITATION)(probe("gtfs_rt_validator.rules.upstream.e001"))


def test_a_non_upstream_id_may_not_collide_with_the_upstream_namespace():
    """Upstream ids keep `E` and `W` so they stay lookup-able in `RULES.md`;
    `spec` and `practice` use `S` and `P`, which cannot collide if upstream ever
    unfreezes its list."""
    with isolated(), pytest.raises(RegistrationError, match="ids start with S"):
        rules.rule("E900", source=CITATION, severity=SEVERITY)(
            probe("gtfs_rt_validator.rules.spec.e900")
        )


def test_an_upstream_id_the_manifest_never_declared_cannot_register():
    with isolated(), pytest.raises(RegistrationError, match="E999"):
        rules.rule("E999")(probe("gtfs_rt_validator.rules.upstream.e999"))


def test_two_modules_cannot_claim_the_same_id():
    with isolated():
        rules.rule("E001")(probe("gtfs_rt_validator.rules.upstream.e001"))
        with pytest.raises(RegistrationError, match="already"):
            rules.rule("E001")(probe("gtfs_rt_validator.rules.upstream.e001_again"))


def test_shared_helpers_are_not_a_tier_and_cannot_register():
    with isolated(), pytest.raises(RegistrationError, match="tier"):
        rules.rule("E001")(probe("gtfs_rt_validator.rules._shared.timestamps"))


def test_compat_is_built_from_the_manifest_so_an_unreachable_rule_never_enters():
    """E010 is the whole reason compat targets 56 and not 57: it is emitted, by
    a validator `BatchProcessor` does not register. A registry built whole and
    filtered on the walk would still hold it, and running it would still have
    effects. Built from `batch_reachable_ids()`, it is absent from the object.
    """
    assert manifest.rule("E001").batch_reachable
    assert manifest.rule("E010").emitters and not manifest.rule("E010").batch_reachable
    with isolated():
        rules.rule("E001")(probe("gtfs_rt_validator.rules.upstream.e001"))
        rules.rule("E010")(probe("gtfs_rt_validator.rules.upstream.e010"))
        rules.rule("S001", source=CITATION, severity=SEVERITY)(
            probe("gtfs_rt_validator.rules.spec.s001")
        )
        compat = Registry.compat()
        assert compat.ids() == ("E001",)
        assert "E010" not in compat
        assert len(compat) == 1
        assert set(Registry.modern().ids()) == {"E001", "E010", "S001"}


def test_the_walk_takes_no_predicate_and_the_object_carries_no_mode():
    """The structural half. A future contributor cannot reintroduce the
    call-time filter without changing these signatures: there is nowhere to pass
    one and nothing on the object to read a mode from. The only two members
    that name a mode are the two constructors, bound to the class, so mode is
    something that happened while the object was built and not something it
    still knows."""
    for method in (Registry.__iter__, Registry.ids, Registry.__len__):
        assert list(inspect.signature(method).parameters) == ["self"]
    with isolated():
        rules.rule("E001")(probe("gtfs_rt_validator.rules.upstream.e001"))
        compat = Registry.compat()
        names = [field.name for field in compat.__dataclass_fields__.values()]
        assert names == ["_rules"]
        mode_named = [n for n in dir(compat) if "mode" in n.lower() or "compat" in n.lower()]
        assert mode_named == ["compat", "modern"]
        assert all(inspect.ismethod(getattr(Registry, name)) for name in mode_named)
        assert compat == Registry.modern()


def test_iterating_a_registry_yields_its_rules_in_manifest_order():
    """Declaration order, which is what `batch_reachable_ids()` reports. The
    compat *output* order is upstream's validator registration order and is
    `report/compat.py`'s contract, never read out of here."""
    with isolated():
        for rule_id in ("W002", "W001"):
            rules.rule(rule_id)(probe(f"gtfs_rt_validator.rules.upstream.{rule_id.lower()}"))
        assert [registered.rule_id for registered in Registry.compat()] == ["W001", "W002"]
