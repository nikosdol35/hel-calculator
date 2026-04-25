"""Chain coordinator — wires the 10 physics modules in dependency order.

Pure Python. No Streamlit imports, no UI side effects. Lives in
``physics/`` (not ``ui/``) so ``tests/`` can import it directly under
the ARCHITECTURE §2 import rules — the M6↔M7 fixed-point loop is
physics-critical and deserves dedicated unit-test coverage.

``ui/app.py`` wraps calls to ``run_full_chain(user_inputs)`` in an
``@st.cache_data`` helper (per ARCHITECTURE §5.3) on the "Run Analysis"
click handler, then renders the returned dict via ``ui/outputs.py`` +
``ui/plots.py``.

**Two modes, selected by presence of ``engagement_geometry`` in inputs:**

  - **v2.0 trajectory mode** (SPEC v2.0 §3 M3 / §4): the engagement
    follows a tracker-supported trajectory R(t) from R_detect down to
    R_min. The upstream chain (M4 atmosphere, M5 turbulence, M6↔M7
    fixed point) is sub-sampled at ~50 ms intervals; M8 receives a
    time-varying ``I_aim(t)`` callable interpolated from those samples
    plus a ``R_of_t`` callable for kill-range bookkeeping. Trajectory
    time-series outputs (``trajectory_R``, ``trajectory_t``,
    ``trajectory_I_peak`` etc.) feed the new Engagement-tab plots.
  - **v1.x single-point mode** (backward-compat): the chain runs once
    at R = R_slant. Preserved verbatim from v1.12 so existing callers
    (golden fixtures, the math-tab worked example, etc.) continue to
    work without modification through this PR.

Dependency graph for v1.x single-point mode (ARCH §5.1 / SPEC §4):

    M1 (laser source)
     ├─→ M9  (NOHD; safety branch, only needs M1)
     └─→ M2 (beam director)
          └─→ M3 (geometry)
               └─→ M4 (atmosphere)
                    └─→ M5 (turbulence)
                         └─→ M7 (spot + PIB) ←─┐
                              ←──── M6 (blooming) [fixed-point iterated]
                                   └─→ M8 (burn-through)
                                        └─→ M10 (power / thermal)

For v2.0 trajectory mode, M4-M7 sub-sample at every ``_DT_SUBSAMPLE_S``
along the trajectory. M6↔M7 Picard fixed-point uses warm-start from
the previous sub-sample's converged ``S_TB``/``w_bloom`` — typical
iteration count drops from 2-4 (cold) to 1-2 (warm). M8 then
integrates the heat PDE forward with the resulting time-varying flux
to engage closure or t_dwell.

The M6↔M7 loop (ARCH §5.1 step 4): seed ``S_TB=1``, ``w_bloom=0``
(or warm-start from previous sub-sample); compute M7's ``w_total``;
pass into M6; update ``S_TB`` and ``w_bloom``; re-run M7. Terminate
when ``|Δw_total| / w_total < 1%`` or at 10 iterations.

Inputs contract:
    ``user_inputs`` is a dict of SI-unit values covering every SPEC §5.1
    Panel A–F key. The canonical default set appears in
    ``tests/conftest.py`` under fixture ``canonical_inputs``. The UI
    layer (panels.py) is responsible for unit conversion (kW→W, µrad→
    rad, °C→K, etc.) before invoking this function — the orchestrator
    receives SI only.

Output contract:
    Flat-merged dict of every module's numeric outputs, plus:
      - ``assumptions_flagged``: union of all modules' flag lists,
        de-duplicated while preserving first-seen order (so Panel 4 of
        SPEC §5.2 can render a clean list).
      - ``by_module``: per-module output dicts keyed by ``"m1".."m10"``
        for callers that want namespaced access (outputs.py Panel 1
        uses this to pull M6 Strehl numbers alongside M7 spot numbers).
      - ``m67_iteration_count``: number of M6↔M7 iterations taken.
      - ``m67_converged``: bool, True if the loop terminated on the
        tolerance criterion rather than max_iter.

References:
    ARCHITECTURE.md §5.1 (data flow), §5.3 (caching strategy),
    §6.1 (caching wrapper in ui/app.py).
    SPEC.md §3 M6 "Iterative coupling with M7" and §4 (orchestration).
"""

