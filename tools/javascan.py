"""Read upstream's rule declarations, emitters and output orders out of Java.

Split out of `map_rules.py`, which is the only caller, for the same reason
`javalex.py` was: that file fetches the sources and assembles the manifest, and
this one knows the shapes upstream writes. `javalex` knows Java tokens, this
knows what `ValidationRules.java` and a `FeedEntityValidator` look like.

Three parsing traps decide whether the manifest comes out right.

1. Emission sites use two call shapes at this pin. `RuleUtils.addOccurrence(E022, ...)`
   relies on a static import; `RuleUtils.addOccurrence(ValidationRules.E046, ...)`
   qualifies. `StopTimeUpdateValidator` uses the qualified form exclusively, so a
   pattern matching only the bare form reports it as emitting nothing and the
   total comes out 45 rather than 57.
2. Comments must be stripped before matching. `FrequencyTypeZeroValidator` names
   W006 twice inside block comments explaining why it does *not* check it
   (lines 57 and 87 at the pin), and counting textual mentions therefore invents
   a second emitter for a rule that has exactly one.
3. Raising an occurrence and handing its list to `errors` are separate acts, and
   only the second decides output order. `emitters` reads the first, `group_order`
   reads the second, and the two are cross-checked against each other.

Every failure exits rather than guessing. A silently mis-scanned source produces
a manifest that is wrong in a way no diff shows.
"""

from __future__ import annotations

import re
import sys

from javalex import read_string_arguments, strip_comments

RULE_ID = r"[EW]\d{3}"
DECLARATION = re.compile(
    rf"public\s+static\s+final\s+ValidationRule\s+({RULE_ID})\s*=\s*new\s+ValidationRule\s*\("
)
# The count guard: any field of this type, whatever it is named and however it
# is initialised. A declaration the strict pattern above cannot read must stop
# the run rather than quietly shrink the manifest.
ANY_RULE_FIELD = re.compile(r"public\s+static\s+final\s+ValidationRule\s+(\w+)\s*=")
EMISSION = re.compile(
    rf"addOccurrence\s*\(\s*(?:ValidationRules\.)?({RULE_ID})\b"
    rf"|new\s+MessageLogModel\s*\(\s*(?:ValidationRules\.)?({RULE_ID})\b"
)
REGISTRATION = re.compile(r"mValidationRules\.add\s*\(\s*new\s+(\w+)\s*\(\s*\)\s*\)")
# The group hand-off at the tail of `validate()`. Narrower than EMISSION on
# purpose: EMISSION answers "which validator mentions this rule", and every
# `addOccurrence` call site counts for that, while output order is decided only
# by the order the finished lists are handed to `errors`.
GROUP = re.compile(
    r"errors\.add\s*\(\s*new\s+ErrorListHelperModel\s*\(\s*new\s+MessageLogModel\s*\(\s*"
    rf"(?:ValidationRules\.)?({RULE_ID})\b"
)


def declarations(text: str) -> dict[str, dict]:
    """The five strings per rule, in declaration order.

    Declaration order is upstream's own: `ValidationRules.getRules()` reflects
    over the declared fields and hands back whatever the class body lists, so
    the manifest keeps that order rather than sorting.
    """
    source = strip_comments(text)
    rules: dict[str, dict] = {}
    for match in DECLARATION.finditer(source):
        rule_id = match.group(1)
        error_id, severity, title, description, suffix = read_string_arguments(
            source, match.end(), 5
        )
        if error_id != rule_id:
            sys.exit(f"field {rule_id} declares errorId {error_id!r}")
        rules[rule_id] = {
            "error_id": error_id,
            "severity": severity,
            "title": title,
            "error_description": description,
            "occurrence_suffix": suffix,
        }
    missed = {match.group(1) for match in ANY_RULE_FIELD.finditer(source)} - set(rules)
    if missed:
        sys.exit(f"ValidationRule fields the parser did not read: {sorted(missed)}")
    return rules


def emitters(texts: dict[str, str], known: set[str]) -> dict[str, list[str]]:
    """Rule id to the validator classes that emit it, in file-name order."""
    found: dict[str, list[str]] = {}
    for name, text in sorted(texts.items()):
        if not name.endswith("Validator.java"):
            continue
        source = strip_comments(text, blank_strings=True)
        class_name = name.removesuffix(".java")
        for match in EMISSION.finditer(source):
            rule_id = match.group(1) or match.group(2)
            if rule_id not in known:
                sys.exit(f"{name} emits {rule_id}, which ValidationRules.java does not declare")
            if class_name not in found.setdefault(rule_id, []):
                found[rule_id].append(class_name)
    return found


def registrations(text: str) -> list[str]:
    """The `FeedEntityValidator`s `BatchProcessor` adds, in registration order.

    Order is part of the output contract: the runner walks the registry in it,
    and compat output is byte-compared. Any listing of the rules sorted by count
    is a different order and is not this one.
    """
    order = [match.group(1) for match in REGISTRATION.finditer(strip_comments(text))]
    if len(order) != len(set(order)):
        sys.exit(f"BatchProcessor registers a validator twice: {order}")
    return order


def validate_body(name: str, source: str) -> str:
    """Just the body of `validate()`, so declaration order cannot pass for run order.

    `GROUP.finditer` over a whole class file would order an `errors.add(...)`
    sitting in a helper by where that helper is *declared*, not by when
    `validate()` calls it, and would accept one in a method nothing calls at all.
    At the pin every call is in `validate()`, so the extracted order is right
    either way; the guard was the unsound part, and a future upstream that moved
    one call into a helper would have been packed in the wrong order silently.

    The `emitters` cross-check does not cover this. `EMISSION` recognises the same
    `new MessageLogModel(X)` expression, so an unused helper is accepted as both
    an emitter and a group and the two sets agree with each other while both being
    wrong.

    Braces are balanced over source that `strip_comments(blank_strings=True)` has
    already emptied, so no brace inside a comment or a string literal is counted.
    """
    start = source.find("validate(")
    if start < 0:
        sys.exit(f"{name} has no validate(); the FeedEntityValidator contract changed")
    opening = source.find("{", start)
    if opening < 0:
        sys.exit(f"{name}.validate() has no body")
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening : index + 1]
    sys.exit(f"{name}.validate() has unbalanced braces")


def group_order(
    texts: dict[str, str], order: list[str], emitted: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Per registered validator, its rule ids in `errors.add(...)` order.

    The second half of the output contract. `batch_registration_order` says which
    group comes first; this says which rule comes first inside a group, and a
    byte comparison sees both.

    Keyed in registration order and holding the nine registered validators only.
    `StopLocationTypeValidator` adds an E010 group of its own, but nothing
    registers it, so a group for it here would invite the writer to emit one.

    Cross-checked against `emitters`, which is read by a different pattern over
    the same source: a rule raised by `addOccurrence` and never handed to
    `errors` would be invisible in output, and a group for a rule this validator
    never raises would always be empty. Neither happens at the pin, and either
    would be a real change in what upstream emits rather than a parsing detail.
    """
    groups: dict[str, list[str]] = {}
    for name in order:
        source = strip_comments(texts[f"{name}.java"], blank_strings=True)
        ids = [match.group(1) for match in GROUP.finditer(validate_body(name, source))]
        if len(ids) != len(set(ids)):
            sys.exit(f"{name} adds a group for the same rule twice: {ids}")
        raised = {rule_id for rule_id, names in emitted.items() if name in names}
        if set(ids) != raised:
            sys.exit(f"{name} raises {sorted(raised)} but groups {sorted(ids)}")
        groups[name] = ids
    return groups
