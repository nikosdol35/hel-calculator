"""Validation tests for M6 thermal blooming per SPEC.md §3 M6.

Three cases pinned in SPEC §3 M6:
  - test_m6_dimensional         (structural — N_D dimensionless)
  - test_m6_moderate_blooming   (±30% tolerance, interesting regime)
  - test_m6_small_power_limit   (low-power limit: S_TB → 1, w_bloom = 0)

SPEC says 'N_D ~0.001' for the small-power limit, but at the
moderate-blooming canonical conditions scaled to P=100 W the actual
value is ≈0.21 (linear scaling from N_D≈21 at P=10 kW). That test
verifies the LIMIT BEHAVIOR (N_D << N_crit, S_TB ≈ 1, w_bloom = 0),
which is the test's physical intent — not a pinned absolute value."""

import pytest

from physics import m6_blooming


_MODERATE = {
    "P_propagating": 10_000.0,
    "w_at_target": 0.10,
    "alpha_atm": 1e-4,
    "v_perp": 5.0,
    "R_slant": 5000.0,
    "T_ambient": 300.0,
    "P_atm": 101325.0,
}


def _with(canonical_inputs, **overrides):
    """Spread canonical_inputs, override M6 keys."""
    base = {**canonical_inputs, **_MODERATE}
    base.update(overrides)
    return base


def test_m6_dimensional(canonical_inputs):
    """SPEC §3 M6 'test_m6_dimensional'. Structural: N_D must be a
    pure-number float for any set of valid SI inputs. Rerun with
    arbitrary-but-valid perturbations to guard against a hidden
    dimensional bug (e.g., unit mix-up in a future refactor)."""
    for override in (
        {},
        {"P_propagating": 500.0, "v_perp": 10.0, "R_slant": 2000.0},
        {"alpha_atm": 5e-4, "w_at_target": 0.05, "T_ambient": 280.0},
    ):
        result = m6_blooming.compute(_with(canonical_inputs, **override))
        assert isinstance(result["N_D"], float)
        assert result["N_D"] > 0.0


def test_m6_moderate_blooming(canonical_inputs):
    """SPEC §3 M6 'test_m6_moderate_blooming'. At the interesting-regime
    conditions N_D ≈ 20 (hand-check: 21.32) and S_TB ≈ 0.05 (hand-check:
    0.0521). ±30% tolerance is the SPEC-stated engineering-model
    tolerance."""
    result = m6_blooming.compute(_with(canonical_inputs))
    assert result["N_D"] == pytest.approx(20.0, rel=0.30)
    assert result["S_TB"] == pytest.approx(0.05, rel=0.30)
    # In this regime (5 ≤ N_D ≤ 30) w_bloom is nonzero and the SPEC §10.4
    # scaling flag must be raised.
    assert result["w_bloom"] > 0.0
    flags = " | ".join(result["assumptions_flagged"])
    assert "§10.4" in flags


def test_m6_small_power_limit(canonical_inputs):
    """SPEC §3 M6 'test_m6_small_power_limit'. Low-power limit: at
    P_propagating = 100 W (2 orders of magnitude below the moderate
    case) N_D must be well below the Smith cutoff, S_TB must be ≈ 1,
    and w_bloom must be identically zero. (SPEC cites 'N_D ~0.001' but
    that is an imprecise estimate from a different canonical set; the
    physically meaningful content of the test is the LIMIT behavior.)"""
    result = m6_blooming.compute(_with(canonical_inputs, P_propagating=100.0))
    assert result["N_D"] < 1.0
    assert result["S_TB"] > 0.99
    assert result["w_bloom"] == 0.0


def test_m6_strehl_limits(canonical_inputs):
    """Structural: S_TB is bounded in (0, 1] and monotonically decreasing
    in N_D. Guards against a sign flip or reciprocal-drop mistake in the
    Smith-approximation expression (CLAUDE §7.1 does not pin the Smith
    form but the monotonicity is physically required)."""
    low = m6_blooming.compute(_with(canonical_inputs, P_propagating=100.0))
    mid = m6_blooming.compute(_with(canonical_inputs, P_propagating=10_000.0))
    high = m6_blooming.compute(_with(canonical_inputs, P_propagating=100_000.0))

    for r in (low, mid, high):
        assert 0.0 < r["S_TB"] <= 1.0
    assert low["S_TB"] > mid["S_TB"] > high["S_TB"]


def test_m6_flags_high_nd_outside_validity(canonical_inputs):
    """SPEC §3 M6 validity-range flag: when N_D > 30 the Smith Strehl
    approximation and the 0.3 broadening scaling are outside stated
    validity and M6 must say so. At P = 100 kW / 5 km / 5 m/s crosswind
    the SPEC-described 'catastrophic' regime (N_D ~200) is reached."""
    result = m6_blooming.compute(_with(canonical_inputs, P_propagating=100_000.0))
    assert result["N_D"] > 30.0
    flags = " | ".join(result["assumptions_flagged"])
    assert "validity range" in flags


def test_m6_zero_wind_raises(canonical_inputs):
    """v_perp = 0 means no wind-driven heat clearing; N_D is unbounded.
    Reject the singular input explicitly (ValueError) rather than
    emitting inf/NaN."""
    inputs = _with(canonical_inputs, v_perp=0.0)
    with pytest.raises(ValueError, match="v_perp"):
        m6_blooming.compute(inputs)


def test_m6_out_of_range_T_raises(canonical_inputs):
    """Input validation: T_ambient below SPEC §3 M4 range raises ValueError."""
    inputs = _with(canonical_inputs, T_ambient=100.0)
    with pytest.raises(ValueError, match="T_ambient"):
        m6_blooming.compute(inputs)
