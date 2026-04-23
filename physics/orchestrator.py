"""Chain coordinator — wires the 10 physics modules in dependency order.

Pure Python. No Streamlit imports, no UI side effects. Lives in
``physics/`` (not ``ui/``) so ``tests/`` can import it directly under
the ARCHITECTURE §2 import rules — the M6↔M7 fixed-point loop is
physics-critical and deserves dedicated unit-test coverage.

``ui/app.py`` wraps calls to ``run_full_chain(user_inputs)`` in an
``@st.cache_data`` helper (per ARCHITECTURE §5.3) on the "Run Analysis"
click handler, then renders the returned dict via ``ui/outputs.py`` +
``ui/plots.py``.

Dependency graph (ARCH §5.1 / SPEC §4):

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

The M6↔M7 loop (ARCH §5.1 step 4): seed ``S_TB=1``, ``w_bloom=0``;
compute M7's ``w_total``; pass into M6; update ``S_TB`` and ``w_bloom``;
re-run M7. Terminate when ``|Δw_total| / w_total < 1%`` or at 10
iterations (whichever first). Non-convergence is flagged, not raised.

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
)

#: Default fixed-point loop limits. Exposed as kwargs on
#: ``_iterate_m6_m7`` for tests that need tighter / looser bounds.
_DEFAULT_MAX_ITER = 10
_DEFAULT_TOL = 0.01  # 1 % relative change in w_total between passes


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
