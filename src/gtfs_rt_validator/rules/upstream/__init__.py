"""Upstream's rules, one module per reported id, filename == id lowercased.

57 ids are emitted upstream and 56 of them are reachable from `BatchProcessor`,
which is the set `Registry.compat()` targets. E010's only emitter is registered
nowhere, so a module for it would run in modern mode only; E005, E007, E008 and
E014 are declared and emitted by nothing, so they have no module at all.

Upstream groups these by validator, with `TripDescriptorValidator` alone
emitting 15 of them. That grouping is deliberately not mirrored: shared logic
goes to `rules/_shared/`, so a code in a report opens exactly one file.

These rules cite no source. Their source is the pinned Java, and the manifest
records it; `registry.register` rejects a citation on this tier.

How full this package is at any commit is pinned by `WRITTEN_COMPAT_RULES` in
`tests/writtenrules.py`, which `tests/test_completeness.py` compares against
what `Registry.compat()` reports.
"""

from __future__ import annotations
