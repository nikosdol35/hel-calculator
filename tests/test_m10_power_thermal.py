"""Validation tests for M10 power & thermal budget per SPEC.md §3 M10.

Three cases pinned in SPEC §3 M10:
  - test_m10_steady_state          (0.1% tolerance — exact arithmetic)
  - test_m10_transient             (1% tolerance — 50 kW class ≈ 59 s)
  - test_m10_insufficient_cooling  (1% tolerance — structural)"""

import math

import pytest

from physics import m10_power_thermal as m10


def _inputs(**overrides):
    """Default M10 inputs — the SPEC §3 M10 'steady-state' validation
    set. Tests override the keys they care about."""
    base = {
        "P0": 3000.0,
        "eta_wallplug": 0.30,
        "Q_cool": 15000.0,
        "C_thermal": 200_000.0,
        "dT_max": 30.0,
        "t_engagement": 5.0,
    }
    base.update(overrides)
    return base


def test_m10_steady_state():
    """SPEC §3 M10 'test_m10_steady_state'. 3 kW class:
        P_in    = 3000/0.30 = 10_000 W
        Q_waste = 10_000 − 3000 = 7000 W
        7000 ≤ 15_000 → t_sustain = ∞, duty_cycle_limit = 1.0.
    Tolerance 0.1% (exact arithmetic)."""
    result = m10.compute(_inputs())
    # SPEC §3 M10 tolerance = 0.1 %: P_in = P0/η is one float divide.
    # Any drift is float64 noise. 1e-3 is defensive; tighter would only
    # catch the SPEC-stated expected value's rounding.
    assert result["P_in"] == pytest.approx(10_000.0, rel=1e-3)
    assert result["Q_waste"] == pytest.approx(7000.0, rel=1e-3)
    assert math.isinf(result["t_sustain"])
    assert result["engagement_viable"] is True
    # rel = 1e-12: duty_cycle_limit = 1.0 is a literal constant in the
    # steady-state branch; machine precision catches any accidental
    # multiplication or clamp change.
    assert result["duty_cycle_limit"] == pytest.approx(1.0, rel=1e-12)
    # rel = 1e-12: engagements_per_hour = 3600/t_eng when duty=1 is
    # one exact float divide — machine precision is correct.
    assert result["engagements_per_hour"] == pytest.approx(720.0, rel=1e-12)


def test_m10_transient():
    """SPEC §3 M10 'test_m10_transient'. 50 kW class, same cooling:
        P_in    = 50_000/0.30 = 166_666.7 W
        Q_waste = 116_666.7 W
        t_sustain = 200_000·30 / (116_666.7 − 15_000) = 59.02 s
    Tolerance 1%. Verifies the tool correctly flags ~1 min of sustained
    fire for the SPEC-default cooling configuration."""
    result = m10.compute(_inputs(P0=50_000.0))
    # SPEC §3 M10 tolerance = 1 %: transient arithmetic (P_in, Q_waste
    # and t_sustain = C·dT/(Q_waste-Q_cool)) is closed form; 1 % budgets
    # the 5-sig-fig rounding of the SPEC reference numbers.
    assert result["P_in"] == pytest.approx(166_667.0, rel=0.01)
    assert result["Q_waste"] == pytest.approx(116_667.0, rel=0.01)
    assert result["t_sustain"] == pytest.approx(59.0, rel=0.01)
    assert result["engagement_viable"] is True
    # Hand-check duty cycle:
    #   recovery = 200_000·30 / 15_000 = 400 s
    #   duty = 59.02 / (59.02 + 400) = 0.1286
    # rel = 2 %: duty is a ratio of two quantities each at 1 %, so the
    # propagated worst-case budget is ~2 %.
    assert result["duty_cycle_limit"] == pytest.approx(0.1286, rel=0.02)
    # 3600 · 0.1286 / 5 ≈ 92.6 engagements/hr — same 2 % budget.
    assert result["engagements_per_hour"] == pytest.approx(92.6, rel=0.02)


def test_m10_insufficient_cooling():
    """SPEC §3 M10 'test_m10_insufficient_cooling'. 100 kW draw with
    a 5 kW cooler and 20 K headroom:
        P_in      = 333_333 W
        Q_waste   = 233_333 W
        t_sustain = 100_000·20 / (233_333 − 5000) = 8.76 s
    Required engagement 30 s → not viable. Tolerance 1%."""
    result = m10.compute(_inputs(
        P0=100_000.0, Q_cool=5000.0,
        C_thermal=100_000.0, dT_max=20.0, t_engagement=30.0,
    ))
    # SPEC §3 M10 tolerance = 1 %: pure closed-form arithmetic at an
    # edge-case cooling shortfall; 1 % absorbs SPEC rounding only.
    assert result["t_sustain"] == pytest.approx(8.76, rel=0.01)
    assert result["t_sustain"] < 30.0
    assert result["engagement_viable"] is False


