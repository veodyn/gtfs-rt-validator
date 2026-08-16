"""Vendor `upstream/realtime-best-practices.md` at the pin in `pins.json`.

The proto is committed and verified against its pin, and upstream's Java is
recorded in `upstream/rules-<pin>.json` beside a hand-kept `.sha256`. The Best
Practices document had neither: no copy, no digest, no fetcher and no test, so
a `practice:` citation pointed at a document nobody in the repository held. This
closes that to the same standard rather than a second one.

Three files, mirroring the rules manifest exactly:

- `upstream/realtime-best-practices.md`, the bytes as served at the pin.
- `upstream/realtime-best-practices.sha256`, kept by hand and **not written
  here**, for the same reason `map_rules.py` does not write
  `upstream/rules-<pin>.sha256`: a generator that wrote its own digest would
  launder a hand-edit into a matching digest on the next run. Paste the digest
  this tool prints.
- `tests/test_practices_drift.py`, which compares the two offline.

Reads `GITHUB_TOKEN` if it is set, and no other environment variable, per the
`tools/` exemption from the project's no-environment-variables rule. The token
is optional: raw.githubusercontent.com serves this file unauthenticated, and it
only exists so a rate-limited runner can get past the anonymous quota.

Run: .venv/bin/python tools/fetch_practices.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINS = ROOT / "upstream" / "pins.json"
TARGET = ROOT / "upstream" / "realtime-best-practices.md"
DIGEST = ROOT / "upstream" / "realtime-best-practices.sha256"


def pin() -> dict[str, str]:
    return json.loads(PINS.read_text(encoding="utf-8"))["realtime_best_practices"]


def fetch() -> bytes:
    spec = pin()
    url = f"https://raw.githubusercontent.com/{spec['repo']}/{spec['commit']}/{spec['path']}"
    # An opener rather than `urlopen`, so the optional token rides on a header
    # without wrapping the URL in a `Request` and losing the literal `https://`
    # that makes the scheme readable at the call site.
    opener = urllib.request.build_opener()
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        opener.addheaders = [("Authorization", f"Bearer {token}")]
    with opener.open(url) as response:
        return response.read()


def main() -> int:
    body = fetch()
    digest = hashlib.sha256(body).hexdigest()
    TARGET.write_bytes(body)
    committed = DIGEST.read_text(encoding="utf-8").strip() if DIGEST.is_file() else None
    print(f"{TARGET.relative_to(ROOT)}: {len(body)} bytes, sha256 {digest}")
    if committed is None:
        print(f"write that digest to {DIGEST.relative_to(ROOT)}")
        return 0
    if committed != digest:
        print(f"MISMATCH: {DIGEST.name} says {committed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
