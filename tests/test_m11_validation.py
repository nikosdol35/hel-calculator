"""Validation tests for M11 self-test runner per SPEC §3 M11.

M11 is a runner, not a physics module. These tests verify that the
runner (a) invokes pytest, (b) parses the JUnit XML correctly, and
(c) returns the SPEC §3 M11 report shape with all 29 SPEC-pinned
test IDs populated.

The runner is invoked once per module (via a module-scoped fixture)
with `--ignore=tests/test_m11_validation.py` to prevent the subprocess
pytest from re-entering this file and forking a runaway chain."""

import pytest

from physics import m11_validation


# --- Metadata-table tests (pure in-process; no subprocess) -------------------

def test_m11_metadata_has_29_spec_entries():
    """SPEC §3 M11 pins a total of 29 validation cases (M1.1 – M10.3).
    The metadata table must have exactly that many."""
    assert len(m11_validation._TEST_METADATA) == 29


def test_m11_metadata_covers_all_spec_ids():
    """Every SPEC §3 M11 test ID in {M1.1, M1.2, M2.1, M3.1, M4.1–3,
    M5.1–4, M6.1–3, M7.1–4, M8.1–4, M9.1–4, M10.1–3} must appear
    exactly once in the metadata table."""
    expected = {
        "M1.1", "M1.2",
        "M2.1",
        "M3.1",
        "M4.1", "M4.2", "M4.3",
        "M5.1", "M5.2", "M5.3", "M5.4",
        "M6.1", "M6.2", "M6.3",
        "M7.1", "M7.2", "M7.3", "M7.4",
        "M8.1", "M8.2", "M8.3", "M8.4",
        "M9.1", "M9.2", "M9.3", "M9.4",
        "M10.1", "M10.2", "M10.3",
    }
    actual = {meta["test_id"] for meta in m11_validation._TEST_METADATA.values()}
    assert actual == expected


def test_m11_metadata_required_fields():
    """Every metadata entry must carry the SPEC §3 M11 result-dict
    fields (test_id, description, expected, tolerance, reference) so
    the report is self-documenting — the user sees WHAT the test
    checks, WHAT value was expected, and WHERE the value comes from."""
    required = {"test_id", "description", "expected", "tolerance", "reference"}
    for key, meta in m11_validation._TEST_METADATA.items():
        missing = required - set(meta.keys())
        assert not missing, f"{key} missing fields: {missing}"


# --- Subprocess-runner tests (one pytest subprocess; shared via fixture) -----

@pytest.fixture(scope="module")
def suite_report():
    """Run the validation suite once per module. Ignoring this file
    prevents the child pytest from re-entering M11 tests (which would
    spawn yet another child, ad infinitum)."""
    return m11_validation.run_validation_suite(
        extra_pytest_args=["--ignore=tests/test_m11_validation.py"],
    )


def test_m11_report_has_spec_shape(suite_report):
    """SPEC §3 M11 return-shape contract: timestamp, total_tests, passed,
    failed, duration_seconds, results."""
    required = {
        "timestamp", "total_tests", "passed", "failed",
        "duration_seconds", "results",
    }
    assert required.issubset(suite_report.keys())
    assert isinstance(suite_report["total_tests"], int)
    assert isinstance(suite_report["passed"], int)
    assert isinstance(suite_report["failed"], int)
    assert isinstance(suite_report["duration_seconds"], float)
    assert isinstance(suite_report["results"], dict)


def test_m11_counts_are_consistent(suite_report):
    """passed + failed ≤ total_tests (skipped tests account for any
    shortfall). All three counts must be non-negative."""
    assert suite_report["total_tests"] >= 0
    assert suite_report["passed"] >= 0
    assert suite_report["failed"] >= 0
    assert (
        suite_report["passed"] + suite_report["failed"]
        <= suite_report["total_tests"]
    )


def test_m11_results_keyed_by_spec_ids(suite_report):
    """The `results` dict must be keyed by SPEC test IDs (M1.1, etc.),
    not by pytest node names. The subprocess run of the full suite
    should surface every one of the 29 SPEC IDs."""
    result_keys = set(suite_report["results"].keys())
    expected_spec_ids = {
        meta["test_id"]
        for meta in m11_validation._TEST_METADATA.values()
    }
    missing = expected_spec_ids - result_keys
    assert not missing, f"SPEC IDs missing from report: {sorted(missing)}"


def test_m11_results_entries_have_status_and_reference(suite_report):
    """Each result entry must carry status∈{PASS,FAIL}, expected,
    tolerance, reference, and error_message per the SPEC §3 M11
    interface. `description` is an M11 extension for UI rendering."""
    required = {
        "status", "expected", "tolerance", "reference", "error_message",
    }
    for test_id, entry in suite_report["results"].items():
        missing = required - set(entry.keys())
        assert not missing, f"{test_id} missing fields: {missing}"
        assert entry["status"] in ("PASS", "FAIL"), (
            f"{test_id} status={entry['status']!r}"
        )


def test_m11_all_spec_tests_pass_on_main(suite_report):
    """If M11 is reporting the suite as green, every SPEC §3 entry
    must be PASS. A FAIL here means a physics regression slipped in;
    the test name will appear in the failure output so the operator
    knows exactly which module to inspect."""
    failing = {
        tid: entry["error_message"]
        for tid, entry in suite_report["results"].items()
        if entry["status"] == "FAIL"
    }
    assert not failing, f"SPEC tests failing on main: {failing}"


def test_m11_duration_is_positive(suite_report):
    """pytest reports elapsed time per suite; must be > 0 after a
    real subprocess run."""
    assert suite_report["duration_seconds"] > 0.0


def test_m11_timestamp_is_iso8601(suite_report):
    """Timestamp must round-trip through datetime.fromisoformat (the
    SPEC §3 M11 interface calls for ISO 8601)."""
    import datetime as dt
    ts = suite_report["timestamp"]
    # Must not raise:
    dt.datetime.fromisoformat(ts)
