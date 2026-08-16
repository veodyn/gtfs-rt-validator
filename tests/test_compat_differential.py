"""This project's compat output against a jar run over the same staged bytes.

`tests/test_compat_writer.py` compares against the five `.results.json` files
committed under `tests/fixtures/jar/`. That is a comparison against a recording.
This module is the comparison against the jar itself: both sides are handed the
same staged directory, the same mtimes and the same static archive, and every
byte of every results file has to agree, including whether a results file exists
at all.

**The archive is the committed `testagency.zip`, unmodified.** Both sides used
to be handed a copy with two lettered `direction_id` cells blanked, because
compat read its static feed through the sibling's strict typed path;
`tools/diff_compat_against_jar.py` records what changed.
`test_the_live_jar_writes_what_the_committed_goldens_hold` is the check that the
archive and the goldens are still the same pair.

The jar-gated tests skip when `jar-build/` holds no jar, because it is gitignored
and a clean checkout will not have one. A skip is not a pass: the pure-Python
tests below run everywhere and are what give the comparison teeth.
"""

from __future__ import annotations

import pytest

from jarcorpus import CORPUS, INPUTS, fingerprint, golden_bytes, import_tool, input_bytes

jarenv = import_tool("jarenv")
jarattest = import_tool("jarattest")
diff = import_tool("diff_compat_against_jar")

NAMES = [entry["name"] for entry in INPUTS]
CORPUS_BYTES = {name: input_bytes(name) for name in NAMES}
FIRST_GOLDEN = "01-no-timestamps.pb"


def _unavailable() -> str:
    """Why this comparison cannot run here, or the empty string if it can."""
    if not jarenv.jar_present():
        return f"no jar at {jarenv.JAR}; run .venv/bin/python tools/build_jar.py"
    try:
        diff.environment()
    except (jarenv.NoJdk17Error, diff.WrongLocaleError) as exc:
        return str(exc)
    return ""


REASON = _unavailable()
needs_jar = pytest.mark.skipif(bool(REASON), reason=REASON or "a jar is present")


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    """One jar run and one compat run over the same corpus, shared by the module."""
    return diff.differential(CORPUS_BYTES, tmp_path_factory.mktemp("differential"))


# --- the differential itself -----------------------------------------------


@needs_jar
def test_every_results_file_agrees_with_the_jar_byte_for_byte(report):
    """The deliverable. A red diff here is a finding, never a reason to widen
    the assertion: either this project is wrong or the jar is, and both stop the
    build."""
    assert report.divergences == [], report.render()


@needs_jar
def test_the_absence_of_a_file_is_compared_too(report):
    """A feed the jar skips gets no output file at all. Writing an empty list for
    one would be this project claiming it validated something upstream never
    read, and a byte comparison over the files that exist would never see it."""
    skipped = [entry["name"] for entry in INPUTS if entry["results"] is None]
    assert skipped == ["05-duplicate-of-04.pb", "06-truncated.pb", "07-empty.pb"]
    for name in skipped:
        assert report.jars[name] is None
        assert report.ours[name] is None
    assert sorted(report.ours) == sorted(report.jars) == sorted(NAMES)


@needs_jar
def test_the_live_jar_writes_what_the_committed_goldens_hold(report):
    """Both sides now run against the committed `testagency.zip` as it stands.

    This used to hand both of them a copy with two lettered `direction_id` cells
    blanked, and asserted that the patch was invisible to the jar by comparing
    its live output against goldens produced from the original. The archive and
    the goldens are the same pair again, so the comparison is direct."""
    for name in NAMES:
        expected = golden_bytes(name) if _has_golden(name) else None
        assert report.jars[name] == expected, name


def _has_golden(name: str) -> bool:
    return next(entry for entry in INPUTS if entry["name"] == name)["results"] is not None


@needs_jar
def test_neither_run_wrote_into_the_committed_corpus(report):
    """Both sides write `.results.json` beside their inputs, and upstream walks
    every regular file with no extension filter, so a run inside the committed
    corpus would leave a directory whose next run ingests its own output. The
    check is the exact file set rather than a spot check for a doubled suffix,
    because a stray file of any name is the same trap.
    """
    expected = {"manifest.json", *NAMES}
    expected |= {entry["results"] for entry in INPUTS if entry["results"] is not None}
    assert set(fingerprint(CORPUS)) == expected
    assert CORPUS not in (report.jar_directory, report.our_directory)


@needs_jar
def test_the_command_is_green_over_the_committed_corpus():
    """Usable as a command, not only as a test. Exit 0 means no divergence."""
    assert diff.main([]) == 0


# --- what the environment has to be ----------------------------------------


@needs_jar
def test_the_comparison_ran_under_jdk_17_and_a_dot_decimal_locale(report):
    """Two pins measured the hard way. `Float.toString` was rewritten in JDK 19
    (JDK-4511638), so E026, E027, E028, E029 and W004 render differently on 19
    or later and neither result is wrong. `String.format("%.2f", ...)` in
    `VehicleValidator` passes no `Locale`, so a comma-decimal FORMAT locale
    writes different bytes for the same float."""
    assert report.environment.java_version.startswith("17.")
    assert report.environment.locale == diff.GOLDEN_LOCALE
    assert report.environment.pin == jarenv.pin()[1]
    assert "17." in report.render()
    assert diff.GOLDEN_LOCALE in report.render()


