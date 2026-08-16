"""`data/rules.json`, the packaged form of the drift artefact, and its loader.

Two files hold the same 61 rules for two reasons. `upstream/rules-<pin>.json` is
the drift artefact: keyed by the upstream SHA, carrying the trace of which Java
bytes produced it, outside the package because a wheel has no business shipping
a record of somebody else's source tree. `data/rules.json` is what the compat
writer reads at run time, where `upstream/` does not exist.

`tools/pack_rules.py` derives the second from the first, so the artefact stays
the only place upstream's Java is read. The packed form drops `source_sha256`
and keeps every rule record byte-identical, which is why one committed digest
covers both files: the check below recomputes it over the packed rules rather
than trusting that packing copied them faithfully.

`test_rules_manifest.py` asserts what the *artefact* says about upstream. This
module asserts that packing preserved it and that the loader reads it as a
package resource.
"""

import ast
import json
import subprocess
import sys
from importlib import resources
from pathlib import Path

import pytest

from gtfs_rt_validator.report import manifest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "gtfs_rt_validator"
PACKED_PATH = SRC / "data" / "rules.json"
PIN = json.loads((ROOT / "upstream" / "pins.json").read_text())["gtfs_realtime_validator"]["commit"]
SOURCE_PATH = ROOT / "upstream" / f"rules-{PIN[:7]}.json"
DIGEST_PATH = ROOT / "upstream" / f"rules-{PIN[:7]}.sha256"


