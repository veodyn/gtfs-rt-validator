"""S036: a localized image URL that is not fully qualified.

The clause mixes an obligation and a recommendation in one sentence, so the
index permits either severity; the rule declares WARNING because the scheme half
is the `should`. The escaping half is enforced in part, and the two tests that
draw the line are `test_the_characters_a_url_may_carry_literally_are_not_reported`,
which is the half R2 still rejects, and `test_a_space_in_the_url_reports`, which
is the half the bytes decide.
"""

from __future__ import annotations

from gtfs_rt_validator.report.occurrence import ENTITY_PATH_KEY
from gtfs_rt_validator.rules.spec.s036 import check
from specfixtures import context, entity, message


def found(*urls):
    alert = {"image": {"localized_image": [{"url": u, "media_type": "image/png"} for u in urls]}}
    return list(check(message(entity("a0", alert=alert)), context()) or ())


def prefixes(*urls):
    return [occurrence.prefix for occurrence in found(*urls)]


def test_a_relative_url_reports():
    assert prefixes("/images/detour.png") == [
        (
            'entity[0].alert.image.localized_image[0] url "/images/detour.png" '
            "does not begin http:// or https://"
        )
    ]


def test_a_scheme_relative_url_reports():
    """`//example.com/a.png` resolves against whatever page loaded it, which is
    exactly what "fully qualified" rules out."""
    assert len(prefixes("//example.com/a.png")) == 1


def test_another_scheme_reports():
    assert len(prefixes("ftp://example.com/a.png")) == 1


def test_both_schemes_the_clause_names_are_silent():
    """The satisfying fixture."""
    assert prefixes("http://example.com/a.png", "https://example.com/b.png") == []


def test_the_occurrence_locates_the_image():
    (occurrence,) = found("https://example.com/a.png", "ftp://example.com/b.png")

    assert occurrence.context[ENTITY_PATH_KEY] == "entity[0].alert.image.localized_image[1]"


def test_each_offending_url_reports_once():
    assert len(prefixes("a.png", "https://example.com/b.png", "ftp://c")) == 2


def test_an_empty_url_reports():
    """`url` is required, so it is always present; present and empty is still
    not a fully qualified URL."""
    assert len(prefixes("")) == 1


def test_a_space_in_the_url_reports():
    """A URI cannot carry a space literally, so a URL that carries one is one
    whose special characters were not correctly escaped. This half of the
    sentence is decidable, unlike the half the module docstring keeps."""
    assert prefixes("https://example.com/a b.png") == [
        (
            'entity[0].alert.image.localized_image[0] url "https://example.com/a b.png" '
            "leaves U+0020 unescaped"
        )
    ]


def test_a_non_ascii_character_reports():
    """The clause's own reference, the W3C URL recommendations, is about exactly
    this: a URL is ASCII and anything else is percent-encoded UTF-8."""
    assert len(prefixes("https://example.com/café.png")) == 1


def test_a_malformed_percent_escape_reports():
    """`%zz` is an escape that is not correct, which the sentence forbids in as
    many words. A trailing `%` is the same defect with nothing after it."""
    assert len(prefixes("https://example.com/a%zz.png", "https://example.com/a%")) == 2


def test_a_correctly_escaped_url_is_silent():
    """The satisfying fixture for the escaping half."""
    assert prefixes("https://example.com/a%20b.png", "https://example.com/caf%C3%A9.png") == []


def test_the_characters_a_url_may_carry_literally_are_not_reported():
    """The half of the escaping sentence that stays rejected under R2. A `?`,
    `&`, `=` or `+` is the same bytes whether the producer escaped something or
    had nothing to escape, so only characters a URI cannot carry at all are
    reported."""
    assert prefixes("https://example.com/a.png?w=1&h=2+3#top") == []


def test_a_url_that_fails_both_halves_reports_once():
    """One image is one finding: the scheme is the half the rule is named for,
    so that is the complaint it makes."""
    assert prefixes("/images/a b.png") == [
        (
            'entity[0].alert.image.localized_image[0] url "/images/a b.png" '
            "does not begin http:// or https://"
        )
    ]


def test_the_scheme_comparison_folds_case():
    """RFC 3986 section 3.1: "Although schemes are case-insensitive, the
    canonical form is lowercase". `HTTPS://example.com/a.png` is the fully
    qualified URL the clause asks for, so reporting it would enforce more than
    the sentence."""
    assert prefixes("HTTPS://example.com/a.png", "Http://example.com/b.png") == []
