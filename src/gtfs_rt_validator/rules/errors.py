"""The one exception the rule layer raises, and the leaf module that holds it.

`proto/errors.py` is the precedent, and the reason is the same one written down
at the top of `registry.py`: every rule imports the rule layer, so the rule
layer must cost nothing to import. Stdlib only here, no import of the sibling,
and no import of anything in this project either.

That last clause is what forces a module of its own rather than a home in
`runner/context.py`, where this class used to live. `rules/_shared/` needs the
type, importing it from `runner.context` runs `runner/__init__`, and that
reaches `static.adapter` and therefore `gtfs_validator`. A string-building
helper then cannot be imported at all without the sibling installed and the
whole static layer built, which a suite that installs the sibling can never
notice. `tests/test_only_adapter_touches_the_sibling.py` imports the rule layer
in a clean interpreter and reads `sys.modules`, which is what does notice.

`runner/context.py` re-exports the name, so every caller that already imports it
from there keeps working.
"""

from __future__ import annotations


class RuleContractError(Exception):
    """A rule broke the contract the runner is written against.

    Never a finding about a feed. It means a module in this repository returned
    something the runner cannot use, or handed a helper here a message of a kind
    it does not serve, which is a bug here and not a malformed message, so it is
    raised rather than recorded.
    """
