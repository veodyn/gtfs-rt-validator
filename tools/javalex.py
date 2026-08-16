"""Just enough Java lexing to read constants out of upstream's source.

Split out of `map_rules.py`, which is the only caller. Not a Java parser: it
knows comments, string and character literals, and escape sequences, because
those are what a regex over Java gets wrong and what decides whether a rule
count comes out right.

Every failure exits rather than guessing. A silently mis-lexed source produces a
manifest that is wrong in a way no diff shows.
"""

from __future__ import annotations

import re
import sys

ESCAPES = {
    "b": "\b",
    "t": "\t",
    "n": "\n",
    "f": "\f",
    "r": "\r",
    "s": " ",
    '"': '"',
    "'": "'",
    "\\": "\\",
}


def strip_comments(text: str, *, blank_strings: bool = False) -> str:
    """Remove comments, optionally blanking string and character literals.

    A scanner rather than a regex: a regex that removes `//` to end of line also
    truncates any string containing `http://`, and one that removes `/* */` eats
    a string containing those characters. Blanking keeps the delimiters, so
    arithmetic on the surrounding syntax still holds, and it means a rule id
    inside an occurrence message can never be read as a call site.
    """
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char == "/" and i + 1 < n and text[i + 1] in "/*":
            i = _skip_comment(text, i)
            out.append("\n" if text[i - 1] == "\n" else " ")
        elif char in "\"'":
            literal, i = read_literal(text, i)
            out.append(char * 2 if blank_strings else literal)
        else:
            out.append(char)
            i += 1
    return "".join(out)


def _skip_comment(text: str, i: int) -> int:
    if text[i + 1] == "/":
        end = text.find("\n", i)
        return len(text) if end == -1 else end + 1
    end = text.find("*/", i + 2)
    if end == -1:
        sys.exit("unterminated block comment; the source is not the Java we expect")
    return end + 2


def read_literal(text: str, i: int) -> tuple[str, int]:
    """Return the raw literal including its delimiters, and the index past it."""
    quote = text[i]
    j = i + 1
    while j < len(text):
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == quote:
            return text[i : j + 1], j + 1
        if text[j] == "\n":
            break
        j += 1
    sys.exit(f"unterminated literal near offset {i}")


def unescape(literal: str) -> str:
    """Java's escape rules, so callers hold the runtime string.

    The pinned `ValidationRules.java` uses none of these, but compat output is
    byte-compared against the jar: the day someone adds a `\\"` to a title,
    approximating it would be a parity failure invisible in a diff of the JSON.
    """
    body = literal[1:-1]
    out: list[str] = []
    i = 0
    while i < len(body):
        if body[i] != "\\":
            out.append(body[i])
            i += 1
            continue
        out_text, width = _unescape_one(body, i, literal)
        out.append(out_text)
        i += width
    return "".join(out)


def _unescape_one(body: str, i: int, literal: str) -> tuple[str, int]:
    marker = body[i + 1]
    if marker == "u":
        return chr(int(body[i + 2 : i + 6], 16)), 6
    if marker in "01234567":
        digits = re.match(r"[0-7]{1,3}", body[i + 1 :]).group()
        return chr(int(digits, 8)), 1 + len(digits)
    if marker in ESCAPES:
        return ESCAPES[marker], 2
    sys.exit(f"unknown Java escape \\{marker} in {literal!r}")


def read_string_arguments(text: str, i: int, count: int) -> list[str]:
    """Read exactly `count` string literals from an already-open argument list.

    Anything else in the list, a concatenation or a named constant, stops the
    run: the caller needs literal strings, and a silently dropped operand is a
    wrong message downstream rather than a crash.
    """
    values: list[str] = []
    while len(values) < count:
        i = _skip_space(text, i)
        if text[i] != '"':
            sys.exit(f"expected a string literal at offset {i}, found {text[i : i + 40]!r}")
        literal, i = read_literal(text, i)
        values.append(unescape(literal))
        i = _skip_space(text, i)
        expected = "," if len(values) < count else ")"
        if text[i] != expected:
            sys.exit(f"expected {expected!r} at offset {i}, found {text[i : i + 40]!r}")
        i += 1
    return values


def _skip_space(text: str, i: int) -> int:
    while text[i].isspace():
        i += 1
    return i
