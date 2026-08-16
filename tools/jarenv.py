"""Where the jar lives, which JDK builds it, and which SHA it is pinned to.

Shared by `tools/build_jar.py`, `tools/run_jar.py`, `tools/gen_golden.py` and the
two jar test modules, so none of them restates a path or a pin. Python rather
than shell for the same reason every other generator here is: the tests import
these functions to decide whether to skip, and a shell script cannot be imported.

Everything this module points at is gitignored. `jar-build/` holds a shallow
checkout of upstream at the pin plus Maven's `target/` output, and the fat jar
inside it is 28 MB. Nothing here is ever committed; what gets committed is the
crafted corpus and the goldens the jar produced from it.
"""

from __future__ import annotations

import functools
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINS = ROOT / "upstream" / "pins.json"
BUILD = ROOT / "jar-build"
CHECKOUT = BUILD / "upstream"
LIB = CHECKOUT / "gtfs-realtime-validator-lib"
JAR = LIB / "target" / "gtfs-realtime-validator-lib-1.0.0-SNAPSHOT-withAllDependencies.jar"

# Upstream's own Apache-2.0 test resources, produced by `process-test-resources`
# during the build. `-DskipTests` skips running the tests, not compiling them, so
# these land even on a build that never executes a test.
TEST_RESOURCES = LIB / "target" / "test-classes"

# The static feed the goldens are paired with, committed so a checkout with no
# jar can still read them. NOTICE already declares tests/fixtures/gtfs/*.zip as
# material taken from upstream rather than derived from it.
GTFS_FIXTURES = ROOT / "tests" / "fixtures" / "gtfs"
GOLDEN_GTFS = GTFS_FIXTURES / "testagency.zip"

# Where the crafted .pb inputs and the goldens the jar wrote for them live.
CORPUS = ROOT / "tests" / "fixtures" / "jar"
MANIFEST = CORPUS / "manifest.json"

# Tier 1, the synthesised conformance corpus. One subdirectory per group,
# because a group is one jar invocation and `-gtfs` takes one archive.
CONFORMANCE = ROOT / "tests" / "fixtures" / "conformance"
CONFORMANCE_MANIFEST = CONFORMANCE / "manifest.json"

RESULTS_SUFFIX = ".results.json"

#: The `Locale.Category.FORMAT` locale the committed goldens were produced
#: under. `VehicleValidator.java:185` and `:229` call `String.format("%.2f",
#: ...)` with no `Locale` argument, so the decimal separator is whatever that
#: category resolves to, and this project writes a dot unconditionally.
GOLDEN_LOCALE = "en-US"

_VERSION = re.compile(r'version "(\d+)')


class NoJdk17Error(RuntimeError):
    """No JDK 17 was found. Upstream targets 17 and nothing else will do."""


class WrongLocaleError(RuntimeError):
    """The JVM's FORMAT locale is not the one the goldens were made under."""


def pin() -> tuple[str, str]:
    """The upstream repository and commit the jar is built from."""
    pins = json.loads(PINS.read_text(encoding="utf-8"))["gtfs_realtime_validator"]
    return pins["repo"], pins["commit"]


def _reports_17(java: Path) -> bool:
    """`java -version` writes to stderr, and has since long before 17."""
    try:
        result = subprocess.run(
            [str(java), "-version"], capture_output=True, text=True, check=False, timeout=60
        )
    except OSError:
        return False
    match = _VERSION.search(result.stderr or result.stdout)
    return bool(match) and match.group(1) == "17"


def _candidates() -> list[Path]:
    """Plausible JAVA_HOMEs, best guess first.

    `/usr/libexec/java_home -v 17` is macOS' own answer and is the only one that
    is authoritative, which is why it goes first. Homebrew's Maven pulls in the
    newest JDK as a dependency and `mvn` then defaults to it, so on this machine
    the JDK on PATH is 26 and asking it would find nothing.
    """
    homes: list[Path] = []
    locator = Path("/usr/libexec/java_home")
    if locator.exists():
        found = subprocess.run(
            [str(locator), "-v", "17"], capture_output=True, text=True, check=False
        )
        if found.returncode == 0 and found.stdout.strip():
            homes.append(Path(found.stdout.strip()))
    # Distribution layouts, newest-looking last so sorting is not relied on.
    for pattern in ("/usr/lib/jvm/*", "/opt/java/*", "/Library/Java/JavaVirtualMachines/*"):
        parent = Path(pattern).parent
        if parent.is_dir():
            homes.extend(sorted(parent.glob(Path(pattern).name)))
    homes.extend(sorted((Path.home() / ".sdkman" / "candidates" / "java").glob("*")))
    # A JDK 17 that is simply on PATH. Two hops up from `bin/java`.
    on_path = shutil.which("java")
    if on_path:
        homes.append(Path(on_path).resolve().parent.parent)
    return homes


