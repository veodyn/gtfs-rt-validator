"""The upstream rule manifest, asserted against facts measured at the pin.

Every number here was measured from upstream at the pinned SHA. A change to any
of them is upstream moving rather than a test needing an update.
`tools/map_rules.py` regenerates the manifest; never hand-edit it. Whether
anyone did is `test_manifest_drift.py`'s question, not this module's: everything
here would still pass on a manifest whose strings had been quietly changed.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PINS = json.loads((ROOT / "upstream" / "pins.json").read_text())
PIN = PINS["gtfs_realtime_validator"]["commit"]
MANIFEST_PATH = ROOT / "upstream" / f"rules-{PIN[:7]}.json"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


@pytest.fixture(scope="module")
def rules(manifest: dict) -> dict:
    return manifest["rules"]


def test_the_manifest_is_named_for_the_pin_it_records(manifest: dict):
    """One pin, one filename. Bumping the pin renames the file, so a stale
    manifest cannot quietly answer questions about a newer upstream."""
    assert manifest["pin"] == PIN
    assert manifest["repo"] == PINS["gtfs_realtime_validator"]["repo"]


def test_sixty_one_constants_are_declared(rules: dict):
    assert len(rules) == 61
    assert sum(1 for rule_id in rules if rule_id.startswith("E")) == 52
    assert sum(1 for rule_id in rules if rule_id.startswith("W")) == 9


def test_every_rule_carries_the_five_strings_validation_rules_java_holds(rules: dict):
    """These are what compat output emits verbatim, so an absent one is a hole
    in the writer's data source rather than a cosmetic gap."""
    for rule_id, rule in rules.items():
        assert rule["error_id"] == rule_id
        assert rule["severity"] in ("ERROR", "WARNING")
        assert rule["title"]
        assert rule["error_description"]
        # W003's suffix is the empty string upstream, so emptiness is a value
        # here rather than a missing key.
        assert isinstance(rule["occurrence_suffix"], str)


def test_severity_follows_the_id_prefix(rules: dict):
    for rule_id, rule in rules.items():
        expected = "ERROR" if rule_id.startswith("E") else "WARNING"
        assert rule["severity"] == expected


def test_fifty_seven_rules_are_emitted_by_some_validator(rules: dict):
    assert sum(1 for rule in rules.values() if rule["emitters"]) == 57


def test_fifty_six_rules_are_reachable_through_the_batch_cli(rules: dict):
    assert sum(1 for rule in rules.values() if rule["batch_reachable"]) == 56


def test_e010_is_the_one_rule_emitted_but_not_batch_reachable(rules: dict):
    """`StopLocationTypeValidator` implements `GtfsFeedValidator`, which
    `BatchProcessor` never registers. Emitting E010 under `--compat` would
    itself be a parity failure."""
    unreachable = {
        rule_id
        for rule_id, rule in rules.items()
        if rule["emitters"] and not rule["batch_reachable"]
    }
    assert unreachable == {"E010"}
    assert rules["E010"]["emitters"] == ["StopLocationTypeValidator"]


def test_four_rules_are_declared_and_emitted_by_nothing(rules: dict):
    orphans = {rule_id for rule_id, rule in rules.items() if not rule["emitters"]}
    assert orphans == {"E005", "E007", "E008", "E014"}
    assert all(rules[rule_id]["batch_reachable"] is False for rule_id in orphans)


def test_no_rule_has_more_than_one_emitter(rules: dict):
    """An earlier draft claimed W006 had two, by counting a mention inside a
    comment. Comments are stripped before matching for exactly this reason."""
    multiple = {
        rule_id: rule["emitters"] for rule_id, rule in rules.items() if len(rule["emitters"]) > 1
    }
    assert multiple == {}