from __future__ import annotations

import bisect
import math
from typing import Callable

from physics import (
    m1_laser_source,
    m2_beam_director,
    m3_geometry,
    m4_atmosphere,
    m5_turbulence,
    m6_blooming,
    m7_spot_pib,
    m8_burnthrough,
    m9_nohd,
    m10_power_thermal,
    m_trajectory,
)

#: Default fixed-point loop limits. Exposed as kwargs on
#: ``_iterate_m6_m7`` for tests that need tighter / looser bounds.
_DEFAULT_MAX_ITER = 10
_DEFAULT_TOL = 0.01  # 1 % relative change in w_total between passes

#: SPEC v2.0 §4 — sub-sample interval for the trajectory loop (s).
#: Most M4/M5/M6/M7 outputs change slowly with R(t); 50 ms resolution
#: gives ~80 sub-samples on a 4-second engagement, plenty for
#: smoothly-varying outputs and well within the M8 PDE timestep budget
#: (the PDE Δt is ~ms; sub-sampling every 50 ms + linear interpolation
#: between samples is sub-1 % accurate on the I_aim callable).
_DT_SUBSAMPLE_S = 0.050

#: Cap on number of trajectory sub-samples — prevents pathological
#: input combinations from producing a million-sample loop. Hits at
#: t_dwell = N * 0.05 s = 25 s under the default sub-sample interval.
_MAX_SUBSAMPLES = 500


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------
def run_full_chain(user_inputs: dict) -> dict:
    """Run M1–M10 in dependency order and return the merged result.

    See module docstring for the dependency graph and output contract.

    Args:
        user_inputs: dict of SI-unit values covering every SPEC §5.1
            Panel A–F key (see ``tests/conftest.py::canonical_inputs``
            for the default set).

    Returns:
        Flat-merged result dict per the module docstring.

    Raises:
        ValueError: propagated unchanged from the first module whose
            ``_validate_inputs`` rejects the user input. The UI layer's
            "Run Analysis" click handler catches this and renders the
            message next to the panel that fed the bad value.
    """
    out1 = m1_laser_source.compute(_inputs_for_m1(user_inputs))
    out9 = m9_nohd.compute(_inputs_for_m9(user_inputs, out1))
    out2 = m2_beam_director.compute(_inputs_for_m2(user_inputs))
    out3 = m3_geometry.compute(_inputs_for_m3(user_inputs))

    # SPEC v2.0 dispatch: trajectory mode if engagement_geometry is
    # given (M3 will have run the v2.0 path internally and reported
    # the trajectory dwell). Otherwise v1.x single-point chain.
    is_v2_trajectory_mode = "engagement_geometry" in user_inputs

    if is_v2_trajectory_mode:
        return _run_v2_trajectory(user_inputs, out1, out2, out3, out9)

    # v1.x single-point chain — preserved verbatim.
    out4 = m4_atmosphere.compute(_inputs_for_m4(user_inputs, out3))
    out5 = m5_turbulence.compute(_inputs_for_m5(user_inputs, out3))
    out7, out6, iter_count, converged = _iterate_m6_m7(
        user_inputs, out1, out2, out3, out4, out5,
    )
    out8 = m8_burnthrough.compute(_inputs_for_m8(user_inputs, out7))
    out10 = m10_power_thermal.compute(_inputs_for_m10(user_inputs, out8, out3))

    return _merge_results(
        out1, out2, out3, out4, out5, out6, out7, out8, out9, out10,
        iteration_count=iter_count,
        converged=converged,
    )


# ---------------------------------------------------------------------------
# SPEC v2.0 — trajectory-mode chain.
# ---------------------------------------------------------------------------

