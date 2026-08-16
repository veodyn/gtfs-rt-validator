"""Running the two Java oracles for `tools/diff_geometry_against_java.py`.

Everything about talking to the jars lives here: caching them from Maven
Central, launching one JVM per corpus, and reading the flat text each dumper
prints back into Python values. Nothing here compares anything.

The pre-LocationTech `com.vividsolutions:jts` groupId is deliberate.
`org.locationtech.jts` is a different artifact with different behaviour, and
upstream's pom.xml pins the old one. spatial4j 0.6 needs JTS beside it, because
`JtsSpatialContext.GEO` is what `GtfsMetadata` builds its multipoint with.
"""

from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path

import geoboxes
import geocorpus
from geoboxes import BoxCase
from geocorpus import Case

ROOT = Path(__file__).resolve().parent.parent
JAR_DIR = ROOT / "tools" / ".jars"
MAVEN = "https://repo1.maven.org/maven2"
JTS_JAR = ("jts-1.13.jar", f"{MAVEN}/com/vividsolutions/jts/1.13/jts-1.13.jar")
S4J_JAR = (
    "spatial4j-0.6.jar",
    f"{MAVEN}/org/locationtech/spatial4j/spatial4j/0.6/spatial4j-0.6.jar",
)
JTS_DUMPER = ROOT / "tools" / "DumpJtsBuffer.java"
S4J_DUMPER = ROOT / "tools" / "DumpSpatial4jBoxes.java"

# Diagnostic only, set by --fdlibm. HotSpot's x86-64 Math.sin/Math.cos intrinsic
# is not the same function as StrictMath's fdlibm, and the two disagree by an ulp
# on some of the fillet angles. Disabling the intrinsic makes the jar agree with
# Python bit for bit on the JTS corpus, which is how the residual boundary
# divergences were attributed. That is a statement about this corpus and not a
# general one: a two-point line exists whose raw offset curve still differs by
# one ulp with the intrinsic off. The default run leaves it on, because that is
# the jar as anyone actually runs it.
JVM_FLAGS: list[str] = []
FDLIBM_FLAGS = ["-XX:+UnlockDiagnosticVMOptions", "-XX:DisableIntrinsic=_dsin,_dcos"]


def enable_fdlibm() -> None:
    JVM_FLAGS.extend(FDLIBM_FLAGS)


def jar_path(name: str, url: str) -> str:
    """Cached jar, downloaded only when missing, like tools/gen_schema_2015.py."""
    JAR_DIR.mkdir(parents=True, exist_ok=True)
    jar = JAR_DIR / name
    if not jar.exists():
        print(f"fetching {name}")
        with urllib.request.urlopen(url) as response:  # noqa: S310 - pinned Maven Central URL
            jar.write_bytes(response.read())
    return str(jar)


def java(classpath: list[str], dumper: Path, args: list[str], stdin: str) -> list[str]:
    """One JVM for a whole corpus; both dumpers stream stdin to stdout."""
    proc = subprocess.run(
        ["java", *JVM_FLAGS, "-cp", ":".join(classpath), str(dumper), *args],
        input=stdin,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def points_of(fields: list[str]) -> list[tuple[float, ...]]:
    """A run of `"<x> <y>"` fields, as both dumpers write coordinate lists."""
    return [tuple(float(v) for v in f.split(" ")) for f in fields]


def run_jts(cases: list[Case], mode: str) -> dict[str, list[list[str]]]:
    """Case id to its answer lines. `--poly` emits one line per polygon ring."""
    stdin = "".join(
        f"{name}\t{geocorpus.encode(shape)}\t{lon!r}\t{lat!r}\t{dist!r}\n"
        for name, shape, lon, lat, dist in cases
    )
    answers: dict[str, list[list[str]]] = {}
    for line in java([jar_path(*JTS_JAR)], JTS_DUMPER, [mode], stdin):
        fields = line.split("\t")
        answers.setdefault(fields[0], []).append(fields[1:])
    return answers


def run_boxes(cases: list[BoxCase]) -> dict[str, dict[str, str]]:
    """Case id to its `key=value` fields, as DumpSpatial4jBoxes prints them."""
    classpath = [jar_path(*S4J_JAR), jar_path(*JTS_JAR)]
    stdin = geoboxes.render_box_corpus(cases)
    answers: dict[str, dict[str, str]] = {}
    for line in java(classpath, S4J_DUMPER, ["-"], stdin):
        name, _, rest = line.partition(" ")
        fields = {}
        for token in rest.split(" "):
            key, sep, value = token.partition("=")
            if sep:
                fields[key] = value
        if "error=" in rest:
            # An exception message has spaces in it, so take the whole tail.
            fields["error"] = rest.split("error=", 1)[1]
        answers[name] = fields
    return answers
