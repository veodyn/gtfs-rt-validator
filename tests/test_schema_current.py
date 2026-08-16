"""The generated current schema, asserted against facts measured from the pin.

These numbers are the pin's, and a change to any of them is upstream moving
rather than a test needing an update. `tools/gen_schema_current.py` regenerates
the module; never hand-edit it.
"""

from gtfs_rt_validator.proto.schema_current import SCHEMA


def test_it_carries_every_message_in_the_pinned_proto():
    assert len(SCHEMA.messages) == 28


def test_required_fields_are_exactly_the_nine_measured_at_the_pin():
    found = {f"{name}.{field}" for name in SCHEMA.messages for field in SCHEMA.required_of(name)}
    assert found == {
        "FeedMessage.header",
        "FeedHeader.gtfs_realtime_version",
        "FeedEntity.id",
        "TripUpdate.trip",
        "Position.latitude",
        "Position.longitude",
        "TranslatedString.Translation.text",
        "TranslatedImage.LocalizedImage.url",
        "TranslatedImage.LocalizedImage.media_type",
    }


def test_everything_is_keyed_by_qualified_name():
    """`ScheduleRelationship` exists in two messages with different values, so
    enums must be qualified; messages follow the same rule so that a
    `type_name` is read the same way whichever kind it names."""
    trip = SCHEMA.enum_values("TripDescriptor.ScheduleRelationship")
    stop_time = SCHEMA.enum_values("TripUpdate.StopTimeUpdate.ScheduleRelationship")
    assert len(trip) == 8
    assert len(stop_time) == 4
    assert "TripUpdate.StopTimeUpdate" in SCHEMA.messages
    assert "StopTimeUpdate" not in SCHEMA.messages


def test_a_cross_scope_type_reference_resolves():
    """`departure_occupancy_status` names an enum declared in another message."""
    field = SCHEMA.message("TripUpdate.StopTimeUpdate").by_name["departure_occupancy_status"]
    assert field.type_name == "VehiclePosition.OccupancyStatus"


def test_declared_defaults_survive_generation():
    field = SCHEMA.message("TripDescriptor").by_name["schedule_relationship"]
    assert field.default == 0  # SCHEDULED
    # The plan asserted `[default = -1]` on `VehiclePosition.occupancy_percentage`.
    # Measured at the pin, that declaration is on the nested `CarriageDetails`
    # (proto line 579); the outer field is a bare `optional uint32 ... = 10;`
    # (line 557) and so takes protobuf's implicit 0.
    carriage = SCHEMA.message("VehiclePosition.CarriageDetails")
    assert carriage.by_name["occupancy_percentage"].default == -1
    assert SCHEMA.message("VehiclePosition").by_name["occupancy_percentage"].default == 0


def test_deprecated_is_recorded_rather_than_dropped():
    assert SCHEMA.message("Alert").by_name["active_period"].deprecated is True


def test_a_deprecated_enum_member_is_recorded_too_rather_than_dropped():
    """`ADDED = 1 [deprecated = true]` at proto line 856.

    Until 2026-08-15 the generator read `[deprecated = true]` on fields only and
    the enum branch discarded its options group, so the pin's *other* deprecation
    reached nothing. The first draft of S024 worked around it by comparing a
    member name;
    with this, a deprecation added at a later pin reaches a rule through the
    regeneration instead of through a code change.
    """
    assert SCHEMA.enum_deprecated("TripDescriptor.ScheduleRelationship") == frozenset({"ADDED"})
    # The value map is untouched by this: `ADDED` is still a member with a
    # number, which is what the decoder and `javafmt.java_enum` read.
    assert SCHEMA.enums["TripDescriptor.ScheduleRelationship"]["ADDED"] == 1
    assert 1 in SCHEMA.enum_values("TripDescriptor.ScheduleRelationship")


def test_the_pin_deprecates_exactly_one_field_and_exactly_one_enum_member():
    """Both `[deprecated = true]` sites in the file, so a third appearing at a
    later pin is a red test that names it rather than a silent new warning."""
    members = {(name, member) for name in SCHEMA.enums for member in SCHEMA.enum_deprecated(name)}
    fields = {
        (name, field.name)
        for name, desc in SCHEMA.messages.items()
        for field in desc.fields
        if field.deprecated
    }
    assert members == {("TripDescriptor.ScheduleRelationship", "ADDED")}
    assert fields == {("Alert", "active_period")}


def test_regenerating_produces_the_committed_file():
    """Hand-editing a generated file makes every drift signal lie."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    target = root / "src" / "gtfs_rt_validator" / "proto" / "schema_current.py"
    before = target.read_text()
    # Both tools come from the interpreter running the suite, which is the
    # venv's, rather than from whatever happens to be on PATH. `-m ruff` runs
    # the same binary as `.venv/bin/ruff` and keeps the call off S603.
    assert (Path(sys.executable).parent / "ruff").exists()
    subprocess.run([sys.executable, "tools/gen_schema_current.py"], check=True, cwd=root)
    subprocess.run(
        [sys.executable, "-m", "ruff", "format", "src/gtfs_rt_validator/proto/schema_current.py"],
        check=True,
        cwd=root,
    )
    assert target.read_text() == before
