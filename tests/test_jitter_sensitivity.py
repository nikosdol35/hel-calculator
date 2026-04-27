"""Tests for the jitter-sensitivity sweep behind Plot N.

PR: feature/plot-n-jitter-sensitivity (2026-04-27).
v3.2 update: log σ_jit axis (1 µrad → 500 mrad, 25 cells) covering
the full operational envelope.

Plot N shows τ_BT scaling vs σ_jit at fixed kinematics. The sweep
deliberately uses two simplifications to hit the <1 ms compute
budget:
  1. Lumped-mass τ_BT instead of M8 PDE (~5 % off PDE-accurate).
  2. Skip M6 blooming (w_bloom = 0, S_TB = 1.0) per cell.

Both are documented in the module docstring + the plot caption. The
user's "you are here" star uses the chain's PDE-accurate τ_BT, so
the headline metric and the star agree exactly.

Coverage:
  - Dataclass shape + linear-spaced axis (v3)
  - Low-σ_jit regime: τ_BT roughly constant (jitter contribution
    negligible vs diffraction)
  - High-σ_jit regime: τ_BT monotone non-decreasing
  - No-kill at extreme σ_jit (spot too wide → I_avg < threshold)
  - Kill-threshold detection: returns the σ_jit at the boundary
    between feasible and infeasible (whichever of dwell-crossover
    or no-kill kicks in first)
  - Star coordinates use chain values, not approximation
  - v1.x inputs rejected with KeyError
  - Wall-clock budget guard (<1 s on local even for n_points=25)
  - Regression test for the v2 cache-helper bug: integration path
    (chain → curve) must yield feasible cells for the canonical
    scenario (would have caught the all-no-kill bug shipped in v2).
"""
from __future__ import annotations

import math
import time

import pytest

