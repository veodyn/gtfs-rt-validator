"""What a rule appends, and the container that collects it.

An occurrence is data, never an exception. A rule that finds something wrong
appends one of these; nothing here raises, because a malformed feed is the
input this project exists to describe.

**The prefix is stored; the suffix never is.** Upstream's `.results.json` keeps
the two halves in separate fields and has no concatenated one: the per-rule
`occurrenceSuffix` sits on the rule object and the per-occurrence `prefix` sits
on the occurrence. The readable message a human sees, and the line upstream
writes to its debug log, is the two joined at write time. So `Occurrence` holds
the prefix and the rule id, and the writer looks the suffix up in the manifest.
Nothing in this module can produce the join, which is what
`tests/test_occurrence.py` asserts.

That join is now measured, and the answer is that nothing here should build it.
`util/RuleUtils.java:40` is `log.debug(om.getPrefix() + " " + rule.getOccurrenceSuffix())`:
one space, unconditionally, so W003, whose suffix is the empty string, logs a
trailing space. It is the **debug log only**. A run of the jar built from the
pinned commit confirms there is no concatenated field anywhere in the JSON, and
`tests/test_jar_output_contract.py` asserts that against the goldens. So the
join reaches no output byte, and no occurrence and no writer produces it.

Sample caps, their names and their numbers follow the sibling's
`NoticeContainer` rather than being reinvented. Three deliberate differences,
each forced by something about this project rather than chosen:

- **No severity.** The sibling's `Notice` carries a `Severity` and keys its
  groups by code plus severity ordinal. Here severity has exactly one home, the
  rule manifest, so an occurrence carries only its rule id and groups key on
  that alone. `has_errors`, `error_count` and `mapping_key` therefore have no
  counterpart here; a caller that needs them joins against the manifest, which
  is where `--fail-on-error` will read them from.
- **Per rule, not per type.** Same idea, renamed to match what the key is:
  `max_per_rule`, `max_exports_per_rule`, `count_for(rule_id)`.
- **Context carries the source file and the entity path.** The sibling's run is
  one static feed, so a notice's context needs no file. A run here spans many
  messages across many files, so a sample that does not say which message it
  came from cannot be looked at. `SOURCE_FILE_KEY` and `ENTITY_PATH_KEY` name
  those two keys; the rest of the context stays the sibling's camelCase.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

#: Context key naming the message this occurrence came from. This project's
#: departure from the sibling, whose run is a single feed.
SOURCE_FILE_KEY = "sourceFile"

#: Context key locating the entity inside that message, for the same reason.
ENTITY_PATH_KEY = "entityPath"

#: The sibling's caps, under this project's per-rule names.
MAX_TOTAL_OCCURRENCES = 10_000_000
MAX_OCCURRENCES_PER_RULE = 100_000
MAX_EXPORTS_PER_RULE = 1_000


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One finding: which rule, upstream's occurrence prefix, and the context.

    `prefix` is upstream's `prefix` field verbatim, the half of the message that
    varies per occurrence. The other half lives in the manifest under the rule
    id and is joined on only when a human has to read it.
    """

    rule_id: str
    prefix: str = ""
    context: dict[str, object] = field(default_factory=dict)


