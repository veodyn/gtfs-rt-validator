"""What this project raises on purpose, and nothing else.

Its own module rather than a corner of `api.py` because two things need it and
one of them is `results.py`, which `api` imports: leaving the base classes in
`api` would make that a cycle. `api` re-exports both names, so a caller still
writes `api.UsageError` and `except api.ValidatorError` catches everything.

The rest of the exception model is prose, and it lives in `api.py` where a
reader meets it. In one line: a malformed *feed* is never an exception here, a
malformed *request* always is, and anything else is a bug in this project.
"""

from __future__ import annotations

__all__ = ["UsageError", "ValidatorError"]


class ValidatorError(Exception):
    """The base of everything this project raises on purpose."""


class UsageError(ValidatorError):
    """The request does not describe a run. The caller has to change it."""
