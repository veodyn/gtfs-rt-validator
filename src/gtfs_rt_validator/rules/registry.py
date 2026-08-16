"""Rules register themselves here, and a mode picks its set by building one.

**Mode selection is registry construction, not a call-time filter.** The spec
records an earlier draft's argument that `spec` and `practice` rules need no
filtering under `--compat`, because upstream's output format could not carry
them, and records that it is wrong twice over: the bean format carries any
`ValidationRule` value, and running a rule has effects beyond its output. So
`Registry.compat()` walks `manifest.batch_reachable_ids()` and looks each id
up, rather than walking what registered and dropping what does not belong. A
rule outside those 56 is never in the object, which is why `Registry` carries
no mode field and `__iter__` takes no predicate. There is nowhere to put the
filter back.

Which tier a rule belongs to comes from where it is written, never from an
argument: `gtfs_rt_validator.rules.spec.s001` is a `spec` rule because of its
own `__module__`. That is what keeps the citation gate below honest, since a
rule cannot claim `upstream` to escape it.

**This module is the manifest for the two cited tiers.** `data/rules.json` is
generated from upstream's Java and never hand-edited, so it has no room for an
`S` or `P` id: it can hold neither their citation nor their severity. Both
therefore live on the registration, and `severity_for` below is the one lookup
that answers for any tier, so a writer never has to know which tier an id came
from. The severity *words* still have exactly one home, `manifest.Severity`; a
rule points at a member of it and cannot spell one.

Stdlib only, and no import of the sibling: every rule imports this.
"""

from __future__ import annotations

import pkgutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from gtfs_rt_validator.report import manifest

PACKAGE = "gtfs_rt_validator.rules"

#: The three tiers, in the order `Registry.modern()` reports them.
TIERS = ("upstream", "spec", "practice")

#: The two tiers that must cite a source, and the id prefix each one uses.
#: Upstream ids keep `E` and `W` so a code in a report stays lookup-able in
#: `RULES.md`; `S` and `P` cannot collide if upstream ever unfreezes its list.
CITED_TIERS = {"spec": "S", "practice": "P"}

#: A rule body: `(message, ctx)`. `ctx` carries the static context, the
#: previous message, the clock, the combined-feed view and the named feed
#: roles, and is deliberately opaque here. Its type and what a rule hands back
#: are the runner's contract, so naming either would couple every rule to a
#: module this one must not import.
RuleFn = Callable[[Any, Any], Any]


class RegistrationError(Exception):
    """A rule module is wrong about itself.

    Never a finding about a feed, and never reachable from feed bytes: this
    fires at import time, from code in this repository, and means the tree does
    not satisfy the rule layer's own contract.
    """


@dataclass(frozen=True, slots=True)
class RegisteredRule:
    """One rule module's claim on an id.

    `source` is the citation, which is `None` for every `upstream` rule (its
    source is the pinned Java, which the manifest already records) and a
    `spec:` or `practice:` clause for every other.

    `severity` follows the same split for the same reason: `None` for an
    `upstream` rule, whose severity is `manifest.rule(id).severity`, and a
    declared `manifest.Severity` member for every other, whose id the packed
    manifest cannot carry. Declaring it is not spelling it: the member is the
    manifest's own value, so `tests/test_packed_manifest.py` still fails the
    build on a rule module that writes the word.
    """

    rule_id: str
    tier: str
    module: str
    check: RuleFn
    source: str | None
    severity: manifest.Severity | None = None


_REGISTERED: dict[str, RegisteredRule] = {}


def tier_of(module: str) -> str:
    """The tier a module's dotted name puts it in.

    `rules/_shared/` is deliberately not a tier: it is factored-out logic, and
    a rule there would be a rule with no id and no manifest entry.
    """
    head = module[len(PACKAGE) + 1 :].split(".")[0] if module.startswith(f"{PACKAGE}.") else ""
    if head not in TIERS:
        raise RegistrationError(f"{module} is in no rule tier; the tiers are {', '.join(TIERS)}")
    return head


def _check_citation(rule_id: str, tier: str, source: str | None) -> None:
    """A rule outside `rules/upstream/` cites its source or does not ship.

    Exactly two sources are permitted, and the citation names the one its tier
    is for: `spec:` a clause of the pinned `gtfs-realtime.proto`, `practice:` a
    clause of the pinned Best Practices. Upstream's 52 open "new rule"
    proposals are candidates against those two, not a third source.
    """
    prefix = f"{tier}: "
    body = source[len(prefix) :] if isinstance(source, str) else ""
    if (
        not isinstance(source, str)
        or not source.startswith(prefix)
        or not body
        or body != body.strip()
    ):
        raise RegistrationError(
            f"{rule_id} is a {tier} rule and must cite its source as "
            f"'{prefix}<clause>', one space and no padding; got {source!r}"
        )


