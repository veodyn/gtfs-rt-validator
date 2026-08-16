"""The sentence splitter and the keyword sweep both clause indexes share.

`scan_clauses.py` assembles the index files, `clauseproto.py` and `clausemd.py`
cut each source into units, and this module turns a unit into normative
sentences. The split mirrors `map_rules.py` / `javascan.py`: the driver
assembles, the readers read, and everything fragile is written down, because a
clause index is only worth what its scanner is.

**The keyword sweep is two passes and must stay two passes.** Measured against
the pinned proto: `PASS_ONE` alone finds 116 sentences and misses 8 real ones
that `PASS_TWO` recovers, among them `TripDescriptor.ADDED`'s deprecation
("This value has been deprecated as the behavior was unspecified") and both
copies of "At most one translation is allowed to have an unspecified language
tag", each of which the spec tier turns into a rule. Collapsing the two
sets into one list of keywords would keep working and keep finding the same
126 sentences; deleting `PASS_TWO` as redundant would silently shrink the
index and silently delete rules' citations. The split is kept so the second
set's contribution stays measurable, and `scan_clauses.py` records both counts
in the index it writes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Modal phrases that make a sentence normative. Two sets, never merged; the
# module docstring says why. Each is matched on word boundaries against the
# lowercased sentence, so "must" does not fire inside "mustard" and capital
# "MUST" is the same keyword as "must".
PASS_ONE = (
    "must",
    "should",
    "required",
    "forbidden",
    "cannot",
    "may only",
    "shall",
    "not allowed",
    "has to",
)
PASS_TWO = (
    "is preferred",
    "recommended",
    "discouraged",
    "encouraged",
    "is allowed",
    "at most one",
    "at least one",
    "deprecated",
    "must be different",
)

# The clause's own modal verb decides the severity, and nothing else is
# consulted. Obligation is an ERROR, advice is a WARNING.
# A sentence carrying both kinds gets both candidates rather than a guess,
# because such a clause is enforced by the half a rule chose to cite.
#
# `is allowed` is in neither set, on purpose. It grants a permission rather
# than stating an obligation or advice, so there is nothing for a rule to
# enforce and a clause whose only modal is that one gets an empty severity
# list, which is what stops a rule from citing it. `:872` "Duplicating a trip
# is allowed if the service ... is operating within the next 30 days" is the
# example; it is rejected on other grounds anyway.
ERROR_MODALS = frozenset(
    {
        "must",
        "required",
        "forbidden",
        "cannot",
        "shall",
        "not allowed",
        "may only",
        "has to",
        "at most one",
        "at least one",
        "must be different",
    }
)
WARNING_MODALS = frozenset(
    {
        "should",
        "recommended",
        "is preferred",
        "discouraged",
        "encouraged",
        "deprecated",
    }
)

# Periods that do not end a sentence: abbreviations, decimals, file names and
# URLs. Masked before splitting and restored after, so the emitted text is the
# source's own bytes. `etc.` is deliberately absent: the proto uses it to end a
# sentence at :709 and mid-sentence at :19, so it is resolved by the following
# character instead.
_PROTECTED = re.compile(
    r"(?:e\.g\.|i\.e\.|cf\.|vs\.|Inc\.|approx\.|No\.\s*\d"
    r"|\d+\.\d+"
    r"|[\w#-]+\.(?:txt|md|proto|html|json|com|org|gov|net)\b"
    r"|https?://[^\s]*[^\s.,;:)])",
    re.IGNORECASE,
)
# A boundary is a terminator plus whitespace. After `etc.` it only counts when
# the next character is an upper-case letter, which is the difference between
# ":709 ... station closure, etc. The image must enhance ..." and ":19 ...
# lines not operating, important delays etc), location ...".
_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_ETC_CONTINUES = re.compile(r"\betc\.$")
# The proto appends two kinds of pointer to a comment without punctuating the
# sentence before them: the `NOTE: This field is still experimental` marker,
# and a bare `See <url>` line. Left alone they glue a real clause to a pointer
# and the pair gets one verdict between them. `Shape` is where it costs the
# most: `:1105` and `:1112` are both "This field is required as per
# reference.md ... because "Required is Forever"", which two rules cite, and
# each arrives with a `See <url>` and a `NOTE:` welded on.
#
# So a gap is also a sentence boundary when what follows is one of those
# pointers, or when what precedes ends in a URL and what follows starts with a
# capital. Checked against the pinned file: every `NOTE:` in it opens the
# experimental marker, both `See http` lines are pointers, and the one URL
# followed by a capital is `:1111`. The Best Practices markdown has none of the
# three and is unaffected.
_URL_END = re.compile(r"https?://\S+$")
_SEE_URL = re.compile(r"See https?://")
_GAP = re.compile(r"\s+")
# A list marker opening a line: "1.", "- ", "*". Never a sentence on its own.
_MARKER = re.compile(r"^(?:[-*•]|\(?\d+[.)]|[a-z][.)])$")


@dataclass(frozen=True)
class Sentence:
    """One sentence of prose, with where it starts in the source."""

    line: int
    text: str


@dataclass(frozen=True)
class Block:
    """A comment block, bullet, paragraph or table cell, with its context."""

    line: int
    scope: str
    kind: str
    text: str


def _unterminated_chunks(text: str) -> list[tuple[int, str]]:
    """Cut `text` where a sentence ends without a full stop.

    The comment above `_URL_END` says which two shapes those are and why the
    pinned file has no false positive for either.
    """
    cuts = []
    for gap in _GAP.finditer(text):
        before, after = text[: gap.start()], text[gap.end() :]
        if before.endswith((".", "!", "?")):
            continue
        opens_pointer = after.startswith("NOTE:") or _SEE_URL.match(after)
        if opens_pointer or (after[:1].isupper() and _URL_END.search(before)):
            cuts.append((gap.start(), gap.end()))
    chunks = []
    start = 0
    for cut_start, cut_end in [*cuts, (len(text), len(text))]:
        chunks.append((start, text[start:cut_start]))
        start = cut_end
    return chunks


def split_sentences(text: str) -> list[tuple[int, str]]:
    """`(offset, sentence)` pairs over `text`, offsets into `text` itself.

    Returns offsets rather than lines because the caller owns the mapping from
    character to source line, which differs between a joined comment block and
    a single markdown cell.
    """
    chunks = _unterminated_chunks(text)
    if len(chunks) > 1:
        return [
            (start + offset, sentence)
            for start, chunk in chunks
            for offset, sentence in split_sentences(chunk)
        ]
    holes: dict[str, str] = {}

    def hide(match: re.Match[str]) -> str:
        key = f"\x00{len(holes)}\x00"
        holes[key] = match.group(0)
        return key

    masked = _PROTECTED.sub(hide, text)
    pieces: list[str] = []
    for piece in _BOUNDARY.split(masked):
        if (pieces and _ETC_CONTINUES.search(pieces[-1]) and not piece[:1].isupper()) or (
            pieces and _MARKER.match(pieces[-1].strip())
        ):
            pieces[-1] = f"{pieces[-1]} {piece}"
        else:
            pieces.append(piece)

    out: list[tuple[int, str]] = []
    cursor = 0
    for piece in pieces:
        for key, value in holes.items():
            piece = piece.replace(key, value)
        stripped = piece.strip()
        if not stripped:
            continue
        found = text.find(stripped, cursor)
        offset = found if found >= 0 else cursor
        cursor = offset + len(stripped)
        out.append((offset, stripped))
    return out


def sentences(block: Block, line_of: list[int]) -> list[Sentence]:
    """Split one block, resolving each sentence's offset back to a source line."""
    return [
        Sentence(line_of[offset] if offset < len(line_of) else block.line, text)
        for offset, text in split_sentences(block.text)
    ]


