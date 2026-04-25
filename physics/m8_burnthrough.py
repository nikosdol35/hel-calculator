"""M8 — Material Burn-Through.

1-D transient heat conduction solver with absorbed-flux surface BC
(convection + IR radiation loss), insulated or convective backside,
and material-specific failure criteria:

  - metals (Al):        T_s ≥ T_melt, then accumulated latent-heat
                        budget ρ·L_f·thickness → mode='melt'
  - polymers (CFRP,
    GFRP, PC, ABS) +
    foam (EPP):         T_s ≥ T_decomp sustained for ≥ 0.05 s
                        → mode='decomposition'
  - LiPo:               T_s ≥ T_vent (= 420 K) → mode='vent'
  - timeout:            mode='no_failure_before_timeout' at t = 60 s
  - SPEC v2.0:          mode='engagement_ended_at_R_min' if t_dwell
                        elapses without failure (tracker-supported case)

SPEC v2.0 §3 M8: ``I_aim`` extended from scalar to callable ``I_aim(t)``
returning the delivered irradiance at engagement-time t. The orchestrator
builds this callable from the trajectory R(t) and the M4-M7 sub-sampling
chain. Scalar callers continue to work — wrapped internally in
``lambda t: scalar``. New optional input ``t_dwell`` stops the
integration when the engagement window ends; when not provided the
solver uses ``_SIM_TIMEOUT_S`` (60 s) as before. New optional input
``R_of_t`` returns the slant range at engagement-time; when given,
``R_at_kill`` is reported in the output dict.

Numerical method per SPEC §3 M8: explicit finite-difference with
Δx = min(50 µm, thickness/20), Δt = 0.4·Δx²·ρ·c_p/k (safety factor 0.4),
ghost-cell stencil at both boundaries. NumPy for vectorized interior
updates — 50–100× faster than list-based Python at Δx=50 µm on the Al
validation case.

References: Carslaw & Jaeger, *Conduction of Heat in Solids* (1959);
Steen & Mazumder, *Laser Material Processing* (4 ed., 2010) Ch. 5–6.
"""

import math
from typing import Callable

import numpy as np

from physics.common import validate_enum, validate_positive, validate_range
from physics.m8_material_tables import (
    A_LAMBDA_TABLE,
    A_LAMBDA_TABLE_WAVELENGTHS_M,
    EMISSIVITY_IR_DEFAULT,
    MATERIAL_PROPERTIES,
    MATERIALS,
    SIGMA_SB,
)


_DX_TARGET = 5.0e-5              # m; SPEC §3 M8 target 50 µm
_N_MIN = 21                      # minimum nodes = 20 intervals
_STABILITY_SAFETY = 0.4          # SPEC §3 M8 Δt safety factor
_SIM_TIMEOUT_S = 60.0            # SPEC §3 M8 integration timeout
_DECOMP_SUSTAIN_S = 0.05         # SPEC §3 M8 decomposition hold time
_BACKSIDE_BCS = ("insulated", "convective")


