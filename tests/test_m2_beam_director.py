"""Validation tests for M2 beam director per SPEC.md §3 M2.

One case pinned in SPEC §3: test_m2_transmission (exact arithmetic,
0.01% tolerance)."""

import pytest

from physics import m2_beam_director


def test_m2_transmission(canonical_inputs):
    """SPEC §3 M2 'test_m2_transmission'. Expected P_exit = 2550 W exactly."""
    inputs = {**canonical_inputs, "P0": 3000, "eta_opt": 0.85}
    result = m2_beam_director.compute(inputs)
    assert result["P_exit"] == pytest.approx(2550.0, rel=1e-4)


def test_m2_out_of_range_eta_opt_raises():
    """Input validation: eta_opt below SPEC §3 M2 valid range raises ValueError."""
    with pytest.raises(ValueError, match="eta_opt"):
        m2_beam_director.compute({"P0": 3000, "eta_opt": 0.30})