def _run_v2_trajectory(
    user_inputs: dict, out1: dict, out2: dict, out3: dict, out9: dict,
) -> dict:
    """v2.0 trajectory chain. M3 has run; this driver builds the
    trajectory R(t) callable, sub-samples M4/M5/M6/M7 along it, builds
    the I_aim(t) callable for M8, runs M8 with time-varying flux, and
    assembles the merged result with the new trajectory series outputs.
    """
    R_detect = user_inputs["R_detect"]
    R_min = user_inputs.get("R_min", 100.0)
    v_tgt = user_inputs["v_tgt"]
    geometry = user_inputs["engagement_geometry"]
    t_dwell = float(out3["available_dwell"])

    # Trajectory R(t) callable. Already validated by M3.
    R_of_t = m_trajectory.trajectory_R_of_t(
        R_detect, R_min, v_tgt, geometry,
    )

    # Sub-sampling schedule. At least two samples (start + end of
    # window). Cap by _MAX_SUBSAMPLES so pathological inputs cannot
    # spin the loop indefinitely.
    n_samples = min(
        max(2, int(math.ceil(t_dwell / _DT_SUBSAMPLE_S)) + 1),
        _MAX_SUBSAMPLES,
    )
    if n_samples == _MAX_SUBSAMPLES:
        # Inflate the dt to span the window with the sample budget.
        sample_times = [t_dwell * i / (n_samples - 1) for i in range(n_samples)]
    else:
        sample_times = [
            min(_DT_SUBSAMPLE_S * i, t_dwell) for i in range(n_samples)
        ]

    # Per-sample upstream-chain outputs. Carried as parallel lists so
    # the I_aim_of_t interpolant and the trajectory-series outputs can
    # both index by sample number.
    samples_R: list[float] = []
    samples_I_avg_aim: list[float] = []
    samples_I_peak: list[float] = []
    samples_d_spot: list[float] = []
    samples_PIB: list[float] = []
    samples_S_TB: list[float] = []
    samples_w_total: list[float] = []
    samples_N_D: list[float] = []
    samples_w_bloom: list[float] = []
    samples_tau_atm: list[float] = []
    samples_r0_sph: list[float] = []
    samples_w_turb: list[float] = []
    first_out4: dict = {}
    first_out5: dict = {}
    first_out6: dict = {}
    first_out7: dict = {}
    last_out4: dict = {}
    last_out5: dict = {}
    last_out6: dict = {}
    last_out7: dict = {}
    last_iter_count = 0
    last_converged = True

    # Warm-start state for the M6↔M7 loop. Each sub-sample re-uses the
    # previous converged S_TB / w_bloom as the starting guess; first
    # sample uses the cold S_TB=1 / w_bloom=0 default.
    warm_S_TB = 1.0
    warm_w_bloom = 0.0

    for sample_idx, t_i in enumerate(sample_times):
        R_now = float(R_of_t(t_i))
        out4_i = m4_atmosphere.compute(
            _inputs_for_m4_at_R(user_inputs, R_now)
        )
        out5_i = m5_turbulence.compute(
            _inputs_for_m5_at_R(user_inputs, R_now)
        )
        out7_i, out6_i, iter_count_i, converged_i = (
            _iterate_m6_m7_at_R(
                user_inputs, out1, out2, R_now,
                out4_i, out5_i,
                S_TB_warm=warm_S_TB, w_bloom_warm=warm_w_bloom,
            )
        )
        warm_S_TB = out6_i["S_TB"]
        warm_w_bloom = out6_i["w_bloom"]
        if sample_idx == 0:
            first_out4 = out4_i
            first_out5 = out5_i
            first_out6 = out6_i
            first_out7 = out7_i
        last_out4 = out4_i
        last_out5 = out5_i
        last_out6 = out6_i
        last_out7 = out7_i
        last_iter_count = iter_count_i
        last_converged = last_converged and converged_i

        samples_R.append(R_now)
        samples_I_avg_aim.append(float(out7_i["I_avg_aim"]))
        samples_I_peak.append(float(out7_i["I_peak"]))
        samples_d_spot.append(float(out7_i["d_spot"]))
        samples_PIB.append(float(out7_i["PIB_fraction"]))
        samples_S_TB.append(float(out6_i["S_TB"]))
        samples_w_total.append(float(out7_i["w_total"]))
        samples_N_D.append(float(out6_i["N_D"]))
        samples_w_bloom.append(float(out6_i["w_bloom"]))
        samples_tau_atm.append(float(out4_i["tau_atm"]))
        samples_r0_sph.append(float(out5_i["r0_sph"]))
        samples_w_turb.append(float(out5_i["w_turb"]))

    # Build I_aim_of_t as a linear interpolant over the sub-samples.
    # bisect.bisect_left gives the index for the upper sample; we
    # linearly interpolate between samples[i-1] and samples[i].
    I_aim_of_t = _build_linear_interpolant(sample_times, samples_I_avg_aim)

    # Take A_λ from the user's override if any, otherwise let M8 do
    # its own table lookup (constant through the engagement since
    # material doesn't change).
    out8 = m8_burnthrough.compute({
        "I_aim": I_aim_of_t,
        "material": user_inputs["material"],
        "thickness": user_inputs["thickness"],
        "wavelength": user_inputs["wavelength"],
        "backside_BC": user_inputs.get("backside_BC", "insulated"),
        "v_tgt": user_inputs["v_tgt"],
        "T_ambient": user_inputs["T_ambient"],
        "t_dwell": t_dwell,
        "R_of_t": R_of_t,
        # PR 8 — record T_surface(t) and E_cumulative(t) for Plot H
        # (engagement-profile timeline). Cheap (~80 sample points)
        # and only allocated when v2 trajectory mode is active.
        "record_trajectory": True,
        **(
            {"A_lambda": user_inputs["A_lambda"]}
            if user_inputs.get("A_lambda") is not None else {}
        ),
    })

    out10 = m10_power_thermal.compute(
        _inputs_for_m10(user_inputs, out8, out3),
    )

    # SPEC v2.0 — emit per-module scalars at the FIRST trajectory
    # sample (R_detect, t=0). This preserves the v1.x semantics where
    # the user's "reference range" drives the displayed values: I_peak,
    # d_spot, S_TB, PIB, w_total, tau_atm etc. all reflect "the
    # conditions at the start of the engagement". Sweep plots that
    # vary R_detect on the x-axis (Plot A on-target performance,
    # Plot G spot-vs-bucket, Plot D blooming, etc.) thus show
    # meaningful variation per engagement instead of collapsing to a
    # single R_min point.
    #
    # Across-trajectory aggregates remain accessible through:
    #   - trajectory_* arrays (per-sample series, t = 0 .. t_dwell)
    #   - I_peak_max / I_avg_aim_max (worst-case maxima)
    #   - the M8 PDE outputs (R_at_kill, T_surface_peak, etc.)
    out4 = first_out4 if first_out4 else last_out4
    out5 = first_out5 if first_out5 else last_out5
    out6 = first_out6 if first_out6 else last_out6
    out7 = first_out7 if first_out7 else last_out7

    merged = _merge_results(
        out1, out2, out3, out4, out5, out6, out7, out8, out9, out10,
        iteration_count=last_iter_count,
        converged=last_converged,
    )

    # SPEC v2.0 §4 trajectory-series outputs.
    merged["trajectory_t"] = tuple(sample_times)
    merged["trajectory_R"] = tuple(samples_R)
    merged["trajectory_I_peak"] = tuple(samples_I_peak)
    merged["trajectory_I_avg_aim"] = tuple(samples_I_avg_aim)
    merged["trajectory_d_spot"] = tuple(samples_d_spot)
    merged["trajectory_PIB"] = tuple(samples_PIB)
    merged["trajectory_S_TB"] = tuple(samples_S_TB)
    merged["trajectory_w_total"] = tuple(samples_w_total)
    merged["trajectory_N_D"] = tuple(samples_N_D)
    merged["I_peak_max"] = max(samples_I_peak) if samples_I_peak else 0.0
    merged["I_avg_aim_max"] = (
        max(samples_I_avg_aim) if samples_I_avg_aim else 0.0
    )

    return merged


