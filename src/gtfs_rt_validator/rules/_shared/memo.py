"""One shared computation per message, however many rules read it.

The spec tier's rules overlap the way the upstream tier's do, and for the same
reason: seven of them resolve ids against one feed-wide index, ten read the same
proto2 schedule_relationship defaults, three walk the same entity list. Each of
those structures is built once per message and read many times, and this is
where the once lives. A structure rebuilt per rule is a performance bug no
output test can see, because every rule still reports exactly what it should.

**Why this is not `walks.walk_events`.** That function is this pattern
specialised to the upstream tier's shape: a generator of `Event`, materialised
into a tuple so the second reader is not handed a spent one, then filtered by
rule id. Two of the six spec-tier walks are not sequences at all
(`feed_index` answers one index object, `polyline` answers one decoded line), so
the tuple is wrong for them and the id filter has nothing to filter. The two
share the `walk:` namespace, imported from there rather than spelled twice, and
the collision guard below is what makes sharing it safe: a spec index and an
upstream walk that ever landed on one key would raise rather than answer each
other.

**Why `build` is handed the message.** The same reason `walks.py` gives. `ctx`
also carries `previous` and `combined`, and a build over one of those, memoised
under this message's key, answers the wrong message for every later reader.
`scope` is the way out for a caller that genuinely needs two of a structure in
one context: it is part of the key, so `index(other, ctx, scope="vp")` and
`index(message, ctx)` are two entries rather than one wrong one. A caller
passing a different message with no scope gets this message's structure, which
is why the scope is a keyword and why the sentence above is here rather than in
a comment at one call site.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from gtfs_rt_validator.rules._shared.walks import KEY_PREFIX
from gtfs_rt_validator.rules.errors import RuleContractError

if TYPE_CHECKING:  # A type-only edge, for the reason `walks.py` states: every
    # rule imports this layer, and importing the runner at run time would drag
    # the static layer and the sibling in behind it.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["memo_key", "memoised"]

T = TypeVar("T")


def memo_key(build: Callable[..., Any], scope: str = "") -> str:
    """The memo entry one build owns, for one message.

    Module plus qualified name, which distinguishes every shared structure this
    project will write from every other: they are module-level functions, one
    per structure, so no two share both. The scope is appended rather than
    prepended so the entry still reads as the module that owns it in a debugger.
    """
    key = f"{KEY_PREFIX}{build.__module__}.{build.__qualname__}"
    return f"{key}#{scope}" if scope else key


def memoised(
    build: Callable[[Any, RuleContext], T],
    message: Any,
    ctx: RuleContext,
    *,
    scope: str = "",
) -> T:
    """Whatever `build` answers for `message`, running its body at most once
    **per message**.

    Cached on the context the runner built for this message, so the cache dies
    with the message rather than outliving it. The build is stored beside its
    value, which is what lets `None` be a cached answer rather than a miss that
    reruns the body for every reader, and what lets a second build claiming this
    key be caught instead of quietly served the first one's structure.

    **The message is part of the cache key, and it has to be.** One context can
    see more than one message: a cross-feed rule reads another role's message
    through the same `ctx`, and the combined view is a third. An earlier version
    keyed on the build alone and left correctness to callers passing a `scope`,
    which meant the second message in a context was silently served the first
    one's structure. That is a wrong answer rather than a crash, in a layer every
    rule of the cited tiers reads, so it is keyed by construction now and `scope`
    is back to being a name rather than a correctness argument. A codex audit
    found it, and the three tests that were meant to cover it all built a second
    `RuleContext` and so could never have seen it.
    """
    name = memo_key(build, scope)
    key = f"{name}\x00{id(message)}"
    cached = ctx.memo.get(key)
    if cached is not None:
        if cached[0] is not build:
            raise RuleContractError(
                f"two shared structures answer to the memo key {name}; one build owns one key, so "
                f"give one of them a name of its own rather than let it read the other's work"
            )
        return cached[2]
    value = build(message, ctx)
    # The message is kept in the entry, and that is load bearing twice. It is
    # what makes `id(message)` safe as part of the key, because a live reference
    # cannot have its address reused by a later object; and it is what lets the
    # identity check below be an identity check rather than an equality one.
    ctx.memo[key] = (build, message, value)
    return value
