"""The contract 57 rules are written against: what they are handed, what they return.

Two decisions are pinned here rather than left for each rule module to guess at.

**A rule returns occurrences; the runner collects them.** It does not append to
a container it was handed. Both shapes obey "notices are data appended to a
container, never exceptions": the argument is about who does the appending, and
the answer is the runner, because it is the only party that can stamp the
source file onto every occurrence, refuse an occurrence carrying another rule's
id, and be tested directly without a container being constructed first.

**Reading the cycle and reporting for it are two questions, and the context
answers them separately.** `ctx.cycle` is the whole cycle and reaches every
role, because a VehiclePositions message has every right to look at the Alerts
file beside it. `ctx.combined` is the same view handed only to the message that
reports for the cycle, so a cross-feed rule fires once per cycle rather than
once per role. It is derived from `cycle` and the role rather than stored, which
is what makes it impossible for the two to disagree.

**`memo` is per message, and the runner owns its lifetime.** Every rule that
sees one message sees one scratch dict, and the next message gets another.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from gtfs_rt_validator.proto.decode import decode
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as V2015
from gtfs_rt_validator.report.occurrence import SOURCE_FILE_KEY, NoticeContainer, Occurrence
from gtfs_rt_validator.runner.clock import ClockSource, Reading
from gtfs_rt_validator.runner.context import (
    DEFAULT_ROLE,
    ROLE_ALERTS,
    ROLE_ORDER,
    ROLE_TRIP_UPDATES,
    ROLE_VEHICLE_POSITIONS,
    CombinedFeed,
    RuleContext,
    RuleContractError,
    collect,
    host_role,
)
from gtfs_rt_validator.static._stoptimes import EMPTY_STOP_TIMES
from gtfs_rt_validator.static.adapter import RawTables
from gtfs_rt_validator.static.context import StaticContext
from runnerfixtures import feed

READING = Reading(1_700_000_000_000, ClockSource.FIXED)


def message(*entity_ids: str):
    return decode(feed(*entity_ids), V2015)


def a_context(**kwargs) -> RuleContext:
    """A context built by hand, over a static feed with nothing in it.

    The memo tests read no static member, and building the empty context costs
    no file at all, so they say what they are about and nothing else.
    """
    return RuleContext(
        static=StaticContext.build(RawTables([], [], [], [], EMPTY_STOP_TIMES, [], [])),
        timezone="America/New_York",
        clock=READING,
        source="a.pb",
        **kwargs,
    )


def combined(**roles):
    return CombinedFeed.of(
        {role: message(*ids) for role, ids in roles.items()},
        sources={role: f"{role}.pb" for role in roles},
        clocks=dict.fromkeys(roles, READING),
    )


def test_the_context_carries_what_the_plan_says_it_carries():
    """Static context, previous message, clock, the cycle, named roles.

    Two of them are pairs rather than single values, and the field list is the
    place that says so: "previous" is a message plus the clock it was read at,
    since a rule comparing two messages that had only one clock would compare a
    timestamp against the wrong now, and "role" names which feed this message
    came from while `cycle` holds all of them. `combined` is absent from this
    list on purpose: it is derived from `cycle` and `role` rather than stored.
    `memo` comes last because it is the only field with a default, and it is the
    only mutable one.
    """
    assert tuple(f.name for f in fields(RuleContext)) == (
        "static",
        "timezone",
        "clock",
        "source",
        "role",
        "previous",
        "previous_clock",
        "cycle",
        "memo",
    )


def collected(result, rule_id="E001", source="a.pb"):
    """`collect` is a generator, so a test that wants the answer asks for it."""
    return list(collect(result, rule_id=rule_id, source=source))


def test_a_rule_may_return_a_list_a_generator_or_nothing():
    """`None` is what a plain-function rule that returned early hands back."""
    found = Occurrence("E001", "one")

    assert collected([found])[0].prefix == "one"
    assert collected(iter([found]))[0].prefix == "one"
    assert collected(None) == []


def test_a_generator_rule_reaches_the_container_one_occurrence_at_a_time():
    """The reason the contract is an iterable, and the claim `collect` has to keep.

    The rule reads the container it is filling, so what it sees is the answer to
    "how much had been retained by the time the next occurrence was produced".
    A `collect` that built a list and returned it would show [0, 0, 0]: nothing
    would have reached the container until the rule had finished, which is the
    million-element list the cap was supposed to make impossible.
    """
    container = NoticeContainer()
    seen_by_the_rule: list[int] = []

    def rule():
        for index in range(3):
            seen_by_the_rule.append(container.retained_for("E001"))
            yield Occurrence("E001", str(index))

    container.add_all(collect(rule(), rule_id="E001", source="a.pb"))

    assert seen_by_the_rule == [0, 1, 2]
    assert container.count_for("E001") == 3


def test_a_rule_with_more_findings_than_anyone_wants_is_never_materialised():
    """A thousand stands in for the million the docstring worries about: pulling
    two costs two, where the tuple version cost all thousand up front."""
    produced: list[int] = []

    def rule():
        for index in range(1000):
            produced.append(index)
            yield Occurrence("E001", str(index))

    stream = collect(rule(), rule_id="E001", source="a.pb")
    first_two = [next(stream), next(stream)]

    assert [each.prefix for each in first_two] == ["0", "1"]
    assert produced == [0, 1]


def test_the_runner_stamps_the_source_file_a_rule_did_not_write():
    """57 rules should not each have to remember which file they are reading."""
    stamped = collected([Occurrence("E001", "one")])

    assert stamped[0].context[SOURCE_FILE_KEY] == "a.pb"


def test_a_rule_that_names_its_own_source_file_keeps_it():
    """A cross-feed rule reports against the other role's file, not its host's."""
    named = Occurrence("E047", "one", {SOURCE_FILE_KEY: "vp.pb"})

    kept = collected([named], rule_id="E047", source="tu.pb")[0]

    assert kept.context[SOURCE_FILE_KEY] == "vp.pb"


def test_an_occurrence_carrying_another_rules_id_is_a_bug_in_this_project():
    """Not a finding about a feed, so not an occurrence: an exception."""
    with pytest.raises(RuleContractError, match="E002"):
        collected([Occurrence("E002", "one")])


def test_a_rule_that_returns_something_that_is_not_an_occurrence_is_a_bug():
    with pytest.raises(RuleContractError, match="Occurrence"):
        collected(["E001"])


def test_the_contract_is_still_enforced_when_the_bad_occurrence_comes_late():
    """Streaming moves the check to where the occurrence is, not to nowhere."""
    good = Occurrence("E001", "one")

    with pytest.raises(RuleContractError, match="E002"):
        collected([good, good, Occurrence("E002", "late")])


def test_the_default_role_is_upstreams_single_unnamed_feed():
    """Compat has one role, so "per role" and "global" are the same thing there."""
    assert DEFAULT_ROLE == "rt"
    assert ROLE_ORDER == (ROLE_TRIP_UPDATES, ROLE_VEHICLE_POSITIONS, ROLE_ALERTS, DEFAULT_ROLE)


def test_the_host_role_is_the_first_one_present_in_cli_order():
    """Fixed order, so the same run always reports a cross-feed finding once."""
    assert host_role(["vp", "tu"]) == "tu"
    assert host_role(["sa", "vp"]) == "vp"
    assert host_role([DEFAULT_ROLE]) == DEFAULT_ROLE


def test_an_unnamed_role_sorts_after_the_named_ones():
    """A role this module does not know about cannot displace `-tu` as host."""
    assert host_role(["zz", "tu"]) == "tu"
    assert host_role(["zz", "aa"]) == "aa"


def test_the_combined_view_walks_roles_in_order_then_entities_in_wire_order():
    view = combined(vp=["v1", "v2"], tu=["t1"])

    assert view.roles() == (ROLE_TRIP_UPDATES, ROLE_VEHICLE_POSITIONS)
    assert [(role, index) for role, index, _ in view.entities()] == [
        (ROLE_TRIP_UPDATES, 0),
        (ROLE_VEHICLE_POSITIONS, 0),
        (ROLE_VEHICLE_POSITIONS, 1),
    ]
    assert [entity.get("id") for _, _, entity in view.entities()] == ["t1", "v1", "v2"]


def test_the_combined_view_names_the_file_and_the_clock_of_each_role():
    """E047 reports a mismatch between two files, so it has to name both."""
    view = combined(tu=["t1"], vp=["v1"])

    assert view.source(ROLE_VEHICLE_POSITIONS) == "vp.pb"
    assert view.clock(ROLE_TRIP_UPDATES) == READING
    assert view.source(ROLE_ALERTS) is None


def test_a_compat_cycle_is_one_role_and_is_its_own_combined_view():
    """So E047 and W003 fire exactly where upstream fires them: on one message
    that happens to carry both entity types, and nowhere else. It is also why
    `--compat` cannot notice the split below: the one unnamed role is always the
    first role present, so both views are the same object there."""
    view = combined(rt=["a", "b"])

    assert view.host_role == DEFAULT_ROLE
    assert view.roles() == (DEFAULT_ROLE,)
    assert [entity.get("id") for _, _, entity in view.entities()] == ["a", "b"]
    assert a_context(role=DEFAULT_ROLE, cycle=view).combined is view


def test_the_cycle_reaches_every_role_and_the_host_token_reaches_one():
    """A rule that only reads the cycle is answered on every role; a rule that
    reports for the cycle is answered on one. Both questions used to be asked of
    one field, so reading the Alerts file from the VehiclePositions message was
    impossible in any run that also had `-tu`."""
    view = combined(tu=["t1"], vp=["v1"], sa=["a1"])

    hosting = a_context(role=ROLE_TRIP_UPDATES, cycle=view)
    guest = a_context(role=ROLE_VEHICLE_POSITIONS, cycle=view)

    assert hosting.cycle is view
    assert guest.cycle is view
    assert hosting.combined is view
    assert guest.combined is None


def test_a_context_with_no_cycle_has_neither():
    """A single message standing alone, which is not the same as a message that
    is in a cycle it does not host: there is nothing else to have been shown."""
    ctx = a_context()

    assert ctx.cycle is None
    assert ctx.combined is None


def test_the_host_token_cannot_be_set_by_hand():
    """Derived, not stored, so no caller can hand a non-host message the token
    that says it reports for the cycle."""
    with pytest.raises(TypeError):
        a_context(combined=combined(tu=["t1"]))


def test_two_contexts_built_independently_do_not_share_a_scratch_dict():
    """The classic mutable-default bug, which `default_factory` is what avoids.

    A bare `memo: dict = {}` on the dataclass would make every context in the
    process share one dict, so the twelfth rule of the second message would read
    the first message's walk.
    """
    one, other = a_context(), a_context()

    one.memo["walk:x"] = ["event"]

    assert one.memo is not other.memo
    assert other.memo == {}


def test_replacing_a_field_keeps_the_scratch_dict_of_the_message_it_belongs_to():
    """`replace` still works on the frozen slotted dataclass, and carries the
    dict rather than starting a new one: the message has not changed."""
    ctx = a_context()
    ctx.memo["walk:x"] = ["event"]

    assert replace(ctx, role=ROLE_ALERTS).memo is ctx.memo
