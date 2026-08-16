"""The schema shape both generated modules produce and the decoder consumes."""

import pytest

from gtfs_rt_validator.proto.descriptor import (
    KIND_WIRE_TYPES,
    FieldDesc,
    MessageDesc,
    Schema,
    wire_type_matches,
)


def a_schema() -> Schema:
    """A two-message stand-in with the shapes that matter: a required field, an
    enum with a default, and a repeated message."""
    return Schema(
        messages={
            "Outer": MessageDesc(
                "Outer",
                (
                    FieldDesc(1, "name", "string", "required"),
                    FieldDesc(2, "kind", "enum", "optional", "Outer.Kind", default=0),
                    FieldDesc(3, "items", "message", "repeated", "Inner"),
                ),
            ),
            "Inner": MessageDesc("Inner", (FieldDesc(1, "value", "int32", "optional"),)),
        },
        enums={"Outer.Kind": {"A": 0, "B": 1}},
        deprecated_enum_values={"Outer.Kind": ("B",)},
    )


def test_fields_are_reachable_by_number_and_by_name():
    outer = a_schema().message("Outer")
    assert outer.by_number[2].name == "kind"
    assert outer.by_name["items"].label == "repeated"


def test_an_unknown_message_is_an_error_rather_than_a_silent_none():
    with pytest.raises(KeyError):
        a_schema().message("Nope")


def test_enum_values_are_the_set_the_decoder_tests_membership_against():
    assert a_schema().enum_values("Outer.Kind") == frozenset({0, 1})


def test_a_deprecated_enum_member_is_named_beside_the_values_rather_than_inside_them():
    """`enums` stays `{name: number}`, which is what protobuf semantics need and
    what `javafmt.java_enum` renders compat occurrence bytes from. Deprecation
    is metadata *about* a member rather than part of that map, so it lives in a
    second mapping keyed the same way, mirroring `FieldDesc.deprecated`."""
    schema = a_schema()
    assert schema.enum_deprecated("Outer.Kind") == frozenset({"B"})
    assert schema.enums["Outer.Kind"] == {"A": 0, "B": 1}


def test_an_enum_with_no_deprecated_member_answers_empty_rather_than_raising():
    """Nine of the pinned proto's twelve enums are in this position, and so is
    every enum in the 2015 view, so the empty answer is the common one."""
    schema = Schema(messages={}, enums={"Only.Kind": {"A": 0}})
    assert schema.enum_deprecated("Only.Kind") == frozenset()


def test_a_deprecated_name_that_no_member_declares_is_a_generator_bug():
    """The one risk a mapping beside the values carries that a widened value
    type would not: the two can drift. Caught at construction rather than left
    to a rule that silently never fires."""
    with pytest.raises(ValueError, match="GONE"):
        Schema(
            messages={},
            enums={"Only.Kind": {"A": 0}},
            deprecated_enum_values={"Only.Kind": ("GONE",)},
        )


def test_required_fields_are_listed_per_message():
    schema = a_schema()
    assert schema.required_of("Outer") == ("name",)
    assert schema.required_of("Inner") == ()


def test_every_kind_maps_to_the_wire_type_an_encoder_must_use():
    assert KIND_WIRE_TYPES["int32"] == 0
    assert KIND_WIRE_TYPES["string"] == 2
    assert KIND_WIRE_TYPES["message"] == 2
    assert KIND_WIRE_TYPES["float"] == 5
    assert KIND_WIRE_TYPES["double"] == 1
    assert KIND_WIRE_TYPES["enum"] == 0


def test_a_field_written_with_the_wire_type_its_kind_requires_matches():
    name = a_schema().message("Outer").by_name["name"]
    assert wire_type_matches(name, 2) is True


def test_a_field_written_with_any_other_wire_type_does_not_match():
    """protobuf-java's generated parser switches on the whole tag, so a known
    field number carrying the wrong wire type misses every case label and falls
    through to `parseUnknownField` rather than raising."""
    name = a_schema().message("Outer").by_name["name"]
    assert wire_type_matches(name, 0) is False
