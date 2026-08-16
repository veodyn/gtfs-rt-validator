"""The vocabulary of a byte-for-byte comparison of two runs' `.results.json`.

Split out of `tools/diff_compat_against_jar.py` so the comparison is testable
without a jar, a JDK or a corpus: `tests/test_compat_differential.py` feeds these
functions committed bytes with one byte moved and checks the offset it reports.
A comparison nothing has ever rejected is a comparison with no teeth.

Nothing here normalises, tolerates or skips. Two runs either produced the same
bytes for the same input or they did not, and a file one side wrote and the other
did not is a difference like any other.

**Three states, not two.** An input can be absent from a side's mapping, present
with `None` because that side wrote no results file for it, or present with
bytes. The first two are different claims: `None` says a run saw the input and
upstream's file loop skipped it, and absence says the run never had the input at
all. Reading both with `.get()` collapses them, and a regression that dropped
every skipped input from one side would then compare clean.

**A comparison of nothing is not a pass.** Two empty mappings agree, and so do
two zero-byte results files, and neither is evidence of anything. Both are
reported here rather than counted as agreement, so a harness that lost its
corpus goes red instead of green.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

# How many bytes of context to print either side of a first difference.
WINDOW = 60


class _Unseen:
    """A name one side never had, as distinct from one it wrote nothing for."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return "<unseen>"


UNSEEN = _Unseen()


@dataclass(frozen=True)
class Environment:
    """What a comparison ran under, recorded so a result can be reproduced."""

    java_version: str
    locale: str
    jar: Path
    pin: str
    #: How far the pin is evidence rather than configuration. See
    #: `tools/jarattest.py`: the SHA alone is read out of `upstream/pins.json`
    #: and says nothing about the artefact, so it is never printed alone.
    pin_evidence: str = "not checked"
    #: The running jar's own sha256, which is what distinguishes two jars.
    jar_sha256: str = ""

    def describe(self) -> str:
        identity = f", jar sha256 {self.jar_sha256[:12]}" if self.jar_sha256 else ""
        return (
            f"JDK {self.java_version}, FORMAT locale {self.locale}, "
            f"jar pin {self.pin} ({self.pin_evidence}){identity}"
        )


@dataclass(frozen=True)
class Divergence:
    """One input the two sides disagreed about, and how."""

    name: str
    kind: str
    detail: str

    def render(self) -> str:
        body = "\n".join(f"    {line}" for line in self.detail.splitlines())
        return f"  {self.name} [{self.kind}]\n{body}"


@dataclass(frozen=True)
class Report:
    """Both sides of one differential, and the verdict."""

    ours: dict[str, bytes | None]
    jars: dict[str, bytes | None]
    divergences: list[Divergence]
    environment: Environment | None = None
    jar_directory: Path | None = None
    our_directory: Path | None = None

    @property
    def exit_code(self) -> int:
        """Non-zero on any difference, and on a run that compared nothing.

        A report over an empty corpus carries no divergences, which is not the
        same as agreement: it is the state a harness reaches when its corpus
        moved, and returning 0 for it is how a differential goes quietly green.
        """
        return 1 if self.divergences or not self.jars else 0

    def render(self) -> str:
        where = self.environment.describe() if self.environment else "no environment recorded"
        written = sum(1 for blob in self.jars.values() if blob is not None)
        count = len(self.divergences)
        head = [
            f"compared {len(self.jars)} inputs under {where}",
            f"  {written} results files, {len(self.jars) - written} skipped by the jar",
            f"  {count} divergence" + ("" if count == 1 else "s"),
        ]
        if not self.jars:
            head.append("  nothing was compared, which is a failure and not a pass")
        return "\n".join(head + [one.render() for one in self.divergences])