def _build_linear_interpolant(
    xs: list[float], ys: list[float],
) -> Callable[[float], float]:
    """Return a callable that linearly interpolates between (xs, ys),
    clamping at the endpoints. Used to build the I_aim(t) callable
    from the sub-sampled I_avg_aim values."""
    # Defensive copies so the closure isn't broken by later mutation.
    xs_copy = tuple(xs)
    ys_copy = tuple(ys)
    n = len(xs_copy)

    def interp(x: float) -> float:
        if n == 0:
            return 0.0
        if x <= xs_copy[0]:
            return ys_copy[0]
        if x >= xs_copy[-1]:
            return ys_copy[-1]
        # Find the bracket.
        i = bisect.bisect_left(xs_copy, x)
        x_lo, x_hi = xs_copy[i - 1], xs_copy[i]
        y_lo, y_hi = ys_copy[i - 1], ys_copy[i]
        if x_hi == x_lo:
            return y_lo
        frac = (x - x_lo) / (x_hi - x_lo)
        return y_lo + frac * (y_hi - y_lo)

    return interp


def _index_sample_outputs(*args, **kwargs) -> dict:
    """Placeholder used only inside the v2 trajectory loop; the simpler
    last-sample assignment in `_run_v2_trajectory` is preferred for the
    per-module dict. Kept here so future iterations have a hook for a
    multi-sample summary if needed."""
    return {"out4": kwargs.get("last_out4")}


