"""The zero-third-party-runtime promise, asserted rather than trusted.

`gtfs-realtime-bindings` is a dev dependency used as an oracle. Importing it
from `src/` would be a design change, and one that installs cleanly in
development and fails only for a user.

The check is an allowlist rather than a blocklist, because a blocklist only
catches the packages someone thought to name: a stray `import requests` or
`import numpy` would pass a `google`/`protobuf` blocklist silently and reach a
user as exactly the same broken install. So an import under `src/` is acceptable
only if its root is the package itself, the one permitted third-party root, or a
standard-library module, per `sys.stdlib_module_names`, which is itself stdlib
and needs no help to answer.

The permitted third-party root is the sibling `gtfs-validator`, which
`static/adapter.py` reads the static feed through and which has no dependencies
of its own, so the promise this file names holds transitively. It is one name
and not a category:
widening this to "anything installed" is a design change, and
`test_only_adapter_touches_the_sibling.py` narrows it further by naming the
single module allowed to import it.
"""

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
PACKAGE = "gtfs_rt_validator"
SIBLING = "gtfs_validator"


def imported_names(tree: ast.AST) -> list[str]:
    """Every absolute module name imported by a parsed module.

    Relative imports are skipped: they resolve inside the package by
    construction, so they can never name a third party.
    """
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            names.append(node.module or "")
    return names


def test_no_module_under_src_imports_a_third_party_package():
    assert SRC.is_dir(), f"expected the package source at {SRC}"
    scanned = 0
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        scanned += 1
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name in imported_names(tree):
            root = name.split(".")[0]
            if root in (PACKAGE, SIBLING) or root in sys.stdlib_module_names:
                continue
            offenders.append(f"{path.relative_to(SRC.parent)}: import {name}")
    # A scan that finds nothing passes, so the count is part of the assertion.
    assert scanned, f"no modules found under {SRC}"
    assert not offenders, "third-party runtime imports under src/:\n" + "\n".join(offenders)
