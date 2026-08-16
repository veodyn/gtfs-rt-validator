"""Conformance with the pinned `gtfs-realtime.proto`, S-prefixed.

Every rule here cites the clause it enforces, as `spec: <clause>`, and does not
register without one. Modern mode is where disagreement with upstream is
allowed, and the citation is what makes a disagreement reviewable.

The tier is not the whole proto. "77 fields" is a measured surface, not a rule
list; producing the list has to decide per clause whether it is a check, whether
it is informational, how experimental messages are treated, and how it overlaps
with an existing E or W rule.
"""

from __future__ import annotations
