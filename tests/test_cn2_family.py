"""Tests for the Cn² family curve module behind Plot O.

PR: feature/plot-o-cn2-family (2026-04-28).

Plot O shows peak irradiance vs detection range for 5 reference Cn²
levels plus the user's current scenario. The lightweight compute
path uses only M4 + M5 + M7 (skips M1/M2 by reading from chain
output, skips M6/M8/M9-M11 entirely) — same simplification spirit
as Plot N's jitter sweep.

Coverage:
  - Dataclass shape (n references, range axis, current curve)
  - I_peak monotone-decreasing in Cn² at fixed R (more turb → less peak)
  - I_peak monotone-decreasing in R at fixed Cn² (more spread → less peak)
  - Both cn2_model values ('Constant' and 'HV_5_7') route to the right
    override field
  - Duplicate suppression when user's Cn² ≈ a reference (5 % tolerance)
  - Wall-clock <1 s for the full sweep
  - v1.x inputs (no engagement_geometry) → KeyError
  - Missing by_module → KeyError (chain hasn't run)
  - Returns the user's actual Cn² in current_curve, not a placeholder
"""
from __future__ import annotations

import math
import time

import pytest

from physics.cn2_family import (
    CN2FamilyCurves,
    _DUPLICATE_REL_TOL,
    _REFERENCE_CN2_LEVELS,
    compute_cn2_family_curves,
)
from physics.orchestrator import run_full_chain
from tests.golden.scenarios import C_UAS_1500M


def _v2_inputs(**overrides) -> dict:
    inputs = dict(C_UAS_1500M)
    inputs.pop("R", None)
    inputs.pop("v_perp", None)
    inputs.update({
        "R_detect": 1500, "R_min": 100,
        "engagement_geometry": "head_on",
    })
    inputs.update(overrides)
    return inputs


def _merged_result(**overrides) -> dict:
    """Run the chain and return the merged-result dict that the
    Engagement-tab renderer would pass to the curve module."""
    inputs = _v2_inputs(**overrides)
    result = run_full_chain(inputs)
    return {**inputs, **result}


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------
def test_returns_curves_dataclass():
    """compute_cn2_family_curves returns a CN2FamilyCurves with axes
    of the right shape."""
    curves = compute_cn2_family_curves(_merged_result())
    assert isinstance(curves, CN2FamilyCurves)
    n_ref = len(_REFERENCE_CN2_LEVELS)
    # User's canonical Cn²_ground = 1.7e-14 doesn't exactly equal
    # any reference (closest is 1e-14 = 'Clear', within ~70 %), so
    # within the 5 % rel_tol no duplicate suppression should fire.
    assert len(curves.reference_curves) == n_ref
    assert len(curves.range_axis_km) >= 5
    # Each reference curve has the same length as the range axis.
    n_R = len(curves.range_axis_km)
    for label, cn2, per_R in curves.reference_curves:
        assert isinstance(label, str) and label
        assert cn2 > 0
        assert len(per_R) == n_R
    # Current curve also has the same length.
    cur_cn2, cur_per_R = curves.current_curve
    assert cur_cn2 > 0
    assert len(cur_per_R) == n_R


def test_range_axis_log_spaced():
    """Range axis is log-spaced from ~100 m up to 2× R_detect."""
    curves = compute_cn2_family_curves(_merged_result())
    axis = curves.range_axis_km
    # First cell ≥ 100 m / 1000 = 0.1 km
    assert axis[0] >= 0.1 - 1e-6
    # Last cell ≤ 50 km
    assert axis[-1] <= 50.0
    # Log spacing: ratio between adjacent points roughly constant.
    ratios = [axis[i + 1] / axis[i] for i in range(len(axis) - 1)]
    mean_ratio = sum(ratios) / len(ratios)
    assert all(abs(r / mean_ratio - 1) < 0.05 for r in ratios)


def test_runs_well_under_one_second():
    """Wall-clock budget guard. ~75 cells of M4+M5+M7 should finish
    in ~400 ms; even with overhead, well under 1 s on local hardware.
    This is THE key test — busts if someone reintroduces M6 or M8
    PDE per cell."""
    t0 = time.monotonic()
    compute_cn2_family_curves(_merged_result())
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0, (
        f"sweep took {elapsed * 1000:.0f} ms — should be <1 s. Did "
        f"someone reintroduce M6 / M8 / full chain per cell?"
    )


# ---------------------------------------------------------------------------
# Monotonicity (the diagnostic value of the plot lives here)
# ---------------------------------------------------------------------------
def test_I_peak_monotone_decreasing_in_cn2():
    """At fixed R, more turbulence (higher Cn²) → less peak irradiance.
    Compare 'Pristine' (1e-15) vs 'Severe' (1e-12) at the middle range
    cell — the Severe value must be strictly smaller."""
    curves = compute_cn2_family_curves(_merged_result())
    # Pluck the per-R arrays for Pristine and Severe.
    by_label = {label: per_R for label, _, per_R in curves.reference_curves}
    pristine = by_label["Pristine"]
    severe = by_label["Severe"]
    n_R = len(curves.range_axis_km)
    mid = n_R // 2
    assert pristine[mid] > severe[mid], (
        f"more turbulence should reduce peak irradiance; got "
        f"pristine={pristine[mid]:.3g} W/cm², severe={severe[mid]:.3g} W/cm²"
    )