def modals(text: str) -> tuple[str, ...]:
    """Every modal keyword the sentence carries, in a stable order.

    `PASS_ONE` first, then `PASS_TWO`, so a reader of the index can see which
    pass a sentence needed without a second field.
    """
    lowered = text.lower()
    return tuple(
        word for word in (*PASS_ONE, *PASS_TWO) if re.search(rf"\b{re.escape(word)}\b", lowered)
    )


def severities(found: tuple[str, ...]) -> tuple[str, ...]:
    """The severities the sentence's modal verbs permit, per the two modal sets.

    Two entries means the sentence mixes obligation and advice, and a rule
    citing it declares the severity of the half it enforces. One entry means a
    rule declaring the other severity is wrong, which is the assertion
    `tests/test_clause_citations.py` makes.
    """
    out = []
    if any(word in ERROR_MODALS for word in found):
        out.append("ERROR")
    if any(word in WARNING_MODALS for word in found):
        out.append("WARNING")
    return tuple(out)


def join_comment_block(rows: list[tuple[int, str]]) -> tuple[str, list[int]]:
    """Join comment lines into one string plus a character-to-line map."""
    text = ""
    line_of: list[int] = []
    for number, body in rows:
        if text:
            text += " "
            line_of.append(number)
        text += body
        line_of.extend([number] * len(body))
    return text, line_of


def normative(blocks: list[tuple[Block, list[int]]]) -> list[tuple[Block, Sentence]]:
    """Every normative sentence of every block, in source order."""
    return [
        (block, sentence)
        for block, line_of in blocks
        for sentence in sentences(block, line_of)
        if modals(sentence.text)
    ]