# ---------------------------------------------------------------------------
# v2.0 trajectory: per-R helpers
# ---------------------------------------------------------------------------

def _inputs_for_m4_at_R(u: dict, R_now: float) -> dict:
    return {
        "V": u["V"],
        "RH": u["RH"],
        "T_ambient": u["T_ambient"],
        "wavelength": u["wavelength"],
        "R_slant": R_now,
    }


def _inputs_for_m5_at_R(u: dict, R_now: float) -> dict:
    return {
        "cn2_model": u["cn2_model"],
        "Cn2_value": u["Cn2_value"],
        "Cn2_ground": u["Cn2_ground"],
        "v_HV": u["v_HV"],
        "wavelength": u["wavelength"],
        "R_slant": R_now,
        "H_e": u["H_e"],
        "H_t": u["H_t"],
    }


def _inputs_for_m7_at_R(u: dict, out1: dict, out2: dict,
                         R_now: float, out4_at_R: dict, out5_at_R: dict,
                         S_TB: float, w_bloom: float) -> dict:
    return {
        "P_exit": out2["P_exit"],
        "tau_atm": out4_at_R["tau_atm"],
        "w0": out1["w0"],
        "zR": out1["zR"],
        "M2": u["M2"],
        "wavelength": u["wavelength"],
        "R_slant": R_now,
        "sigma_jit": u["sigma_jit"],
        "r0_sph": out5_at_R["r0_sph"],
        "S_TB": S_TB,
        "w_bloom": w_bloom,
        "d_aim": u["d_aim"],
    }


def _inputs_for_m6_at_R(u: dict, out2: dict, R_now: float,
                         out4_at_R: dict, out7_at_R: dict) -> dict:
    return {
        "P_propagating": out2["P_exit"],
        "w_at_target": out7_at_R["w_total"],
        "alpha_atm": out4_at_R["alpha_atm"],
        "v_perp": u.get("v_perp", u["v_tgt"]),  # v1.x compat fallback
        "R_slant": R_now,
        "T_ambient": u["T_ambient"],
        "P_atm": u["P_atm"],
    }


def _iterate_m6_m7_at_R(
    user_inputs: dict, out1: dict, out2: dict, R_now: float,
    out4_at_R: dict, out5_at_R: dict,
    S_TB_warm: float, w_bloom_warm: float,
    max_iter: int = _DEFAULT_MAX_ITER,
    tol: float = _DEFAULT_TOL,
) -> tuple[dict, dict, int, bool]:
    """v2.0 trajectory variant of `_iterate_m6_m7`. Same Picard logic
    as the single-point version, but evaluated at `R_now` and warm-
    started from the previous sub-sample's converged S_TB/w_bloom."""
    S_TB = S_TB_warm
    w_bloom = w_bloom_warm
    w_total_prev: float | None = None
    out6: dict = {"N_D": 0.0, "S_TB": S_TB, "w_bloom": w_bloom,
                  "assumptions_flagged": []}
    out7: dict = {}
    iterations = 0
    converged = False

    for i in range(1, max_iter + 1):
        iterations = i
        out7 = m7_spot_pib.compute(_inputs_for_m7_at_R(
            user_inputs, out1, out2, R_now,
            out4_at_R, out5_at_R, S_TB, w_bloom,
        ))
        out6 = m6_blooming.compute(_inputs_for_m6_at_R(
            user_inputs, out2, R_now, out4_at_R, out7,
        ))
        S_TB = out6["S_TB"]
        w_bloom = out6["w_bloom"]

        w_total = out7["w_total"]
        if w_total_prev is not None and w_total_prev > 0.0:
            rel_change = abs(w_total - w_total_prev) / w_total_prev
            if rel_change < tol:
                converged = True
                break
        w_total_prev = w_total

    return out7, out6, iterations, converged


