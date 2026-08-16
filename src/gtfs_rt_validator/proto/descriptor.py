"""What a schema is, independent of where it came from.

Two modules produce one of these: `schema_current` from the pinned .proto, and
`schema_2015` from the bindings jar upstream compiles against. The decoder takes
one as an argument and has no idea which it got, which is how compat mode stays
a parameter rather than a branch.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The wire type an encoder must use for each kind. Reading tolerates more than
# this (an unknown field arrives with whatever wire type it was written with),
# but writing has exactly one correct answer per kind.
KIND_WIRE_TYPES = {
    "int32": 0,
    "int64": 0,
    "uint32": 0,
    "uint64": 0,
    "sint32": 0,
    "sint64": 0,
    "bool": 0,
    "enum": 0,
    "fixed64": 1,
    "sfixed64": 1,
    "double": 1,
    "string": 2,
    "bytes": 2,
    "message": 2,
    "fixed32": 5,
    "sfixed32": 5,
    "float": 5,
}


@dataclass(frozen=True, slots=True)
class FieldDesc:
    number: int
    name: str
    kind: str
    label: str
    type_name: str | None = None
    # proto2 lets a field declare a default that `getX()` returns while `hasX()`
    # stays false. Nine fields in GTFS-Realtime do, and rules read both, so the
    # default is part of the schema rather than a decoder convention.
    default: object = None
    deprecated: bool = False


@dataclass(frozen=True, slots=True)
class MessageDesc:
    name: str
    fields: tuple[FieldDesc, ...]
    by_number: dict[int, FieldDesc] = field(default_factory=dict, compare=False)
    by_name: dict[str, FieldDesc] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        for desc in self.fields:
            self.by_number[desc.number] = desc
            self.by_name[desc.name] = desc


@dataclass(frozen=True, slots=True)
class Schema:
    messages: dict[str, MessageDesc]
    enums: dict[str, dict[str, int]]
    #: Which members of which enum carry `[deprecated = true]`, the enum-side
    #: twin of `FieldDesc.deprecated`. Beside the value map rather than inside
    #: it: `enums` is the `{name: number}` map protobuf semantics need, and the
    #: map `javafmt.java_enum` renders compat occurrence bytes from, while
    #: deprecation is metadata *about* a member and nothing on the decode path
    #: reads it. Both generators emit this mapping unconditionally, so an enum
    #: with no entry is one the source was asked about and declared none for.
    deprecated_enum_values: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, members in self.deprecated_enum_values.items():
            unknown = [member for member in members if member not in self.enums.get(name, {})]
            if unknown:
                raise ValueError(
                    f"{name} is recorded as deprecating {unknown}, which it does not declare. "
                    "A mapping beside the value map is the one shape that can drift from it, "
                    "and a rule reading a member name no member carries never fires."
                )

    def message(self, name: str) -> MessageDesc:
        return self.messages[name]

    def enum_values(self, name: str) -> frozenset[int]:
        return frozenset(self.enums[name].values())

    def enum_deprecated(self, name: str) -> frozenset[str]:
        """The members of `name` that carry `[deprecated = true]`, possibly none."""
        return frozenset(self.deprecated_enum_values.get(name, ()))

    def required_of(self, name: str) -> tuple[str, ...]:
        return tuple(f.name for f in self.messages[name].fields if f.label == "required")


def wire_type_matches(field: FieldDesc, wire_type: int) -> bool:
    """Whether this field was written with the wire type its kind requires.

    A mismatch is not an error. protobuf-java's generated parser switches on the
    whole tag rather than on the field number, so a known number carrying the
    wrong wire type misses every case label and lands in `parseUnknownField`.
    Established by reading the generated `FeedEntity` parser in the 0.0.4 jar.
    """
    return KIND_WIRE_TYPES[field.kind] == wire_type
