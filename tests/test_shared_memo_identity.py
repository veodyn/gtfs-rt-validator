"""One context, two messages: the second must not be served the first's answer.

Both cases here were found by a codex audit of the tier infrastructure, and both
are the same class of defect: a cached structure that is *wrong* rather than
merely stale, in a layer every rule of the cited tiers reads.

The memo was keyed on the builder alone, so `walk(second, ctx)` returned
`walk(first, ctx)`'s structure. One context genuinely sees more than one message:
a cross-feed rule reads another role's message through the same `ctx`, and the
combined view is a third. Correctness was left to callers remembering a `scope`
argument, which is a convention rather than a contract.

Three existing tests were meant to cover this and could not, because each built a
second `RuleContext` for the second call. Two contexts have two memos, so the
second call was always a miss and always rebuilt. That is why this file is
separate and why every test in it reuses ONE context: the shared context is the
whole point, and a test that quietly makes a new one proves nothing.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.rules._shared.memo import memo_key, memoised
from gtfs_rt_validator.rules.errors import RuleContractError


class Ctx:
    """The only part of `RuleContext` the memo touches.

    A real context would do, but it drags the runner and the sibling in behind
    it, and `rules/_shared/` may not import either. `tests/test_rule_layering.py`
    enforces that in a subprocess.
    """

    def __init__(self) -> None:
        self.memo: dict[str, object] = {}


def build_ids(message, ctx):
    """Something whose answer depends on the message, so a wrong hit is visible."""
    return tuple(message)


def test_a_second_message_in_one_context_is_not_served_the_first_ones_answer():
    """The audit's exact reproduction, which the old key answered wrongly."""
    ctx = Ctx()
    first = ("one",)
    second = ("two",)
    assert memoised(build_ids, first, ctx) == ("one",)
    assert memoised(build_ids, second, ctx) == ("two",)


def test_the_same_message_twice_in_one_context_builds_once():
    """The property the memo exists for, which the fix must not cost."""
    ctx = Ctx()
    runs = []

    def counted(message, context):
        runs.append(message)
        return tuple(message)

    message = ("one",)
    assert memoised(counted, message, ctx) is memoised(counted, message, ctx)
    assert runs == [message]


def test_two_messages_that_compare_equal_are_still_two_entries():
    """Identity, not equality.

    Two decoded messages can be equal and still be different feed files, and the
    runner hands the walk the object rather than a copy. Keying on equality would
    need every structure to be hashable, which a decoded message is not.
    """
    ctx = Ctx()
    # Lists rather than tuples, because CPython folds equal tuple constants in
    # one code object to a single object: `("same",)` twice would bind the same
    # tuple and the test would be asserting nothing at all about identity.
    first = ["same"]
    second = ["same"]
    assert first == second and first is not second
    assert memoised(build_ids, first, ctx) == ("same",)
    assert memoised(build_ids, second, ctx) == ("same",)
    assert len(ctx.memo) == 2


def test_the_entry_keeps_the_message_alive_so_its_address_cannot_be_reused():
    """Why `id(message)` is safe here and would not be on its own.

    A freed object's address can be handed to the next allocation, so a key built
    from `id()` alone could collide across a garbage collection. The entry holds
    the message, so an entry's message cannot be freed while the entry lives.
    """
    ctx = Ctx()
    message = ("one",)
    memoised(build_ids, message, ctx)
    entry = next(iter(ctx.memo.values()))
    assert entry[1] is message


def test_two_builds_claiming_one_name_are_still_refused():
    """The pre-existing guard, kept: it is about names colliding, not messages."""
    ctx = Ctx()
    message = ("one",)

    def impostor(msg, context):
        return ()

    impostor.__module__ = build_ids.__module__
    impostor.__qualname__ = build_ids.__qualname__

    memoised(build_ids, message, ctx)
    with pytest.raises(RuleContractError, match="two shared structures"):
        memoised(impostor, message, ctx)


def test_memo_key_is_still_the_readable_name():
    """`memo_key` stayed a name for debuggers; the message is appended inside
    `memoised`, so nothing that prints a key gained an address."""
    assert memo_key(build_ids).endswith("build_ids")
    assert memo_key(build_ids, "other-role").endswith("#other-role")
