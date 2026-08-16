"""The committed jar corpus: provenance, integrity and what it says about skips.

Runs anywhere. The jar and its checkout are gitignored, so nothing here touches
either; `tests/test_jar_output_contract.py` asserts the byte-level shape of the
same files, and `tests/test_jar_differential.py` is the half that needs a jar.
"""

from __future__ import annotations

import json

import pytest

from gtfs_rt_validator.proto.decode import decode
from gtfs_rt_validator.proto.errors import DecodeError
from gtfs_rt_validator.proto.schema_2015 import SCHEMA
from jarcorpus import CORPUS, GOLDENS, INPUTS, MANIFEST, ROOT, digest, import_tool, input_bytes


def test_the_corpus_is_pinned_to_the_sha_the_rest_of_the_project_is():
    """A golden from a different jar than the manifest describes proves nothing."""
    pins = json.loads((ROOT / "upstream" / "pins.json").read_text(encoding="utf-8"))
    assert MANIFEST["pin"] == pins["gtfs_realtime_validator"]["commit"]
    assert MANIFEST["generated_by"] == "tools/gen_golden.py"


def test_every_committed_input_has_the_bytes_the_manifest_records():
    for entry in INPUTS:
        assert digest(input_bytes(entry["name"])) == entry["sha256"], entry["name"]


def test_every_committed_golden_has_the_bytes_the_manifest_records():
    for entry in GOLDENS:
        assert digest((CORPUS / entry["results"]).read_bytes()) == entry["results_sha256"]


def test_the_directory_holds_nothing_the_manifest_does_not_list():
    """A stale golden left behind by a renamed feed would never be compared."""
    listed = {"manifest.json"}
    for entry in INPUTS:
        listed.add(entry["name"])
        if entry["results"]:
            listed.add(entry["results"])
    assert {path.name for path in CORPUS.iterdir()} == listed


def test_the_static_feed_the_goldens_were_produced_against_is_committed():
    """Without it the goldens could be read but never regenerated.

    The build tree it was copied out of is gitignored, so committing the zip is
    what makes `tools/gen_golden.py` reproducible on a machine that has one.
    """
    zip_path = ROOT / "tests" / "fixtures" / "gtfs" / MANIFEST["gtfs"]
    assert digest(zip_path.read_bytes()) == MANIFEST["gtfs_sha256"]


def test_the_files_the_jar_skipped_have_no_golden_committed():
    """Upstream writes nothing at all for a file it skips, not an empty list."""
    for entry in INPUTS:
        if entry["skip"] is None:
            continue
        assert entry["results"] is None
        assert not (CORPUS / (entry["name"] + ".results.json")).exists()


def test_the_corpus_covers_both_reasons_upstream_writes_nothing():
    """One duplicate and two undecodable files, so neither path is untested."""
    reasons = [entry["skip"] for entry in INPUTS if entry["skip"]]
    assert sorted(reasons) == ["decode", "decode", "duplicate"]


def test_our_decoder_refuses_exactly_the_bytes_protobuf_java_refused():
    """`skip` separates the two reasons, which the output directory cannot.

    A `"duplicate"` file was never decoded by upstream at all, so it must still
    decode here; only a `"decode"` file is a `DecodeError`. Collapsing the two
    would let a real decoder regression hide behind the MD5 dedupe.
    """
    for entry in INPUTS:
        blob = input_bytes(entry["name"])
        if entry["skip"] == "decode":
            with pytest.raises(DecodeError):
                decode(blob, SCHEMA)
        else:
            assert decode(blob, SCHEMA).get("header") is not None, entry["name"]


def test_mtimes_are_stamped_consecutively_from_the_recorded_base():
    """Upstream sorts by mtime and uses it as the clock, so it is input, not metadata."""
    base = MANIFEST["mtime_base"]
    assert [entry["mtime"] for entry in INPUTS] == [base + i for i in range(len(INPUTS))]


def test_the_committed_inputs_are_what_the_generator_produces_today():
    """Hand-editing a generated corpus makes the differential lie about its inputs."""
    feeds = import_tool("goldenfeeds").FEEDS
    assert [feed.name for feed in feeds] == [entry["name"] for entry in INPUTS]
    for feed in feeds:
        assert input_bytes(feed.name) == feed.blob, feed.name
        assert record_skip(feed.name) == feed.skip, feed.name


def record_skip(name: str) -> str | None:
    return next(entry["skip"] for entry in INPUTS if entry["name"] == name)
