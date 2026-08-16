"""Whether `upstream/realtime-best-practices.md` still is what the pin serves.

The design's drift table lists three sources to watch and, until this landed,
two of them were watched and the third was not. Upstream's Java is watched by
`upstream/rules-<pin>.json` plus its hand-kept `.sha256` plus
`test_manifest_drift.py`; the proto is watched by the vendored copy plus the two
generated schemas plus their regeneration tests. The Best Practices document had
no copy, no digest, no fetcher and no test, so a `practice:` citation pointed at
a document nobody in the repository held.

This closes it with the same mechanism rather than a second one, so the honest
limits are the same too. `upstream/realtime-best-practices.sha256` is kept by
hand and `tools/fetch_practices.py` deliberately does not write it: a fetcher
that wrote its own digest would launder a hand-edit into a matching digest on
the next run. Offline that digest is what stands between the committed bytes and
a quiet edit; it is not a cryptographic barrier, it is the difference between an
edit nothing notices and an edit that has to be made twice with a `.sha256` in
the diff. The only complete check needs the network, and it skips loudly.

Bumping the pin means: edit `upstream/pins.json`, run
`.venv/bin/python tools/fetch_practices.py`, paste the digest it prints into the
sidecar, then re-run `tools/scan_clauses.py` and re-adjudicate every statement
whose verdict moved.
"""

import hashlib
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCUMENT = ROOT / "upstream" / "realtime-best-practices.md"
DIGEST = ROOT / "upstream" / "realtime-best-practices.sha256"
PIN = json.loads((ROOT / "upstream" / "pins.json").read_text(encoding="utf-8"))[
    "realtime_best_practices"
]


def test_the_committed_document_matches_the_committed_digest():
    actual = hashlib.sha256(DOCUMENT.read_bytes()).hexdigest()
    assert actual == DIGEST.read_text(encoding="utf-8").strip(), (
        f"{DOCUMENT.name} does not match {DIGEST.name}. If the pin moved, re-run "
        f".venv/bin/python tools/fetch_practices.py and write {actual} to {DIGEST.name}. If it "
        f"did not, the document was hand-edited: git diff {DOCUMENT.name}."
    )


def test_the_document_is_the_size_that_was_measured():
    """Two numbers rather than one, because a digest says "changed" and these
    say what the value is. Both were read off the pinned document when the
    practice tier was written and both reproduce."""
    body = DOCUMENT.read_bytes()
    assert len(body) == 16426
    assert body.decode("utf-8").count("\n") == 166


def test_the_pin_names_the_document_this_repository_holds():
    """The sidecar and the bytes agree; this says which upstream commit they
    claim to be, so a reader does not have to open the fetcher to find out."""
    assert PIN["repo"] == "MobilityData/gtfs.org"
    assert PIN["path"] == "docs/en/documentation/realtime/realtime-best-practices.md"
    assert PIN["commit"] == "5a495dbf9a53c3633e3352e0d2d2caabf761ed8a"


def test_refetching_at_the_pin_produces_the_committed_bytes():
    """The only check that compares the vendored copy against what upstream
    actually serves, and therefore the only one that would catch the pin naming
    a commit whose content is not this. It needs the network and skips without
    it, and the skip reason says what stopped running."""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import fetch_practices
    finally:
        sys.path.pop(0)
    try:
        served = fetch_practices.fetch()
    except (urllib.error.URLError, OSError) as exc:
        pytest.skip(
            "NOT ENFORCED: pin-versus-vendored drift was not checked at all. Refetching "
            f"{DOCUMENT.name} needs raw.githubusercontent.com, which is unreachable ({exc}). "
            "Only the offline digest check in this module ran, and it compares the document "
            "against a value committed beside it rather than against upstream."
        )
    assert served == DOCUMENT.read_bytes()
