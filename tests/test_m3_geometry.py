"""Validation tests for M3 engagement geometry per SPEC.md §3 M3.

One case pinned in SPEC §3: test_m3_geometry (plain geometry, 0.1%
tolerance)."""

import pytest

from physics import m3_geometry


def test_m3_geometry(canonical_inputs):
    """SPEC §3 M3 'test_m3_geometry'. Expected R_h≈4996.1 m, elev≈0.0396 rad."""
    inputs = {
        **canonical_inputs,
        "H_e": 2, "R": 5000, "H_t": 200, "v_tgt": 20, "v_perp": 3,
    }
    result = m3_geometry.compute(inputs)
    # SPEC §3 M3 tolerance = 0.1 %: R_h and elevation_angle come from
    # exact Pythagoras + arctan2. Tighter than 1e-3 would start tripping
    # on the 4-sig-fig rounding of the SPEC reference values themselves.
    assert result["R_h"] == pytest.approx(4996.1, rel=1e-3)
    assert result["elevation_angle"] == pytest.approx(0.0396, rel=1e-3)


def test_m3_flags_dwell_heuristic(canonical_inputs):
    """SPEC §3 M3 always flags the SPEC §10.5 dwell heuristic."""
    result = m3_geometry.compute(canonical_inputs)
    assert any("dwell" in flag and "§10.5" in flag
               for flag in result["assumptions_flagged"])


def test_m3_infeasible_geometry_raises(canonical_inputs):
    """R < |H_t - H_e| violates SPEC §3 M3 'R ≥ |ΔH|' precondition."""
    inputs = {**canonical_inputs, "H_e": 0, "R": 100, "H_t": 1000}
    with pytest.raises(ValueError, match="geometry infeasible"):
        m3_geometry.compute(inputs)


# ---------------------------------------------------------------------------
# SPEC v2.0 §3 M3 — tracker-supported trajectory dwell. PR 3 of
# docs/tracker_dwell_plan_2026-04-25.md.
# ---------------------------------------------------------------------------

def test_m3_v2_head_on_canonical(canonical_inputs):
    """SPEC v2.0 §3 M3: head-on closure at R_detect=5000, R_min=100,
    v_tgt=20 → t_dwell = (5000-100)/20 = 245 s. R_h, elevation as v1."""
    inputs = {
        **canonical_inputs,
        "H_e": 2, "H_t": 200, "v_tgt": 20,
        "R_detect": 5000, "R_min": 100,
        "engagement_geometry": "head_on",
    }
    # Strip v1 keys so v2.0 path is selected unambiguously.
    inputs.pop("R", None)
    inputs.pop("v_perp", None)
    result = m3_geometry.compute(inputs)
    assert result["available_dwell"] == pytest.approx(245.0, rel=1e-12)
    assert result["R_at_dwell_end"] == 100.0
    # R_h, elevation_angle still computed at the initial detection range
    # — same closed forms as v1.x.
    assert result["R_slant"] == 5000.0
    assert result["R_h"] == pytest.approx(4996.1, rel=1e-3)
    assert result["elevation_angle"] == pytest.approx(0.0396, rel=1e-3)


def test_m3_v2_lateral_canonical(canonical_inputs):
    """SPEC v2.0 §3 M3: lateral pass at R_detect=5000, R_min=100,
    v_tgt=20 → t_dwell = sqrt(5000² - 100²)/20 ≈ 249.95 s."""
    import math
    inputs = {
        **canonical_inputs,
        "H_e": 2, "H_t": 200, "v_tgt": 20,
        "R_detect": 5000, "R_min": 100,
        "engagement_geometry": "lateral",
    }
    inputs.pop("R", None)
    inputs.pop("v_perp", None)
    result = m3_geometry.compute(inputs)
    expected = math.sqrt(5000.0**2 - 100.0**2) / 20.0
    assert result["available_dwell"] == pytest.approx(expected, rel=1e-12)
    assert result["R_at_dwell_end"] == 100.0


def test_m3_v2_flags_tracker_supported(canonical_inputs):
    """v2.0 mode must NOT carry the v1 §10.5 deferred flag; it carries
    the tracker-supported flag instead."""
    inputs = {
        **canonical_inputs,
        "H_e": 2, "H_t": 200, "v_tgt": 20,
        "R_detect": 1500, "R_min": 100,
        "engagement_geometry": "head_on",
    }
    inputs.pop("R", None); inputs.pop("v_perp", None)
    result = m3_geometry.compute(inputs)
    flags = result["assumptions_flagged"]
    assert any("tracker-supported" in f for f in flags), (
        f"missing tracker-supported flag in {flags}"
    )
    assert not any("§10.5" in f for f in flags), (
        f"v2.0 mode should not carry §10.5 deferred flag: {flags}"
    )


def test_m3_v2_R_detect_below_R_min_rejected(canonical_inputs):
    """v2.0 validator rejects R_detect < R_min."""
    inputs = {
        **canonical_inputs,
        "H_e": 2, "H_t": 50, "v_tgt": 10,
        "R_detect": 50, "R_min": 100,
        "engagement_geometry": "head_on",
    }
    inputs.pop("R", None); inputs.pop("v_perp", None)
    with pytest.raises(ValueError, match="R_detect"):
        m3_geometry.compute(inputs)


def test_m3_v2_stationary_target(canonical_inputs):
    """Stationary target (v_tgt < 0.1 m/s) → dwell clamps to 60 s
    and R_at_dwell_end equals R_detect (no closure)."""
    inputs = {
        **canonical_inputs,
        "H_e": 2, "H_t": 50, "v_tgt": 0.0,
        "R_detect": 500, "R_min": 100,
        "engagement_geometry": "head_on",
    }
    inputs.pop("R", None); inputs.pop("v_perp", None)
    result = m3_geometry.compute(inputs)
    assert result["available_dwell"] == 60.0
    assert result["R_at_dwell_end"] == 500.0


def test_m3_v2_unknown_geometry_rejected(canonical_inputs):
    """v2.0 validator rejects unknown engagement_geometry."""
    inputs = {
        **canonical_inputs,
        "H_e": 2, "H_t": 50, "v_tgt": 10,
        "R_detect": 500, "R_min": 100,
        "engagement_geometry": "diving",
    }
    inputs.pop("R", None); inputs.pop("v_perp", None)
    with pytest.raises(ValueError, match="engagement_geometry"):
        m3_geometry.compute(inputs)


def test_m3_v1_path_carries_R_at_dwell_end_for_compat(canonical_inputs):
    """v1.x backward-compat path emits R_at_dwell_end = R_slant so
    every consumer of the v2.0 output schema works regardless of which
    M3 mode produced the result."""
    result = m3_geometry.compute(canonical_inputs)
    assert "R_at_dwell_end" in result
    assert result["R_at_dwell_end"] == result["R_slant"]


def test_m3_v2_default_R_min_when_omitted(canonical_inputs):
    """v2.0 contract supplies R_min=100 m default when the caller omits
    it, per plan §14 default."""
    inputs = {
        **canonical_inputs,
        "H_e": 2, "H_t": 50, "v_tgt": 20,
        "R_detect": 1500,
        "engagement_geometry": "head_on",
    }
    inputs.pop("R", None); inputs.pop("v_perp", None)
    inputs.pop("R_min", None)
    result = m3_geometry.compute(inputs)
    # t_dwell = (1500 - 100) / 20 = 70 s implies R_min = 100 was used.
    assert result["available_dwell"] == pytest.approx(70.0, rel=1e-12)
    assert result["R_at_dwell_end"] == 100.0
