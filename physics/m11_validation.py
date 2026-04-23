"""M11 — Validation Self-Test Runner per SPEC §3 M11.

Runs the pytest suite via subprocess, parses the JUnit XML report, and
returns a structured dict keyed by the 29 SPEC §3 test IDs (M1.1 – M10.3).
M11 is uniquely NOT a `compute(inputs) -> dict` physics module; it is a
runner that `ui/app.py` calls from the "Run Validation Suite" button.

Design choices:
  * subprocess + --junitxml — no new dependencies, clean process isolation
    (a programmatic `pytest.main()` from inside pytest would recurse).
  * A fixed metadata table (`_TEST_METADATA`) maps each SPEC §3 validation
    case to its SPEC ID, human description, expected value, tolerance,
    and reference citation. Non-SPEC tests (input validation, always-on
    assumption-flag guards) still count toward `total_tests`/`passed`/
    `failed` but are not keyed into `results`.
  * The 29 SPEC §3 entries are:
      M1.1 M1.2  M2.1  M3.1
      M4.1 M4.2 M4.3
      M5.1 M5.2 M5.3 M5.4
      M6.1 M6.2 M6.3
      M7.1 M7.2 M7.3 M7.4
      M8.1 M8.2 M8.3 M8.4
      M9.1 M9.2 M9.3 M9.4
      M10.1 M10.2 M10.3

Callers in the test harness must pass `extra_pytest_args=["--ignore=
tests/test_m11_validation.py"]` to prevent the subprocess from re-entering
the M11 tests and forking a runaway chain.

References:
    SPEC §3 M11 for return-shape contract and test inventory.
    pytest --junitxml spec (pytest docs → "Creating JUnitXML format files").
"""

from __future__ import annotations

