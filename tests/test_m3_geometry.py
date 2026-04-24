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