def compute(inputs: dict) -> dict:
    """Compute tau_BT, peak surface T, delivered energy, and failure
    mode per SPEC §3 M8.

    Inputs (required keys):
      - I_aim (W/m² or Callable[[float], float]): delivered irradiance.
        SPEC v2.0: may be either a scalar (constant flux during the
        integration — v1.x behaviour) or a callable returning the
        flux at engagement-time t. The orchestrator wraps the
        trajectory + upstream-chain computation in a callable so
        time-varying flux flows through M8 transparently.
      - material (str): enum — one of MATERIALS
      - thickness (m): 0.0001 – 0.020
      - wavelength (m): for default A_λ table lookup (from M1)
      - backside_BC (str): 'insulated' or 'convective'
      - v_tgt (m/s): for h_conv (from M3); 0 allowed (natural convection)
      - T_ambient (K): 253 – 328 (from M4)
    Optional:
      - A_lambda (—): user override; 0.05 – 0.99. If absent or None,
        M8 looks up from the SPEC §3 M8 table and flags the default
        as SPEC §10.2 HIGH UNCERTAINTY.
      - t_dwell (s): SPEC v2.0. Engagement window from M3. When given,
        the solver stops at ``t ≥ t_dwell`` if T_fail hasn't been
        reached; the result reports
        ``failure_mode = 'engagement_ended_at_R_min'``. When absent,
        the solver uses _SIM_TIMEOUT_S (60 s) as the timeout, matching
        v1.x.
      - R_of_t (Callable[[float], float]): SPEC v2.0. Trajectory range
        at engagement-time. When given, ``R_at_kill`` is reported in
        the output dict (None otherwise).

    Outputs:
      - tau_BT (s): time-to-failure (or = window-end on no-kill)
      - T_surface_peak (K): peak surface temperature observed
      - E_delivered (J/m²): total absorbed energy per unit area at
        failure (SPEC §3 M8 Outputs table writes unit as J; M8 reports
        per unit area since the module sees only irradiance, not a spot
        area. The UI multiplies by π·R_aim² to get total energy.)
      - failure_mode (str): 'melt' | 'decomposition' | 'vent' |
        'no_failure_before_timeout' | 'engagement_ended_at_R_min'
      - R_at_kill (float | None): SPEC v2.0. Slant range at moment of
        failure, evaluated by R_of_t(tau_BT) when R_of_t is supplied;
        None otherwise.
      - assumptions_flagged (list[str])

    Equations (SPEC §3 M8):
        PDE:    ρ·c_p·∂T/∂t = k·∂²T/∂x²
        x=0:    -k·∂T/∂x = A_λ·I_aim − h·(T_s − T_amb)
                            − ε·σ·(T_s⁴ − T_amb⁴)
        x=L:    insulated  → ∂T/∂x = 0
                convective → -k·∂T/∂x = h·(T_back − T_amb)
        h_conv = 10 + 6.2·√v_tgt  W/(m²·K)

    Melt handling: once T_s ≥ T_fail (metals), surface is clamped at
    T_fail (phase front). Net surface flux then accumulates against
    the latent-heat budget ρ·L_f·thickness; burn-through declared when
    the accumulation exceeds the budget. Interior conduction continues
    normally with T_s as a Dirichlet BC. Engineering approximation —
    ignores interior conduction drawing from melt energy (minor effect
    for high-k metals where interior reaches T_melt before surface).
    """
    _validate_inputs(inputs)

    material = inputs["material"]
    props = MATERIAL_PROPERTIES[material]
    rho = props["rho"]
    c_p = props["c_p"]
    k = props["k"]
    T_fail = props["T_fail"]
    L_f = props["L_f"]
    failure_mode_target = props["failure_mode"]

    # SPEC v2.0 — I_aim may be a scalar (v1.x) or a callable (v2.0).
    # Wrap scalar in lambda so the inner loop is uniform.
    I_aim_in = inputs["I_aim"]
    if callable(I_aim_in):
        I_aim_of_t: Callable[[float], float] = I_aim_in
        I_aim_was_callable = True
    else:
        I_aim_scalar = float(I_aim_in)

        def _constant_flux(_t: float, _v: float = I_aim_scalar) -> float:
            return _v

        I_aim_of_t = _constant_flux
        I_aim_was_callable = False

    thickness = inputs["thickness"]
    wavelength = inputs["wavelength"]
    backside_BC = inputs["backside_BC"]
    v_tgt = inputs["v_tgt"]
    T_amb = inputs["T_ambient"]

    # SPEC v2.0 — engagement window and trajectory hooks (optional).
    t_dwell_in = inputs.get("t_dwell")
    if t_dwell_in is not None:
        t_dwell = float(t_dwell_in)
        if t_dwell <= 0:
            raise ValueError(
                f"t_dwell must be > 0 s, got {t_dwell}"
            )
    else:
        t_dwell = None  # use _SIM_TIMEOUT_S as fallback

    R_of_t_in = inputs.get("R_of_t")
    R_of_t: Callable[[float], float] | None = (
        R_of_t_in if callable(R_of_t_in) else None
    )

    # PR 8 — optional trajectory recording. When ``record_trajectory``
    # is True, M8 collects (t, T_surface, E_cumulative) samples every
    # ~_TRAJECTORY_SAMPLE_DT_S of engagement time and emits them in
    # the result dict. Plot H consumes these for the engagement-
    # profile timeline. Default False keeps the v1.x scalar-output
    # contract unchanged.
    record_trajectory = bool(inputs.get("record_trajectory", False))

    assumptions_flagged: list[str] = []

    # A_λ: user override or table lookup
    A_user = inputs.get("A_lambda")
    if A_user is not None:
        A_lambda = float(A_user)
    else:
        A_lambda, lookup_flag = _lookup_A_lambda(material, wavelength)
        if lookup_flag:
            assumptions_flagged.append(lookup_flag)
        assumptions_flagged.append(
            f"A_λ for '{material}' taken from default table (SPEC §10.2 "
            f"HIGH UNCERTAINTY — override with measured or program-"
            f"specific value before formal use)"
        )

    # Grid and step
    dx = min(_DX_TARGET, thickness / (_N_MIN - 1))
    n_nodes = int(round(thickness / dx)) + 1
    # Re-solve dx so thickness = (n_nodes-1)·dx exactly.
    dx = thickness / (n_nodes - 1)
    alpha_diff = k / (rho * c_p)
    dt = _STABILITY_SAFETY * dx * dx / alpha_diff

    # Boundary coefficients
    h_conv = 10.0 + 6.2 * math.sqrt(v_tgt)
    eps_ir = EMISSIVITY_IR_DEFAULT
    sigma_sb = SIGMA_SB

    # State
    T = np.full(n_nodes, T_amb, dtype=float)
    t = 0.0
    T_surface_peak = T_amb
    melting = False
    melt_energy = 0.0
    melt_budget = rho * L_f * thickness if L_f is not None else None
    decomp_timer = 0.0
    failure_mode: str | None = None
    tau_BT: float | None = None

    # SPEC v2.0: absorbed_flux now varies with t through I_aim_of_t(t).
    # The cumulative absorbed-energy integral becomes a Riemann sum
    # (E_cumulative_absorbed) accumulated each step, since the simple
    # absorbed_flux * tau_BT identity from v1.x assumes constant flux.
    r = alpha_diff * dt / (dx * dx)            # Fourier number per step, ≤ safety
    two_dx_over_k = 2.0 * dx / k

    # Window-end: SPEC v2.0 t_dwell stop, falling back to _SIM_TIMEOUT_S
    # for v1.x callers (no t_dwell supplied).
    t_max = t_dwell if t_dwell is not None else _SIM_TIMEOUT_S
    max_steps = int(t_max / dt) + 1

    E_cumulative_absorbed = 0.0  # J/m² absorbed integrated over the run

    # Trajectory-recording state (PR 8). Sample every ~50 ms of
    # engagement time so the time series has ~80 points across a
    # 4-second engagement (small enough for plotting + Streamlit
    # serialisation; large enough to show the temperature ramp shape).
    _TRAJECTORY_SAMPLE_DT_S = 0.050
    sample_stride_steps = max(1, int(_TRAJECTORY_SAMPLE_DT_S / dt))
    traj_t_pde: list[float] = []
    traj_T_surface: list[float] = []
    traj_E_cumulative: list[float] = []
    if record_trajectory:
        traj_t_pde.append(0.0)
        traj_T_surface.append(float(T[0]))
        traj_E_cumulative.append(0.0)

    for step_index, _step in enumerate(range(max_steps)):
        T_s = float(T[0])

        # SPEC v2.0 — flux at current engagement time.
        absorbed_flux = A_lambda * I_aim_of_t(t)

        # Losses at the current surface temperature
        conv_loss = h_conv * (T_s - T_amb)
        rad_loss = eps_ir * sigma_sb * (T_s ** 4 - T_amb ** 4)
        net_surface_flux = absorbed_flux - conv_loss - rad_loss

        # Failure-criterion evaluation (BEFORE the time step so tau_BT
        # is the instant the criterion first holds)
        if failure_mode_target == "melt":
            # melt_budget is only None for materials without a latent heat
            # (non-metals); the failure_mode_target==melt branch is only
            # taken for metals, so melt_budget is guaranteed non-None here.
            assert melt_budget is not None
            if melting:
                if net_surface_flux > 0.0:
                    melt_energy += net_surface_flux * dt
                if melt_energy >= melt_budget:
                    failure_mode = "melt"
                    tau_BT = t
                    break
            elif T_s >= T_fail:
                melting = True
        elif failure_mode_target == "decomposition":
            if T_s >= T_fail:
                decomp_timer += dt
                if decomp_timer >= _DECOMP_SUSTAIN_S:
                    failure_mode = "decomposition"
                    tau_BT = t
                    break
            else:
                decomp_timer = 0.0
        elif failure_mode_target == "vent":
            if T_s >= T_fail:
                failure_mode = "vent"
                tau_BT = t
                break

        # Advance one time step using explicit FD
        T_new = np.empty_like(T)

        # Interior nodes (central difference)
        T_new[1:-1] = T[1:-1] + r * (T[:-2] - 2.0 * T[1:-1] + T[2:])

        # Surface BC (x=0), ghost cell method
        if melting:
            # Phase-front clamp: T[0] fixed at T_fail, surface absorbs
            # into latent heat rather than raising temperature.
            T_new[0] = T_fail
        else:
            # Ghost T[-1] = T[1] + (2·dx/k)·net_surface_flux → stencil
            # reduces to: T_new[0] = T[0] + 2r·(T[1]-T[0]) + 2r·(dx/k)·q
            T_new[0] = T[0] + 2.0 * r * (T[1] - T[0]) + r * two_dx_over_k * net_surface_flux

        # Backside BC (x=thickness)
        if backside_BC == "insulated":
            T_new[-1] = T[-1] + 2.0 * r * (T[-2] - T[-1])
        else:  # convective
            back_flux = h_conv * (T[-1] - T_amb)
            T_new[-1] = T[-1] + 2.0 * r * (T[-2] - T[-1]) - r * two_dx_over_k * back_flux

        T = T_new
        t += dt

        # Accumulate absorbed energy (Riemann sum) — replaces the v1.x
        # `absorbed_flux * tau_BT` identity which assumed constant flux.
        E_cumulative_absorbed += max(absorbed_flux, 0.0) * dt

        # PR 8 — record trajectory series at sparse intervals for
        # Plot H. Sub-sampling rather than recording every PDE step
        # keeps storage bounded (~80-200 points per engagement).
        if record_trajectory and (step_index + 1) % sample_stride_steps == 0:
            traj_t_pde.append(t)
            traj_T_surface.append(float(T[0]))
            traj_E_cumulative.append(E_cumulative_absorbed)

        if T[0] > T_surface_peak:
            T_surface_peak = float(T[0])

    if failure_mode is None:
        # No failure within the budget. Pick the right "no kill" verdict
        # depending on whether we ran out of t_dwell (v2.0 engagement
        # window) or _SIM_TIMEOUT_S (v1.x fallback).
        if t_dwell is not None:
            failure_mode = "engagement_ended_at_R_min"
            assumptions_flagged.append(
                f"engagement window of {t_dwell:.3g} s elapsed without "
                f"reaching T_fail — target reached the engagement-end "
                f"range (SPEC v2.0 §3 M8)"
            )
        else:
            failure_mode = "no_failure_before_timeout"
            assumptions_flagged.append(
                f"simulation reached {_SIM_TIMEOUT_S:.0f} s timeout "
                f"without failure — engagement not viable at this flux "
                f"/ material / thickness combination (SPEC §3 M8 "
                f"timeout criterion)"
            )
        tau_BT = t

    E_delivered = E_cumulative_absorbed

    # SPEC v2.0 — R_at_kill from the trajectory at tau_BT, when R_of_t
    # is supplied. None for v1.x callers and for "no kill" verdicts
    # (the run stopped without a failure event, so there is no kill
    # range to report).
    R_at_kill: float | None
    if R_of_t is not None and failure_mode in ("melt", "decomposition", "vent"):
        # A kill verdict guarantees tau_BT was set inside the loop —
        # narrow the type for mypy.
        assert tau_BT is not None
        R_at_kill = float(R_of_t(tau_BT))
    else:
        R_at_kill = None

    assumptions_flagged.append(
        f"1-D transient conduction: Δx = {dx*1e6:.1f} µm, "
        f"Δt = {dt*1e6:.3g} µs, {n_nodes} nodes, stability-safety "
        f"factor = {_STABILITY_SAFETY} (SPEC §3 M8 explicit FD)"
    )
    assumptions_flagged.append(
        f"surface conv+rad losses with h_conv = {h_conv:.2f} W/(m²·K), "
        f"ε_IR = {eps_ir:.2f}; same h_conv applied to front and back "
        f"faces when enabled (SPEC §3 M8 v1 simplification)"
    )
    if backside_BC == "convective":
        assumptions_flagged.append(
            "backside convective BC active; note SPEC §10.6 HIGH "
            "UNCERTAINTY on the h_conv = 10 + 6.2·√v_tgt engineering "
            "correlation"
        )

    if I_aim_was_callable:
        assumptions_flagged.append(
            "SPEC v2.0: I_aim time-varying through engagement (callable); "
            "absorbed-energy integral evaluated as Riemann sum over PDE "
            "timesteps"
        )

    # PR 8 — finalise the trajectory recording with the last state
    # so the series ends at tau_BT (or the engagement-end moment).
    if record_trajectory:
        last_t = tau_BT if tau_BT is not None else t
        if not traj_t_pde or traj_t_pde[-1] < last_t - 1e-12:
            traj_t_pde.append(last_t)
            traj_T_surface.append(float(T[0]))
            traj_E_cumulative.append(E_cumulative_absorbed)

    result: dict = {
        "tau_BT": tau_BT,
        "T_surface_peak": T_surface_peak,
        "E_delivered": E_delivered,
        "failure_mode": failure_mode,
        "R_at_kill": R_at_kill,
        "assumptions_flagged": assumptions_flagged,
    }
    if record_trajectory:
        result["trajectory_t_pde"] = tuple(traj_t_pde)
        result["trajectory_T_surface"] = tuple(traj_T_surface)
        result["trajectory_E_cumulative"] = tuple(traj_E_cumulative)
    return result


