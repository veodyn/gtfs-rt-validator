"""Cut the pinned `gtfs-realtime.proto` into comment blocks, and count it.

The proto keeps its normative content in `//` comment blocks rather than in the
wire format: `Shape.shape_id` is declared `optional` and its comment says the
field is required and that proto2's "Required is Forever" rule is the only
reason it is not. So a validator that read the cardinality would enforce the
opposite of what the file says, and the comments are the specification.

A block is a maximal run of comment lines at any indent. Scope is the enclosing
`message`/`enum` path, tracked by brace depth over the non-comment lines, so a
comment inside `TripUpdate.StopTimeUpdate` reports that path rather than the
file. File-level comments report the empty scope.
"""

from __future__ import annotations

import re

from clausescan import Block, join_comment_block

_OPENS = re.compile(r"(?:message|enum)\s+(\w+)\s*\{")
_FIELD = re.compile(r"^\s*(required|optional|repeated)\s")
_EXPERIMENTAL = "still experimental"


def blocks(source: str) -> list[tuple[Block, list[int]]]:
    """Every comment block, paired with its character-to-line map."""
    stack: list[str] = []
    pending: list[tuple[int, str]] = []
    out: list[tuple[Block, list[int]]] = []

    def flush() -> None:
        if not pending:
            return
        text, line_of = join_comment_block(pending)
        out.append((Block(pending[0][0], ".".join(stack), "comment", text), line_of))
        pending.clear()

    for number, raw in enumerate(source.split("\n"), 1):
        stripped = raw.strip()
        if stripped.startswith("//"):
            pending.append((number, stripped[2:].strip()))
            continue
        flush()
        opened = _OPENS.search(stripped)
        if opened:
            stack.append(opened.group(1))
        elif stripped.startswith("}") and stack:
            stack.pop()
    flush()
    return out


def counts(source: str) -> dict[str, int]:
    """The proto's shape, measured rather than transcribed.

    `experimental_fields` and `experimental_messages` count declarations whose
    immediately preceding comment block carries the "still experimental" note,
    not lines matching it: the note appears once per declaration but a block can
    hold several sentences, and the interesting number is how much of the
    surface is marked. `enum OccupancyStatus` carries the note too and is not
    counted here, because the number this feeds is "messages out of 28".
    """
    lines = source.split("\n")
    marked_fields = 0
    marked_messages = 0
    note_open = False
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("//"):
            note_open = note_open or _EXPERIMENTAL in stripped
            continue
        if _FIELD.match(raw):
            marked_fields += note_open
        elif re.match(r"^\s*message ", raw):
            marked_messages += note_open
        note_open = False
    return {
        "lines": len(lines) - 1 if lines and lines[-1] == "" else len(lines),
        "messages": sum(1 for line in lines if re.match(r"^\s*message ", line)),
        "enums": sum(1 for line in lines if re.match(r"^\s*enum ", line)),
        "field_definitions": sum(1 for line in lines if _FIELD.match(line)),
        "required_fields": sum(1 for line in lines if re.match(r"^\s*required ", line)),
        "deprecated_sites": sum(1 for line in lines if "deprecated = true" in line),
        "experimental_fields": marked_fields,
        "experimental_messages": marked_messages,
    }
