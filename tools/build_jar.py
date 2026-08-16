"""Build upstream's fat jar from the pinned SHA, idempotently.

Every differential here needs a jar to compare against, and a jar built from
anything but `upstream/pins.json`'s commit compares against the wrong software.
So this owns both halves: the shallow checkout at the pin and the Maven build
over it.

Two things are load-bearing.

**JDK 17.** Upstream's pom targets 17. Homebrew's Maven declares the newest JDK
as a dependency, so `mvn` on this machine defaults to 26 and produces a jar built
against the wrong release without saying so. `jarenv.java_home_17` finds a real
17 or raises; this script then passes it to Maven as `JAVA_HOME`, which is the
only way Maven takes the answer. That is a subprocess's environment rather than
this project's own configuration, which is why it does not break the
no-environment-variables rule.

**Idempotence.** A build takes long enough that a test suite cannot afford one
per run. The jar is rebuilt only when it is older than the newest source file in
the checkout, or absent, or `--force` is given.

Run: .venv/bin/python tools/build_jar.py
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from jarattest import checkout_head, stale
from jarenv import BUILD, CHECKOUT, JAR, LIB, NoJdk17Error, java_home_17, pin


def git(*args: str) -> str:
    """git inside the checkout, failing loudly."""
    return subprocess.run(
        ["git", "-C", str(CHECKOUT), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def fetch() -> None:
    """A depth-1 checkout at the pin, created or moved to it.

    `git init` plus `fetch <sha>` rather than `clone`, because a clone cannot be
    shallow *and* land on an arbitrary commit: `--depth 1` clones the default
    branch tip. Fetching the SHA directly downloads one commit's trees and
    nothing else, which is 4 MB against the repository's full history.
    """
    repo, commit = pin()
    url = f"https://github.com/{repo}"
    if checkout_head() == commit:
        print(f"checkout already at {commit[:7]}")
        return
    BUILD.mkdir(parents=True, exist_ok=True)
    if not (CHECKOUT / ".git").is_dir():
        CHECKOUT.mkdir(parents=True, exist_ok=True)
        git("init", "-q")
        git("remote", "add", "origin", url)
    else:
        git("remote", "set-url", "origin", url)
    print(f"fetching {repo} at {commit[:7]}")
    git("fetch", "-q", "--depth", "1", "origin", commit)
    git("checkout", "-q", "FETCH_HEAD")
    landed = checkout_head()
    if landed != commit:
        sys.exit(f"checkout landed on {landed}, wanted {commit}")


def maven() -> Path:
    found = shutil.which("mvn")
    if found is None:
        sys.exit(
            "no `mvn` on PATH. Upstream builds with Maven (macOS: `brew install maven`; "
            "Debian: `apt install maven`)."
        )
    return Path(found)


def build() -> None:
    home = java_home_17()
    mvn = maven()
    print(f"building with JAVA_HOME={home} and {mvn}")
    # `-pl ... -am` builds the lib module and the parent pom it inherits from,
    # skipping the webapp module, which pulls a Jetty stack the differential
    # never runs.
    #
    # The environment handed to Maven is built rather than inherited: JAVA_HOME
    # so it uses 17 (its wrapper reads that and nothing else), HOME so it finds
    # ~/.m2, and a PATH holding only the JDK and Maven themselves. A stray
    # MAVEN_OPTS or JAVA_TOOL_OPTIONS in the developer's shell therefore cannot
    # change the artefact the differential compares against.
    result = subprocess.run(
        [
            str(mvn),
            "-q",
            "-pl",
            "gtfs-realtime-validator-lib",
            "-am",
            "package",
            "-DskipTests",
        ],
        cwd=CHECKOUT,
        env={
            "JAVA_HOME": str(home),
            "HOME": str(Path.home()),
            "PATH": f"{home / 'bin'}:{mvn.parent}:/usr/bin:/bin",
        },
        check=False,
    )
    if result.returncode != 0:
        sys.exit(f"maven failed with {result.returncode}; re-run without -q to see why")
    if not JAR.exists():
        sys.exit(f"maven succeeded but {JAR} is not there")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="rebuild even if the jar looks fresh")
    args = parser.parse_args()

    try:
        java_home_17()
    except NoJdk17Error as exc:
        print(exc, file=sys.stderr)
        return 2

    fetch()
    if not args.force and not stale():
        print(f"jar is newer than the checkout, nothing to do: {JAR}")
        return 0
    build()
    size = JAR.stat().st_size
    print(f"wrote {JAR} ({size / 1_048_576:.1f} MiB)")
    print(f"test resources at {LIB / 'target' / 'test-classes'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
