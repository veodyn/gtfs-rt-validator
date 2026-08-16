"""No rule body branches on mode. Mode is descriptor, registry and writer.

Split out of `tests/test_completeness.py`, which is about the registry, the
manifest and the tree agreeing on *which* rules exist. This file is about what
may be written inside one, and it is a source scanner rather than a registry
check, so it shares only the "which files are rule modules" helper.

The gate exists before the first rule, because retrofitting it across 56 modules
is much harder than writing it against zero. It is vacuous today by design.
"""

from __future__ import annotations

import ast
import re

from test_completeness import EXCUSED, RULES_DIR, rule_modules

#: Identifier tokens that mean "this code knows which mode it is running in".
MODE_TOKENS = frozenset({"compat", "compatibility", "mode", "modes", "modern"})

BRANCHES_ON_MODE = "def check(message, ctx):\n    if ctx.compat:\n        return None\n"
READS_A_MODE_FLAG = 'def check(message, ctx):\n    return ctx.flags["--compat"]\n'
CLEAN = '"""E001 exists for compat parity with upstream."""\n\n\ndef check(message, ctx):\n    return message.header\n'


def tokens(identifier: str) -> set[str]:
    """`isCompat` and `compat_mode` split; `model` and `decode` do not."""
    return {part.lower() for part in re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+", identifier)}


def mode_references(source: str) -> list[str]:
    """Names and exact strings that reference a mode, by parse not by text.

    Identifiers count on a token match, so `ctx.compat`, `Mode.COMPAT` and
    `compat_mode` are all found. String *constants* count only when the whole
    value is a mode word, so `ctx.flags["--compat"]` is found while a docstring
    that says the word compat in a sentence is invisible. That is the same
    split `test_packed_manifest.py` uses for severity literals: prose is not a
    second source of truth, use is.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            names = [node.id]
        elif isinstance(node, ast.Attribute):
            names = [node.attr]
        elif isinstance(node, ast.arg) or (isinstance(node, ast.keyword) and node.arg):
            names = [node.arg]
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names = [node.name]
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found += [node.value] if node.value.strip().lstrip("-").lower() in MODE_TOKENS else []
            continue
        else:
            continue
        found += [name for name in names if tokens(name) & MODE_TOKENS]
    return found


def test_the_no_mode_branch_scanner_catches_a_branch_and_a_flag_read():
    """The gate's own proof. Both violations are caught by parse, and prose
    about compat in a docstring is not a violation."""
    assert mode_references(BRANCHES_ON_MODE) == ["compat"]
    assert mode_references(READS_A_MODE_FLAG) == ["--compat"]
    assert mode_references(CLEAN) == []


def test_no_rule_module_branches_on_mode():
    """Mode is descriptor, registry and writer, never a branch inside a rule.
    Vacuous at zero rules by design: the gate has to exist before the first
    module, not after 56 of them."""
    assert [path for path in EXCUSED if not path.exists()] == []
    offenders = {
        path.relative_to(RULES_DIR).as_posix(): mode_references(path.read_text(encoding="utf-8"))
        for path in rule_modules()
        if mode_references(path.read_text(encoding="utf-8"))
    }
    assert offenders == {}, "mode is registry and writer, never a branch in a rule"
