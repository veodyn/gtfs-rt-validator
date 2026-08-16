"""Where a `spec` or `practice` rule's severity lives, and that it reaches disk.

The packed manifest holds upstream's 61 ids and cannot grow an `S` or `P` one:
`data/rules.json` is generated from `ValidationRules.java` and never
hand-edited. So `manifest.rule("S001")` raises, and a writer that resolved every
severity that way would crash on the first non-upstream occurrence.

**The home chosen: the registration, exactly where the citation already lives.**
A cited-tier rule declares `severity=manifest.Severity.<MEMBER>` beside its
`source=`, `registry.register` refuses the registration without one, and
`registry.severity_for` is the single lookup that answers for every tier: the
manifest for upstream's ids, the registration for the other two tiers'. Three
things follow, and each is a test below.

1. **The words keep one home.** `Severity` is the manifest's own value set, so a
   rule points at a member and never spells the string.
2. **It cannot be invented per call site.** A missing declaration is a
   `RegistrationError` at import, not a default picked by the registry or by a
   writer, because how serious a check is belongs to the check.
3. **The production path resolves it.** Not the `severity_of` hook: the
   end-to-end test at the bottom registers a real `spec` rule, fires it, and
   reads `WARNING` back out of the `report.json` `write_reports` wrote.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from gtfs_rt_validator import rules
from gtfs_rt_validator.report import manifest, modern
from gtfs_rt_validator.report.occurrence import (
    ENTITY_PATH_KEY,
    SOURCE_FILE_KEY,
    NoticeContainer,
    Occurrence,
)
from gtfs_rt_validator.rules.registry import RegistrationError, Registry
from modernrun import MESSAGE, a_summary
from test_packed_manifest import severity_literals
from test_registry import isolated, probe

S_ID = "S999"
S_MODULE = "gtfs_rt_validator.rules.spec.s999"
CITATION = "spec: gtfs-realtime.proto, message FeedHeader, field gtfs_realtime_version"

#: A rule module as one would be written. The point of it is the decorator line:
#: the severity is a member reference, so the source carries no severity string.
A_RULE_MODULE = f'''"""S001: the feed does not declare the version this project reads."""

from gtfs_rt_validator.report.manifest import Severity
from gtfs_rt_validator.rules import rule


@rule("{S_ID}", source="{CITATION}", severity=Severity.WARNING)
def check(message, ctx):
    return message.header.gtfs_realtime_version
'''


def a_feed(version: str) -> SimpleNamespace:
    """Enough of a decoded message for one field-level rule to look at."""
    return SimpleNamespace(header=SimpleNamespace(gtfs_realtime_version=version))


def a_spec_rule(container: NoticeContainer):
    """A real `spec` rule, registered through the real decorator.

    It appends rather than raising, like every rule, and it is attributed to
    `rules/spec/s999.py` the only way a tier is ever claimed: through the
    function's own `__module__`. S999 is a stub id that ships nowhere: what is
    under test is the severity plumbing rather than any real rule's content.
    """

    def check(message: SimpleNamespace, ctx: object) -> None:
        if message.header.gtfs_realtime_version != "2.0":
            container.add(
                Occurrence(
                    S_ID,
                    prefix=f"gtfs_realtime_version {message.header.gtfs_realtime_version}",
                    context={
                        SOURCE_FILE_KEY: MESSAGE,
                        ENTITY_PATH_KEY: "header",
                        "gtfsRealtimeVersion": message.header.gtfs_realtime_version,
                    },
                )
            )

    check.__module__ = S_MODULE
    return rules.rule(S_ID, source=CITATION, severity=manifest.Severity.WARNING)(check)


def test_the_vocabulary_names_every_severity_the_packed_manifest_carries():
    """The enum is upstream's value set with a name, not a set of this
    project's own: if `ValidationRules.java` ever grows a third level, this
    fails rather than letting a declaration mean what the data does not."""
    packed = {manifest.rule(rule_id).severity for rule_id in manifest.all_ids()}
    assert packed == {member.value for member in manifest.Severity}
    assert manifest.SYSTEM_ERROR_SEVERITY in manifest.Severity


def test_a_cited_tier_rule_that_declares_no_severity_does_not_register():
    """The gate, and the reason it is a gate rather than a default: a tree
    cannot ship a rule whose report entry has no severity to print."""
    with isolated():
        with pytest.raises(RegistrationError, match="must declare its severity"):
            rules.rule(S_ID, source=CITATION)(probe(S_MODULE))
        assert Registry.modern().ids() == ()


def test_a_severity_spelled_as_a_string_is_not_a_declaration():
    """Pointing at the member is the whole design."""
    with isolated():
        for spelled in ("ERROR", "warning", "INFO", 2):
            with pytest.raises(RegistrationError, match="must declare its severity"):
                rules.rule(S_ID, source=CITATION, severity=spelled)(probe(S_MODULE))
        assert Registry.modern().ids() == ()


def test_an_upstream_rule_may_not_declare_a_severity():
    """The mirror of the citation gate: upstream's severity is the manifest's,
    and a declaration here would be a second answer that no drift test watches.
    """
    with isolated(), pytest.raises(RegistrationError, match="declares no severity"):
        rules.rule("E001", severity=manifest.Severity.WARNING)(
            probe("gtfs_rt_validator.rules.upstream.e001")
        )


def test_one_lookup_answers_for_every_tier():
    """`severity_for` is what the writer calls, and it does not parse the id."""
    with isolated():
        rules.rule("E001")(probe("gtfs_rt_validator.rules.upstream.e001"))
        rules.rule(S_ID, source=CITATION, severity=manifest.Severity.WARNING)(probe(S_MODULE))
        assert rules.severity_for("E001") == manifest.rule("E001").severity
        assert rules.severity_for(S_ID) == manifest.Severity.WARNING
        assert rules.severity_for(S_ID) != manifest.rule("E001").severity
        # An upstream id resolves through the manifest whether or not a module
        # for it registered, since that is where its severity has always lived.
        assert rules.severity_for("W003") == manifest.rule("W003").severity


def test_an_id_that_no_tier_declared_is_a_bug_and_raises():
    """Feeds cannot reach this: an id that neither registered nor sits in the
    manifest is a rule this project never wrote down anywhere."""
    with isolated(), pytest.raises(KeyError):
        rules.severity_for("S999")


def test_a_rule_module_that_declares_a_severity_spells_none(tmp_path):
    """The constraint a rule module has to satisfy, checked with the build's own
    scanner rather than by eye: `test_packed_manifest.py` fails on a severity
    string anywhere under `src/`, and a declaration is a member reference."""
    written = tmp_path / "s001.py"
    written.write_text(A_RULE_MODULE, encoding="utf-8")
    assert severity_literals(written) == []
    assert "Severity.WARNING" in A_RULE_MODULE


def test_an_s_tier_rule_reaches_write_reports_and_its_severity_lands_in_the_file(tmp_path):
    """End to end through the production entry point, which is the finding.

    No `severity_of` argument anywhere: `write_reports` is called the way
    `api.py` calls it, and before this change the first `S` occurrence raised
    `KeyError` inside it and no report was written at all.
    """
    container = NoticeContainer()
    with isolated():
        check = a_spec_rule(container)
        assert Registry.modern().get(S_ID).severity is manifest.Severity.WARNING
        check(a_feed("2.0"), None)
        assert container.count_for(S_ID) == 0
        check(a_feed("1.0"), None)
        report_path, _ = modern.write_reports(
            tmp_path / "out", container, NoticeContainer(), a_summary()
        )
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["notices"] == [
        {
            "code": S_ID,
            "severity": "WARNING",
            "totalNotices": 1,
            "sampleNotices": [
                {
                    modern.PREFIX_KEY: "gtfs_realtime_version 1.0",
                    SOURCE_FILE_KEY: MESSAGE,
                    ENTITY_PATH_KEY: "header",
                    "gtfsRealtimeVersion": "1.0",
                }
            ],
        }
    ]
    # Declared, not borrowed: the value differs from what an upstream rule of
    # the same shape would have reported, so nothing could have supplied it but
    # the registration.
    assert payload["notices"][0]["severity"] != manifest.rule("E002").severity
