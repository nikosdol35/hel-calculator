"""End-to-end golden-output regression tests.

Per the Package 2 plan (validation/README.md Layer 2.4), four canonical
engagement scenarios are pinned at a per-key tolerance tight enough to
catch any silent numeric drift. The expected values live in JSON files
under `tests/golden/*.json`, one file per scenario.

Bootstrap / update procedure
----------------------------
On first run (or after an intentional SPEC-driven revision), the JSON
files must be regenerated. Run:

    GOLDEN_UPDATE=1 pytest tests/test_golden.py -v

This writes fresh JSON files based on the current orchestrator outputs;
review the diff in git and commit alongside the SPEC/code change that
motivated it. Subsequent runs (no envvar) compare against the committed
JSONs.

When the expected JSON is missing (never seeded), the test SKIPS with a
message telling the user to seed. CI stays green while the bootstrap is
pending.

Tolerances
----------
Per SPEC §3 per-module tolerances — the loosest being 5 % on M8 tau_BT
(numerical PDE) and 3 % on M6 N_D. We pin scalar floats at 1e-3 (0.1 %)
for closed-form outputs, and relax to 5 % for M8 keys that depend on the
PDE solver; `failure_mode` is a string, compared as exact match.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from physics import orchestrator
from tests.golden.scenarios import (
    INFEASIBLE,
    SCENARIOS,
)


GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE_MODE = os.environ.get("GOLDEN_UPDATE") == "1"

# Keys that depend on the explicit finite-difference PDE (M8). These
# inherit SPEC §3 M8 validation tolerance of 5 %.
_M8_KEYS = {"tau_BT", "T_surface_peak", "E_delivered"}

# Keys where a looser tolerance is appropriate (M6 N_D is 3 % per SPEC).
_M6_KEYS = {"N_D", "S_TB", "w_bloom"}

# Everything else — closed-form or simple arithmetic — pinned tight.
_DEFAULT_REL_TOL = 1e-3


def _golden_path(scenario_name: str) -> Path:
    return GOLDEN_DIR / f"{scenario_name}.json"


def _numeric_keys(result: dict) -> list[str]:
    """Return the sorted list of keys whose values are comparable floats.
    Skips: dict-valued keys (by_module), bool flags, str classifications,
    list-valued `assumptions_flagged`."""
    skip = {"by_module", "assumptions_flagged", "failure_mode",
            "laser_class", "m67_converged", "engagement_viable"}
    out = []
    for k, v in result.items():
        if k in skip:
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(k)
    return sorted(out)


def _serialize_for_json(result: dict) -> dict:
    """Produce a JSON-safe snapshot of the orchestrator result.

    - numeric keys: kept as floats
    - failure_mode, laser_class: kept as strings
    - m67_iteration_count, m67_converged: kept as int/bool
    - engagement_viable: kept as bool
    - by_module and assumptions_flagged: dropped (too noisy for regression;
      covered by dedicated tests)
    - SPEC v2.0 trajectory_* tuples: dropped (per-sample time series that
      bloat the JSON without adding regression value; the scalar
      trajectory summaries — R_at_kill, I_peak_max, I_avg_aim_max — are
      kept and pin the outcome)
    """
    snap: dict = {}
    for k, v in result.items():
        if k in ("by_module", "assumptions_flagged"):
            continue
        if k.startswith("trajectory_"):
            continue
        if isinstance(v, float):
            if math.isinf(v):
                snap[k] = "inf"
            elif math.isnan(v):
                snap[k] = "nan"
            else:
                snap[k] = v
        elif isinstance(v, (int, bool, str)):
            snap[k] = v
        else:
            snap[k] = str(v)
    return snap


def _rel_tol_for(key: str) -> float:
    if key in _M8_KEYS:
        return 0.05
    if key in _M6_KEYS:
        return 0.03
    return _DEFAULT_REL_TOL


@pytest.mark.parametrize("name,inputs", list(SCENARIOS.items()))
def test_golden_scenario(name: str, inputs: dict) -> None:
    """Full-chain orchestrator output must match the committed baseline
    to within per-key tolerance. Seed the baseline with GOLDEN_UPDATE=1."""
    result = orchestrator.run_full_chain(inputs)
    snap = _serialize_for_json(result)
    path = _golden_path(name)

    if UPDATE_MODE:
        GOLDEN_DIR.mkdir(exist_ok=True)
        with open(path, "w") as f:
            json.dump(snap, f, indent=2, sort_keys=True)
        pytest.skip(f"wrote {path.name} in update mode (GOLDEN_UPDATE=1)")

    if not path.exists():
        pytest.skip(
            f"golden baseline missing: {path.name}. Seed it with "
            f"`GOLDEN_UPDATE=1 pytest tests/test_golden.py` and commit."
        )

    with open(path) as f:
        expected = json.load(f)

    # Compare every numeric key at the appropriate tolerance.
    mismatches: list[str] = []
    for key in _numeric_keys(result):
        if key not in expected:
            mismatches.append(f"key {key!r} absent from committed golden")
            continue
        actual = result[key]
        exp_val = expected[key]
        if isinstance(exp_val, str):
            # "inf" / "nan" sentinel.
            if exp_val == "inf" and math.isinf(actual):
                continue
            if exp_val == "nan" and math.isnan(actual):
                continue
            mismatches.append(
                f"{key}: expected sentinel {exp_val!r}, got {actual!r}"
            )
            continue
        if not math.isfinite(actual):
            mismatches.append(
                f"{key}: got non-finite {actual!r}, expected {exp_val!r}"
            )
            continue
        rel = _rel_tol_for(key)
        if actual != pytest.approx(exp_val, rel=rel):
            mismatches.append(
                f"{key}: expected {exp_val:.6g}, got {actual:.6g} "
                f"(rel tol {rel:.0%})"
            )

    # Non-numeric exact-match keys.
    for key in ("failure_mode", "laser_class", "m67_converged",
                "engagement_viable"):
        if key in expected and key in result:
            if result[key] != expected[key]:
                mismatches.append(
                    f"{key}: expected {expected[key]!r}, got {result[key]!r}"
                )

    if mismatches:
        msg = (
            f"\nScenario {name!r}: {len(mismatches)} golden-output "
            "mismatch(es):\n  - " + "\n  - ".join(mismatches)
            + "\n\nIf this change is intentional, run "
            "GOLDEN_UPDATE=1 pytest tests/test_golden.py -v "
            "and commit the diff alongside the SPEC/code change."
        )
        pytest.fail(msg)


def test_infeasible_geometry_raises() -> None:
    """R < |H_t − H_e| must raise ValueError from M3 before any
    downstream module runs. No NaN, no silent fallback."""
    with pytest.raises(ValueError, match="geometry infeasible"):
        orchestrator.run_full_chain(INFEASIBLE)
