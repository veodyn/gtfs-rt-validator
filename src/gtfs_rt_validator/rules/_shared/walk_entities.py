"""One pass over a message's `FeedEntity` list, read by S001, S002 and S003.

Three spec-tier rules ask about the entity list itself rather than about
anything inside a payload: whether exactly one payload is present (S001),
whether two entities share an `id` (S002), and whether two TripUpdates describe
one trip instance (S003). All three want the same pass, so it happens once and
they filter it. `memo.py` says why the once matters and where it is kept.

**The payload names come from the descriptor**, not from a tuple written here.
The current `FeedEntity` declares six message-typed fields and the 2015 one
declares three, and a rule handed either message gets the answer for the schema
that decoded it. A hand-written list would be a fourth place the pin has to be
remembered, and the failure it produces is silent: a payload the list does not
name reads as no payload at all, so S001 would report a correct entity as
carrying nothing.

**`payloads` is a tuple and `payload` is the single one or nothing.** The
obvious shape for this walk is `(index, entity, payload_kind)`, and it cannot
state S001's own condition: "none of them, or more than one" needs to know which
ones, because the occurrence text has to say. So the record carries the tuple
and answers `payload` only when there is exactly one, which is the reading every
other rule wants.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gtfs_rt_validator.proto.decode import Msg
from gtfs_rt_validator.proto.descriptor import MessageDesc
from gtfs_rt_validator.rules._shared.memo import memoised

if TYPE_CHECKING:  # Type-only: `runner.context` reaches the static layer and so
    # the sibling, and nothing under `rules/` may import that at run time.
    from gtfs_rt_validator.runner.context import RuleContext

__all__ = ["Entities", "EntityRecord", "entities", "payload_names"]


def payload_names(desc: MessageDesc) -> tuple[str, ...]:
    """The `FeedEntity` fields that carry a payload, in field-number order.

    Every message-typed field, which for `FeedEntity` is exactly the payload
    set: `id` is a string and `is_deleted` a bool, so nothing else qualifies at
    either pin.
    """
    return tuple(field.name for field in desc.fields if field.kind == "message")


@dataclass(frozen=True, slots=True)
class EntityRecord:
    """One `FeedEntity`, with what the three rules above need to read of it."""

    index: int
    entity: Msg
    entity_id: str
    is_deleted: bool
    payloads: tuple[str, ...]
    path: str

    @property
    def payload(self) -> str | None:
        """The one payload this entity carries, or `None` for none or several.

        `None` deliberately answers both defects with one value: a rule that
        cares which it was reads `payloads`, and every rule that does not is
        asking "is this a well-formed entity of some kind", where none and two
        are the same answer.
        """
        return self.payloads[0] if len(self.payloads) == 1 else None


@dataclass(frozen=True, slots=True)
class Entities:
    """Every entity of one message, plus the `id` multiset over all of them."""

    records: tuple[EntityRecord, ...]
    id_counts: Mapping[str, int]

    def carrying(self, payload: str) -> Iterator[EntityRecord]:
        """The entities carrying this payload, in entity order.

        An entity carrying two payloads is yielded by both, which is what the
        wire allows and what S001 is there to report.
        """
        for record in self.records:
            if payload in record.payloads:
                yield record

    def repeated_ids(self) -> tuple[str, ...]:
        """The ids more than one entity claims, in first-seen order.

        First-seen rather than sorted, because an occurrence about a feed reads
        in the order the feed is written, and `Counter` preserves it.
        """
        return tuple(entity_id for entity_id, count in self.id_counts.items() if count > 1)


def entities(message: Any, ctx: RuleContext) -> Entities:
    """Every `FeedEntity` of `message`, walked at most once per context."""
    return memoised(_build, message, ctx)


def _build(message: Any, ctx: RuleContext) -> Entities:
    records = []
    for index, entity in enumerate(message.get("entity")):
        names = payload_names(entity.desc)
        records.append(
            EntityRecord(
                index=index,
                entity=entity,
                entity_id=entity.get("id"),
                is_deleted=bool(entity.get("is_deleted")),
                payloads=tuple(name for name in names if entity.has(name)),
                path=f"entity[{index}]",
            )
        )
    return Entities(tuple(records), Counter(record.entity_id for record in records))