from physics.jitter_sensitivity import (
    JitterSensitivityCurve,
    _LUMPED_TO_PDE_RATIO,
    compute_jitter_sensitivity,
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
    """Run the chain and return the merged-result dict the
    Engagement-tab renderer would pass to compute_jitter_sensitivity."""
    inputs = _v2_inputs(**overrides)
    result = run_full_chain(inputs)
    return {**inputs, **result}


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------
def test_returns_curve_dataclass():
    """compute_jitter_sensitivity returns a JitterSensitivityCurve
    with axes of length n_points and the no-kill mask aligned."""
    curve = compute_jitter_sensitivity(_merged_result(), n_points=25)
    assert isinstance(curve, JitterSensitivityCurve)
    assert len(curve.sigma_jit_axis_urad) == 25
    assert len(curve.tau_BT_axis_s) == 25
    assert len(curve.no_kill_mask) == 25


def test_axis_log_spaced():
    """σ_jit axis is log-spaced from 1 µrad to 500 mrad (v3.2)."""
    curve = compute_jitter_sensitivity(_merged_result(), n_points=25)
    axis = curve.sigma_jit_axis_urad
    assert axis[0] == pytest.approx(1.0, rel=1e-3)
    assert axis[-1] == pytest.approx(5.0e5, rel=1e-3)
    # Log spacing: ratio between adjacent points is constant.
    ratio_first = axis[1] / axis[0]
    ratio_last = axis[-1] / axis[-2]
    assert ratio_first == pytest.approx(ratio_last, rel=1e-6)


def test_runs_well_under_one_second():
    """Wall-clock budget guard. 15 cells of closed-form arithmetic
    should finish in milliseconds; even at 25 cells it should be
    well under 1 s on local hardware. This is THE key test —
    busts if someone reintroduces M6 / M8 to the sweep loop."""
    t0 = time.monotonic()
    compute_jitter_sensitivity(_merged_result(), n_points=25)
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0, (
        f"sweep took {elapsed*1000:.0f} ms — should be <1 s. Did "
        f"someone reintroduce M6 or M8 PDE per cell?"
    )


# ---------------------------------------------------------------------------
# Regime checks — flat at low σ_jit, climbing at high σ_jit, no-kill at extreme
# ---------------------------------------------------------------------------
def test_low_sigma_regime_nearly_flat():
    """In the low-σ_jit regime (σ_jit · R ≪ w_diff), the jitter
    contribution to w_total is negligible and τ_BT is essentially
    flat. The two cells deepest in the flat regime should be
    within ~5 % of each other.

    With v3.2's log axis (1 µrad → 500 mrad, 25 cells), cell 0
    sits at σ = 1 µrad and cell 1 at σ ≈ 1.7 µrad — both well
    below the canonical knee (~17 µrad)."""
    curve = compute_jitter_sensitivity(_merged_result(), n_points=25)
    early = [curve.tau_BT_axis_s[i] for i in range(2)]   # cells 0 + 1
    assert all(not math.isnan(t) for t in early)
    mean = sum(early) / len(early)
    variation = abs(early[1] - early[0])
    assert variation / mean < 0.05, (
        f"low-σ_jit regime should be nearly flat; got {early}"
    )


def test_finite_cells_monotone_non_decreasing():
    """As σ_jit grows, τ_BT_lumped grows (PIB shrinks → I_avg
    shrinks → τ_BT grows). Ignore no-kill cells (NaN)."""
    curve = compute_jitter_sensitivity(_merged_result(), n_points=25)
    finite_pairs = [
        (curve.tau_BT_axis_s[i - 1], curve.tau_BT_axis_s[i])
        for i in range(1, len(curve.tau_BT_axis_s))
        if not math.isnan(curve.tau_BT_axis_s[i - 1])
        and not math.isnan(curve.tau_BT_axis_s[i])
    ]
    for prev, curr in finite_pairs:
        assert curr >= prev - 1e-9, (
            f"τ_BT should be monotone non-decreasing in σ_jit; "
            f"got {prev:.3f} → {curr:.3f}"
        )


def test_extreme_sigma_jit_is_no_kill():
    """At σ_jit = 500 mrad (the v3.2 upper bound), the spot-wander
    envelope is 2 · 0.5 · 1500 = 1500 m. PIB collapses to ~0;
    surface flux is well below the no-kill threshold."""
    curve = compute_jitter_sensitivity(_merged_result(), n_points=25)
    assert curve.no_kill_mask[-1] is True
    assert math.isnan(curve.tau_BT_axis_s[-1])


def test_no_kill_threshold_set_when_no_kill_engaged():
    """no_kill_threshold_urad is the smallest σ_jit at which the
    cell is in the no-kill region. For the canonical 3 kW scenario
    it kicks in around ~180 µrad — within the 1 µrad → 500 mrad
    range."""
    curve = compute_jitter_sensitivity(_merged_result(), n_points=25)
    assert curve.no_kill_threshold_urad is not None
    assert 50.0 < curve.no_kill_threshold_urad < 1.0e4


# ---------------------------------------------------------------------------
# Kill-threshold detection
# ---------------------------------------------------------------------------
def test_kill_threshold_set_when_curve_crosses_dwell():
    """For the canonical scenario, τ_BT eventually exceeds dwell.
    kill_threshold_urad must be a finite value in the climbing
    portion of the curve."""
    curve = compute_jitter_sensitivity(_merged_result(), n_points=25)
    assert curve.kill_threshold_urad is not None
    assert curve.kill_threshold_urad > curve.sigma_jit_axis_urad[0]
    assert curve.kill_threshold_urad <= curve.sigma_jit_axis_urad[-1]


def test_kill_threshold_at_or_before_no_kill_threshold():
    """The kill threshold marks the boundary between feasible and
    infeasible. It can never be ABOVE the no-kill threshold (which
    is itself a hard infeasibility line)."""
    curve = compute_jitter_sensitivity(_merged_result(), n_points=25)
    if (curve.kill_threshold_urad is not None
            and curve.no_kill_threshold_urad is not None):
        assert (
            curve.kill_threshold_urad <= curve.no_kill_threshold_urad + 1e-6
        )


# ---------------------------------------------------------------------------
# Star coordinates use chain values, not the approximation
# ---------------------------------------------------------------------------
def test_star_uses_chain_tau_BT_not_approximation():
    """The 'you are here' coordinate carries the chain's PDE-
    accurate τ_BT — not the lumped-mass approximation. The
    headline metric on the page (also the chain's tau_BT) and the
    star value agree exactly so the user reads consistent numbers."""
    merged = _merged_result()
    chain_tau_BT = float(merged["tau_BT"])
    curve = compute_jitter_sensitivity(merged)
    assert curve.current_tau_BT_s == pytest.approx(chain_tau_BT, rel=1e-9)


def test_star_sigma_jit_in_microrad():
    """current_sigma_jit_urad converts the input σ_jit (in radians)
    to µrad. Default canonical scenario uses σ_jit = 10 µrad."""
    curve = compute_jitter_sensitivity(_merged_result())
    assert curve.current_sigma_jit_urad == pytest.approx(10.0, rel=1e-6)


def test_lumped_correction_factor_locked_at_0_83():
    """The empirical PDE/lumped correction was measured during the
    closing-physics review. Bumping it without re-measuring would
    silently shift the entire curve by a fixed factor."""
    assert _LUMPED_TO_PDE_RATIO == 0.83


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
def test_v1_inputs_rejected():
    """The plot is v2-only (we use available_dwell from the v2
    trajectory chain). Missing engagement_geometry → KeyError."""
    inputs = dict(C_UAS_1500M)
    for key in ("R_detect", "R_min", "engagement_geometry"):
        inputs.pop(key, None)
    result = run_full_chain(inputs)
    merged = {**inputs, **result}
    with pytest.raises(KeyError, match="engagement_geometry"):
        compute_jitter_sensitivity(merged)


def test_missing_material_does_not_crash():
    """Missing material → E_fail can't be computed → all cells are
    marked no-kill and the function returns a curve, not raises."""
    merged = _merged_result()
    # Force material lookup to miss.
    merged["material"] = "definitely_not_a_real_material"
    curve = compute_jitter_sensitivity(merged)
    # All cells should be no-kill.
    assert all(curve.no_kill_mask)
    assert all(math.isnan(t) for t in curve.tau_BT_axis_s)


# ---------------------------------------------------------------------------
# Regression test for the v2 → v3 cache-helper bug
# ---------------------------------------------------------------------------
def test_canonical_scenario_yields_feasible_cells():
    """Regression test for the v2 → v3 cache-helper bug.

    The chain produces a real merged result with a valid τ_BT.
    compute_jitter_sensitivity on that result must NOT mark every
    cell as no-kill, and the star's current_tau_BT_s must come from
    the chain (not zero).

    The shipped v2 plot was failing both checks because the
    rendering pipeline (_render_jitter_sensitivity →
    _frozen_inputs_for_envelope → _cached_jitter_sensitivity) was
    stripping the chain outputs (by_module, tau_BT, available_dwell)
    from the dict before passing it to this function. With those
    stripped, every cell saw P_exit = 0 → I_avg = 0 → no-kill, and
    the star landed at y = 0.

    The v3 fix bypasses the cache entirely and passes the merged
    result dict directly. This test verifies the integration path
    end-to-end.
    """
    inputs = _v2_inputs()
    result = run_full_chain(inputs)
    merged = {**inputs, **result}
    curve = compute_jitter_sensitivity(merged)
    assert any(not n for n in curve.no_kill_mask), (
        "All-no-kill curve for canonical scenario — chain outputs "
        "may not be reaching the curve module."
    )
    assert curve.current_tau_BT_s > 0, (
        "Star τ_BT is zero — chain's tau_BT not propagated."
    )
    # Star τ_BT must equal the chain's tau_BT exactly.
    assert curve.current_tau_BT_s == pytest.approx(
        float(merged["tau_BT"]), rel=1e-9,
    )