# ---------------------------------------------------------------------------
# M6↔M7 fixed-point iteration.
# ---------------------------------------------------------------------------
def _iterate_m6_m7(
    user_inputs: dict,
    out1: dict, out2: dict, out3: dict, out4: dict, out5: dict,
    max_iter: int = _DEFAULT_MAX_ITER,
    tol: float = _DEFAULT_TOL,
) -> tuple[dict, dict, int, bool]:
    """Alternate M6 and M7 until ``w_total`` converges.

    Returns ``(out7, out6, iterations_taken, converged)``. When the loop
    exits via ``max_iter`` without meeting ``tol``, ``converged`` is
    False and a SPEC §3 M6 iteration-did-not-converge flag is appended
    to ``out6['assumptions_flagged']``.
    """
    S_TB = 1.0
    w_bloom = 0.0
    w_total_prev: float | None = None
    out6: dict = {"N_D": 0.0, "S_TB": 1.0, "w_bloom": 0.0,
                  "assumptions_flagged": []}
    out7: dict = {}
    iterations = 0
    converged = False

    for i in range(1, max_iter + 1):
        iterations = i
        out7 = m7_spot_pib.compute(
            _inputs_for_m7(user_inputs, out1, out2, out4, out5, S_TB, w_bloom)
        )
        out6 = m6_blooming.compute(
            _inputs_for_m6(user_inputs, out2, out3, out4, out7)
        )
        S_TB = out6["S_TB"]
        w_bloom = out6["w_bloom"]

        w_total = out7["w_total"]
        if w_total_prev is not None and w_total_prev > 0.0:
            rel_change = abs(w_total - w_total_prev) / w_total_prev
            if rel_change < tol:
                converged = True
                break
        w_total_prev = w_total

    if not converged:
        out6["assumptions_flagged"].append(
            f"M6↔M7 fixed-point loop did not converge to {tol:.0%} in "
            f"{max_iter} iterations; reported values are the last pass "
            "(SPEC §3 M6)."
        )

    return out7, out6, iterations, converged


# ---------------------------------------------------------------------------
# Per-module input builders. Each returns exactly the keys required by
# the corresponding module's ``_validate_inputs`` — no more, no less.
# ---------------------------------------------------------------------------
def _inputs_for_m1(u: dict) -> dict:
    return {k: u[k] for k in ("P0", "M2", "D", "wavelength")}


def _inputs_for_m2(u: dict) -> dict:
    return {k: u[k] for k in ("P0", "eta_opt")}


def _inputs_for_m3(u: dict) -> dict:
    """Build the M3 input dict. SPEC v2.0 §3 M3 supports two input
    shapes; pass through whichever keys are present and let M3 dispatch
    on `engagement_geometry`."""
    if "engagement_geometry" in u:
        # v2.0 mode
        out = {k: u[k] for k in ("H_e", "R_detect", "H_t", "v_tgt",
                                  "engagement_geometry")}
        if "R_min" in u:
            out["R_min"] = u["R_min"]
        return out
    # v1.x backward-compat mode
    return {k: u[k] for k in ("H_e", "R", "H_t", "v_tgt", "v_perp")}


def _inputs_for_m4(u: dict, out3: dict) -> dict:
    return {
        "V": u["V"],
        "RH": u["RH"],
        "T_ambient": u["T_ambient"],
        "wavelength": u["wavelength"],
        "R_slant": out3["R_slant"],
    }


def _inputs_for_m5(u: dict, out3: dict) -> dict:
    return {
        "cn2_model": u["cn2_model"],
        "Cn2_value": u["Cn2_value"],
        "Cn2_ground": u["Cn2_ground"],
        "v_HV": u["v_HV"],
        "wavelength": u["wavelength"],
        "R_slant": out3["R_slant"],
        "H_e": u["H_e"],
        "H_t": u["H_t"],
    }


def _inputs_for_m6(u: dict, out2: dict, out3: dict, out4: dict,
                   out7: dict) -> dict:
    return {
        # SPEC §3 M6 convention: P is the transmitted beam power along
        # the path; we feed the exit-aperture power (Gebhardt 1990).
        "P_propagating": out2["P_exit"],
        "w_at_target": out7["w_total"],
        "alpha_atm": out4["alpha_atm"],
        "v_perp": u["v_perp"],
        "R_slant": out3["R_slant"],
        "T_ambient": u["T_ambient"],
        "P_atm": u["P_atm"],
    }


