"""What the jar being run can actually be shown to be, rather than configured as.

`jarenv.pin()` is configuration. It says which upstream commit a jar *should*
have been built from, and a jar built from some other commit, or by another
project, answers to it just the same: the SHA is read out of
`upstream/pins.json` and never compared against the artefact. A differential
that labels its run with that SHA is therefore reporting an intention.

What can be checked without a jar that carries its own provenance (upstream's
Maven build embeds no commit) is the tree it came out of:

- `jar-build/upstream` is a git checkout, so its HEAD is readable, and
- the jar sits inside that checkout's `target/`, so its mtime against the
  newest source in the checkout says whether it postdates them.

Together those mean this artefact came out of a Maven build over sources at the
pin. A jar hand-copied into `target/` still defeats them, which is why
`attested_pin` returns the *reason* alongside the SHA and every report prints
it: an unverified pin may be printed as unverified, never as ground truth.

`jar_digest` is the other half. The build is not byte-reproducible across
machines, so a committed expected digest is not available, but printing the
running jar's own digest makes two different jars distinguishable in two
reports, which a configured SHA cannot do.
"""

from __future__ import annotations

import hashlib
import subprocess

from jarenv import CHECKOUT, JAR, pin

#: Everything Maven writes into the checkout, plus git's own store. Neither says
#: anything about whether the sources changed, and `target/` holds the jar being
#: timed against, so walking it would make the jar newer than itself.
IGNORED_DIRS = {"target", ".git"}


def checkout_head() -> str | None:
    """The commit `jar-build/upstream` sits on, or None if there is no checkout."""
    if not (CHECKOUT / ".git").is_dir():
        return None
    done = subprocess.run(
        ["git", "-C", str(CHECKOUT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.strip() if done.returncode == 0 else None


def newest_source() -> float:
    """The newest mtime among the checkout's sources, ignoring build output.

    A fresh `git checkout` stamps every file with the time it wrote them, so on
    a cold machine this is later than any jar and the build always runs. On a
    warm machine nothing has been rewritten, so the jar wins.
    """
    newest = 0.0
    for path in CHECKOUT.rglob("*"):
        if any(part in IGNORED_DIRS for part in path.relative_to(CHECKOUT).parts):
            continue
        if path.is_file():
            newest = max(newest, path.stat().st_mtime)
    return newest


def stale() -> bool:
    """Whether the jar predates the sources it is supposed to have been built from."""
    return not JAR.exists() or JAR.stat().st_mtime < newest_source()


def jar_digest() -> str:
    """The sha256 of the jar actually being run."""
    hashed = hashlib.sha256()
    with JAR.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            hashed.update(block)
    return hashed.hexdigest()


def attested_pin() -> tuple[str, str]:
    """The commit the running jar was built from, and how far that is evidence."""
    configured = pin()[1]
    head = checkout_head()
    if head is None:
        return configured, "configured, unverified: no checkout at jar-build/upstream"
    if head != configured:
        return configured, f"configured, CONTRADICTED: the checkout is at {head}"
    if stale():
        return configured, "configured, unverified: the jar is older than the checkout's sources"
    return configured, "verified against the checkout the jar was built in"
