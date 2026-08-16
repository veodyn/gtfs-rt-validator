"""The spec tier's memo contract, proved against a build that counts its runs.

What is asserted here is the part every one of the six spec-tier walks relies on
and none of them would assert any better: the body runs once however many rules
read it, a second message runs it again, two builds are kept apart, and two
builds that answer to one key raise rather than silently returning each other's
work.

The build under test is a fake for the same reason `tests/test_shared_walks.py`
uses one: the contract is about the caching, not about any structure a real walk
happens to yield.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.rules._shared.memo import memo_key, memoised
from gtfs_rt_validator.rules._shared.walks import KEY_PREFIX
from gtfs_rt_validator.rules.errors import RuleContractError
from specfixtures import context

FIRST_MESSAGE = "message one"
SECOND_MESSAGE = "message two"


def counting(name: str, value: object = "built"):
    """A fake build, plus the list of messages its body has actually run over.

    The name is written onto `__qualname__` because that is what the memo key is
    built from, and two closures made here would otherwise be one key.
    """
    ran: list[object] = []

    def build(message, ctx):
        ran.append(message)
        return value

    build.__qualname__ = name
    return build, ran


def test_the_build_runs_once_however_many_rules_read_it():
    """The whole point. Seven rules resolve ids against one feed index, and the
    index is built once between them."""
    build, ran = counting("index")
    ctx = context()

    for _ in range(4):
        assert memoised(build, FIRST_MESSAGE, ctx) == "built"

    assert ran == [FIRST_MESSAGE]


def test_the_next_message_runs_the_build_again():
    """The memo lives on the context and the runner builds one per message, so a
    cached structure can never answer for a message it was not built from."""
    build, ran = counting("index")

    memoised(build, FIRST_MESSAGE, context())
    memoised(build, SECOND_MESSAGE, context())

    assert ran == [FIRST_MESSAGE, SECOND_MESSAGE]


def test_two_builds_over_one_message_are_memoised_apart():
    one, one_ran = counting("entities", "first")
    other, other_ran = counting("translations", "second")
    ctx = context()

    assert memoised(one, FIRST_MESSAGE, ctx) == "first"
    assert memoised(other, FIRST_MESSAGE, ctx) == "second"
    assert (one_ran, other_ran) == ([FIRST_MESSAGE], [FIRST_MESSAGE])


def test_a_scope_makes_a_second_entry_rather_than_a_wrong_answer():
    """A rule that indexes another role's message in the same context needs a
    key of its own. Without one it would be handed this message's index and
    would resolve every id against the wrong feed."""
    build, ran = counting("index")
    ctx = context()

    memoised(build, FIRST_MESSAGE, ctx)
    memoised(build, SECOND_MESSAGE, ctx, scope="vp")

    assert ran == [FIRST_MESSAGE, SECOND_MESSAGE]
    # The names, not the whole keys. A key now carries the message identity as a
    # suffix, because leaving separation to the caller's `scope` was the bug a
    # codex audit found: without one, the second message was served the first
    # one's structure. `scope` still names an entry, it is just no longer what
    # makes the entry correct. See `tests/test_shared_memo_identity.py`.
    assert sorted(key.split("\x00")[0] for key in ctx.memo) == [
        memo_key(build),
        memo_key(build, "vp"),
    ]


def test_the_memo_key_names_the_build_and_shares_the_walk_namespace():
    """Module plus qualified name, under the namespace `walks.py` already owns,
    so a spec-tier index and an upstream walk cannot land on one entry and a
    rule caching something of its own cannot land on either."""
    build, _ = counting("index")
    ctx = context()

    memoised(build, FIRST_MESSAGE, ctx)

    expected = f"{KEY_PREFIX}{__name__}.index"

    assert memo_key(build) == expected
    assert memo_key(build, "vp") == expected + "#vp"
    # One entry, named for the build. The message identity follows the name after
    # a NUL, which no module or qualified name can contain, so splitting on it
    # recovers the name exactly.
    assert [key.split("\x00")[0] for key in ctx.memo] == [expected]


def test_two_builds_that_answer_to_one_key_are_a_bug_in_this_repository():
    """Not a finding about a feed: two modules claiming one memo entry, which
    would silently answer one build with the other's structure."""
    one, _ = counting("index")
    other, _ = counting("index", "something else")
    ctx = context()

    memoised(one, FIRST_MESSAGE, ctx)

    with pytest.raises(RuleContractError, match="index"):
        memoised(other, FIRST_MESSAGE, ctx)


def test_a_build_that_answers_none_is_still_only_run_once():
    """The cache stores the build beside its value, so `None` is a cached answer
    rather than a cache miss that reruns the body on every reader."""
    build, ran = counting("index", None)
    ctx = context()

    assert memoised(build, FIRST_MESSAGE, ctx) is None
    assert memoised(build, FIRST_MESSAGE, ctx) is None
    assert ran == [FIRST_MESSAGE]
