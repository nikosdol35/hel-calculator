"""Tests for M8 with time-varying flux (SPEC v2.0 §3 M8).

PR 4 of `docs/tracker_dwell_plan_2026-04-25.md`. M8 now accepts
``I_aim`` as either a scalar (v1.x backward-compat) or a callable
``I_aim(t)`` returning the absorbed flux at engagement-time t.

Coverage:
  - constant-flux callable reproduces the v1.x scalar-flux result
    within tight tolerance (regression guard for the Riemann-sum
    refactor)
  - linearly ramping flux integrates correctly (energy balance vs
    closed-form integral)
  - ``t_dwell`` window stop produces ``failure_mode =
    "engagement_ended_at_R_min"`` when T_fail is not reached
  - ``R_of_t`` callable produces ``R_at_kill`` at the failure moment
  - PDE stability under time-varying BC (Fourier number unchanged)
"""
from __future__ import annotations

import pytest

from physics import m8_burnthrough


# ---------------------------------------------------------------------------
# Backward-compat: scalar I_aim still works
# ---------------------------------------------------------------------------

_BASE_INPUTS: dict = {
    "material": "CFRP",
    "thickness": 0.002,
    "wavelength": 1.07e-6,
    "backside_BC": "insulated",
    "v_tgt": 20.0,
    "T_ambient": 293.0,
    "A_lambda": 0.85,
}


def test_constant_callable_matches_scalar_flux():
    """A callable that returns the same value at every t must produce
    the same tau_BT as the scalar input. This is the regression guard
    for the v2.0 Riemann-sum refactor — it must reproduce the v1.x
    behaviour to within Riemann-sum rounding."""
    scalar_inputs = {**_BASE_INPUTS, "I_aim": 5.0e5}
    res_scalar = m8_burnthrough.compute(scalar_inputs)

    callable_inputs = {**_BASE_INPUTS, "I_aim": lambda t: 5.0e5}
    res_callable = m8_burnthrough.compute(callable_inputs)

    # Same kill mode, near-identical tau_BT.
    assert res_callable["failure_mode"] == res_scalar["failure_mode"]
    assert res_callable["tau_BT"] == pytest.approx(
        res_scalar["tau_BT"], rel=1e-6,
    )
    # E_delivered Riemann sum vs. closed-form: 1-2 ulp drift.
    assert res_callable["E_delivered"] == pytest.approx(
        res_scalar["E_delivered"], rel=1e-9,
    )


def test_scalar_path_omits_R_at_kill():
    """v1.x callers (no R_of_t supplied) get R_at_kill=None."""
    inputs = {**_BASE_INPUTS, "I_aim": 5.0e5}
    res = m8_burnthrough.compute(inputs)
    assert res["R_at_kill"] is None


# ---------------------------------------------------------------------------
# t_dwell window stop
# ---------------------------------------------------------------------------

def test_t_dwell_engagement_window_stop():
    """When t_dwell elapses without T_fail being reached, M8 reports
    failure_mode='engagement_ended_at_R_min' (SPEC v2.0)."""
    # Anodized Al with low flux can't melt within a 1-second window.
    inputs = {
        "I_aim": 1.0e5,
        "material": "anodized_Al",
        "thickness": 0.002,
        "wavelength": 1.07e-6,
        "backside_BC": "insulated",
        "v_tgt": 20.0,
        "T_ambient": 293.0,
        "A_lambda": 0.1,
        "t_dwell": 1.0,
    }
    res = m8_burnthrough.compute(inputs)
    assert res["failure_mode"] == "engagement_ended_at_R_min"
    # tau_BT should be at the dwell-end (within one PDE timestep).
    assert res["tau_BT"] == pytest.approx(1.0, rel=0.01)
    # No kill → R_at_kill is None even if R_of_t had been supplied.
    assert res["R_at_kill"] is None


def test_t_dwell_long_enough_kills():
    """When t_dwell exceeds tau_BT, the kill happens normally and
    tau_BT < t_dwell."""
    inputs = {
        **_BASE_INPUTS,
        "I_aim": 5.0e5,  # CFRP with this flux kills in <2s
        "t_dwell": 10.0,
    }
    res = m8_burnthrough.compute(inputs)
    assert res["failure_mode"] == "decomposition"
    assert res["tau_BT"] < 10.0


def test_t_dwell_negative_rejected():
    """t_dwell ≤ 0 is a contract error."""
    inputs = {**_BASE_INPUTS, "I_aim": 5.0e5, "t_dwell": -1.0}
    with pytest.raises(ValueError, match="t_dwell"):
        m8_burnthrough.compute(inputs)