def _lookup_A_lambda(material: str, wavelength: float) -> tuple[float, str | None]:
    """Linear-in-wavelength interpolation of A_λ from the SPEC §3 M8
    table. Clamps at endpoints (flag raised). Returns (A_λ, flag_or_None)."""
    table = A_LAMBDA_TABLE[material]
    wls = A_LAMBDA_TABLE_WAVELENGTHS_M

    if wavelength < wls[0]:
        return table[0], (
            f"wavelength {wavelength*1e6:.3f} µm below tabulated A_λ "
            f"range [{wls[0]*1e6:.2f}, {wls[-1]*1e6:.2f}] µm — clamped "
            f"at endpoint (reduced confidence)"
        )
    if wavelength > wls[-1]:
        return table[-1], (
            f"wavelength {wavelength*1e6:.3f} µm above tabulated A_λ "
            f"range [{wls[0]*1e6:.2f}, {wls[-1]*1e6:.2f}] µm — clamped "
            f"at endpoint (reduced confidence)"
        )

    for i in range(len(wls) - 1):
        if wls[i] <= wavelength <= wls[i + 1]:
            if any(abs(wavelength - w) <= 5e-9 for w in wls):
                for j, w in enumerate(wls):
                    if abs(wavelength - w) <= 5e-9:
                        return table[j], None
            t_ = (wavelength - wls[i]) / (wls[i + 1] - wls[i])
            return (
                table[i] + t_ * (table[i + 1] - table[i]),
                f"A_λ for '{material}' linearly interpolated between "
                f"tabulated points ({wls[i]*1e6:.2f} µm, "
                f"{wls[i+1]*1e6:.2f} µm)",
            )
    raise RuntimeError("unreachable bracket search in A_λ interpolation")


