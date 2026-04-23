"""M6 — Thermal Blooming.

Computes the Gebhardt distortion number N_D and the Smith-approximation
Strehl loss from beam-induced heating of the atmospheric path. For
N_D ≥ 5, also returns a blooming-induced spot-broadening contribution.

Immutable SPEC formulas per CLAUDE §7.1:
  - Gebhardt prefactor: 4·√2
  - Gladstone-Dale dn/dT with full T and P scaling:
        dn/dT = -0.93e-6 · (288/T) · (P/P₀)

M6 and M7 form a fixed-point iteration on `w_at_target` (SPEC §3 M6
"Iterative coupling with M7"); this module exposes the single-pass
kernel and lets the orchestrator drive the loop.

Reference: Gebhardt, F. G., "Twenty-five years of thermal blooming: an
overview," *Proc. SPIE* 1221 (1990), 2–25 — current engineering form
and 4√2 prefactor. Gebhardt 1976, *Applied Optics* 15(6), 1479–1493 —
original distortion-number derivation.
"""

import math

from physics.common import validate_positive, validate_range


_MOLAR_MASS_AIR = 0.029      # kg/mol (standard dry air)
_R_UNIVERSAL = 8.314         # J/(mol·K)
_C_P_AIR = 1005.0            # J/(kg·K) — weakly T-dependent, treated constant
_N0_AIR = 1.000293           # standard-air index at ~500 nm (SPEC §3 M6 NIR approx)
_DNDT_STP = -0.93e-6         # K⁻¹ at STP (Gladstone-Dale)
_T_REF = 288.0               # K — Gladstone-Dale reference temperature
_P_REF = 101325.0            # Pa — Gladstone-Dale reference pressure
_N_CRIT = 5.0                # Smith Strehl cutoff per SPEC §3 M6
_N_VALIDITY = 30.0           # upper bound of blooming-model validity per SPEC §3 M6


def compute(inputs: dict) -> dict:
    """Compute N_D, S_TB, and w_bloom per SPEC §3 M6.

    Inputs (required keys):
      - P_propagating (W): avg power along path (from M4 attenuation)
      - w_at_target (m): beam 1/e² radius at target (iterated w/ M7)
      - alpha_atm (1/m): total atmospheric absorption (from M4)
      - v_perp (m/s): crosswind component (from M3); must be > 0
      - R_slant (m): path length (from M3)
      - T_ambient (K): ambient air temperature (from M4)
      - P_atm (Pa): atmospheric pressure; default sea level = 101325

    Outputs:
      - N_D (—): Gebhardt distortion number
      - S_TB (—): thermal-blooming Strehl ratio (peak reduction)
      - w_bloom (m): blooming-induced 1/e² broadening; 0 if N_D < 5
      - assumptions_flagged (list[str])

    Equations (SPEC §3 M6, immutable per CLAUDE §7.1):
        ρ      = P_atm · 0.029 / (8.314 · T_ambient)
        dn/dT  = -0.93e-6 · (288/T_ambient) · (P_atm/101325)
        N_D    = 4·√2 · (-dn/dT) · (α_atm·P·R²) / (n₀·ρ·c_p·v_perp·w³)
        S_TB   = 1 / (1 + (N_D/5)²)
        w_bloom = 0                               if N_D < 5
                  w · √((N_D/5)² − 1) · 0.3       if N_D ≥ 5

    v_perp=0 raises ValueError (physically means no wind-driven heat
    clearing → unbounded N_D); the caller must substitute a small
    minimum or pass v_perp > 0.

    The 0.3 empirical broadening scaling is SPEC §10.4 HIGH UNCERTAINTY
    and is flagged whenever w_bloom > 0.
    """
    _validate_inputs(inputs)

    P = inputs["P_propagating"]
    w = inputs["w_at_target"]
    alpha_atm = inputs["alpha_atm"]
    v_perp = inputs["v_perp"]
    R = inputs["R_slant"]
    T = inputs["T_ambient"]
    P_atm = inputs["P_atm"]

    rho = P_atm * _MOLAR_MASS_AIR / (_R_UNIVERSAL * T)
    dn_dT = _DNDT_STP * (_T_REF / T) * (P_atm / _P_REF)

    numerator = 4.0 * math.sqrt(2.0) * (-dn_dT) * (alpha_atm * P * R ** 2)
    denominator = _N0_AIR * rho * _C_P_AIR * v_perp * w ** 3
    N_D = numerator / denominator

    S_TB = 1.0 / (1.0 + (N_D / _N_CRIT) ** 2)

    assumptions_flagged: list[str] = []

    if N_D < _N_CRIT:
        w_bloom = 0.0
    else:
        w_bloom = w * math.sqrt((N_D / _N_CRIT) ** 2 - 1.0) * 0.3
        assumptions_flagged.append(
            "blooming-broadening 0.3 empirical scaling used (SPEC §10.4 "
            "HIGH UNCERTAINTY — refine against wave-optics runs before "
            "formal use)"
        )
        if N_D > _N_VALIDITY:
            assumptions_flagged.append(
                f"N_D = {N_D:.1f} > 30: Smith Strehl approximation and "
                f"broadening scaling outside stated validity range "
                f"(SPEC §3 M6; engagement is in catastrophic-blooming regime)"
            )

    return {
        "N_D": N_D,
        "S_TB": S_TB,
        "w_bloom": w_bloom,
        "assumptions_flagged": assumptions_flagged,
    }


def _validate_inputs(inputs: dict) -> None:
    """Raise ValueError with a descriptive message if any required input
    is missing or out of range. Ranges reflect SPEC §3 M6 inputs table
    and the upstream modules (M3/M4) that feed M6."""
    required = (
        "P_propagating", "w_at_target", "alpha_atm", "v_perp",
        "R_slant", "T_ambient", "P_atm",
    )
    missing = [k for k in required if k not in inputs]
    if missing:
        raise ValueError(f"M6 missing required inputs: {missing}")

    validate_positive(inputs["P_propagating"], "P_propagating")
    validate_positive(inputs["w_at_target"], "w_at_target")
    validate_range(inputs["alpha_atm"], "alpha_atm", 0.0, 1.0e-2)
    validate_positive(inputs["v_perp"], "v_perp")
    validate_range(inputs["R_slant"], "R_slant", 50.0, 50_000.0)
    validate_range(inputs["T_ambient"], "T_ambient", 253.0, 328.0)
    validate_range(inputs["P_atm"], "P_atm", 5.0e4, 1.1e5)