# ---------------------------------------------------------------------------
# R_of_t and R_at_kill
# ---------------------------------------------------------------------------

def test_R_at_kill_evaluated_at_tau_BT():
    """R_of_t is called at tau_BT to fix R_at_kill (SPEC v2.0)."""
    # Linear closing trajectory: R(t) = 1000 - 100*t (head-on at 100 m/s).
    R_of_t = lambda t: 1000.0 - 100.0 * t  # noqa: E731
    inputs = {**_BASE_INPUTS, "I_aim": 5.0e5, "R_of_t": R_of_t}
    res = m8_burnthrough.compute(inputs)
    assert res["failure_mode"] == "decomposition"
    expected_R = R_of_t(res["tau_BT"])
    assert res["R_at_kill"] == pytest.approx(expected_R, rel=1e-9)


def test_R_at_kill_None_when_no_kill():
    """If the engagement ends without a kill (timeout or t_dwell), R_at_kill
    is None even if R_of_t was supplied — there is no kill range to
    report."""
    R_of_t = lambda t: 1000.0  # noqa: E731
    inputs = {
        "I_aim": 1.0e5,
        "material": "anodized_Al",
        "thickness": 0.002,
        "wavelength": 1.07e-6,
        "backside_BC": "insulated",
        "v_tgt": 20.0,
        "T_ambient": 293.0,
        "A_lambda": 0.1,
        "t_dwell": 1.0,
        "R_of_t": R_of_t,
    }
    res = m8_burnthrough.compute(inputs)
    assert res["failure_mode"] == "engagement_ended_at_R_min"
    assert res["R_at_kill"] is None


# ---------------------------------------------------------------------------
# Time-varying flux — energy balance
# ---------------------------------------------------------------------------

def test_ramping_flux_integral_balance():
    """A linearly-ramping I_aim(t) = a + b·t produces an absorbed
    energy E ≈ A_λ · ∫(a + b·t) dt = A_λ · (a·tau + b·tau²/2).
    The Riemann sum should match this within sub-percent at our
    PDE timestep."""
    a = 1.0e5  # W/m²
    b = 2.0e5  # W/m²/s — flux doubles over a 0.5 s engagement
    A_lambda = 0.85

    def I_aim_of_t(t):
        return a + b * t

    inputs = {
        **_BASE_INPUTS,
        "I_aim": I_aim_of_t,
        "t_dwell": 0.5,  # short window so the slab heats but doesn't fail
    }
    res = m8_burnthrough.compute(inputs)
    tau = res["tau_BT"]
    # Closed-form integral of A_λ * (a + b·t) from 0 to tau.
    expected_E = A_lambda * (a * tau + 0.5 * b * tau * tau)
    # The Riemann sum is a forward-Euler integral on the PDE Δt;
    # it has error ~Δt/tau ~ 1e-4 / 0.5 ~ 0.02%. Allow 1% to be safe.
    assert res["E_delivered"] == pytest.approx(expected_E, rel=0.01)


def test_zero_flux_no_kill():
    """I_aim_of_t(t) = 0 means no energy delivered — failure_mode
    must be the 'no kill' verdict and tau_BT runs to the window end."""
    inputs = {
        **_BASE_INPUTS,
        "I_aim": lambda t: 0.0,
        "t_dwell": 0.5,
    }
    res = m8_burnthrough.compute(inputs)
    assert res["failure_mode"] == "engagement_ended_at_R_min"
    assert res["E_delivered"] == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Assumption-flag content
# ---------------------------------------------------------------------------

def test_callable_flux_emits_v2_assumption_flag():
    """When I_aim is callable, M8 must add an explicit flag so the
    Diagnostics tab shows that the engagement used a time-varying
    flux model."""
    inputs = {**_BASE_INPUTS, "I_aim": lambda t: 5.0e5}
    res = m8_burnthrough.compute(inputs)
    assert any(
        "I_aim time-varying" in flag or "callable" in flag
        for flag in res["assumptions_flagged"]
    ), f"missing v2 callable-flux flag in {res['assumptions_flagged']}"


def test_scalar_flux_does_not_emit_v2_flag():
    """Scalar callers (v1.x) should not see the new v2 flag — keeps
    the Diagnostics tab clean for the legacy single-point model."""
    inputs = {**_BASE_INPUTS, "I_aim": 5.0e5}
    res = m8_burnthrough.compute(inputs)
    assert not any(
        "callable" in flag for flag in res["assumptions_flagged"]
    )
