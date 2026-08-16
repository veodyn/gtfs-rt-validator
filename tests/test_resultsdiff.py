"""The teeth of the comparison itself, over committed bytes and no jar.

`tools/resultsdiff.py` is the vocabulary both differentials compare with, and a
comparison nothing has ever rejected is a comparison with no teeth. Nothing here
needs a JDK, so these run on every machine: the corruption is always a copy in
memory or in `tmp_path`, never a committed fixture.

Three families, and the second and third are the ones an audit found missing:

- **bytes**: one moved byte, a truncation, and the negative control.
- **three states, not two**: a name absent from a mapping is not the same claim
  as a name present with `None`. `compare({}, {"x.pb": None})` used to report
  nothing at all, so a side that dropped every input the jar skipped compared
  clean against a side that kept them.
- **nothing is not agreement**: two empty mappings agree, and so do two
  zero-byte results files. Neither is evidence, and both used to exit 0.

Split out of `tests/test_compat_differential.py`, which keeps the checks that
need a real run.
"""

from __future__ import annotations

from jarcorpus import INPUTS, golden_bytes, import_tool

diff = import_tool("diff_compat_against_jar")
resultsdiff = import_tool("resultsdiff")

NAMES = [entry["name"] for entry in INPUTS]
FIRST_GOLDEN = "01-no-timestamps.pb"


def _has_golden(name: str) -> bool:
    return next(entry for entry in INPUTS if entry["name"] == name)["results"] is not None


def _both_sides() -> dict[str, bytes | None]:
    """The committed corpus as one side of a comparison, absences included."""
    return {name: golden_bytes(name) if _has_golden(name) else None for name in NAMES}


# --- bytes -----------------------------------------------------------------


def test_one_moved_byte_is_reported_with_its_offset():
    """The corruption is a copy in memory, never a committed fixture."""
    jars = _both_sides()
    ours = dict(jars)
    good = jars[FIRST_GOLDEN]
    offset = good.index(b'"errorId" : "W002"') + len('"errorId" : "')
    ours[FIRST_GOLDEN] = good[:offset] + b"X" + good[offset + 1 :]

    divergences = diff.compare(ours, jars)

    assert [one.name for one in divergences] == [FIRST_GOLDEN]
    assert divergences[0].kind == "bytes"
    assert f"first difference at byte {offset}" in divergences[0].detail
    assert "X002" in divergences[0].detail


def test_a_truncated_file_reports_where_the_bytes_ran_out():
    """Two files that agree until one ends are not equal, and the offset of the
    first difference does not exist, so the report says so instead."""
    good = golden_bytes(FIRST_GOLDEN)
    divergences = diff.compare({FIRST_GOLDEN: good[:-4]}, {FIRST_GOLDEN: good})
    assert divergences[0].kind == "bytes"
    assert f"identical for {len(good) - 4} bytes" in divergences[0].detail


def test_an_identical_pair_is_no_divergence():
    """The negative control, so the checks above are not passing on everything."""
    both = _both_sides()
    assert diff.compare(both, dict(both)) == []


# --- three states, not two -------------------------------------------------


def test_a_file_only_this_project_wrote_is_a_divergence():
    """The jar skipped it, so writing anything at all is a parity failure."""
    jars = {"07-empty.pb": None}
    divergences = diff.compare({"07-empty.pb": b"[ ]"}, jars)
    assert [(one.name, one.kind) for one in divergences] == [("07-empty.pb", "only-ours")]


def test_a_file_only_the_jar_wrote_is_a_divergence():
    """The mirror image, and the one a comparison that iterates our own output
    would miss entirely."""
    ours = {FIRST_GOLDEN: None}
    divergences = diff.compare(ours, {FIRST_GOLDEN: golden_bytes(FIRST_GOLDEN)})
    assert [(one.name, one.kind) for one in divergences] == [(FIRST_GOLDEN, "only-jar")]


def test_a_name_one_side_never_saw_is_a_divergence_rather_than_a_skip():
    """Skipping an awkward file is how a differential goes quietly green.

    The kinds name which side is short, and they are not the `only-*` kinds: a
    run that never had the input is a different failure from a run that had it
    and wrote nothing for it.
    """
    divergences = diff.compare({"a.pb": b"[ ]"}, {"b.pb": b"[ ]"})
    assert sorted((one.name, one.kind) for one in divergences) == [
        ("a.pb", "unseen-by-jar"),
        ("b.pb", "unseen-by-ours"),
    ]