def _inputs_for_m7(u: dict, out1: dict, out2: dict, out4: dict, out5: dict,
                   S_TB: float, w_bloom: float) -> dict:
    return {
        "P_exit": out2["P_exit"],
        "tau_atm": out4["tau_atm"],
        "w0": out1["w0"],
        "zR": out1["zR"],
        "M2": u["M2"],
        "wavelength": u["wavelength"],
        "R_slant": u["R"],  # equal to R_slant in v1; M3 pass-through
        "sigma_jit": u["sigma_jit"],
        "r0_sph": out5["r0_sph"],
        "S_TB": S_TB,
        "w_bloom": w_bloom,
        "d_aim": u["d_aim"],
    }


def _inputs_for_m8(u: dict, out7: dict) -> dict:
    inputs = {
        "I_aim": out7["I_avg_aim"],
        "material": u["material"],
        "thickness": u["thickness"],
        "wavelength": u["wavelength"],
        "backside_BC": u.get("backside_BC", "insulated"),
        "v_tgt": u["v_tgt"],
        "T_ambient": u["T_ambient"],
    }
    # A_λ override is only present when the user has explicitly set it
    # in Panel E (SPEC §5.1). M8 falls back to the material table when
    # the key is absent — so we pass it only when truly present.
    if u.get("A_lambda") is not None:
        inputs["A_lambda"] = u["A_lambda"]
    return inputs


def _inputs_for_m9(u: dict, out1: dict) -> dict:
    return {
        "P0": u["P0"],
        "D": u["D"],
        "theta_diff": out1["theta_diff"],
        "wavelength": u["wavelength"],
        "t_exp": u["t_exp"],
    }


def _inputs_for_m10(u: dict, out8: dict, out3: dict) -> dict:
    # t_engagement is the time the laser must sustain output to reach
    # burn-through. If M8 times out (target never fails within the
    # sim cap), we fall back to the geometric dwell window from M3 so
    # M10 still reports a finite power/thermal answer rather than
    # booting out on a validation error.
    tau_bt = out8.get("tau_BT")
    dwell = out3.get("available_dwell")
    if tau_bt is not None and tau_bt > 0.0:
        t_engagement = tau_bt
    elif dwell is not None and dwell > 0.0:
        t_engagement = dwell
    else:
        t_engagement = 1.0  # degenerate: M10 will report single-shot
    return {
        "P0": u["P0"],
        "eta_wallplug": u["eta_wallplug"],
        "Q_cool": u["Q_cool"],
        "C_thermal": u["C_thermal"],
        "dT_max": u["dT_max"],
        "t_engagement": t_engagement,
    }


# ---------------------------------------------------------------------------
# Result merging.
# ---------------------------------------------------------------------------
def _merge_results(
    out1: dict, out2: dict, out3: dict, out4: dict, out5: dict,
    out6: dict, out7: dict, out8: dict, out9: dict, out10: dict,
    iteration_count: int,
    converged: bool,
) -> dict:
    """Flat-merge all module outputs; union the flag lists in order."""
    # Preserve per-module namespaces for callers that need them.
    by_module = {
        "m1": out1, "m2": out2, "m3": out3, "m4": out4, "m5": out5,
        "m6": out6, "m7": out7, "m8": out8, "m9": out9, "m10": out10,
    }

    # Union of assumptions_flagged, de-duplicated while preserving the
    # first-seen order so Panel 4 shows the chain's natural top-down flow.
    seen: set[str] = set()
    all_flags: list[str] = []
    for out in (out1, out2, out3, out4, out5, out6, out7, out8, out9, out10):
        for flag in out.get("assumptions_flagged", []):
            if flag not in seen:
                seen.add(flag)
                all_flags.append(flag)

    merged: dict = {}
    for out in by_module.values():
        for k, v in out.items():
            if k == "assumptions_flagged":
                continue
            merged[k] = v
    merged["assumptions_flagged"] = all_flags
    merged["by_module"] = by_module
    merged["m67_iteration_count"] = iteration_count
    merged["m67_converged"] = converged
    return merged