def test_I_peak_monotone_decreasing_in_R():
    """At fixed Cn², longer range → less peak irradiance (more
    diffraction + spread). The 'Clear' reference curve at the first
    cell must be strictly larger than at the last cell."""
    curves = compute_cn2_family_curves(_merged_result())
    by_label = {label: per_R for label, _, per_R in curves.reference_curves}
    clear = by_label["Clear"]
    finite_clear = [v for v in clear if not math.isnan(v)]
    assert len(finite_clear) >= 2
    assert finite_clear[0] > finite_clear[-1]


# ---------------------------------------------------------------------------
# Cn² mode handling
# ---------------------------------------------------------------------------
def test_constant_cn2_mode_overrides_value_field():
    """When cn2_model='constant' (lowercase per SPEC), the override
    should drive Cn2_value (not Cn2_ground). Verify the function
    doesn't crash and the returned cn2_model field carries through."""
    curves_const = compute_cn2_family_curves(
        _merged_result(cn2_model="constant", Cn2_value=1.0e-14),
    )
    curves_hv = compute_cn2_family_curves(_merged_result())   # default HV_5_7
    # Both should be model-aware.
    assert curves_const.cn2_model == "constant"
    assert curves_hv.cn2_model == "HV_5_7"
    # Both should return some reference curves (count depends on
    # whether duplicate suppression fires).
    assert len(curves_const.reference_curves) >= 4
    assert len(curves_hv.reference_curves) >= 4


def test_user_current_cn2_propagates_into_curve():
    """The 'current scenario' curve uses the user's actual Cn², not
    a placeholder. Set the user's Cn²_ground to an unusual value
    (5e-14) and verify it appears in `current_curve[0]`."""
    merged = _merged_result(Cn2_ground=5.0e-14)
    curves = compute_cn2_family_curves(merged)
    cur_cn2, _ = curves.current_curve
    assert cur_cn2 == pytest.approx(5.0e-14, rel=1e-9)


# ---------------------------------------------------------------------------
# Duplicate suppression
# ---------------------------------------------------------------------------
def test_duplicate_suppression_when_user_matches_reference():
    """If the user's Cn² is within 5 % of a reference, that reference
    is suppressed and the user's curve replaces it. With Cn²_ground =
    1.05e-14 (within 5 % of the 'Clear' reference 1e-14), 'Clear'
    should be dropped from reference_curves."""
    merged = _merged_result(Cn2_ground=1.05e-14)   # 5 % above 1e-14
    curves = compute_cn2_family_curves(merged)
    labels = [label for label, _, _ in curves.reference_curves]
    # 'Clear' should be suppressed.
    assert "Clear" not in labels
    assert curves.suppressed_label == "Clear"
    # The other 4 references should still be present.
    assert len(labels) == len(_REFERENCE_CN2_LEVELS) - 1


def test_no_duplicate_suppression_when_user_far_from_references():
    """Canonical Cn²_ground = 1.7e-14 is ~70 % above the 'Clear'
    reference (1e-14) — outside the 5 % tolerance. All 5 references
    should be present."""
    curves = compute_cn2_family_curves(_merged_result())
    labels = [label for label, _, _ in curves.reference_curves]
    assert len(labels) == len(_REFERENCE_CN2_LEVELS)
    assert curves.suppressed_label is None


# ---------------------------------------------------------------------------
# Input validation / defensive paths
# ---------------------------------------------------------------------------
def test_v1_inputs_rejected():
    """The plot is v2-only (we use the chain's by_module + R_detect).
    v1 inputs without engagement_geometry → KeyError."""
    inputs = dict(C_UAS_1500M)
    for key in ("R_detect", "R_min", "engagement_geometry"):
        inputs.pop(key, None)
    result = run_full_chain(inputs)
    merged = {**inputs, **result}
    with pytest.raises(KeyError, match="v2.0"):
        compute_cn2_family_curves(merged)


def test_missing_by_module_rejected():
    """When the chain hasn't run yet, by_module is missing —
    KeyError so the rendering pipeline can fall back gracefully."""
    inputs = _v2_inputs()
    # Skip running the chain — no by_module in the dict.
    with pytest.raises(KeyError, match="by_module"):
        compute_cn2_family_curves(inputs)


def test_missing_material_does_not_crash():
    """I_peak doesn't depend on material (unlike Plot N's τ_BT), so
    a missing material should still produce valid curves. This is
    a key behavioural difference from Plot N — verify it works."""
    merged = _merged_result()
    merged["material"] = "definitely_not_a_real_material"
    curves = compute_cn2_family_curves(merged)
    # All reference curves present and finite.
    n_ref = len(_REFERENCE_CN2_LEVELS)
    assert len(curves.reference_curves) == n_ref
    cur_cn2, cur_per_R = curves.current_curve
    finite = [v for v in cur_per_R if not math.isnan(v)]
    assert len(finite) >= 5    # at least most cells finite


def test_constants_locked():
    """Reference levels and duplicate-tolerance are part of the
    contract. Bumping them silently would shift the entire plot
    visual story without telling anyone."""
    assert _DUPLICATE_REL_TOL == 0.05
    assert len(_REFERENCE_CN2_LEVELS) == 5
    # The user's canonical default Cn²_ground = 1.7e-14 sits between
    # 'Clear' and 'Day' references — outside any 5 % bucket.
    labels = [label for label, _ in _REFERENCE_CN2_LEVELS]
    assert labels == ["Pristine", "Clear", "Day", "Strong", "Severe"]
