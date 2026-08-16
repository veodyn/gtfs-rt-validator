"""Mode, and the three things it chooses.

Worth one small module, because the design turns on it: mode is **descriptor,
registry and writer**, never a branch inside a rule. Two of the three are here,
because both are a pure function of the mode and neither needs anything a run
knows. The third is not: a writer needs somewhere to write, and the two disagree
about where. `Result.write` takes an output directory, while `report/compat.py`
writes one `.results.json` beside each input from inside the run. So `run.py`
returns a result the caller's chosen writer consumes, and the `Mode` it was run
under is on the config for that caller to switch on.

Selecting the schema here rather than at the decode call site is what keeps
compat honest. `decode(data, mode.schema())` cannot accidentally decode with the
current schema and mask afterwards, which is the design `tests/test_two_views.py`
records two counterexamples against.
"""

from __future__ import annotations

from enum import StrEnum

from gtfs_rt_validator.proto.descriptor import Schema
from gtfs_rt_validator.proto.schema_2015 import SCHEMA as SCHEMA_2015
from gtfs_rt_validator.proto.schema_current import SCHEMA as SCHEMA_CURRENT
from gtfs_rt_validator.rules.registry import Registry

__all__ = ["Mode"]


class Mode(StrEnum):
    """Which of the two validators this run is being."""

    #: Reproduce the jar: the 2015 schema and the 56 batch-reachable rules.
    COMPAT = "compat"

    #: This project's own: the pinned current schema and all three tiers.
    MODERN = "modern"

    def schema(self) -> Schema:
        """The descriptor the decoder is parameterised by."""
        return SCHEMA_2015 if self is Mode.COMPAT else SCHEMA_CURRENT

    def registry(self) -> Registry:
        """The rules this mode runs, built rather than filtered at call time.

        `Registry.compat()` walks the manifest's 56 batch-reachable ids, so a
        `spec` or `practice` rule cannot enter a compat run however it
        registered. Both constructors call `discover()`, which is idempotent.
        """
        return Registry.compat() if self is Mode.COMPAT else Registry.modern()