import datetime as _dt
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# SPEC §3 M11 test inventory.
#
# Key: (module_basename, test_name_with_params).
#   module_basename is the last dotted component of the pytest classname
#   (e.g. "test_m1_laser_source"), so we tolerate both "tests.test_m1_..."
#   and "test_m1_..." forms that pytest emits depending on rootdir/init.
#   test_name_with_params is the pytest node-name, including any
#   "[param]" suffix for parametrized tests.
# ---------------------------------------------------------------------------
_TEST_METADATA: dict[tuple[str, str], dict[str, str]] = {
    # --- M1 ---------------------------------------------------------------
    ("test_m1_laser_source", "test_m1_divergence"): {
        "test_id": "M1.1",
        "description": "θ_diff vs hand calculation",
        "expected": "13.547 µrad @ M²=1, λ=1.064 µm, D=0.10 m",
        "tolerance": "0.1%",
        "reference": "SPEC §3 M1 / Siegman 1986 Ch. 17",
    },
    ("test_m1_laser_source", "test_m1_rayleigh_range"): {
        "test_id": "M1.2",
        "description": "Rayleigh range zR",
        "expected": "≈7340 m @ D=0.10 m, λ=1.07 µm",
        "tolerance": "1%",
        "reference": "SPEC §3 M1",
    },
    # --- M2 ---------------------------------------------------------------
    ("test_m2_beam_director", "test_m2_transmission"): {
        "test_id": "M2.1",
        "description": "Transmission arithmetic (P = P0·η_opt)",
        "expected": "2550 W from 3000 W @ η_opt=0.85",
        "tolerance": "0.01%",
        "reference": "SPEC §3 M2",
    },
    # --- M3 ---------------------------------------------------------------
    ("test_m3_geometry", "test_m3_geometry"): {
        "test_id": "M3.1",
        "description": "Slant range + elevation from ground geometry",
        "expected": "R_slant ≈ 1513 m, elevation ≈ 7.6° @ R=1500, H_t=200",
        "tolerance": "0.1%",
        "reference": "SPEC §3 M3",
    },
    # --- M4 (two parametrized IDs + one standalone) -----------------------
    ("test_m4_atmosphere", "test_m4_aerosol_kruse[m4_clear]"): {
        "test_id": "M4.1",
        "description": "Kruse aerosol extinction at V=23 km, 1.07 µm",
        "expected": "α_aer_total ≈ 0.0716 1/km",
        "tolerance": "5%",
        "reference": "SPEC §3 M4 / Kruse 1962",
    },
    ("test_m4_atmosphere", "test_m4_aerosol_kruse[m4_hazy]"): {
        "test_id": "M4.2",
        "description": "Kim/Kruse aerosol extinction at V=5 km, 1.07 µm",
        "expected": "α_aer_total ≈ 0.366 1/km",
        "tolerance": "5%",
        "reference": "SPEC §3 M4 / Kim 2001",
    },
    ("test_m4_atmosphere", "test_m4_wavelength_interpolation"): {
        "test_id": "M4.3",
        "description": "Log-space linear wavelength interpolation of α_mol",
        "expected": "exact match to closed-form log-linear interpolate",
        "tolerance": "exact (float-tight)",
        "reference": "SPEC §3 M4",
    },
    # --- M5 ---------------------------------------------------------------
    ("test_m5_turbulence", "test_m5_r0_uniform_cn2"): {
        "test_id": "M5.1",
        "description": "r0_sph (spherical wave) for uniform Cn²",
        "expected": "≈5.1 cm @ Cn²=1e-14, λ=1.07 µm, L=5 km",
        "tolerance": "2%",
        "reference": "SPEC §3 M5 / Andrews & Phillips 2005 §6.5",
    },
    ("test_m5_turbulence", "test_m5_w_turb_5km"): {
        "test_id": "M5.2",
        "description": "Engineering-form w_turb at 5 km",
        "expected": "≈0.33 m @ r0=5.1 cm, L=5 km, λ=1.07 µm",
        "tolerance": "2%",
        "reference": "SPEC §3 M5",
    },
    ("test_m5_turbulence", "test_m5_spherical_vs_plane_ratio"): {
        "test_id": "M5.3",
        "description": "r0_sph/r0_plane ratio for uniform Cn²",
        "expected": "3/8 → (3/8)^(-3/5) ≈ 1.676",
        "tolerance": "0.1% (structural)",
        "reference": "SPEC §3 M5",
    },
    ("test_m5_turbulence", "test_m5_r0_at_1500m"): {
        "test_id": "M5.4",
        "description": "r0_sph at near-field 1.5 km",
        "expected": "closed-form check @ L=1500 m",
        "tolerance": "2%",
        "reference": "SPEC §3 M5",
    },
    # --- M6 ---------------------------------------------------------------
    ("test_m6_blooming", "test_m6_dimensional"): {
        "test_id": "M6.1",
        "description": "N_D dimensional / unit-consistency check",
        "expected": "N_D finite and positive for canonical inputs",
        "tolerance": "structural",
        "reference": "SPEC §3 M6 / Gebhardt 1990",
    },
    ("test_m6_blooming", "test_m6_moderate_blooming"): {
        "test_id": "M6.2",
        "description": "Moderate blooming @ 10 kW canonical",
        "expected": "S_TB in the [0.1, 0.9] moderate regime",
        "tolerance": "±30%",
        "reference": "SPEC §3 M6 / Smith 1977",
    },
    ("test_m6_blooming", "test_m6_small_power_limit"): {
        "test_id": "M6.3",
        "description": "Low-power limit → S_TB → 1, w_bloom → 0",
        "expected": "asymptotic to no-blooming limit",
        "tolerance": "structural",
        "reference": "SPEC §3 M6",
    },
    # --- M7 ---------------------------------------------------------------
    ("test_m7_spot_pib", "test_m7_pure_diffraction_5km"): {
        "test_id": "M7.1",
        "description": "Pure diffraction (no turb, no jit, no bloom) @ 5 km",
        "expected": "w_total ≈ w_diff to <1% @ canonical inputs",
        "tolerance": "2%",
        "reference": "SPEC §3 M7",
    },
    ("test_m7_spot_pib", "test_m7_diff_plus_turb_5km"): {
        "test_id": "M7.2",
        "description": "Diffraction + turbulence @ 5 km",
        "expected": "w_total from quadrature of w_diff, w_turb",
        "tolerance": "2%",
        "reference": "SPEC §3 M7",
    },
    ("test_m7_spot_pib", "test_m7_typical_c_uas_1500m"): {
        "test_id": "M7.3",
        "description": "C-UAS near-field case at 1.5 km",
        "expected": "w_total, PIB match hand-check for 3 kW canonical",
        "tolerance": "2%",
        "reference": "SPEC §3 M7",
    },
    ("test_m7_spot_pib", "test_m7_convention_consistency"): {
        "test_id": "M7.4",
        "description": "w / σ_spot / PIB convention consistency",
        "expected": "PIB = 1 − exp(−2·R²/w²) uses 1/e² radius (structural)",
        "tolerance": "exact (structural)",
        "reference": "SPEC §3 M7 / CLAUDE §7.1",
    },
    # --- M8 ---------------------------------------------------------------
    ("test_m8_burnthrough", "test_m8_aluminum_standard"): {
        "test_id": "M8.1",
        "description": "Anodized Al burn-through at 2 MW/m²",
        "expected": "tau_BT ≈ 6 s, failure_mode='melt', T_peak≈933 K",
        "tolerance": "25%",
        "reference": "SPEC §3 M8",
    },
    ("test_m8_burnthrough", "test_m8_cfrp_thin"): {
        "test_id": "M8.2",
        "description": "Thin CFRP decomposition at 500 kW/m²",
        "expected": "tau_BT < 2 s, failure_mode='decomposition'",
        "tolerance": "structural",
        "reference": "SPEC §3 M8",
    },
    ("test_m8_burnthrough", "test_m8_polycarbonate_nir"): {
        "test_id": "M8.3",
        "description": "Polycarbonate NIR transparency vs CFRP",
        "expected": "PC tau_BT ≥ 5× CFRP tau_BT (A_λ gap)",
        "tolerance": "structural comparison",
        "reference": "SPEC §3 M8",
    },
    ("test_m8_burnthrough", "test_m8_stability_criterion"): {
        "test_id": "M8.4",
        "description": "Explicit-FD numerical stability across material set",
        "expected": "T bounded, no NaN/inf for every material in table",
        "tolerance": "structural",
        "reference": "SPEC §3 M8",
    },
    # --- M9 ---------------------------------------------------------------
    ("test_m9_nohd", "test_m9_retinal_band_baseline"): {
        "test_id": "M9.1",
        "description": "Band A retinal NOHD baseline @ 1.07 µm, t_exp=0.25 s",
        "expected": "MPE≈25.5 W/m², NOHD_tophat≈223 m, NOHD_gausspeak≈315 m",
        "tolerance": "2%",
        "reference": "SPEC §3 M9 / ANSI Z136.1-2014",
    },
    ("test_m9_nohd", "test_m9_eyesafer_band"): {
        "test_id": "M9.2",
        "description": "Band B eye-safer NOHD @ 1.55 µm, t_exp=0.25 s",
        "expected": "MPE≈15839 W/m², NOHD_tophat≈7.97 m (formula value)",
        "tolerance": "5%",
        "reference": "SPEC §3 M9 / ANSI Z136.1-2014",
    },
    ("test_m9_nohd", "test_m9_ratio_sqrt2"): {
        "test_id": "M9.3",
        "description": "NOHD_gausspeak / NOHD_tophat = √2 (pre-aperture)",
        "expected": "exact √2 on the pre-aperture raw term",
        "tolerance": "0.1% (structural, float-tight on pre-aperture form)",
        "reference": "SPEC §3 M9 / CLAUDE §7.1",
    },
    ("test_m9_nohd", "test_m9_chronic_viewing"): {
        "test_id": "M9.4",
        "description": "Band A chronic MPE saturation for t_exp > 10 s",
        "expected": "MPE = 1.0e-3 W/cm² = 10 W/m² plateau",
        "tolerance": "2%",
        "reference": "SPEC §3 M9 / ANSI Z136.1-2014",
    },
    # --- M10 --------------------------------------------------------------
    ("test_m10_power_thermal", "test_m10_steady_state"): {
        "test_id": "M10.1",
        "description": "Steady-state 3 kW class: Q_waste ≤ Q_cool",
        "expected": "t_sustain=∞, duty_cycle=1.0, engagements/hr=720",
        "tolerance": "0.1% (exact arithmetic)",
        "reference": "SPEC §3 M10",
    },
    ("test_m10_power_thermal", "test_m10_transient"): {
        "test_id": "M10.2",
        "description": "Transient 50 kW class: Q_waste > Q_cool",
        "expected": "t_sustain ≈ 59 s, duty_cycle ≈ 0.1286",
        "tolerance": "1%",
        "reference": "SPEC §3 M10",
    },
    ("test_m10_power_thermal", "test_m10_insufficient_cooling"): {
        "test_id": "M10.3",
        "description": "100 kW w/ 5 kW cooler: engagement_viable=False",
        "expected": "t_sustain ≈ 8.76 s < 30 s required → not viable",
        "tolerance": "1%",
        "reference": "SPEC §3 M10",
    },
}


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------
def run_validation_suite(
    tests_dir: str = "tests/",
    extra_pytest_args: list[str] | None = None,
) -> dict:
    """Invoke pytest on tests_dir and return a SPEC §3 M11 report dict.

    Args:
        tests_dir: path (relative to project root) to the test directory.
        extra_pytest_args: additional args appended to the pytest command.
            Tests that call this function MUST pass
            ``["--ignore=tests/test_m11_validation.py"]`` to prevent the
            child pytest process from re-entering M11 and forking a
            runaway chain of pytest processes.

    Returns:
        dict with keys `timestamp`, `total_tests`, `passed`, `failed`,
        `duration_seconds`, `results` per SPEC §3 M11.
    """
    start_utc = _dt.datetime.now(_dt.timezone.utc)
    project_root = _project_root()

    with tempfile.TemporaryDirectory() as tmpdir:
        report_xml = Path(tmpdir) / "report.xml"
        cmd = [
            sys.executable, "-m", "pytest",
            tests_dir,
            f"--junitxml={report_xml}",
            "-q",
        ]
        if extra_pytest_args:
            cmd.extend(extra_pytest_args)

        # Run pytest; we do NOT raise on non-zero exit — a failing test
        # is a normal outcome that we want to surface through the report,
        # not propagate as a CalledProcessError.
        subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
        )

        if not report_xml.exists():
            # pytest crashed before writing the XML (e.g., collection error).
            # Return an empty-but-well-formed report so the UI can surface it.
            return {
                "timestamp": start_utc.isoformat(),
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "duration_seconds": 0.0,
                "results": {},
            }

        return _parse_junit_xml(report_xml, start_utc=start_utc)


