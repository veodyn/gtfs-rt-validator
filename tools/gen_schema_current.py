"""Generate `proto/schema_current.py` from the vendored gtfs-realtime.proto.

A focused parser, not a general one. It handles exactly what the pinned file
uses, measured on 2026-08-14: proto2, nested messages and enums, `[default =]`
and `[deprecated = true]`, and `extensions` ranges. It does not handle oneof,
map, groups, or packed, because the file contains none of them, and it raises
rather than guessing if one appears. That is the drift signal: a spec revision
introducing a construct we cannot represent should stop the build, not be
silently mis-parsed.

Run: .venv/bin/python tools/gen_schema_current.py
Then: .venv/bin/ruff format src/gtfs_rt_validator/proto/schema_current.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "upstream" / "gtfs-realtime.proto"
TARGET = ROOT / "src" / "gtfs_rt_validator" / "proto" / "schema_current.py"

SCALARS = {
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
    "float",
    "double",
    "bool",
    "string",
    "bytes",
}
INTEGERS = SCALARS - {"float", "double", "bool", "string", "bytes"}

# Matched against a whole logical declaration, not against a raw line: exactly
# one field in the pinned file wraps its options onto a second line, and a
# line-anchored match drops it silently rather than failing.
FIELD = re.compile(
    r"^(required|optional|repeated)\s+([\w.]+)\s+(\w+)\s*=\s*(\d+)\s*(\[[^\]]*\])?\s*;"
)
FIELD_START = re.compile(r"^(?:required|optional|repeated)\s", re.M)
ENUM_VALUE = re.compile(r"^(\w+)\s*=\s*(-?\d+)\s*(\[[^\]]*\])?\s*;")
OPENER = re.compile(r"(message|enum)\s+(\w+)\s*\{")
REJECT = re.compile(r"\b(oneof|map\s*<|group\b|packed\s*=)")

# protobuf's implicit default for a singular non-message field that declares
# none. Enums are absent because theirs is the first value declared, which is
# per-enum rather than per-kind.
IMPLICIT: dict[str, object] = {
    "float": 0.0,
    "double": 0.0,
    "bool": False,
    "string": "",
    "bytes": b"",
    **dict.fromkeys(INTEGERS, 0),
}


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//.*", "", text)


def is_deprecated(options: str) -> bool:
    """Whether an options group carries `[deprecated = true]`.

    One predicate for fields and enum members, because the pin deprecates one
    of each and reading only one of them is exactly the bug this replaced. It
    matches the value rather than the keyword: `[deprecated = false]` appears
    nowhere in the pinned file, so this is output-identical today, but it is
    the reading that stays right if one ever does.
    """
    return re.search(r"deprecated\s*=\s*true", options) is not None


def record_enum_value(declaration: str, values: dict[str, int], deprecated: list[str]) -> None:
    """One `NAME = n [options];`, into the value map and the deprecation list.

    The options group has always been captured here and was thrown away until
    2026-08-15, which is why `ADDED = 1 [deprecated = true]` reached nothing and
    S024 had to compare a member name instead of reading the option. It now
    reads `Schema.deprecated_enum_values`, which this fills.
    """
    value = ENUM_VALUE.match(declaration)
    if value is None:
        return
    values[value.group(1)] = int(value.group(2))
    if is_deprecated(value.group(3) or ""):
        deprecated.append(value.group(1))


def parse(text: str):
    """Walk the file keeping a scope stack, so nested names qualify correctly."""
    messages: dict[str, list] = {}
    enums: dict[str, dict[str, int]] = {}
    deprecated: dict[str, list[str]] = {}
    scope: list[str] = []
    kinds: list[str] = []  # parallel to scope: "message" or "enum"
    pending = ""  # a logical declaration accumulated until its terminating `;`

    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if REJECT.search(line):
            sys.exit(f"unsupported construct, the generator must be taught it: {line!r}")

        if not pending:
            opened = OPENER.match(line)
            if opened:
                kind, name = opened.groups()
                scope.append(name)
                kinds.append(kind)
                qualified = ".".join(scope)
                if kind == "message":
                    messages[qualified] = []
                else:
                    enums[qualified] = {}
                    deprecated[qualified] = []
                continue
            if line.startswith("}"):
                if scope:
                    scope.pop()
                    kinds.pop()
                continue
            if not scope:
                continue

        pending = f"{pending} {line}" if pending else line
        if not pending.endswith(";"):
            continue
        declaration, pending = pending, ""

        qualified = ".".join(scope)
        if kinds[-1] == "enum":
            record_enum_value(declaration, enums[qualified], deprecated[qualified])
            continue

        field = FIELD.match(declaration)
        if field:
            label, type_name, name, number, options = field.groups()
            messages[qualified].append((label, type_name, name, int(number), options or ""))

    if pending:
        sys.exit(f"declaration never terminated: {pending!r}")
    return messages, enums, deprecated


def resolve(type_name: str, scope: str, messages, enums) -> tuple[str, str | None]:
    """Innermost-outward name resolution, protobuf's own rule.

    `StopTimeUpdate.departure_occupancy_status` names `VehiclePosition.OccupancyStatus`
    from a sibling scope, so a bare-name lookup is not enough.
    """
    if type_name in SCALARS:
        return type_name, None
    parts = scope.split(".")
    while parts:
        candidate = ".".join([*parts, type_name])
        if candidate in messages:
            return "message", candidate
        if candidate in enums:
            return "enum", candidate
        parts.pop()
    if type_name in messages:
        return "message", type_name
    if type_name in enums:
        return "enum", type_name
    sys.exit(f"cannot resolve type {type_name!r} from scope {scope!r}")


def default_of(options: str, label: str, kind: str, type_name: str | None, enums) -> object:
    """protobuf's *effective* default, which is not only the declared one.

    Measured against the 2015 bindings through protobuf-java's
    `getDefaultValue()`: it answers `SCHEDULED=0` for `TripDescriptor`'s bare
    `optional ScheduleRelationship schedule_relationship = 4;` even though
    `hasDefaultValue()` is false, and that is the value upstream's rules see.
    It throws for repeated and message-kind fields, which keep `None`; `Msg.get`
    already answers a repeated field with `[]`.
    """
    if label == "repeated" or kind == "message":
        return None
    match = re.search(r"default\s*=\s*([^\],]+)", options)
    if not match:
        if kind == "enum":
            return next(iter(enums[type_name].values()))
        return IMPLICIT[kind]
    literal = match.group(1).strip()
    if kind == "enum":
        return enums[type_name][literal]
    if kind == "bool":
        return literal == "true"
    if kind in ("float", "double"):
        return float(literal)
    if kind in INTEGERS:
        return int(literal)
    if kind == "bytes":
        return literal.strip('"').encode()
    return literal.strip('"')


def render_deprecated_enum_values(deprecated_members) -> list[str]:
    """The `deprecated_enum_values=` block, shared in shape with the 2015 tool.

    Enums with no deprecated member are left out rather than written as `()`,
    which would add a line per enum and say nothing: the keyword itself is the
    statement that the source was asked, and `Schema.enum_deprecated` answers
    the empty set for a name that is not here.
    """
    lines = ["    deprecated_enum_values={"]
    for qualified, members in deprecated_members.items():
        if members:
            lines.append(f'        "{qualified}": {tuple(members)!r},')
    lines.append("    },")
    return lines


def render(messages, enums, deprecated_members) -> str:
    lines = [
        '"""GENERATED by tools/gen_schema_current.py. Do not edit.',
        "",
        "Source: upstream/gtfs-realtime.proto at the pin in upstream/pins.json.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from gtfs_rt_validator.proto.descriptor import FieldDesc, MessageDesc, Schema",
        "",
        "SCHEMA = Schema(",
        "    messages={",
    ]
    for qualified, fields in messages.items():
        lines.append(f'        "{qualified}": MessageDesc("{qualified}", (')
        for label, type_name, name, number, options in fields:
            kind, target = resolve(type_name, qualified, messages, enums)
            default = default_of(options, label, kind, target, enums)
            retired = is_deprecated(options)
            lines.append(
                f'            FieldDesc({number}, "{name}", "{kind}", "{label}", '
                f"{target!r}, {default!r}, {retired!r}),"
            )
        lines.append("        )),")
    lines.append("    },")
    lines.append("    enums={")
    for qualified, values in enums.items():
        lines.append(f'        "{qualified}": {values!r},')
    lines.append("    },")
    lines.extend(render_deprecated_enum_values(deprecated_members))
    lines.append(")")
    return "\n".join(lines) + "\n"


def main() -> None:
    # Qualified names throughout, matching tools/gen_schema_2015.py, which takes
    # its names from the jar's own fully-qualified descriptors. Two schemas that
    # disagree about what a message is called would make every `type_name`
    # lookup resolve under one and fail under the other.
    text = strip_comments(SOURCE.read_text())
    messages, enums, deprecated = parse(text)

    # Every field-start keyword in the source must have become a declaration.
    # The one that wraps onto a second line was dropped silently before this
    # check existed, and a missing field is not a parse error.
    declared = len(FIELD_START.findall(re.sub(r"^[ \t]+", "", text, flags=re.M)))
    parsed = sum(len(f) for f in messages.values())
    if parsed != declared:
        sys.exit(f"parsed {parsed} field declarations but the source starts {declared}")

    TARGET.write_text(render(messages, enums, deprecated))
    retired = sum(len(members) for members in deprecated.values())
    print(
        f"wrote {TARGET} with {len(messages)} messages, {len(enums)} enums, {parsed} fields "
        f"and {retired} deprecated enum members"
    )


if __name__ == "__main__":
    main()
