"""Closing-physics regression guards for the v2.0 trajectory chain.

Two direct assertions on the most important property of the v2 chain:
the burn-through time must respect the closing geometry. Without these
tests, a future regression that froze the on-target flux at R_detect
(instead of integrating the time-varying I_aim_of_t through M8) would
slip past the existing test suite — the I_peak monotonicity test
covers the trajectory-series shape but not the integrated τ_BT outcome.

Coverage:

  1. ``test_tau_BT_grows_with_R_detect`` — same scenario at two
     detection ranges; the longer one must produce a longer τ_BT
     (more of the dwell is spent at far / weak conditions).
  2. ``test_trajectory_tau_BT_at_least_static_floor`` — closing
     engagement vs near-static engagement (very slow target) at the
     same R_detect; the closing one cannot be longer than the near-
     static one (closing only helps, never hurts).

These map to the user's intuition flagged 2026-04-26: "τ_BT at 1 km
should be more than at 500 m" and "closing should reduce τ_BT
because flux grows during dwell." Both are true for the v2 chain
when implemented correctly.

Tests use C_UAS_1500M with explicit overrides to keep the closing-
physics signal large enough that NaN / floor effects don't dominate.
"""
from __future__ import annotations

import pytest

from physics.orchestrator import run_full_chain
from tests.golden.scenarios import C_UAS_1500M


def _v2_inputs(**overrides) -> dict:
    """C_UAS_1500M minus the v1.x duplicate keys, plus per-test
    overrides. Ensures the orchestrator dispatches on the v2 path."""
    base = dict(C_UAS_1500M)
    base.pop("R", None)
    base.pop("v_perp", None)
    base.update(overrides)
    return base


def test_tau_BT_grows_with_R_detect():
    """Detection at a longer R must produce a longer trajectory τ_BT.

    Locked-in physics: each cell of a trajectory engagement re-runs
    M4-M7 at the current R(t). At larger R the atmosphere transmits
    less and the spot is wider, so I_avg(t=0) is lower. The Riemann-
    sum integral in M8 takes longer to reach the front-face failure
    temperature, even though I grows during the closing.

    A regression that froze I_aim at R_detect (or pulled it from a
    fixed reference range) would still produce a monotone-growing
    trajectory_I_peak series — but the integrated τ_BT response to
    R_detect would be wrong (or worse, flat).
    """
    inputs_short = _v2_inputs(R_detect=500, R_min=100)
    inputs_long = _v2_inputs(R_detect=2000, R_min=100)

    res_short = run_full_chain(inputs_short)
    res_long = run_full_chain(inputs_long)

    # Both must close (kill within window).
    assert res_short["failure_mode"] in ("decomposition", "melt", "vent"), (
        f"short-R scenario expected to close; got "
        f"failure_mode={res_short['failure_mode']!r}"
    )
    assert res_long["failure_mode"] in ("decomposition", "melt", "vent"), (
        f"long-R scenario expected to close; got "
        f"failure_mode={res_long['failure_mode']!r}"
    )

    tau_short = float(res_short["tau_BT"])
    tau_long = float(res_long["tau_BT"])

    # The headline property — τ_BT(2 km) > τ_BT(500 m) on the
    # canonical CFRP scenario. Tolerant assertion: longer R must
    # produce a strictly longer τ_BT, no equality, with a 5 % margin
    # to leave headroom for Riemann-step rounding.
    assert tau_long > tau_short * 1.05, (
        f"τ_BT must grow with R_detect on the canonical scenario "
        f"(closing-physics direction). Got τ_BT(500m)={tau_short:.3f} s, "
        f"τ_BT(2000m)={tau_long:.3f} s"
    )


def test_trajectory_tau_BT_at_least_static_floor():
    """Closing must not produce a longer τ_BT than the near-static
    case at the same R_detect.

    Two runs at the same R_detect but different v_tgt:
      * "closing" — v_tgt = 30 m/s (fast head-on closure)
      * "static-ish" — v_tgt = 0.1 m/s (target essentially stationary)

    Closing means the flux grows during the dwell; the integrated
    PDE reaches T_fail at least as fast as the static (or no faster
    than the static — if the engagement is so brief that the closing
    barely moves the target, the two are within Riemann-rounding of
    each other).

    A regression that mis-applied the closing geometry (e.g., using
    R_min instead of R_detect, or sign-flipping v_tgt in R(t)) would
    fail this assertion in the wrong direction.
    """
    inputs_closing = _v2_inputs(
        R_detect=1500, R_min=100, v_tgt=30,  # closing fast
    )
    inputs_static = _v2_inputs(
        R_detect=1500, R_min=100, v_tgt=0.1,  # essentially static
    )

    res_closing = run_full_chain(inputs_closing)
    res_static = run_full_chain(inputs_static)

    # Both must close; if either fails to kill within window the test
    # is degenerate (skip rather than false-fail).
    if res_closing["failure_mode"] not in ("decomposition", "melt", "vent"):
        pytest.skip(
            "closing scenario didn't kill — degenerate inputs for this guard"
        )
    if res_static["failure_mode"] not in ("decomposition", "melt", "vent"):
        pytest.skip(
            "static scenario didn't kill — degenerate inputs for this guard"
        )

    tau_closing = float(res_closing["tau_BT"])
    tau_static = float(res_static["tau_BT"])

    # Closing must be at most the static value, plus a Riemann-step
    # tolerance. We don't require closing to be strictly shorter
    # because for a fast burn-through (e.g. ~1 s) the target barely
    # moves during τ_BT and the two are close to identical. But
    # closing must never be more than ~5 % longer than static.
    assert tau_closing <= tau_static * 1.05, (
        f"closing τ_BT must not exceed static τ_BT by more than 5 % — "
        f"closing physics should help, never hurt. Got "
        f"closing τ_BT={tau_closing:.3f} s, "
        f"static τ_BT={tau_static:.3f} s"
    )


def test_v2_sweep_label_helper_recognises_v2_results():
    """Spot-check the _is_v2_sweep helper — locks in the rule that
    a sweep entry carrying ``engagement_geometry`` is a v2 result and
    triggers the "Detection range R_detect" axis label."""
    from ui.plots import _is_v2_sweep, _range_axis_title

    res_v2 = run_full_chain(_v2_inputs(R_detect=1000, R_min=100))
    sweep_v2 = [{**res_v2, "range": 1000.0}]
    assert _is_v2_sweep(sweep_v2) is True
    assert _range_axis_title(sweep_v2) == "Detection range R_detect (km)"

    # v1.x sweep — drop the v2 keys, run with R / v_perp instead.
    inputs_v1 = dict(C_UAS_1500M)
    for k in ("R_detect", "R_min", "engagement_geometry"):
        inputs_v1.pop(k, None)
    res_v1 = run_full_chain(inputs_v1)
    sweep_v1 = [{**res_v1, "range": 1500.0}]
    assert _is_v2_sweep(sweep_v1) is False
    assert _range_axis_title(sweep_v1) == "Slant range (km)"


def test_empty_or_none_sweep_falls_back_to_slant_label():
    """The default state on an empty / None sweep is the v1.x label
    so the "infeasible geometry" empty-frame still reads sensibly."""
    from ui.plots import _is_v2_sweep, _range_axis_title

    assert _is_v2_sweep(None) is False
    assert _is_v2_sweep([]) is False
    assert _range_axis_title(None) == "Slant range (km)"
    assert _range_axis_title([]) == "Slant range (km)"
