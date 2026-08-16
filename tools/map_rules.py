"""Generate `upstream/rules-<pin>.json` from upstream's Java at the pinned SHA.

The manifest is two things at once. It is the drift source: 61 constants, 57 of
them emitted, 56 of those reachable from `BatchProcessor`, and any of those
numbers moving means upstream moved. It is also the compat writer's data source,
because the five strings `ValidationRules.java` carries per rule are what compat
output emits verbatim, so they are extracted with Java's own escape rules rather
than approximated.

This file fetches the Java and assembles the artefact. Reading the Java is
`javascan.py`, which is where the parsing traps that decide whether the counts
come out right are written down.

Reads `upstream/pins.json` for the SHA, so a pin bump is a one-line edit there.
Sources are cached under `tools/.upstream/<sha>/` (gitignored) and re-downloaded
only when absent; the cache is keyed by SHA so a bump cannot reuse stale Java.
Reads no environment variables: raw.githubusercontent.com serves these
unauthenticated, and no GitHub API call is needed.

Because that cache is gitignored, a clean checkout holds the artefact and no
trace of what produced it. `source_sha256` is the trace: the SHA-256 of each
Java file as served, written into the manifest so a checkout with the sources
back can prove they are the same bytes. It does not help a checkout with no
network, which is what `upstream/rules-<pin>.sha256` is for; that file is
deliberately *not* written here, and `tests/test_manifest_drift.py` says why.

Run: .venv/bin/python tools/map_rules.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

from javascan import declarations, emitters, group_order, registrations

ROOT = Path(__file__).resolve().parent.parent
PINS = ROOT / "upstream" / "pins.json"
CACHE = ROOT / "tools" / ".upstream"
LIB = "gtfs-realtime-validator-lib/src/main/java/edu/usf/cutr/gtfsrtvalidator/lib"

# The nine `FeedEntityValidator`s, plus `StopLocationTypeValidator`, which sits
# in a different package because it implements `GtfsFeedValidator` instead and
# is registered nowhere. That difference is the whole reason E010 is emitted but
# unreachable, so the odd path is load-bearing rather than a typo.
FEED_ENTITY_VALIDATORS = (
    "CrossFeedDescriptor",
    "FrequencyTypeOne",
    "FrequencyTypeZero",
    "Header",
    "StopTimeUpdate",
    "Stop",
    "Timestamp",
    "TripDescriptor",
    "Vehicle",
)
GTFS_FEED_VALIDATORS = ("StopLocationType",)


def pin() -> tuple[str, str]:
    pins = json.loads(PINS.read_text(encoding="utf-8"))["gtfs_realtime_validator"]
    return pins["repo"], pins["commit"]


def wanted() -> dict[str, str]:
    """Local file name to path within the upstream repository."""
    paths = {
        "ValidationRules.java": f"{LIB}/validation/ValidationRules.java",
        "BatchProcessor.java": f"{LIB}/batch/BatchProcessor.java",
    }
    for name in FEED_ENTITY_VALIDATORS:
        paths[f"{name}Validator.java"] = f"{LIB}/validation/rules/{name}Validator.java"
    for name in GTFS_FEED_VALIDATORS:
        paths[f"{name}Validator.java"] = f"{LIB}/validation/gtfs/{name}Validator.java"
    return paths


def sources() -> dict[str, bytes]:
    """Cached Java at the pin, downloading only the files that are missing.

    Raises rather than returning partial results, so a caller can tell "the
    network is unavailable" from "upstream moved this file".

    Bytes rather than text, because `source_sha256` digests what upstream
    actually served. Decoding first would fold CRLF to LF and a BOM to nothing,
    so two different upstream files could digest the same.
    """
    repo, commit = pin()
    directory = CACHE / commit
    directory.mkdir(parents=True, exist_ok=True)
    blobs = {}
    for name, path in wanted().items():
        cached = directory / name
        if not cached.exists():
            url = f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"
            print(f"fetching {path}")
            with urllib.request.urlopen(url) as response:
                cached.write_bytes(response.read())
        blobs[name] = cached.read_bytes()
    return blobs


def source_sha256(blobs: dict[str, bytes]) -> dict[str, str]:
    """Per-file SHA-256 of the Java this manifest was generated from.

    The manifest and its pin alone do not say which bytes upstream served at that
    SHA, and a clean checkout has no cache to compare against, so without this
    the only record of the inputs is a gitignored directory. Sorted by name so
    the field is byte-stable whatever order `sources()` filled its dict in.
    """
    return {name: hashlib.sha256(blob).hexdigest() for name, blob in sorted(blobs.items())}


def build() -> dict:
    blobs = sources()
    texts = {name: blob.decode("utf-8") for name, blob in blobs.items()}
    repo, commit = pin()
    rules = declarations(texts["ValidationRules.java"])
    order = registrations(texts["BatchProcessor.java"])
    emitted = emitters(texts, set(rules))

    unknown = set(order) - {name.removesuffix(".java") for name in texts}
    if unknown:
        sys.exit(f"BatchProcessor registers validators this tool never read: {sorted(unknown)}")

    for rule_id, rule in rules.items():
        rule["emitters"] = emitted.get(rule_id, [])
        rule["batch_reachable"] = any(name in order for name in rule["emitters"])
    return {
        "generated_by": "tools/map_rules.py",
        "do_not_edit": "Regenerate with .venv/bin/python tools/map_rules.py",
        "repo": repo,
        "pin": commit,
        "source_sha256": source_sha256(blobs),
        "batch_registration_order": order,
        "group_order": group_order(texts, order, emitted),
        "rules": rules,
    }


def report(manifest: dict) -> None:
    rules = manifest["rules"]
    emitted = [rule for rule in rules.values() if rule["emitters"]]
    counts: dict[str, int] = {}
    for rule in emitted:
        for name in rule["emitters"]:
            counts[name] = counts.get(name, 0) + 1
    ids = sorted(rules)
    print(
        f"  {len(rules)} declared: {sum(1 for r in ids if r[0] == 'E')} E, "
        f"{sum(1 for r in ids if r[0] == 'W')} W"
    )
    print(
        f"  {len(emitted)} emitted, "
        f"{sum(1 for r in emitted if r['batch_reachable'])} batch-reachable"
    )
    print(
        f"  emitted but unreachable: "
        f"{sorted(r['error_id'] for r in emitted if not r['batch_reachable'])}"
    )
    print(
        f"  emitted by nothing: "
        f"{sorted(r['error_id'] for r in rules.values() if not r['emitters'])}"
    )
    for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {name}: {count}")
    print(f"  registration order: {manifest['batch_registration_order']}")
    for name, ids in manifest["group_order"].items():
        print(f"  {name} groups: {', '.join(ids)}")


def main() -> None:
    manifest = build()
    target = ROOT / "upstream" / f"rules-{manifest['pin'][:7]}.json"
    # ASCII-escaped so the committed manifest is byte-identical whatever the
    # writer's locale, and 2-space indent so a drift diff reads line by line.
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    report(manifest)


if __name__ == "__main__":
    main()
