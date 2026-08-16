"""Logic more than one rule needs: frequency expansion, timestamps, geometry.

Not a tier. `registry.tier_of` refuses a registration from here and `discover`
never imports it, so nothing in this package can claim an id: a rule here would
be a rule with no manifest entry and no citation. Upstream's 15-rules-in-one-
validator grouping is factored into helpers here instead of being copied across
rule modules, which is the whole reason the package exists.
"""

from __future__ import annotations