def test_m10_flags_not_viable_when_insufficient():
    """When cooling is insufficient, the not-viable branch must add a
    user-readable flag (CLAUDE §4.5 + §9.4: user sees WHY, not just a
    False boolean)."""
    result = m10.compute(_inputs(
        P0=100_000.0, Q_cool=5000.0,
        C_thermal=100_000.0, dT_max=20.0, t_engagement=30.0,
    ))
    flags = " | ".join(result["assumptions_flagged"])
    assert "not viable" in flags


def test_m10_flags_lumped_mass_always():
    """CLAUDE §4.5 always-on: the lumped-mass / constant-Q_waste
    modeling assumption must be disclosed every call so the user
    knows what simplification is in play."""
    result = m10.compute(_inputs())
    flags = " | ".join(result["assumptions_flagged"])
    assert "lumped-mass" in flags
    assert "SPEC §3 M10" in flags


def test_m10_zero_cooling_single_shot():
    """Q_cool=0 is allowed (uncooled passive system) but forces
    duty_cycle_limit=0 and a single-shot flag — the recovery-time
    denominator would be infinite."""
    result = m10.compute(_inputs(P0=50_000.0, Q_cool=0.0))
    assert result["duty_cycle_limit"] == 0.0
    assert result["engagements_per_hour"] == 0.0
    # t_sustain still computable since Q_waste − Q_cool = Q_waste > 0:
    assert math.isfinite(result["t_sustain"])
    flags = " | ".join(result["assumptions_flagged"])
    assert "single-shot" in flags


def test_m10_boundary_q_waste_equals_q_cool():
    """At the exact steady/transient boundary (Q_waste = Q_cool) the
    steady-state branch must be taken — t_sustain is infinite, not a
    0/0 NaN from the transient formula."""
    # Pick eta such that Q_waste = P0·(1−η)/η exactly equals Q_cool.
    # Q_waste = P0·(1−η)/η = Q_cool → η = P0/(P0+Q_cool).
    p0 = 7500.0
    q_cool = 17500.0
    eta = p0 / (p0 + q_cool)  # = 0.30
    result = m10.compute(_inputs(P0=p0, eta_wallplug=eta, Q_cool=q_cool))
    assert math.isinf(result["t_sustain"])
    assert result["engagement_viable"] is True
    assert result["duty_cycle_limit"] == 1.0


def test_m10_out_of_range_eta_raises():
    """Panel F sanity: η_wallplug ∈ [0.05, 0.50]."""
    with pytest.raises(ValueError, match="eta_wallplug"):
        m10.compute(_inputs(eta_wallplug=0.60))
    with pytest.raises(ValueError, match="eta_wallplug"):
        m10.compute(_inputs(eta_wallplug=0.01))


def test_m10_negative_q_cool_raises():
    """Q_cool must be ≥ 0 (negative cooling is unphysical)."""
    with pytest.raises(ValueError, match="Q_cool"):
        m10.compute(_inputs(Q_cool=-1000.0))


def test_m10_out_of_range_dT_max_raises():
    """Panel F sanity: dT_max ∈ [5, 80] K."""
    with pytest.raises(ValueError, match="dT_max"):
        m10.compute(_inputs(dT_max=2.0))
    with pytest.raises(ValueError, match="dT_max"):
        m10.compute(_inputs(dT_max=200.0))


def test_m10_zero_t_engagement_raises():
    """t_engagement must be > 0 (would divide engagements_per_hour)."""
    with pytest.raises(ValueError, match="t_engagement"):
        m10.compute(_inputs(t_engagement=0.0))


def test_m10_p_in_scales_with_p0_inverse_eta():
    """Structural: P_in = P0/η. Doubling P0 doubles P_in; halving η
    doubles P_in. Guards against the formula being wired with η in
    the numerator (a sign-flip bug)."""
    r1 = m10.compute(_inputs(P0=3000.0, eta_wallplug=0.30))
    r2 = m10.compute(_inputs(P0=6000.0, eta_wallplug=0.30))
    r3 = m10.compute(_inputs(P0=3000.0, eta_wallplug=0.15))
    # rel = 1e-12: structural identity (doubling P0 doubles P_in, halving
    # η doubles P_in). One float divide; machine precision catches any
    # sign-flip bug (η in numerator) or scaling regression.
    assert r2["P_in"] == pytest.approx(2.0 * r1["P_in"], rel=1e-12)
    assert r3["P_in"] == pytest.approx(2.0 * r1["P_in"], rel=1e-12)
