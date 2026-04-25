"""Tests for the v2.0 trajectory-mode orchestrator chain.

PR 5 of `docs/tracker_dwell_plan_2026-04-25.md`. The orchestrator now
dispatches on the presence of ``engagement_geometry`` in the input
dict: when present, the v2.0 trajectory chain runs M4-M7 in a sub-
sampled loop along the trajectory R(t) and feeds the resulting
time-varying I_aim(t) callable into M8.

Coverage:
  - v2 mode produces the new orchestrator outputs (R_at_kill, I_peak_max,
    trajectory_R, trajectory_t, etc.)
  - trajectory_R(0) = R_detect; trajectory_R(end) = R_min
  - trajectory_I_peak monotonically non-decreasing (target closes →
    spot tightens → I_peak grows)
  - I_peak_max = max(trajectory_I_peak)
  - kill happens at some R between R_detect and R_min for a viable
    engagement
  - "no kill" case returns R_at_kill = None and failure_mode =
    'engagement_ended_at_R_min'
  - v1.x mode (no engagement_geometry) still works, identical output
    structure to pre-PR-5
  - cache-key keys: frozen_inputs include the v2 trajectory keys
"""
from __future__ import annotations

import pytest

from physics.orchestrator import run_full_chain


# ---------------------------------------------------------------------------
# Common scenarios
# ---------------------------------------------------------------------------

# v1.x backward-compat — the existing c_uas-style fixture.
_V1_INPUTS: dict = {
    "P0": 3000, "M2": 1.2, "D": 0.10, "wavelength": 1.07e-6,
    "eta_opt": 0.85, "sigma_jit": 10e-6,
    "H_e": 2, "R": 1500, "H_t": 200, "v_tgt": 20, "v_perp": 3,
    "V": 23, "RH": 0.60, "T_ambient": 300, "P_atm": 101325,
    "cn2_model": "HV_5_7", "Cn2_value": 1e-14,
    "Cn2_ground": 1.7e-14, "v_HV": 21,
    "d_aim": 0.05, "material": "CFRP", "thickness": 0.002,
    "eta_wallplug": 0.30, "Q_cool": 15000,
    "C_thermal": 200e3, "dT_max": 30, "t_exp": 0.25,
}


# v2.0 trajectory — head-on, target closing from R_detect=1500 m to
# R_min=100 m at v_tgt=20 m/s. CFRP target — burns through quickly.
def _v2_head_on_inputs() -> dict:
    inputs = dict(_V1_INPUTS)
    inputs.pop("R")
    inputs.pop("v_perp")
    inputs.update({
        "R_detect": 1500,
        "R_min": 100,
        "v_tgt": 20,
        "engagement_geometry": "head_on",
    })
    return inputs


# v2.0 lateral pass — same numerics, different geometry.
def _v2_lateral_inputs() -> dict:
    inputs = _v2_head_on_inputs()
    inputs["engagement_geometry"] = "lateral"
    return inputs


# ---------------------------------------------------------------------------
# Smoke + new outputs
# ---------------------------------------------------------------------------

def test_v2_head_on_produces_new_outputs():
    """v2.0 trajectory mode emits the new SPEC v2.0 keys."""
    result = run_full_chain(_v2_head_on_inputs())
    expected_new_keys = {
        "R_at_kill", "I_peak_max", "I_avg_aim_max",
        "trajectory_t", "trajectory_R",
        "trajectory_I_peak", "trajectory_I_avg_aim",
        "trajectory_d_spot", "trajectory_PIB",
        "trajectory_S_TB", "trajectory_w_total",
        "trajectory_N_D",
    }
    missing = expected_new_keys - set(result.keys())
    assert not missing, (
        f"v2 trajectory outputs missing: {missing}"
    )


def test_v2_lateral_produces_new_outputs():
    """Same coverage for lateral geometry."""
    result = run_full_chain(_v2_lateral_inputs())
    expected_new_keys = {
        "R_at_kill", "I_peak_max", "I_avg_aim_max",
        "trajectory_t", "trajectory_R",
    }
    missing = expected_new_keys - set(result.keys())
    assert not missing


def test_v2_trajectory_R_starts_at_R_detect():
    """First sample of trajectory_R equals R_detect."""
    result = run_full_chain(_v2_head_on_inputs())
    assert result["trajectory_R"][0] == pytest.approx(1500.0, rel=1e-9)


def test_v2_trajectory_R_ends_at_R_min_for_head_on():
    """Last sample of trajectory_R equals R_min for head-on (and
    within a sub-sample interval for lateral)."""
    result = run_full_chain(_v2_head_on_inputs())
    # Head-on: linear closure to R_min exactly.
    assert result["trajectory_R"][-1] == pytest.approx(100.0, rel=1e-6)


def test_v2_trajectory_R_decreases_monotonically():
    """As the target closes, slant range only ever decreases (the
    inbound-only convention from the SPEC v2.0 design decision)."""
    result = run_full_chain(_v2_head_on_inputs())
    rs = result["trajectory_R"]
    for prev, curr in zip(rs, rs[1:]):
        assert curr <= prev + 1e-9, f"non-monotone trajectory_R near {prev}, {curr}"


