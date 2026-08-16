"""Cut the pinned Best Practices markdown into its normative units.

Three unit shapes carry the document's recommendations, and headings carry
none:

- **Table recommendation rows.** Two-column tables of field name and
  recommendation. The recommendation is every cell after the first, because a
  continuation row leaves the field-name cell empty and the text is still a
  recommendation about the field above it.
- **Top-level bullets.** A `*` at column zero, plus any indented lines that
  follow it, because `:143` runs onto `:144`.
- **Free paragraphs.** Everything else that is not blank, not a heading and not
  a table, grouped between blank lines.

**Only two rewrites happen, and both are reversible by eye.** `<br>` and
`<br/>` become a single space, because a table cell uses them where prose would
use a paragraph break and a sentence splitter cannot see them otherwise; and
the cell's surrounding pipes and padding are dropped. Nothing else is
normalised, no link is unwrapped and no backtick is stripped, so a sentence in
the index is a verbatim substring of a cell in the committed document. The
drift test in `tests/test_clause_citations.py` is what keeps that honest.
"""

from __future__ import annotations

import re

from clausescan import Block

_HEADING = re.compile(r"^#{1,6}\s")
_DELIMITER = re.compile(r"^\|[\s|:-]+\|?$")
_BULLET = re.compile(r"^\*\s")
_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _cells(row: str) -> list[str]:
    body = row.strip()
    body = body[1:] if body.startswith("|") else body
    body = body[:-1] if body.endswith("|") else body
    return [cell.strip() for cell in body.split("|")]


def _unit(line: int, kind: str, text: str) -> tuple[Block, list[int]]:
    """One unit and its character-to-line map.

    Markdown units are quoted from a single starting line even when they span
    several, so every sentence in a unit reports the unit's own line. That is
    the document's granularity: a table cell is one recommendation however it
    wraps, and `<br>` inside it is not a line break in the file.
    """
    return Block(line, "", kind, text), [line] * len(text)


def units(source: str) -> list[tuple[Block, list[int]]]:
    """Every recommendation-carrying unit, in document order."""
    lines = source.split("\n")
    out: list[tuple[Block, list[int]]] = []
    paragraph: list[str] = []
    paragraph_line = 0
    in_table = False
    table_row = 0

    def flush_paragraph() -> None:
        nonlocal paragraph_line
        if paragraph:
            out.append(_unit(paragraph_line, "paragraph", " ".join(paragraph)))
        paragraph.clear()
        paragraph_line = 0

    for number, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped:
            flush_paragraph()
            in_table = False
            continue
        if _HEADING.match(stripped):
            flush_paragraph()
            in_table = False
            continue
        if stripped.startswith("|"):
            flush_paragraph()
            if _DELIMITER.match(stripped):
                in_table = True
                table_row = 0
                continue
            if not in_table:
                continue  # the header row, which names columns rather than rules
            table_row += 1
            text = " ".join(cell for cell in _cells(_BREAK.sub(" ", raw))[1:] if cell)
            if text:
                out.append(_unit(number, "table_row", text))
            continue
        in_table = False
        if _BULLET.match(raw):
            flush_paragraph()
            paragraph_line = number
            paragraph.append(stripped[1:].strip())
            continue
        if paragraph:
            paragraph.append(stripped)
            continue
        paragraph_line = number
        paragraph.append(stripped)
    flush_paragraph()
    return out


def counts(source: str) -> dict[str, int]:
    """The document's shape, measured rather than transcribed."""
    lines = source.split("\n")
    found = units(source)
    kinds = [block.kind for block, _ in found]
    bullets = sum(1 for line in lines if _BULLET.match(line))
    return {
        "lines": len(lines) - 1 if lines and lines[-1] == "" else len(lines),
        "headings": sum(1 for line in lines if _HEADING.match(line.strip())),
        "table_recommendation_rows": kinds.count("table_row"),
        "top_level_bullets": bullets,
        # A bullet is a paragraph unit here, so the free-paragraph count is the
        # paragraphs that are not one.
        "free_paragraphs": kinds.count("paragraph") - bullets,
    }
