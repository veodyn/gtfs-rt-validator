"""Generate `proto/schema_2015.py` by asking the pinned bindings jar.

Needs a JDK and the 0.0.4 jar, both dev-only. The jar is fetched from Maven
Central once and cached under `tools/.jars/` (gitignored), so regenerating after
the first run needs no network. Its protobuf-java dependency comes along because
`DumpDescriptor` uses `Descriptors` from it.

Run: .venv/bin/python tools/gen_schema_2015.py
Then: .venv/bin/ruff format src/gtfs_rt_validator/proto/schema_2015.py
"""

from __future__ import annotations

import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "src" / "gtfs_rt_validator" / "proto" / "schema_2015.py"
JAR_DIR = ROOT / "tools" / ".jars"
JARS = {
    "gtfs-realtime-bindings-0.0.4.jar": (
        "https://repo1.maven.org/maven2/com/google/transit/gtfs-realtime-bindings/0.0.4/"
        "gtfs-realtime-bindings-0.0.4.jar"
    ),
    "protobuf-java-2.6.1.jar": (
        "https://repo1.maven.org/maven2/com/google/protobuf/protobuf-java/2.6.1/"
        "protobuf-java-2.6.1.jar"
    ),
}
PACKAGE = "transit_realtime."

# protobuf's own type names to ours. The jar reports protobuf type enums, which
# spell a few kinds differently from the .proto keywords the other generator sees.
TYPES = {
    "int32": "int32",
    "int64": "int64",
    "uint32": "uint32",
    "uint64": "uint64",
    "sint32": "sint32",
    "sint64": "sint64",
    "fixed32": "fixed32",
    "fixed64": "fixed64",
    "sfixed32": "sfixed32",
    "sfixed64": "sfixed64",
    "float": "float",
    "double": "double",
    "bool": "bool",
    "string": "string",
    "bytes": "bytes",
    "enum": "enum",
    "message": "message",
    "group": "group",
}
INTEGERS = {
    "int32",
    "int64",
    "uint32",
    "uint64",
    "sint32",
    "sint64",
    "fixed32",
    "fixed64",
    "sfixed32",
    "sfixed64",
}


def jar_paths() -> list[str]:
    """Cached jars, downloaded only when missing.

    `tools/.jars/` is gitignored and is where `.gitignore` already says these
    land. Downloading into a fresh temp directory each run would make every
    regeneration need the network for bytes that never change: both coordinates
    are pinned releases.
    """
    JAR_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, url in JARS.items():
        jar = JAR_DIR / name
        if not jar.exists():
            print(f"fetching {name}")
            with urllib.request.urlopen(url) as response:  # noqa: S310 - pinned Maven Central URL
                jar.write_bytes(response.read())
        paths.append(str(jar))
    return paths


def dump() -> str:
    """Run the dumper under JDK 17's single-file source launcher, no compile step."""
    java_src = ROOT / "tools" / "DumpDescriptor.java"
    return subprocess.run(
        ["java", "-cp", ":".join(jar_paths()), str(java_src)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def strip_package(full_name: str) -> str:
    """`transit_realtime.TripUpdate.StopTimeUpdate` -> `TripUpdate.StopTimeUpdate`."""
    return full_name[len(PACKAGE) :] if full_name.startswith(PACKAGE) else full_name


def parse(text: str) -> tuple[dict[str, list], dict[str, dict[str, int]], dict[str, list[str]]]:
    messages: dict[str, list] = {}
    enums: dict[str, dict[str, int]] = {}
    deprecated: dict[str, list[str]] = {}
    for line in text.strip().split("\n"):
        parts = line.split("\t")
        if parts[0] == "M":
            messages.setdefault(parts[1], [])
        elif parts[0] == "E":
            enums.setdefault(parts[1], {})
            deprecated.setdefault(parts[1], [])
        elif parts[0] == "V":
            enums[parts[1]][parts[2]] = int(parts[3])
            if parts[4] == "true":
                deprecated[parts[1]].append(parts[2])
        elif parts[0] == "F":
            _, owner, number, name, type_name, label, target, flag, default, retired = parts
            messages[owner].append(
                (
                    int(number),
                    name,
                    TYPES[type_name],
                    label,
                    strip_package(target) or None,
                    flag == "D",
                    default,
                    retired == "true",
                )
            )
        else:
            sys.exit(f"unrecognised record from DumpDescriptor: {line!r}")
    return messages, enums, deprecated


def decode_default(kind: str, applies: bool, literal: str, target: str | None, enums) -> object:
    """The dump's ninth column as a Python value.

    `applies` is the dumper's flag column rather than a test on `literal`: the
    empty string is a real default for sixteen fields here, so emptiness cannot
    be the signal for "no default". Repeated and message-kind fields keep `None`;
    `Msg.get` already answers a repeated field with `[]`.
    """
    if not applies:
        return None
    if kind == "enum":
        return enums[target][literal]
    if kind == "bool":
        return literal == "true"
    if kind in ("float", "double"):
        return float(literal)
    if kind in INTEGERS:
        return int(literal)
    if kind == "bytes":
        # The dumper refuses to render one, so reaching here means the descriptor
        # grew a bytes field and both sides need teaching.
        sys.exit("a bytes default needs a rendering neither side implements")
    return literal


def render(messages, enums, deprecated_members) -> str:
    lines = [
        '"""GENERATED by tools/gen_schema_2015.py. Do not edit.',
        "",
        "Source: com.google.transit:gtfs-realtime-bindings:0.0.4, published 2015-02-27,",
        "the artifact upstream compiles against. This is the compat view.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from gtfs_rt_validator.proto.descriptor import FieldDesc, MessageDesc, Schema",
        "",
        "SCHEMA = Schema(",
        "    messages={",
    ]
    for owner, fields in messages.items():
        lines.append(f'        "{owner}": MessageDesc("{owner}", (')
        for number, name, kind, label, target, applies, literal, retired in fields:
            default = decode_default(kind, applies, literal, target, enums)
            lines.append(
                f'            FieldDesc({number}, "{name}", "{kind}", "{label}", '
                f"{target!r}, {default!r}, {retired!r}),"
            )
        lines.append("        )),")
    lines.append("    },")
    lines.append("    enums={")
    for name, values in enums.items():
        lines.append(f'        "{name}": {values!r},')
    lines.append("    },")
    # Written even when it is empty, and empty is the whole answer for 0.0.4:
    # the artifact predates the pinned .proto's one deprecated enum member. The
    # keyword being present is what makes that a measurement rather than an
    # omission, and it keeps both generated modules the same shape.
    lines.append("    deprecated_enum_values={")
    for name, members in deprecated_members.items():
        if members:
            lines.append(f'        "{name}": {tuple(members)!r},')
    lines.append("    },")
    lines.append(")")
    return "\n".join(lines) + "\n"


def main() -> None:
    # Qualified names throughout, matching tools/gen_schema_current.py. The jar
    # reports them package-qualified, so the package prefix is stripped: two
    # schemas that disagree about what a message is called would make every
    # `type_name` lookup resolve under one and fail under the other.
    messages, enums, deprecated = parse(dump())
    TARGET.write_text(render(messages, enums, deprecated))
    fields = sum(len(f) for f in messages.values())
    retired = sum(len(members) for members in deprecated.values())
    print(
        f"wrote {TARGET} with {len(messages)} messages, {len(enums)} enums, {fields} fields "
        f"and {retired} deprecated enum members"
    )


if __name__ == "__main__":
    main()