@needs_jar
def test_the_pin_in_the_report_was_checked_against_the_jar_being_run(report):
    """The pin is configuration until something looks at the artefact.

    `jarattest.attested_pin` reports how far it got, and the report prints that
    reason and the running jar's own digest. Here the jar was built from the
    checkout, so the evidence has to say so rather than say `configured`.
    """
    assert report.environment.pin_evidence == "verified against the checkout the jar was built in"
    assert report.environment.jar_sha256 == jarattest.jar_digest()
    assert jarattest.checkout_head() == jarenv.pin()[1]
    assert report.environment.jar_sha256[:12] in report.render()


def test_an_unbuilt_or_moved_checkout_is_reported_as_unverified(monkeypatch):
    """The three states `attested_pin` distinguishes, none of which may print a
    bare SHA as though the artefact had been inspected."""
    monkeypatch.setattr(jarattest, "checkout_head", lambda: None)
    assert jarattest.attested_pin()[1].startswith("configured, unverified")

    monkeypatch.setattr(jarattest, "checkout_head", lambda: "0" * 40)
    pin, evidence = jarattest.attested_pin()
    assert pin == jarenv.pin()[1]
    assert evidence.startswith("configured, CONTRADICTED")
    assert "0" * 40 in evidence

    monkeypatch.setattr(jarattest, "checkout_head", lambda: jarenv.pin()[1])
    monkeypatch.setattr(jarattest, "stale", lambda: True)
    assert "older than the checkout's sources" in jarattest.attested_pin()[1]


def test_a_jdk_that_is_not_17_is_refused_rather_than_measured(monkeypatch):
    """`jarenv.java_home_17` refusing anything but 17 is load bearing rather
    than tidiness, so the harness must not paper over it with a fallback."""

    def no_seventeen():
        raise jarenv.NoJdk17Error("no JDK 17 found")

    monkeypatch.setattr(diff.jarenv, "java_17", no_seventeen)
    with pytest.raises(jarenv.NoJdk17Error):
        diff.environment()


def test_a_comma_decimal_locale_is_refused_rather_than_compared(monkeypatch):
    """Under `de_DE` the jar writes `"69,35"` where this project writes `"69.35"`
    and neither is wrong. Refusing up front names the reason; comparing anyway
    produces a red diff that reads like a bug in a rule."""
    monkeypatch.setattr(
        jarenv,
        "properties",
        lambda _java: {"java.version": "17.0.19", "user.language": "de", "user.country": "DE"},
    )
    monkeypatch.setattr(diff.jarenv, "java_17", lambda: diff.jarenv.JAR)
    with pytest.raises(diff.WrongLocaleError, match="de-DE"):
        diff.environment()


def test_a_format_locale_override_alone_is_refused(monkeypatch):
    """The case reading `user.language` and `user.country` cannot see.

    `String.format` with no `Locale` reads `Locale.getDefault(Category.FORMAT)`,
    and `-Duser.language.format=de -Duser.country.format=DE` moves that category
    while leaving the base locale at `en`/`US`. A harness that reads only the
    base pair reports `en-US` and compares against a jar formatting `1,00
    mile(s)` where the golden has `1.00 mile(s)`.
    """
    monkeypatch.setattr(
        jarenv,
        "properties",
        lambda _java: {
            "java.version": "17.0.19",
            "user.language": "en",
            "user.country": "US",
            "user.language.format": "de",
            "user.country.format": "DE",
        },
    )
    monkeypatch.setattr(diff.jarenv, "java_17", lambda: diff.jarenv.JAR)
    with pytest.raises(diff.WrongLocaleError, match="de-DE"):
        diff.environment()


def test_the_format_locale_falls_back_to_the_base_pair_the_way_java_does():
    """`initDefault(Category)` reads the `.format` property and falls back to
    the base one, so a JVM with neither override is still `en-US` here."""
    assert jarenv.format_locale({"user.language": "en", "user.country": "US"}) == "en-US"
    assert jarenv.format_locale({"user.language.format": "fr", "user.country": "US"}) == "fr-US"
    assert jarenv.format_locale({}) == "?-?"


# --- the teeth -------------------------------------------------------------
#
# These need no jar. A comparison nothing has ever rejected is a comparison with
# no teeth, and the whole point of this harness is that it goes red.


@needs_jar
def test_one_moved_byte_in_a_real_run_turns_the_harness_red(report):
    """The teeth, end to end, over the bytes this run actually produced.

    The corruption is applied to the copy sitting in the run's own temporary
    directory, never to a committed fixture, and it is one byte: if the harness
    can be green over that, it is green over anything.
    """
    written = report.our_directory / f"{FIRST_GOLDEN}{diff.RESULTS_SUFFIX}"
    good = written.read_bytes()
    offset = good.index(b"W002")
    written.write_bytes(good[:offset] + b"X" + good[offset + 1 :])

    corrupted = dict(report.ours)
    corrupted[FIRST_GOLDEN] = written.read_bytes()
    divergences = diff.compare(corrupted, report.jars)

    assert [(one.name, one.kind) for one in divergences] == [(FIRST_GOLDEN, "bytes")]
    assert f"first difference at byte {offset}" in divergences[0].detail
    written.write_bytes(good)