def java_home_17() -> Path:
    """The JAVA_HOME of a JDK 17, or raise.

    Deliberately not configured by an environment variable of ours: this is
    discovery, not configuration. An inherited `JAVA_HOME` is consulted only as
    one candidate among several and only if it really is 17, so a shell that
    happens to point at 26 cannot silently produce a jar built against the wrong
    release.
    """
    seen: set[Path] = set()
    for home in _candidates():
        if home in seen or not home.is_dir():
            continue
        seen.add(home)
        for java in (home / "bin" / "java", home / "Contents" / "Home" / "bin" / "java"):
            if java.exists() and _reports_17(java):
                return java.parent.parent
    raise NoJdk17Error(
        "no JDK 17 found. Upstream's pom targets 17 and a newer JDK produces a "
        "different jar. Install one (macOS: `brew install openjdk@17`; Debian: "
        "`apt install openjdk-17-jdk`) and re-run. Looked at: "
        + ", ".join(str(home) for home in sorted(seen))
    )


def java_17() -> Path:
    """The `java` binary of a JDK 17."""
    return java_home_17() / "bin" / "java"


def jar_present() -> bool:
    """Whether a built jar is sitting where `build_jar.py` leaves one.

    The tests call this to skip rather than fail: the jar is gitignored, so a
    clean checkout and most CI runs will not have one.
    """
    return JAR.exists()


@functools.cache
def properties(java: Path) -> dict[str, str]:
    """The running JVM's own system properties, as it reports them.

    Read from the JVM rather than from the lookup that found it, so a JAVA_HOME
    that lies about a release cannot get past `checked_java_17`, and so the
    options a JVM picks up from `JAVA_TOOL_OPTIONS` or `_JAVA_OPTIONS` are
    visible here: those reach the jar's JVM too, and this probe inherits the
    same environment.
    """
    done = subprocess.run(
        [str(java), "-XshowSettings:properties", "-version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    props: dict[str, str] = {}
    for line in (done.stderr + done.stdout).splitlines():
        key, separator, value = line.partition(" = ")
        if separator:
            props[key.strip()] = value.strip()
    return props


def format_locale(props: dict[str, str]) -> str:
    """`Locale.getDefault(Locale.Category.FORMAT)`, which is what `%.2f` reads.

    Java keeps two default locales. `user.language` and `user.country` set the
    base one, and `user.language.format` and `user.country.format` override the
    FORMAT category on their own (`java.util.Locale.initDefault(Category)` reads
    the `.format` property first and falls back to the base). Reading only the
    base pair therefore reports `en-US` for a JVM started with
    `-Duser.language.format=de -Duser.country.format=DE`, which is measured to
    write `1,00 mile(s)` where the golden has `1.00 mile(s)`. Both properties
    appear in `-XshowSettings:properties` output, and the fallback below is the
    one Java itself applies.
    """
    language = props.get("user.language.format") or props.get("user.language", "?")
    country = props.get("user.country.format") or props.get("user.country", "?")
    return f"{language}-{country}"


def checked_java_17() -> tuple[Path, str, str]:
    """A JDK 17 `java` whose own properties are the goldens', or raise.

    Returns the binary, its `java.version` and its FORMAT locale. Every path
    that invokes the jar goes through this, because both pins are properties of
    the JVM the jar runs in rather than of the harness that starts it.
    """
    java = java_17()
    props = properties(java)
    version = props.get("java.version", "")
    if not version.startswith("17."):
        raise NoJdk17Error(
            f"{java} reports java.version {version!r}. Float.toString was rewritten in "
            "JDK 19 (JDK-4511638), so E026, E027, E028, E029 and W004 render differently "
            "there and the comparison would be against bytes neither side is wrong about."
        )
    locale = format_locale(props)
    if locale != GOLDEN_LOCALE:
        raise WrongLocaleError(
            f"the JVM's FORMAT locale is {locale!r}, not {GOLDEN_LOCALE!r}. "
            'VehicleValidator calls String.format("%.2f", ...) with no Locale, so a '
            "comma-decimal environment writes different bytes for the same float and "
            "neither result is wrong. Re-run under the goldens' locale."
        )
    return java, version, locale