class NoticeContainer:
    """Collects occurrences under the sibling's caps.

    The per-rule count moves for every occurrence added, retained or not,
    because the exported total is the true count. A report that says 14 while
    holding 3 samples is the intended shape, not a bug.
    """

    def __init__(
        self,
        max_total: int = MAX_TOTAL_OCCURRENCES,
        max_per_rule: int = MAX_OCCURRENCES_PER_RULE,
        max_exports_per_rule: int = MAX_EXPORTS_PER_RULE,
    ) -> None:
        self.max_total = max_total
        self.max_per_rule = max_per_rule
        self.max_exports_per_rule = max_exports_per_rule
        self._occurrences: list[Occurrence] = []
        self._counts: dict[str, int] = {}
        self._retained: dict[str, int] = {}

    def add(self, occurrence: Occurrence) -> None:
        """Count it, and retain it if neither cap has been reached.

        Never raises, whatever the occurrence holds.
        """
        rule_id = occurrence.rule_id
        count = self._counts.get(rule_id, 0) + 1
        self._counts[rule_id] = count

        if len(self._occurrences) >= self.max_total or count > self.max_per_rule:
            return
        self._occurrences.append(occurrence)
        self._retained[rule_id] = self._retained.get(rule_id, 0) + 1

    def add_all(self, occurrences: Iterable[Occurrence]) -> None:
        for occurrence in occurrences:
            self.add(occurrence)

    def observe_dropped(self, rule_id: str, count: int = 1) -> None:
        """`add`'s bookkeeping without retention.

        For a caller that already knows an occurrence cannot be retained and so
        does not carry it: the count must still move exactly as that many capped
        `add` calls would have moved it. The sibling's version also takes a
        severity, which this project reads from the manifest instead.
        """
        self._counts[rule_id] = self._counts.get(rule_id, 0) + count

    def merge(self, other: NoticeContainer) -> None:
        """Absorb another container, mirroring the sibling's `merge`.

        Not the same as `add_all` over its occurrences: the counts are summed
        rather than recomputed, so a rule that hit the per-rule cap in the other
        container still contributes its full total. Forwarding only the retained
        occurrences would make the reported total undercount.

        The caps are deliberately not re-applied to the merged occurrences,
        matching the sibling: each container already applied them on the way in,
        so the result may hold more than the maxima.
        """
        self._occurrences.extend(other._occurrences)
        for rule_id, count in other._counts.items():
            self._counts[rule_id] = self._counts.get(rule_id, 0) + count
        for rule_id, count in other._retained.items():
            self._retained[rule_id] = self._retained.get(rule_id, 0) + count

    def count_for(self, rule_id: str) -> int:
        """Every occurrence added for this rule, including ones not retained."""
        return self._counts.get(rule_id, 0)

    def retained_for(self, rule_id: str) -> int:
        """How many of them this container still holds."""
        return self._retained.get(rule_id, 0)

    def dropped_for(self, rule_id: str) -> int:
        """What capping cost. Nonzero means the samples are a sample."""
        return self.count_for(rule_id) - self.retained_for(rule_id)

    def rule_ids(self) -> tuple[str, ...]:
        """Every rule that fired, in first-seen order, retained or not."""
        return tuple(self._counts)

    def in_order(self) -> tuple[Occurrence, ...]:
        """The retained occurrences in insertion order, across all rules.

        This layer promises only not to reorder. The compat output order is
        upstream's `BatchProcessor` registration order, which `report/compat.py`
        owns and states, so a writer must not read it out of here.
        """
        return tuple(self._occurrences)

    def grouped(self) -> dict[str, list[Occurrence]]:
        """Rule id to its retained occurrences, insertion order within each.

        Keys are sorted, as the sibling sorts its grouping keys. That is a
        stable presentation order, not upstream's output order.
        """
        groups: dict[str, list[Occurrence]] = {}
        for occurrence in self._occurrences:
            groups.setdefault(occurrence.rule_id, []).append(occurrence)
        return {rule_id: groups[rule_id] for rule_id in sorted(groups)}

    def samples_for(self, rule_id: str) -> tuple[Occurrence, ...]:
        """The first `max_exports_per_rule` retained occurrences for one rule.

        The export cap is separate from the retention cap, as in the sibling:
        the container may hold far more than a report should print.
        """
        return tuple(self._take(rule_id, self.max_exports_per_rule))

    def _take(self, rule_id: str, limit: int) -> Iterator[Occurrence]:
        taken = 0
        for occurrence in self._occurrences:
            if taken >= limit:
                return
            if occurrence.rule_id == rule_id:
                taken += 1
                yield occurrence
