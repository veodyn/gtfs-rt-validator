"""One module under `src/` may import the sibling, and it is named here.

The sibling `gtfs-validator` is the only third-party runtime dependency this
project has, and confining it to `static/adapter.py` is what keeps that fact
cheap to verify: everything downstream consumes `RawTables` and then
`StaticContext`, neither of which knows the sibling exists. The adapter also
carries an unsupported import of `DependencyFailed`, so a second importer would
be a second place to fix when the sibling exports it.

Companion to `test_no_runtime_dependency.py`, which allows `gtfs_validator`
anywhere under `src/`. That one says which package may be imported; this one
says by whom, directly and transitively.

The transitive half is the one that caught a real regression: a pure
string-building helper in `rules/_shared/` imported `RuleContractError` from
`runner.context`, whose package `__init__` reaches `static.adapter` and
therefore the sibling. Nothing failed, because the sibling is installed
wherever this suite runs. So the check below imports the rules layer in a clean
interpreter and reads `sys.modules`, which is the only way to see an edge that
a passing suite hides.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
SIBLING = "gtfs_validator"
ONLY_IMPORTER = "gtfs_rt_validator/static/adapter.py"

RULES = SRC / "gtfs_rt_validator" / "rules"

#: What the rules layer may not drag in. `static` is named as well as the
#: sibling because it is the layer that imports it, so an edge into `static` is
#: the same regression one commit before it shows up as an edge into
#: `gtfs_validator`.
FORBIDDEN = (SIBLING, "gtfs_rt_validator.static")

PROBE = """
import importlib, json, sys

def forbidden():
    return {{
        name
        for name in sys.modules
        for banned in {forbidden!r}
        if name == banned or name.startswith(banned + ".")
    }}

blamed, seen = {{}}, forbidden()
for module in {modules!r}:
    importlib.import_module(module)
    now = forbidden()
    blamed[module] = sorted(now - seen)
    seen = now
print(json.dumps(blamed))
"""


def rule_layer() -> list[str]:
    """Every module under `rules/`, found rather than listed.

    Listing them would cover the four that exist today and none of the 56 to
    come, which is exactly the file the next agent adds the edge back in.
    """
    modules = []
    for path in sorted(RULES.rglob("*.py")):
        relative = path.relative_to(SRC).with_suffix("")
        parts = relative.parts[:-1] if relative.name == "__init__" else relative.parts
        modules.append(".".join(parts))
    return modules


def blamed_for_forbidden_imports() -> dict[str, list[str]]:
    """Per module, the forbidden modules importing it brought in with it.

    One clean interpreter, importing them in order and reading `sys.modules`
    after each, so the module that first pulled something in is the one blamed
    for it. A subprocess, because by the time any test runs this process has
    imported the whole package and `sys.modules` would answer for the suite
    rather than for the module under test.
    """
    probe = PROBE.format(forbidden=FORBIDDEN, modules=rule_layer())
    result = subprocess.run(  # noqa: S603 - argv is this module's own constants
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return json.loads(result.stdout)


def imports_the_sibling(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level:
            names = [node.module or ""]
        else:
            continue
        if any(name == SIBLING or name.startswith(f"{SIBLING}.") for name in names):
            return True
    return False


def test_the_adapter_is_the_only_module_under_src_importing_the_sibling():
    importers = [
        str(path.relative_to(SRC))
        for path in sorted(SRC.rglob("*.py"))
        if imports_the_sibling(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert importers == [ONLY_IMPORTER]


def test_the_rules_layer_imports_neither_the_sibling_nor_the_static_layer():
    """A rule is a string builder over a decoded message, and the shared helpers
    under it are less than that. None of them needs the static feed loaded to be
    imported, and an edge that loads it makes the whole rules layer unimportable
    wherever the sibling is not installed."""
    blamed = blamed_for_forbidden_imports()

    assert blamed == {module: [] for module in blamed}
    assert "gtfs_rt_validator.rules._shared.walks" in blamed
