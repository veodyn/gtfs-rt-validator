"""The rule layer: three tiers of rules, and the registry a mode builds.

```
rules/upstream/e001.py … w009.py   filename == the reported id, lowercased
rules/spec/<id>.py                 new-schema conformance, S-prefixed, cited
rules/practice/<id>.py             best-practice checks, P-prefixed, cited
rules/_shared/                     factored-out logic, not a tier
```

A rule is one module that registers itself:

```python
@rule("E001")
def check(message, ctx): ...
```

and a `spec` or `practice` rule additionally declares the two things the packed
manifest cannot hold for it, its citation and its severity:

```python
from gtfs_rt_validator.report.manifest import Severity

@rule("S001", source="spec: <clause>", severity=Severity.WARNING)
def check(message, ctx): ...
```

Both appends `Occurrence`s rather than raising, because a malformed feed is the
input this project exists to describe. `ctx` is opaque to this package.

No rule body branches on mode; `tests/test_no_mode_branch.py` scans for one.
Severity is never spelled here either: `Severity` is the manifest's own
vocabulary, and `registry.severity_for` is the one lookup that answers for
every tier.
"""

from __future__ import annotations

from gtfs_rt_validator.rules.registry import (
    CITED_TIERS,
    TIERS,
    RegisteredRule,
    RegistrationError,
    Registry,
    RuleFn,
    discover,
    register,
    rule,
    severity_for,
    tier_of,
)

__all__ = [
    "CITED_TIERS",
    "TIERS",
    "RegisteredRule",
    "RegistrationError",
    "Registry",
    "RuleFn",
    "discover",
    "register",
    "rule",
    "severity_for",
    "tier_of",
]