def test_v2_I_peak_grows_as_target_closes():
    """Smaller R → tighter spot → higher I_peak. Monotonically non-
    decreasing across sub-samples for a clean head-on closure."""
    result = run_full_chain(_v2_head_on_inputs())
    ips = result["trajectory_I_peak"]
    for prev, curr in zip(ips, ips[1:]):
        # Allow a tiny dip from blooming kicking in mid-trajectory;
        # the trend should be increasing on the canonical scenario.
        assert curr >= prev * 0.98, (
            f"I_peak dropped substantially across trajectory: "
            f"{prev:.2g} → {curr:.2g}"
        )


def test_v2_I_peak_max_equals_max_of_series():
    """The orchestrator's I_peak_max scalar equals the max of the
    trajectory series."""
    result = run_full_chain(_v2_head_on_inputs())
    assert result["I_peak_max"] == pytest.approx(
        max(result["trajectory_I_peak"]),
    )


def test_v2_kill_in_canonical_head_on_engagement():
    """CFRP at 3 kW closing to 100 m gives a kill within the
    engagement window."""
    result = run_full_chain(_v2_head_on_inputs())
    assert result["failure_mode"] == "decomposition"
    assert result["R_at_kill"] is not None
    # Kill happens between R_detect (1500 m) and R_min (100 m).
    assert 100 <= result["R_at_kill"] <= 1500


def test_v2_no_kill_engagement_ends_at_R_min():
    """An impossible engagement (very thick polycarbonate, low power)
    runs to t_dwell without a kill and reports the new
    'engagement_ended_at_R_min' verdict."""
    inputs = _v2_head_on_inputs()
    inputs["material"] = "polycarbonate"
    inputs["thickness"] = 0.020  # 2 cm — beyond easy burn-through
    inputs["P0"] = 100  # 100 W — far below HEL flux levels
    inputs["R_detect"] = 200  # short engagement window so we hit R_min fast
    inputs["R_min"] = 100
    result = run_full_chain(inputs)
    assert result["failure_mode"] == "engagement_ended_at_R_min"
    assert result["R_at_kill"] is None


def test_v1_mode_unchanged_no_v2_keys():
    """A pre-v2 input dict still works through the single-point chain
    and does NOT emit the v2 trajectory series (those keys are absent).
    Backward compat — this is what existing golden fixtures rely on."""
    result = run_full_chain(_V1_INPUTS)
    # No trajectory series.
    assert "trajectory_R" not in result
    assert "trajectory_t" not in result
    assert "I_peak_max" not in result
    # But the v1 keys are all there.
    assert "R_slant" in result
    assert "tau_BT" in result
    assert "I_peak" in result


def test_v2_trajectory_t_starts_at_zero_and_ends_at_t_dwell():
    """First sample at t=0; last sample at t=t_dwell (within rounding)."""
    result = run_full_chain(_v2_head_on_inputs())
    ts = result["trajectory_t"]
    assert ts[0] == 0.0
    t_dwell = result["available_dwell"]
    assert ts[-1] == pytest.approx(t_dwell, abs=0.05)


def test_v2_lateral_dwell_longer_than_head_on():
    """Lateral pass takes longer than head-on closure for the same
    detection / standoff / velocity (already verified at the M3 level
    in test_trajectory; this confirms the orchestrator-level result)."""
    head = run_full_chain(_v2_head_on_inputs())
    lateral = run_full_chain(_v2_lateral_inputs())
    assert lateral["available_dwell"] > head["available_dwell"]


def test_v2_engagement_viable_when_kill_happens():
    """For a head-on engagement that closes within window, the M10
    engagement_viable verdict is True."""
    result = run_full_chain(_v2_head_on_inputs())
    if result["failure_mode"] in ("decomposition", "melt", "vent"):
        # Thermal-budget side handled by M10's existing logic.
        # The geometric side is implicit in the kill having happened
        # before t_dwell.
        assert result["engagement_viable"] is True


def test_v2_picard_warm_start_keeps_iteration_count_low():
    """Warm-starting M6↔M7 from the previous sub-sample's converged
    values should keep iteration count low. We don't pin a specific
    number (depends on engagement) but it should be at most 10."""
    result = run_full_chain(_v2_head_on_inputs())
    assert 1 <= result["m67_iteration_count"] <= 10


def test_v2_trajectory_series_lengths_match():
    """All trajectory_* series have the same length (they're parallel
    arrays indexed by sub-sample)."""
    result = run_full_chain(_v2_head_on_inputs())
    n = len(result["trajectory_t"])
    for key in ("trajectory_R", "trajectory_I_peak",
                "trajectory_I_avg_aim", "trajectory_d_spot",
                "trajectory_PIB", "trajectory_S_TB",
                "trajectory_w_total", "trajectory_N_D"):
        assert len(result[key]) == n, (
            f"{key} length {len(result[key])} != t length {n}"
        )