@pytest.fixture(scope="module")
def packed() -> dict:
    return json.loads(PACKED_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rules(packed: dict) -> dict:
    return packed["rules"]


def test_regenerating_reproduces_the_committed_file_byte_for_byte():
    """Packing reads a committed artefact, so unlike `map_rules.py` this needs
    no network and the check is unconditional: there is no version of this
    checkout where the generated file may quietly differ from its generator."""
    before = PACKED_PATH.read_bytes()
    subprocess.run([sys.executable, "tools/pack_rules.py"], check=True, cwd=ROOT)
    assert PACKED_PATH.read_bytes() == before


def test_the_packed_rules_carry_the_drift_artefacts_committed_digest(rules: dict):
    """The rule records are copied verbatim, so the sidecar digest that protects
    the artefact protects the packaged copy too, without a second digest file to
    keep in step. A reshape of any record breaks this before it reaches a wheel.
    """
    from test_manifest_drift import rule_digest

    assert rule_digest(rules) == DIGEST_PATH.read_text().strip()


def test_packing_drops_the_generator_trace_and_nothing_else(packed: dict):
    """The reshape, stated as a test rather than as a comment.

    `source_sha256` is a claim about Java files that a wheel cannot check and
    runtime code must never act on, so it stays in the artefact. Everything the
    runtime reads survives, plus the pin, so an installed copy can say which
    upstream it reproduces."""
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    assert set(source) - set(packed) == {"source_sha256"}
    assert set(packed) - set(source) == {"packed_from"}
    assert packed["packed_from"] == f"upstream/{SOURCE_PATH.name}"
    assert packed["generated_by"] == "tools/pack_rules.py"
    assert packed["pin"] == source["pin"] == PIN
    assert packed["repo"] == source["repo"]
    assert packed["rules"] == source["rules"]
    assert packed["batch_registration_order"] == source["batch_registration_order"]


def test_the_counts_survive_packing(rules: dict):
    """Asserted against the packed form, not the artefact: a reshape that lost
    `emitters` would leave the three-way split unrecoverable at run time."""
    assert len(rules) == 61
    assert sum(1 for rule in rules.values() if rule["emitters"]) == 57
    assert sum(1 for rule in rules.values() if rule["batch_reachable"]) == 56
    unreachable = {i for i, r in rules.items() if r["emitters"] and not r["batch_reachable"]}
    assert unreachable == {"E010"}
    assert {i for i, r in rules.items() if not r["emitters"]} == {"E005", "E007", "E008", "E014"}


def test_the_manifest_api_reports_the_same_counts():
    """The same three-way split through the public surface the registry and the
    report writers consume, since those never open the JSON themselves."""
    assert len(manifest.all_ids()) == 61
    assert len(manifest.emitted_ids()) == 57
    assert len(manifest.batch_reachable_ids()) == 56
    assert set(manifest.emitted_ids()) - set(manifest.batch_reachable_ids()) == {"E010"}
    assert set(manifest.all_ids()) - set(manifest.emitted_ids()) == {"E005", "E007", "E008", "E014"}
    assert manifest.rule("E010").batch_reachable is False
    assert manifest.rule("E005").emitters == ()


def test_declaration_and_registration_order_survive_packing(packed: dict):
    """Both orders are output contracts: declaration order is what upstream's
    reflective `getRules()` hands back, registration order is what the runner
    walks."""
    assert list(packed["rules"]) == list(manifest.all_ids())
    assert manifest.all_ids()[:3] == ("W001", "W002", "W003")
    assert manifest.all_ids()[9] == "E001"
    assert manifest.all_ids()[-1] == "E052"
    # The nine names themselves are pinned against the artefact in
    # test_rules_manifest.py, and packing preserves them by the test above.
    assert manifest.registration_order() == tuple(packed["batch_registration_order"])
    assert len(manifest.registration_order()) == 9


# The order each validator's `errors.add(...)` calls run in at the tail of its
# `validate()`, which is the order its rule groups appear in a `.results.json`.
# Pinned here as a drift check on the generator, not as its input: `map_rules.py`
# reads it out of the Java, and this table was transcribed independently off the
# same Java under `upstream/` so that a generator bug cannot silently rewrite
# both sides.
GROUP_ORDER = {
    "CrossFeedDescriptorValidator": "W003 E047",
    "VehicleValidator": "E026 E027 E028 E029 W002 W004 E052",
    "TimestampValidator": "W001 W007 W008 E001 E012 E017 E018 E022 E025 E048 E050",
    "StopTimeUpdateValidator": "E002 E009 E036 E037 E040 E041 E042 E043 E044 E045 E046 E051",
    "TripDescriptorValidator": (
        "E003 E004 E016 E020 E021 E023 E024 E030 E031 E032 E033 E034 E035 W006 W009"
    ),
    "StopValidator": "E011 E015",
    "FrequencyTypeZeroValidator": "E006 E013 W005",
    "FrequencyTypeOneValidator": "E019",
    "HeaderValidator": "E038 E039 E049",
}


def test_group_order_survives_packing(packed: dict):
    """The second half of the output contract. Registration order says which
    group comes first; this says which rule comes first inside a group, and both
    reach the compat writer's bytes."""
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    assert packed["group_order"] == source["group_order"]
    assert packed["group_order"] == {n: ids.split() for n, ids in GROUP_ORDER.items()}


def test_group_order_is_keyed_by_the_nine_registered_validators(packed: dict):
    """Nine keys, in registration order, and `StopLocationTypeValidator` is not
    one of them: it implements `GtfsFeedValidator`, `BatchProcessor` registers it
    nowhere, and a group for it in compat output would itself be a parity
    failure."""
    assert list(packed["group_order"]) == list(packed["batch_registration_order"])
    assert "StopLocationTypeValidator" not in packed["group_order"]


def test_group_order_and_emitters_are_the_same_relation_seen_from_two_sides():
    """Neither is derived from the other in the generator, so agreement between
    them is evidence the Java scan read both correctly. Every batch-reachable
    rule appears in exactly one group, which is why a group list is an order
    rather than a filter."""
    listed = [rule_id for ids in manifest.group_order().values() for rule_id in ids]
    assert sorted(listed) == sorted(manifest.batch_reachable_ids())
    assert len(listed) == len(set(listed)) == 56
    for validator, ids in manifest.group_order().items():
        for rule_id in ids:
            assert validator in manifest.rule(rule_id).emitters


def test_the_group_order_accessor_returns_tuples_in_the_packed_order():
    """The shape the compat writer imports: class name to rule ids, tuples so a
    caller cannot mutate the cached manifest out from under the next one."""
    order = manifest.group_order()
    assert order == {name: tuple(ids.split()) for name, ids in GROUP_ORDER.items()}
    assert all(isinstance(ids, tuple) for ids in order.values())
    assert order["CrossFeedDescriptorValidator"] == ("W003", "E047")
    # Not sorted, and not declaration order either: `TimestampValidator` adds its
    # three warning groups before any of its errors.
    assert order["TimestampValidator"][:4] == ("W001", "W007", "W008", "E001")


def test_the_five_strings_are_byte_exact_through_the_loader():
    """Two rules chosen because a helpful edit would silently break parity.

    E019's description carries a double space after the sentence and upstream's
    "doesn't not" typo; W003's suffix is genuinely the empty string, so
    emptiness is a value rather than a missing key and the writer must join a
    prefix to nothing rather than skip the field."""
    e019 = manifest.rule("E019")
    assert e019.error_description.endswith(
        "for the corresponding time period.  Note that this doesn't not apply to "
        "frequency-based trips defined in frequencies.txt with exact_times = 0."
    )
    assert "period.  Note" in e019.error_description
    assert e019.severity == "ERROR"
    assert e019.occurrence_suffix == (
        "- the GTFS-rt start_time is not a multiple of headway_secs later than GTFS start_time"
    )
    w003 = manifest.rule("W003")
    assert w003.occurrence_suffix == ""
    assert w003.title == "ID in one feed missing from the other"
    assert w003.severity == "WARNING"


def test_an_unknown_id_is_a_bug_in_this_project_not_a_finding():
    """Rules are the registry's own ids, so an id the manifest never declared is
    a programming error and raises. Nothing about a feed can reach here."""
    with pytest.raises(KeyError):
        manifest.rule("E999")


def test_the_loader_reads_a_package_resource_rather_than_a_source_path():
    """A path built from `__file__` is a directory that does not exist inside a
    zipped wheel. Asserted over the parse rather than the text, so the module
    may say the word in prose and only using it counts."""
    tree = ast.parse(Path(manifest.__file__).read_text(encoding="utf-8"))
    assert not [node for node in ast.walk(tree) if getattr(node, "id", None) == "__file__"]
    resource = resources.files("gtfs_rt_validator").joinpath("data/rules.json")
    assert json.loads(resource.read_text(encoding="utf-8")) == json.loads(
        PACKED_PATH.read_text(encoding="utf-8")
    )


def severity_literals(path: Path) -> list[str]:
    """String constants whose value is exactly a severity, by parse not by text.

    Only string *constants* count, so `ValueError`, `DecodeError` and a comment
    about error handling are invisible. Only an exact match counts, so a
    docstring saying the word ERROR in a sentence is not a finding while
    `severity = "ERROR"` is."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value in ("ERROR", "WARNING")
    ]


def test_no_severity_literal_lives_outside_the_manifest():
    """Severity gets one home. A rule module that spells its own severity is a
    second source of truth no drift check watches, and it would keep passing
    after upstream changed the value in `ValidationRules.java`.

    Scoped to shipped source: `tools/` produces the value and the suite asserts
    against it, so neither is a second home. Two files under `src/` are excused.
    `report/manifest.py` is the home. The generated `proto/schema_*.py` carry
    "WARNING" because `gtfs-realtime.proto` has an `Alert.SeverityLevel` member
    of that name, which is a field value in somebody's feed and not a notice
    severity; they are generated from the pinned proto and drift-tested, so a
    hand-added severity there would fail elsewhere."""
    excused = [SRC / "report" / "manifest.py", *sorted((SRC / "proto").glob("schema_*.py"))]
    assert len(excused) == 3, f"the exclusion list names files that are gone: {excused}"
    offenders = {
        path.relative_to(ROOT).as_posix(): severity_literals(path)
        for path in sorted(SRC.rglob("*.py"))
        if path not in excused and severity_literals(path)
    }
    assert offenders == {}, "severity comes from manifest.rule(id).severity, never a literal"
