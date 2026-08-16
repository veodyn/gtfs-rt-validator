"""Jackson's `DefaultPrettyPrinter`, reproduced byte for byte.

Upstream writes its `.results.json` with `new ObjectMapper().writerWithDefault
PrettyPrinter()`, so the layout is not a style choice on either side: it is the
output of one specific printer, and a compat run is byte-compared against it.
`json.dumps` cannot produce it at any setting, which is why this module exists
rather than a keyword argument.

The printer is two indenters, and every visible difference follows from which
one applies where:

- **Objects** use `DefaultIndenter`, a newline plus two spaces per level. It is
  not inline, so it is what raises the nesting level.
- **Arrays** use `FixedSpaceIndenter`, a single space and no newline. It *is*
  inline, so an array does not raise the nesting level at all.

That single fact explains the whole shape. A list of objects opens `[ {`,
separates with `}, {` on one line and closes `} ]`; the objects inside an
`occurrenceList` are indented as if the array were not there; an empty container
is `[ ]` or `{ }`, because the end indenter writes its one space whether or not
anything was written. The entry separator is `" : "`, a space on each side,
which is `DefaultPrettyPrinter`'s `_spacesInObjectEntries` default. Nothing adds
a trailing newline: `writeValue` ends at the last bracket.

Non-ASCII is written as raw UTF-8. Jackson escapes exactly the quote, the
backslash and the control characters, using `\\b`, `\\t`, `\\n`, `\\f` and `\\r`
where they exist and `\\u00XX` otherwise, which is what `json.dumps` with
`ensure_ascii=False` already does. So string escaping is delegated and the rest
is written out longhand.

The value model is deliberately narrow: dict, list, str, int and None, which is
every value a `.results.json` carries. A float or a bool would raise, because
neither has been measured against the printer and guessing at one is how a byte
comparison goes quietly wrong. `bool` is a subclass of `int`, so it is refused
explicitly rather than by omission.
"""

from __future__ import annotations

import json
import re

__all__ = ["INDENT", "KEY_SEPARATOR", "dumps"]

#: `DefaultIndenter.SYSTEM_LINEFEED_INSTANCE`, two spaces per level. Upstream
#: hardcodes the linefeed to `\n` on every platform.
INDENT = "  "
NEWLINE = "\n"

#: `DefaultPrettyPrinter.writeObjectFieldValueSeparator`, spaces included.
KEY_SEPARATOR = " : "


def dumps(value: object) -> str:
    """One JSON document in the printer's layout, with no trailing newline."""
    out: list[str] = []
    _write(value, 0, out)
    return "".join(out)


def _write(value: object, nesting: int, out: list[str]) -> None:
    if isinstance(value, dict):
        _object(value, nesting, out)
    elif isinstance(value, list):
        _array(value, nesting, out)
    elif value is None:
        out.append("null")
    elif isinstance(value, str):
        out.append(_string(value))
    elif isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{type(value).__name__} is not a value this printer was measured for")
    else:
        out.append(str(value))


def _object(value: dict, nesting: int, out: list[str]) -> None:
    """`{`, an entry per line at one level deeper, then `}` back at this level.

    An empty object is `{ }`: `writeEndObject` writes a single space when no
    entry was written, in place of the indentation.
    """
    out.append("{")
    inner = nesting + 1
    for index, (key, item) in enumerate(value.items()):
        out.append("," if index else "")
        out.append(NEWLINE + INDENT * inner + _string(key) + KEY_SEPARATOR)
        _write(item, inner, out)
    out.append(NEWLINE + INDENT * nesting + "}" if value else " }")


def _array(value: list, nesting: int, out: list[str]) -> None:
    """`[`, the values separated by `, `, then `]`, all on the caller's line.

    The nesting level does not move: `FixedSpaceIndenter.isInline()` is true, so
    `writeStartArray` never increments it and an object inside an array is
    indented as though the array were not there.
    """
    out.append("[")
    for index, item in enumerate(value):
        out.append("," if index else "")
        out.append(" ")
        _write(item, nesting, out)
    out.append(" ]")


#: A `\uXXXX` escape as `json.dumps` writes it, for re-casing the four hex
#: digits. Only the escapes `json.dumps` itself produced can match, because a
#: literal backslash in the value is already doubled by the time this runs.
_ESCAPE = re.compile(r"\\u([0-9a-f]{4})")


def _string(value: str) -> str:
    """The quoted, escaped form. Jackson's escape *set* is `json.dumps`'s own.

    Its escape *spelling* is not. **Jackson writes the four hex digits in upper
    case and Python writes them in lower**, so a control character in an
    occurrence prefix is a byte-for-byte divergence. Measured against the pinned
    jar's own Jackson on JDK 17:

        U+0001 -> "\\u0001"   agrees, no letter to disagree about
        U+001F -> "\\u001F"   Python writes "\\u001f"
        U+000B -> "\\u000B"   Python writes "\\u000b"
        U+001B -> "\\u001B"   Python writes "\\u001b"

    Reachable: a `trip_id` is bytes on the wire, so a producer can put U+001F in
    one, and W002 renders it into a prefix. The escape set itself does agree,
    which is the part worth keeping: `/` stays raw, U+2028, U+2029, U+00AD and
    U+007F all stay raw, and the named short escapes match.

    `tests/test_jackson_printer.py` pinned U+0000 before this was found, whose
    escape has no letter in it and so could not see the difference. It now pins a
    character from each hex digit class.
    """
    return _ESCAPE.sub(
        lambda hit: "\\u" + hit.group(1).upper(), json.dumps(value, ensure_ascii=False)
    )