def first_difference(ours: bytes, jars: bytes) -> str:
    """Where two results files first disagree, with the bytes around it.

    A whole-file diff of a results file is unreadable, and the failure that
    matters is almost always one string, so this reports the offset and a window
    rather than the file.
    """
    for offset in range(min(len(ours), len(jars))):
        if ours[offset] != jars[offset]:
            window = slice(max(0, offset - WINDOW), offset + WINDOW)
            return (
                f"first difference at byte {offset}\n"
                f"  ours: {ours[window]!r}\n"
                f"  jar : {jars[window]!r}"
            )
    if len(ours) != len(jars):
        shorter = min(len(ours), len(jars))
        longer = ours if len(ours) > len(jars) else jars
        return (
            f"identical for {shorter} bytes, then ours is {len(ours)} bytes and the jar's "
            f"{len(jars)}; the extra bytes are {longer[shorter : shorter + WINDOW]!r}"
        )
    return ""


def _held(value: object) -> str:
    """What one side holds for a name, short enough to print in a divergence."""
    if isinstance(value, bytes):
        return f"{len(value)} bytes"
    return "no results file" if value is None else "nothing"


def not_results(blob: bytes) -> str:
    """Why these bytes are not a results file, or the empty string if they are.

    Upstream writes Jackson's pretty-printed array and its smallest output is
    `[ ]`, four bytes, so zero bytes is never something a jar run produced.
    Two sides that both wrote nothing at all agree on every byte of it, which is
    why the check is here rather than in the callers: a run in which every
    results file came out empty must not pass for a run in which every file
    matched.
    """
    if not blob:
        return "0 bytes, and the jar's smallest results file is `[ ]`"
    try:
        parsed = json.loads(blob)
    except ValueError as exc:
        return f"not JSON: {exc}"
    if not isinstance(parsed, list):
        return f"a JSON {type(parsed).__name__}, and a results file is an array"
    return ""


def compare(ours: Mapping[str, bytes | None], jars: Mapping[str, bytes | None]) -> list[Divergence]:
    """Every input either side saw, compared byte for byte, absence included.

    Iterating the union rather than one side is deliberate. A loop over our own
    output cannot notice a file only the jar wrote, and a loop over the jar's
    cannot notice one only we wrote; both are parity failures. A feed the jar
    skips for a duplicate MD5 or a decode failure gets no output file at all, so
    `None` on both sides is the agreement being asserted, not a case to skip.

    A name missing from one mapping is read as missing rather than as `None`.
    The two states are different claims, and `.get()` on both sides would let a
    side that dropped every skipped input compare clean against a side that
    kept them.
    """
    names = sorted(set(ours) | set(jars))
    if not names:
        return [
            Divergence(
                "<no inputs>",
                "vacuous",
                "neither side was handed an input, so nothing was compared. An empty "
                "comparison agrees about everything and is evidence of nothing.",
            )
        ]
    divergences = []
    for name in names:
        mine = ours.get(name, UNSEEN)
        theirs = jars.get(name, UNSEEN)
        if mine is UNSEEN:
            detail = f"the jar's run has it ({_held(theirs)}); this project's run never saw it"
            divergences.append(Divergence(name, "unseen-by-ours", detail))
        elif theirs is UNSEEN:
            detail = f"this project's run has it ({_held(mine)}); the jar's run never saw it"
            divergences.append(Divergence(name, "unseen-by-jar", detail))
        elif mine == theirs:
            reason = not_results(mine) if isinstance(mine, bytes) else ""
            if reason:
                divergences.append(
                    Divergence(
                        name,
                        "vacuous",
                        f"both sides wrote {reason}, so the agreement "
                        "between them says nothing about either",
                    )
                )
        elif theirs is None:
            detail = f"the jar wrote no results file; this project wrote {len(mine or b'')} bytes"
            divergences.append(Divergence(name, "only-ours", detail))
        elif mine is None:
            detail = f"the jar wrote {len(theirs)} bytes; this project wrote no results file"
            divergences.append(Divergence(name, "only-jar", detail))
        else:
            divergences.append(Divergence(name, "bytes", first_difference(mine, theirs)))
    return divergences