# ---------------------------------------------------------------------------
# Internals.
# ---------------------------------------------------------------------------
def _project_root() -> Path:
    """Repo root = parent of the `physics/` directory."""
    return Path(__file__).resolve().parent.parent


def _parse_junit_xml(xml_path: Path, start_utc: _dt.datetime) -> dict:
    """Parse pytest's JUnit XML into the SPEC §3 M11 report shape."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Pytest emits a top-level <testsuites> wrapping a single <testsuite>,
    # or (less commonly) a bare <testsuite>. Handle both.
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        return {
            "timestamp": start_utc.isoformat(),
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "duration_seconds": 0.0,
            "results": {},
        }

    total = int(suite.attrib.get("tests", 0))
    failures = int(suite.attrib.get("failures", 0))
    errors = int(suite.attrib.get("errors", 0))
    skipped = int(suite.attrib.get("skipped", 0))
    duration = float(suite.attrib.get("time", 0.0))

    failed = failures + errors
    passed = total - failed - skipped

    results: dict[str, dict] = {}

    for case in suite.findall("testcase"):
        classname = case.attrib.get("classname", "")
        name = case.attrib.get("name", "")
        module_basename = classname.rsplit(".", 1)[-1] if classname else ""

        meta = _TEST_METADATA.get((module_basename, name))
        if meta is None:
            # Non-SPEC test (input validation, always-on flag guard, etc.).
            # It counts toward total/passed/failed but is not keyed in results.
            continue

        failure_el = case.find("failure")
        error_el = case.find("error")
        is_fail = failure_el is not None or error_el is not None

        if is_fail:
            failed_el = failure_el if failure_el is not None else error_el
            error_message = (failed_el.attrib.get("message")
                             or (failed_el.text or "").strip()
                             or "test failed")
        else:
            error_message = ""

        results[meta["test_id"]] = {
            "status": "FAIL" if is_fail else "PASS",
            "expected": meta["expected"],
            "actual": "(see test body)" if not is_fail else "deviated from expected",
            "tolerance": meta["tolerance"],
            "reference": meta["reference"],
            "description": meta["description"],
            "error_message": error_message,
        }

    return {
        "timestamp": start_utc.isoformat(),
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "duration_seconds": duration,
        "results": results,
    }