def _validate_inputs(inputs: dict) -> None:
    """Raise ValueError with a descriptive message if any required input
    is missing or out of range. Ranges per SPEC §3 M8 inputs table."""
    required = (
        "I_aim", "material", "thickness", "wavelength",
        "backside_BC", "v_tgt", "T_ambient",
    )
    missing = [k for k in required if k not in inputs]
    if missing:
        raise ValueError(f"M8 missing required inputs: {missing}")

    # SPEC v2.0: I_aim may be a positive scalar (v1.x) or a callable
    # (v2.0 trajectory mode). Validate scalar-shape only when scalar.
    if not callable(inputs["I_aim"]):
        validate_positive(inputs["I_aim"], "I_aim")
    validate_enum(inputs["material"], "material", list(MATERIALS))
    validate_range(inputs["thickness"], "thickness", 1.0e-4, 2.0e-2)
    validate_range(inputs["wavelength"], "wavelength", 0.5e-6, 5.0e-6)
    validate_enum(inputs["backside_BC"], "backside_BC", list(_BACKSIDE_BCS))
    validate_range(inputs["v_tgt"], "v_tgt", 0.0, 100.0)
    validate_range(inputs["T_ambient"], "T_ambient", 253.0, 328.0)

    A = inputs.get("A_lambda")
    if A is not None:
        validate_range(float(A), "A_lambda", 0.05, 0.99)
