"""Pack `upstream/rules-<pin>.json` into `src/gtfs_rt_validator/data/rules.json`.

The same 61 rules exist twice on purpose, and the two copies answer different
questions.

`upstream/rules-<pin>.json` is the drift artefact. Its name carries the upstream
SHA, it records the SHA-256 of every Java file `map_rules.py` read, and it lives
outside the package because a wheel has no reason to ship a record of somebody
else's source tree. `src/gtfs_rt_validator/data/rules.json` is what the compat
writer reads at run time: an installed wheel has no `upstream/` directory, and
the five strings `ValidationRules.java` carries per rule are emitted verbatim in
compat output, so they must travel with the code.

The packed form is a **subset, not a copy**. Exactly one field is dropped,
`source_sha256`, because it is a claim about files the runtime cannot see and
must never act on; verifying it is `tests/test_manifest_drift.py`'s job, in a
checkout, against a cache. Everything else is carried through unchanged, and
every rule record is copied byte for byte in declaration order. That is what
lets `upstream/rules-<pin>.sha256` cover both files: `tests/test_packed_manifest.py`
recomputes that digest over the packed rules, so a reshape here shows up as a
digest mismatch rather than as silently different compat output.

One field is added: `packed_from`, naming the artefact this was derived from, so
an installed copy says where it came from and not only which pin it claims.

This tool reads no Java and no network. It reads a committed artefact, which is
why its regeneration test runs unconditionally where `map_rules.py`'s has to
skip without the sources.

Run: .venv/bin/python tools/pack_rules.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINS = ROOT / "upstream" / "pins.json"
PACKED = ROOT / "src" / "gtfs_rt_validator" / "data" / "rules.json"

# Dropped rather than carried. Named as a set so adding a field to the artefact
# is a deliberate decision here about whether the runtime should see it.
GENERATOR_TRACE = frozenset({"source_sha256"})
RULE_FIELDS = (
    "error_id",
    "severity",
    "title",
    "error_description",
    "occurrence_suffix",
    "emitters",
    "batch_reachable",
)


def source_path() -> Path:
    pin = json.loads(PINS.read_text(encoding="utf-8"))["gtfs_realtime_validator"]["commit"]
    return ROOT / "upstream" / f"rules-{pin[:7]}.json"


def check(manifest: dict) -> None:
    """Refuse to pack an artefact this tool does not recognise.

    Not a re-run of the manifest's own tests, which assert what upstream says.
    This asserts only that every record has the fields the runtime reads, so a
    hole in the artefact fails here rather than at the first compat run that
    needs the missing string."""
    rules = manifest.get("rules")
    if not rules:
        sys.exit(f"{source_path().name} carries no rules")
    for rule_id, rule in rules.items():
        missing = [field for field in RULE_FIELDS if field not in rule]
        if missing:
            sys.exit(f"{rule_id} is missing {missing}; re-run tools/map_rules.py")
        if rule["error_id"] != rule_id:
            sys.exit(f"{rule_id} declares error_id {rule['error_id']!r}")


def pack(manifest: dict, source: Path) -> dict:
    """The artefact minus its generator trace, in the artefact's own key order.

    Built by walking `manifest` rather than by naming the fields to keep, so a
    field added upstream of here reaches the runtime instead of being dropped
    silently. `generated_by` and `do_not_edit` are overwritten because they now
    describe this tool, and a stale `map_rules.py` in the packed file would send
    the next person to regenerate the wrong file."""
    packed = {key: value for key, value in manifest.items() if key not in GENERATOR_TRACE}
    packed["generated_by"] = "tools/pack_rules.py"
    packed["do_not_edit"] = "Regenerate with .venv/bin/python tools/pack_rules.py"
    packed["packed_from"] = f"upstream/{source.name}"
    return packed


def main() -> None:
    source = source_path()
    manifest = json.loads(source.read_text(encoding="utf-8"))
    check(manifest)
    packed = pack(manifest, source)
    PACKED.parent.mkdir(parents=True, exist_ok=True)
    # Same serialisation as the artefact: ASCII-escaped so the committed bytes
    # do not move with a locale, 2-space indent so a diff reads line by line.
    PACKED.write_text(json.dumps(packed, indent=2) + "\n", encoding="utf-8")
    rules = packed["rules"]
    print(f"wrote {PACKED} from {source.name}")
    print(
        f"  {len(rules)} rules, {sum(1 for r in rules.values() if r['batch_reachable'])} reachable"
    )
    print(f"  dropped: {sorted(GENERATOR_TRACE & set(manifest))}")


if __name__ == "__main__":
    main()