def test_per_validator_emission_counts(rules: dict):
    counts: dict[str, int] = {}
    for rule in rules.values():
        for emitter in rule["emitters"]:
            counts[emitter] = counts.get(emitter, 0) + 1
    assert counts == {
        "TripDescriptorValidator": 15,
        "StopTimeUpdateValidator": 12,
        "TimestampValidator": 11,
        "VehicleValidator": 7,
        "HeaderValidator": 3,
        "FrequencyTypeZeroValidator": 3,
        "CrossFeedDescriptorValidator": 2,
        "StopValidator": 2,
        "FrequencyTypeOneValidator": 1,
        "StopLocationTypeValidator": 1,
    }
    assert sum(counts.values()) == 57


def test_batch_registers_nine_validators_in_this_order(manifest: dict):
    """Order matters: the runner walks the registry in it, and compat output
    ordering is a byte-for-byte contract."""
    assert manifest["batch_registration_order"] == [
        "CrossFeedDescriptorValidator",
        "VehicleValidator",
        "TimestampValidator",
        "StopTimeUpdateValidator",
        "TripDescriptorValidator",
        "StopValidator",
        "FrequencyTypeZeroValidator",
        "FrequencyTypeOneValidator",
        "HeaderValidator",
    ]


def test_batch_reachable_means_the_emitter_is_registered(manifest: dict, rules: dict):
    registered = set(manifest["batch_registration_order"])
    for rule in rules.values():
        expected = any(emitter in registered for emitter in rule["emitters"])
        assert rule["batch_reachable"] is expected


def test_stop_time_update_rules_survive_the_qualified_call_shape(rules: dict):
    """`StopTimeUpdateValidator` writes `RuleUtils.addOccurrence(ValidationRules.E046, ...)`
    exclusively. A pattern matching only the bare `E046` form reports this
    validator as emitting nothing and the total comes out 45, not 57."""
    for rule_id in (
        "E002",
        "E009",
        "E036",
        "E037",
        "E040",
        "E041",
        "E042",
        "E043",
        "E044",
        "E045",
        "E046",
        "E051",
    ):
        assert rules[rule_id]["emitters"] == ["StopTimeUpdateValidator"]


def test_the_five_strings_are_extracted_verbatim(rules: dict):
    """Three spot checks against the Java, including one whose suffix is empty
    and one whose description carries an apostrophe and a parenthetical."""
    assert rules["W003"] == {
        "error_id": "W003",
        "severity": "WARNING",
        "title": "ID in one feed missing from the other",
        "error_description": (
            "a trip_id that is provided in the VehiclePositions feed should be provided in "
            "the TripUpdates feed, and a vehicle_id that is provided in the TripUpdates feed "
            "should be provided in the VehiclePositions feed"
        ),
        "occurrence_suffix": "",
        "emitters": ["CrossFeedDescriptorValidator"],
        "batch_reachable": True,
    }
    assert rules["E001"] == {
        "error_id": "E001",
        "severity": "ERROR",
        "title": "Not in POSIX time",
        "error_description": (
            "All timestamps must be in POSIX time (i.e., number of seconds since "
            "January 1st 1970 00:00:00 UTC)"
        ),
        "occurrence_suffix": "is not POSIX time",
        "emitters": ["TimestampValidator"],
        "batch_reachable": True,
    }
    assert rules["E010"] == {
        "error_id": "E010",
        "severity": "ERROR",
        "title": "location_type not 0 in stops.txt",
        "error_description": (
            "If location_type is used in stops.txt, all stops referenced in stop_times.txt "
            "must have location_type of 0"
        ),
        "occurrence_suffix": "is not location_type 0",
        "emitters": ["StopLocationTypeValidator"],
        "batch_reachable": False,
    }


def test_declaration_order_is_preserved(rules: dict):
    """`ValidationRules.getRules()` reflects over declared fields, so upstream's
    own rule list comes out in declaration order. Ours must too."""
    order = list(rules)
    assert order[:3] == ["W001", "W002", "W003"]
    assert order[9] == "E001"
    assert order[-1] == "E052"
