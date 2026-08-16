"""What `report/compat.py` exports, and the one name it keeps for a caller.

`tests/test_compat_writer.py` owns this module's bytes, which is nearly all of
what it does. What no byte comparison can hold is the smaller question of what a
library user may import from it, and `compat.py` makes two promises in prose
that nothing else here checks.

`validation_rule` was private until a consumer needed to assemble MobilityData's
webapp-shaped body, `report` beside an `enabledRules` list of those beans, and
found this the only way to build one. Publishing it was additive on purpose: the
old private spelling stayed where it was rather than being renamed, because the
consumer had been told nothing would move. That request was later withdrawn and
the export kept, so today nothing in this tree reads `_validation_rule` and
nothing outside it is known to either. A name with no reader is a name a refactor
deletes, and every other test in this suite would stay green while it went.
"""

from __future__ import annotations

import pytest

from gtfs_rt_validator.report import compat, manifest

#: The three names `validation_rule`'s docstring points a caller at as the way to
#: build upstream's webapp body. Listed here so removing one from `__all__` has
#: to be a deliberate edit in two places rather than an oversight in one.
BEAN_SURFACE = ("validation_rule", "entries", "output_order")


def test_the_old_private_spelling_still_resolves_to_the_public_one():
    """The compatibility promise, asserted as identity rather than as behaviour.

    Two functions that happened to return equal dicts would satisfy a value
    comparison and still mean the module had grown a second implementation to
    keep in step. `is` says what was actually promised: one function, reachable
    under both names.
    """
    assert compat._validation_rule is compat.validation_rule


def test_the_bean_the_docstring_sends_a_caller_to_build_is_exported():
    assert set(BEAN_SURFACE) <= set(compat.__all__)


@pytest.mark.parametrize("name", sorted(compat.__all__))
def test_every_exported_name_resolves(name: str):
    """`__all__` is hand-written, so it can name something that is not there.

    A star import would raise on the first such name and nothing else in this
    suite performs one: every other module imports `compat` and reaches through
    it, which works whatever `__all__` says.
    """
    assert hasattr(compat, name)


def test_the_bean_carries_the_five_keys_in_the_beans_declaration_order():
    """Order is part of the contract, because upstream serialises a Java bean's
    declaration order and a caller pasting this into that body inherits it.
    A `dict` comparison would pass on any permutation, so this compares keys.
    """
    rule = manifest.rule("E001")

    bean = compat.validation_rule("E001")

    assert list(bean) == [
        "errorId",
        "severity",
        "title",
        "errorDescription",
        "occurrenceSuffix",
    ]
    assert list(bean.values()) == [
        rule.error_id,
        rule.severity,
        rule.title,
        rule.error_description,
        rule.occurrence_suffix,
    ]
