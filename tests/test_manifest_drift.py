"""Whether `upstream/rules-<pin>.json` still is what its generator produced.

Split from `test_rules_manifest.py`, which asserts what the manifest *says*
about upstream. This module asserts that nobody has edited it by hand. The two
questions read the same file and share nothing else, and putting them together
pushed one module past the size the hooks warn at.

The honest limit first: a checkout with no network and no `tools/.upstream/`
cache cannot compare a generated file against the sources that generated it,
because it does not have them. `test_regenerating_produces_the_committed_file`
is that comparison, it is the only complete one, and it skips loudly rather than
pretending. Everything above it is what remains possible offline:

- `upstream/rules-<pin>.sha256` is a digest over the manifest's own 61 rule
  records. A hand-edit to any of the five strings compat emits verbatim changes
  it, so the edit has to be made in two files rather than one. That is not a
  cryptographic barrier and is not meant to be. It is the difference between an
  edit nothing notices and an edit that has to be made deliberately, twice, with
  a `.sha256` in the diff for a reviewer to ask about. The generator does not
  write that file, on purpose: if it did, `map_rules.py` would tie the two
  together and re-running it would launder a hand-edit into a matching digest.
- `source_sha256` inside the manifest records the SHA-256 of each Java file
  upstream served at the pin. Offline it proves nothing about upstream, but it
  pins which bytes are claimed, and any checkout that does have the cache can
  check the claim without a network round trip.

Bumping the pin therefore means: edit `upstream/pins.json`, re-run
`.venv/bin/python tools/map_rules.py`, then paste the digest this module prints
into the new `upstream/rules-<pin>.sha256`.
"""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PINS = json.loads((ROOT / "upstream" / "pins.json").read_text())
PIN = PINS["gtfs_realtime_validator"]["commit"]
MANIFEST_PATH = ROOT / "upstream" / f"rules-{PIN[:7]}.json"
DIGEST_PATH = ROOT / "upstream" / f"rules-{PIN[:7]}.sha256"
CACHE = ROOT / "tools" / ".upstream" / PIN

# The five strings `ValidationRules.java` carries per rule. Named here because
# the digest exists to protect exactly these: they are what compat output emits
# verbatim, so a silent edit to one is a silent divergence from the jar.
VERBATIM_FIELDS = ("error_id", "severity", "title", "error_description", "occurrence_suffix")


def rule_digest(rules: dict) -> str:
    """SHA-256 over every rule record, in declaration order.

    Serialised the way the generator would have to serialise it: no key sorting,
    so a reordered record fails, and `ensure_ascii` so the digest does not move
    with a locale. Covers the five strings plus `emitters` and `batch_reachable`,
    which is every field of every rule.
    """
    payload = json.dumps(rules, ensure_ascii=True, sort_keys=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def test_all_sixty_one_rules_match_the_separately_committed_digest(manifest: dict):
    """The whole verbatim check, offline, for all 61 rather than a spot-checked 3.

    `test_rules_manifest.py` still pastes three records out in full, because a
    digest says "changed" and those say *what the value is*. This says the other
    fifty-eight are equally untouched.
    """
    expected = DIGEST_PATH.read_text().strip()
    actual = rule_digest(manifest["rules"])
    assert actual == expected, (
        f"{MANIFEST_PATH.name} does not match {DIGEST_PATH.name}. If upstream moved, re-run "
        f".venv/bin/python tools/map_rules.py and write {actual} to {DIGEST_PATH.name}. If it "
        f"did not, the manifest was hand-edited: git diff {MANIFEST_PATH.name}."
    )


def test_the_digest_moves_when_any_rule_string_moves(manifest: dict):
    """Non-vacuity, asserted rather than assumed.

    A digest over a subset of the data would pass the test above while leaving
    most of the manifest unprotected, and nothing else would say so. This
    perturbs every one of the 61 rules' five strings in turn and requires the
    digest to notice each one, which is 305 edits the offline suite now catches.
    """
    baseline = rule_digest(manifest["rules"])
    assert len(manifest["rules"]) == 61
    for rule_id in manifest["rules"]:
        for field in VERBATIM_FIELDS:
            edited = json.loads(json.dumps(manifest["rules"]))
            edited[rule_id][field] = f"{edited[rule_id][field]}!"
            assert rule_digest(edited) != baseline, f"the digest ignores {rule_id}.{field}"


def test_the_manifest_records_a_digest_of_every_java_file_it_read(manifest: dict):
    """The artefact names its inputs, so the pin is not the only thing to trust.

    The key set is asserted against the generator's own `wanted()` rather than
    against a pasted list: a file added there and absent here means the manifest
    was generated before that source was being read.
    """
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import map_rules
    finally:
        sys.path.pop(0)

    digests = manifest["source_sha256"]
    assert set(digests) == set(map_rules.wanted())
    assert list(digests) == sorted(digests), "written sorted so the field is byte-stable"
    assert all(len(digest) == 64 and int(digest, 16) >= 0 for digest in digests.values())


def test_the_recorded_source_digests_match_the_cached_java():
    """The claim `source_sha256` makes, checked wherever the sources are on disk.

    The cache is gitignored and keyed by SHA, so this runs for anyone who has
    ever regenerated at this pin and skips on a clean checkout. It is cheaper
    than the regeneration test and catches the same class of drift in the
    sources, though not in the parsing.
    """
    if not CACHE.is_dir():
        pytest.skip(f"no cached upstream Java at {CACHE}; run tools/map_rules.py to fetch it")
    manifest = json.loads(MANIFEST_PATH.read_text())
    for name, digest in manifest["source_sha256"].items():
        cached = CACHE / name
        assert cached.is_file(), f"{name} is recorded in the manifest but not cached"
        assert hashlib.sha256(cached.read_bytes()).hexdigest() == digest, name


def test_regenerating_produces_the_committed_file():
    """Hand-editing a generated file makes every drift signal lie.

    The only check that compares the artefact against upstream's actual Java,
    and therefore the only one that would catch the generator's *parsing*
    drifting rather than its output being edited. It needs the sources, so it
    skips without them, and the skip reason says what stopped running.
    """
    import subprocess
    import sys
    import urllib.error

    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import map_rules
    finally:
        sys.path.pop(0)
    try:
        map_rules.sources()
    except (urllib.error.URLError, OSError) as exc:
        pytest.skip(
            "NOT ENFORCED: source-versus-artefact drift was not checked at all. Regenerating "
            f"{MANIFEST_PATH.name} needs upstream's Java at the pin, which is neither cached "
            f"under tools/.upstream/ nor fetchable ({exc}). Only the offline digest checks in "
            "this module ran, and they compare the manifest against a value committed beside "
            "it rather than against upstream."
        )

    before = MANIFEST_PATH.read_text()
    subprocess.run([sys.executable, "tools/map_rules.py"], check=True, cwd=ROOT)
    assert MANIFEST_PATH.read_text() == before
