"""M4 — Atmospheric Attenuation.

Beer-Lambert transmission through the lower atmosphere, combining
molecular absorption/scattering (tabulated sea-level mid-latitude
summer, 60% RH baseline — HIGH UNCERTAINTY per SPEC §10.1) with
Kruse-McClatchey aerosol extinction. Four-way decomposition
(mol_abs, mol_scat, aer_abs, aer_scat) exposed for Panel-5 display.

References:
  - Kruse, Elements of Infrared Technology (Wiley, 1962) — aerosol formula
  - McClatchey et al., AFCRL-TR-72-0497 — molecular baselines
  - Andrews & Phillips Ch. 12 — engineering formulations
"""

import math

from physics.common import interp_log_space, validate_range
from physics.m4_data_tables import (
    ALPHA_MOL_ABSORPTION_1_PER_KM,
    ALPHA_MOL_SCATTERING_1_PER_KM,
)


_AER_SCAT_FRACTION = 0.95
_AER_ABS_FRACTION = 0.05
_RH_BASELINE = 0.60


def compute(inputs: dict) -> dict:
    """Compute atmospheric extinction and transmission per SPEC §3 M4.

    Inputs (required keys):
      - V (km): meteorological visibility, 0.5 – 50
      - RH (—): relative humidity (0–1 fraction), 0.0 – 1.0
      - T_ambient (K): ambient air temperature, 253 – 328
      - wavelength (m): laser wavelength, 0.5e-6 – 5.0e-6 (from M1)
      - R_slant (m): path length, 50 – 50_000 (from M3)

    Outputs (all α in 1/m per SPEC §3 M4 outputs table):
      - alpha_atm (1/m): total extinction coefficient
      - tau_atm (—): transmission factor exp(-α·R)
      - alpha_mol_abs (1/m): molecular absorption
      - alpha_mol_scat (1/m): molecular scattering
      - alpha_aer_abs (1/m): aerosol absorption (5% of aerosol total)
      - alpha_aer_scat (1/m): aerosol scattering (95% of aerosol total)
      - assumptions_flagged (list[str])

    Equations (SPEC §3 M4):
        α_aer_total_per_km = (3.91/V_km) · (λ_µm/0.55)^(-q)
        α_atm              = α_mol_abs + α_mol_scat + α_aer_abs + α_aer_scat
        τ_atm              = exp(-α_atm · R_slant)

    q rule (Kruse modified):
        V > 50 km:    q = 1.6   (dead code — outside SPEC §3 M4 V range)
        6 ≤ V ≤ 50:   q = 1.3
        1 ≤ V < 6:    q = 0.16·V + 0.34
        V < 1 km:     q = V − 0.5
    """
    _validate_inputs(inputs)

    V = inputs["V"]
    RH = inputs["RH"]
    wavelength = inputs["wavelength"]
    R_slant = inputs["R_slant"]

    tabulated_wl = sorted(ALPHA_MOL_ABSORPTION_1_PER_KM.keys())
    abs_tbl = [ALPHA_MOL_ABSORPTION_1_PER_KM[w] for w in tabulated_wl]
    scat_tbl = [ALPHA_MOL_SCATTERING_1_PER_KM[w] for w in tabulated_wl]

    assumptions_flagged: list[str] = [
        "α_mol tables are engineering placeholders per SPEC §10.1 "
        "(HIGH UNCERTAINTY — refine against HITRAN/MODTRAN before formal use)",
        "sea-level atmospheric coefficients used along slant path "
        "(v1 simplification per CLAUDE §4.5)",
    ]

    lo, hi = tabulated_wl[0], tabulated_wl[-1]
    if wavelength < lo or wavelength > hi:
        assumptions_flagged.append(
            f"wavelength {wavelength*1e6:.3f} µm outside tabulated range "
            f"[{lo*1e6:.2f}, {hi*1e6:.2f}] µm — clamped at endpoint "
            f"(reduced confidence)"
        )
    elif not any(abs(wavelength - w) <= 5e-9 for w in tabulated_wl):
        assumptions_flagged.append(
            "wavelength interpolated between tabulated molecular-coefficient "
            "points (log-space linear)"
        )

    alpha_mol_abs_per_km = (
        interp_log_space(wavelength, tabulated_wl, abs_tbl) * (RH / _RH_BASELINE)
    )
    alpha_mol_scat_per_km = interp_log_space(wavelength, tabulated_wl, scat_tbl)

    wavelength_um = wavelength * 1e6
    q = _kruse_q(V)
    alpha_aer_total_per_km = (3.91 / V) * (wavelength_um / 0.55) ** (-q)
    alpha_aer_abs_per_km = _AER_ABS_FRACTION * alpha_aer_total_per_km
    alpha_aer_scat_per_km = _AER_SCAT_FRACTION * alpha_aer_total_per_km

    alpha_atm_per_km = (
        alpha_mol_abs_per_km + alpha_mol_scat_per_km
        + alpha_aer_abs_per_km + alpha_aer_scat_per_km
    )

    alpha_mol_abs = alpha_mol_abs_per_km / 1000.0
    alpha_mol_scat = alpha_mol_scat_per_km / 1000.0
    alpha_aer_abs = alpha_aer_abs_per_km / 1000.0
    alpha_aer_scat = alpha_aer_scat_per_km / 1000.0
    alpha_atm = alpha_atm_per_km / 1000.0

    tau_atm = math.exp(-alpha_atm * R_slant)

    return {
        "alpha_atm": alpha_atm,
        "tau_atm": tau_atm,
        "alpha_mol_abs": alpha_mol_abs,
        "alpha_mol_scat": alpha_mol_scat,
        "alpha_aer_abs": alpha_aer_abs,
        "alpha_aer_scat": alpha_aer_scat,
        "assumptions_flagged": assumptions_flagged,
    }


def _kruse_q(V_km: float) -> float:
    """Kruse modified q exponent per SPEC §3 M4."""
    if V_km > 50.0:
        return 1.6
    if V_km >= 6.0:
        return 1.3
    if V_km >= 1.0:
        return 0.16 * V_km + 0.34
    return V_km - 0.5


def _validate_inputs(inputs: dict) -> None:
    """Raise ValueError with a descriptive message if any required input
    is missing or out of range. Ranges from SPEC §3 M4 Inputs table."""
    required = ("V", "RH", "T_ambient", "wavelength", "R_slant")
    missing = [k for k in required if k not in inputs]
    if missing:
        raise ValueError(f"M4 missing required inputs: {missing}")

    validate_range(inputs["V"], "V", 0.5, 50.0)
    validate_range(inputs["RH"], "RH", 0.0, 1.0)
    validate_range(inputs["T_ambient"], "T_ambient", 253.0, 328.0)
    validate_range(inputs["wavelength"], "wavelength", 0.5e-6, 5.0e-6)
    validate_range(inputs["R_slant"], "R_slant", 50.0, 50_000.0)