def test_an_input_missing_from_one_side_is_not_the_same_as_one_it_skipped():
    """The case `.get()` on both sides collapses, and the reason for `UNSEEN`.

    `{"skipped.pb": None}` says a run saw the input and upstream's file loop
    wrote nothing for it. `{}` says the run never had the input. Reading both
    with `.get()` makes them equal, and a regression that dropped every skipped
    input from one side is then invisible.
    """
    divergences = diff.compare({}, {"skipped.pb": None})

    assert [(one.name, one.kind) for one in divergences] == [("skipped.pb", "unseen-by-ours")]
    assert "never saw it" in divergences[0].detail
    assert diff.compare({"skipped.pb": None}, {}) != []
    assert diff.compare({"skipped.pb": None}, {"skipped.pb": None}) == []


def test_a_side_that_dropped_every_skipped_input_goes_red():
    """The regression the case above stands for, at corpus scale."""
    jars = _both_sides()
    ours = {name: blob for name, blob in jars.items() if blob is not None}

    divergences = diff.compare(ours, jars)

    assert {one.kind for one in divergences} == {"unseen-by-ours"}
    assert sorted(one.name for one in divergences) == sorted(
        name for name in NAMES if not _has_golden(name)
    )


# --- nothing is not agreement ----------------------------------------------


def test_comparing_nothing_against_nothing_is_a_divergence():
    """Two empty mappings agree about every input either of them has, which is
    the state a harness reaches when its corpus moved, not a pass."""
    divergences = diff.compare({}, {})

    assert [one.kind for one in divergences] == ["vacuous"]
    assert "nothing was compared" in divergences[0].detail


def test_two_empty_results_files_are_not_agreement():
    """The jar's smallest results file is `[ ]`, so zero bytes on both sides is
    two runs that produced nothing, byte-identically."""
    divergences = diff.compare({"a.pb": b""}, {"a.pb": b""})

    assert [(one.name, one.kind) for one in divergences] == [("a.pb", "vacuous")]
    assert "0 bytes" in divergences[0].detail


def test_bytes_that_are_not_a_results_array_are_not_agreement():
    """Identical rubbish is still rubbish. A results file is a JSON array, and
    both sides writing the same non-array is a failure of both."""
    assert [one.kind for one in diff.compare({"a.pb": b"nope"}, {"a.pb": b"nope"})] == ["vacuous"]
    assert [one.kind for one in diff.compare({"a.pb": b"{}"}, {"a.pb": b"{}"})] == ["vacuous"]
    assert resultsdiff.not_results(b"[ ]") == ""
    assert diff.compare({"a.pb": b"[ ]"}, {"a.pb": b"[ ]"}) == []


def test_a_report_over_no_inputs_exits_nonzero():
    """`differential({})` builds one of these, and a `Report` with no
    divergences was green whether or not anything had been compared."""
    empty = diff.Report(ours={}, jars={}, divergences=[])

    assert empty.exit_code == 1
    assert "nothing was compared" in empty.render()


# --- the report ------------------------------------------------------------


def test_the_exit_code_is_the_verdict():
    """Non-zero on any difference, so the harness is usable as a command."""
    jars = {FIRST_GOLDEN: golden_bytes(FIRST_GOLDEN)}
    assert diff.Report(ours=dict(jars), jars=jars, divergences=[]).exit_code == 0
    red = diff.compare({FIRST_GOLDEN: b"[ ]"}, jars)
    assert diff.Report(ours={FIRST_GOLDEN: b"[ ]"}, jars=jars, divergences=red).exit_code == 1


def test_the_rendered_report_names_every_divergence():
    """A summary that counts divergences without naming them cannot be acted on."""
    jars = _both_sides()
    ours = {**jars, "04-combined-feed.pb": b"[ ]"}
    report = diff.Report(ours=ours, jars=jars, divergences=diff.compare(ours, jars))
    assert "04-combined-feed.pb" in report.render()
    assert "1 divergence" in report.render()


def test_the_rendered_report_says_how_far_the_jar_pin_was_checked():
    """A configured SHA printed alone reads as the identity of the artefact.

    `upstream/pins.json` says which commit a jar *should* come from; swapping in
    a jar built from another commit does not change it. So the evidence is
    printed with it, and the running jar's own digest beside that.
    """
    where = resultsdiff.Environment(
        "17.0.19", "en-US", diff.jarenv.JAR, "abc123", "configured", "f" * 64
    )

    assert "jar pin abc123 (configured)" in where.describe()
    assert "jar sha256 ffffffffffff" in where.describe()
    assert "FORMAT locale en-US" in where.describe()
