"""The 2015 view, asserted against the bindings jar upstream compiles against.

Every number here was measured from com.google.transit:gtfs-realtime-bindings
0.0.4, published 2015-02-27.
"""

import pytest

from gtfs_rt_validator.proto.schema_2015 import SCHEMA
from gtfs_rt_validator.proto.schema_current import SCHEMA as CURRENT


def test_it_carries_the_fifteen_messages_the_jar_defines():
    assert set(SCHEMA.messages) == {
        "FeedMessage",
        "FeedHeader",
        "FeedEntity",
        "TripUpdate",
        "TripUpdate.StopTimeEvent",
        "TripUpdate.StopTimeUpdate",
        "VehiclePosition",
        "Alert",
        "TimeRange",
        "Position",
        "TripDescriptor",
        "VehicleDescriptor",
        "EntitySelector",
        "TranslatedString",
        "TranslatedString.Translation",
    }


def test_the_messages_added_since_2015_are_absent():
    for name in (
        "TripModifications",
        "Shape",
        "Stop",
        "TripUpdate.TripProperties",
        "VehiclePosition.CarriageDetails",
        "TranslatedImage.LocalizedImage",
    ):
        assert name in CURRENT.messages
        assert name not in SCHEMA.messages


def test_trip_schedule_relationship_has_four_values_where_today_it_has_eight():
    """The divergence that changes rule outcomes rather than only coverage."""
    assert SCHEMA.enum_values("TripDescriptor.ScheduleRelationship") == frozenset({0, 1, 2, 3})
    assert len(CURRENT.enum_values("TripDescriptor.ScheduleRelationship")) == 8


def test_it_has_seven_required_fields_where_today_there_are_nine():
    """The two extras live in LocalizedImage, a message that did not exist."""
    found = {f"{name}.{field}" for name in SCHEMA.messages for field in SCHEMA.required_of(name)}
    assert len(found) == 7
    # Substring, not prefix: the qualified name is TranslatedImage.LocalizedImage.url,
    # so a startswith check here would pass without testing anything.
    assert not any("LocalizedImage" in name for name in found)


def test_the_jar_deprecates_no_enum_member_at_all():
    """Asked of the descriptor, not assumed from the era.

    `ADDED` acquired its `[deprecated = true]` long after 2015 and the 0.0.4
    artifact knows nothing about it, so the compat view carries an empty map
    rather than no map: "the jar was asked and answered none" is a different
    statement from "nobody looked", and only the first one survives a re-run.
    """
    assert {name: SCHEMA.enum_deprecated(name) for name in SCHEMA.enums} == dict.fromkeys(
        SCHEMA.enums, frozenset()
    )
    assert "ADDED" in SCHEMA.enums["TripDescriptor.ScheduleRelationship"]
    assert CURRENT.enum_deprecated("TripDescriptor.ScheduleRelationship") == frozenset({"ADDED"})


def test_occupancy_status_was_already_there_in_2015():
    """A guard against assuming everything modern-looking postdates the pin."""
    assert "occupancy_status" in SCHEMA.message("VehiclePosition").by_name


def test_regenerating_produces_the_committed_file():
    """Hand-editing a generated file makes every drift signal lie.

    Skips rather than fails without a JDK or without the jars: the generated
    module is committed, so running the suite needs neither. Only regenerating
    does, and that is what this test is checking.
    """
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    if shutil.which("java") is None:
        pytest.skip("no JDK on PATH, so the dumper cannot run")

    # The tool owns the jar coordinates and the cache location; importing it
    # keeps this test from restating either. `jar_paths` is a no-op once the
    # jars are cached and downloads them when they are not, so the failure it
    # raises is exactly "absent and cannot be fetched".
    sys.path.insert(0, str(root / "tools"))
    try:
        import gen_schema_2015
    finally:
        sys.path.pop(0)
    try:
        gen_schema_2015.jar_paths()
    except OSError as exc:
        pytest.skip(f"the 0.0.4 jars are not cached and cannot be fetched: {exc}")

    target = root / "src" / "gtfs_rt_validator" / "proto" / "schema_2015.py"
    before = target.read_text()
    # Both tools come from the interpreter running the suite, which is the
    # venv's, rather than from whatever happens to be on PATH.
    assert (Path(sys.executable).parent / "ruff").exists()
    subprocess.run([sys.executable, "tools/gen_schema_2015.py"], check=True, cwd=root)
    subprocess.run(
        [sys.executable, "-m", "ruff", "format", "src/gtfs_rt_validator/proto/schema_2015.py"],
        check=True,
        cwd=root,
    )
    assert target.read_text() == before
