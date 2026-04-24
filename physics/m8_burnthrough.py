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
  - otherwise:          mode='no_failure_before_timeout' at t = 60 s

Numerical method per SPEC §3 M8: explicit finite-difference with
Δx = min(50 µm, thickness/20), Δt = 0.4·Δx²·ρ·c_p/k (safety factor 0.4),
ghost-cell stencil at both boundaries. NumPy for vectorized interior
updates — 50–100× faster than list-based Python at Δx=50 µm on the Al
validation case.

References: Carslaw & Jaeger, *Conduction of Heat in Solids* (1959);
Steen & Mazumder, *Laser Material Processing* (4 ed., 2010) Ch. 5–6.
"""

import math

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
      - I_aim (W/m²): delivered irradiance (from M7)
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

    Outputs:
      - tau_BT (s): time-to-failure (or = _SIM_TIMEOUT_S on timeout)
      - T_surface_peak (K): peak surface temperature observed
      - E_delivered (J/m²): total absorbed energy per unit area at
        failure (SPEC §3 M8 Outputs table writes unit as J; M8 reports
        per unit area since the module sees only irradiance, not a spot
        area. The UI multiplies by π·R_aim² to get total energy.)
      - failure_mode (str): 'melt' | 'decomposition' | 'vent' |
        'no_failure_before_timeout'
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

    I_aim = inputs["I_aim"]
    thickness = inputs["thickness"]
    wavelength = inputs["wavelength"]
    backside_BC = inputs["backside_BC"]
    v_tgt = inputs["v_tgt"]
    T_amb = inputs["T_ambient"]

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

    absorbed_flux = A_lambda * I_aim           # W/m² into surface at T_s=T_amb peak
    r = alpha_diff * dt / (dx * dx)            # Fourier number per step, ≤ safety
    two_dx_over_k = 2.0 * dx / k

    max_steps = int(_SIM_TIMEOUT_S / dt) + 1

    for _step in range(max_steps):
        T_s = float(T[0])

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

        if T[0] > T_surface_peak:
            T_surface_peak = float(T[0])

    if failure_mode is None:
        failure_mode = "no_failure_before_timeout"
        tau_BT = t
        assumptions_flagged.append(
            f"simulation reached {_SIM_TIMEOUT_S:.0f} s timeout without "
            f"failure — engagement not viable at this flux / material / "
            f"thickness combination (SPEC §3 M8 timeout criterion)"
        )

    E_delivered = absorbed_flux * tau_BT

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

    return {
        "tau_BT": tau_BT,
        "T_surface_peak": T_surface_peak,
        "E_delivered": E_delivered,
        "failure_mode": failure_mode,
        "assumptions_flagged": assumptions_flagged,
    }


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