def _check_severity(rule_id: str, tier: str, severity: manifest.Severity | None) -> None:
    """A rule outside `rules/upstream/` declares its severity or does not ship.

    A `manifest.Severity` member, never a string: the words live in the manifest
    and a rule points at them. Declared at registration rather than resolved at
    write time, so a tree cannot ship a rule whose report entry has no severity
    to print, and rejected here rather than defaulted, because a default would
    be this module deciding how serious somebody else's check is.
    """
    if not isinstance(severity, manifest.Severity):
        raise RegistrationError(
            f"{rule_id} is a {tier} rule and must declare its severity as a "
            f"manifest.Severity member; the packed manifest holds upstream's ids only and "
            f"cannot grow one for it. Got {severity!r}"
        )


def register(
    rule_id: str,
    check: RuleFn,
    *,
    module: str,
    source: str | None = None,
    severity: manifest.Severity | None = None,
) -> RegisteredRule:
    """Record one rule. The decorator below is how a module calls this."""
    tier = tier_of(module)
    if tier == "upstream":
        if source is not None:
            raise RegistrationError(
                f"{rule_id} is an upstream rule and takes no citation; its source is the "
                f"pinned Java, which the manifest records. Got {source!r}"
            )
        if severity is not None:
            raise RegistrationError(
                f"{rule_id} is an upstream rule and declares no severity; the manifest carries "
                f"the one upstream ships. Got {severity!r}"
            )
        try:
            manifest.rule(rule_id)
        except KeyError as exc:
            raise RegistrationError(str(exc)) from None
    else:
        _check_citation(rule_id, tier, source)
        _check_severity(rule_id, tier, severity)
        expected = CITED_TIERS[tier]
        if not rule_id.startswith(expected):
            raise RegistrationError(
                f"{rule_id} is a {tier} rule, whose ids start with {expected} so they cannot "
                f"collide with the upstream ids the manifest owns"
            )
    if rule_id in _REGISTERED:
        raise RegistrationError(f"{rule_id} is already registered by {_REGISTERED[rule_id].module}")
    _REGISTERED[rule_id] = RegisteredRule(rule_id, tier, module, check, source, severity)
    return _REGISTERED[rule_id]


def rule(
    rule_id: str,
    *,
    source: str | None = None,
    severity: manifest.Severity | None = None,
) -> Callable[[RuleFn], RuleFn]:
    """Register the decorated `(message, ctx)` function as `rule_id`.

    Returns the function unchanged, so a rule stays directly callable and a
    test can exercise it without going through a registry.
    """

    def decorate(check: RuleFn) -> RuleFn:
        register(rule_id, check, module=check.__module__, source=source, severity=severity)
        return check

    return decorate


def severity_for(rule_id: str) -> str:
    """The severity of any rule that fired, whichever tier wrote it.

    Upstream's 56 resolve through the manifest, which is the only thing that
    knows what `ValidationRules.java` says. The cited tiers resolve through
    their own registration, because the packed manifest cannot hold their ids.
    One function, so a writer never parses an id to decide which to ask.

    Reads the registration table rather than calling `discover()`: an id can
    only reach a report by having fired, which means its module was imported.
    A missing id therefore raises `KeyError` from the manifest, which is the
    right answer: it is a rule this project never declared anywhere, not
    anything a feed did.
    """
    registered = _REGISTERED.get(rule_id)
    if registered is not None and registered.severity is not None:
        return registered.severity
    return manifest.rule(rule_id).severity


def discover() -> None:
    """Import every rule module, so that its decorator has run. Idempotent.

    Modules are imported in sorted order within a tier and the tiers in
    `TIERS` order, so `Registry.modern()` has a deterministic order that does
    not depend on who imported what first.
    """
    for tier in TIERS:
        package = import_module(f"{PACKAGE}.{tier}")
        for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda info: info.name):
            if not info.name.startswith("_"):
                import_module(f"{PACKAGE}.{tier}.{info.name}")


@dataclass(frozen=True, slots=True)
class Registry:
    """An immutable set of rules, already restricted to one mode's.

    Built by `compat()` or `modern()` and never mutated afterwards. It does not
    know which of the two built it, on purpose: the runner walks whatever it is
    given, and mode lives in the descriptor, this construction and the writer.
    """

    _rules: tuple[RegisteredRule, ...]

    @classmethod
    def compat(cls) -> Registry:
        """Exactly the batch-reachable rules that have a module.

        Built from the manifest's ids, not from what registered, so a rule
        outside the 56 cannot enter however it registered. Complete, that is
        56 rules; a partly written tree is what `tests/test_completeness.py`
        fails on.
        """
        discover()
        return cls._of(manifest.batch_reachable_ids())

    @classmethod
    def modern(cls) -> Registry:
        """Every registered rule, all three tiers, in discovery order."""
        discover()
        return cls._of(tuple(_REGISTERED))

    @classmethod
    def _of(cls, rule_ids: tuple[str, ...]) -> Registry:
        return cls(tuple(_REGISTERED[rule_id] for rule_id in rule_ids if rule_id in _REGISTERED))

    def ids(self) -> tuple[str, ...]:
        return tuple(registered.rule_id for registered in self._rules)

    def get(self, rule_id: str) -> RegisteredRule | None:
        return next((r for r in self._rules if r.rule_id == rule_id), None)

    def __iter__(self) -> Iterator[RegisteredRule]:
        return iter(self._rules)

    def __len__(self) -> int:
        return len(self._rules)

    def __contains__(self, rule_id: object) -> bool:
        return rule_id in self.ids()
