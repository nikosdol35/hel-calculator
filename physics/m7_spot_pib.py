"""M7 — Spot Size and Power-in-the-Bucket.

The integrating module. Combines every upstream 1/e² spot-radius
contribution — exact-Gaussian diffraction, turbulence (long-term
convention), per-axis jitter, blooming-induced broadening — into the
total spot radius at the target, then computes peak irradiance and
power-in-the-bucket for a user-specified aimpoint disk.

Immutable SPEC formulas per CLAUDE §7.1 (each was the subject of a
plan-revision bug):
  - Exact Gaussian: w_diff = w₀·√(1 + (M²·L/zR)²), NOT the far-field
    asymptote. The far-field form under-predicts by 2×–15× at typical
    C-UAS engagement ranges.
  - Bucket RADIUS in the PIB exponent: R_aim = d_aim/2, not d_aim.
  - Jitter factor of 2: w_jit = 2·σ_jit·L (σ → 1/e² radius per axis).
  - Quadrature: w_total² = w_diff² + w_turb² + w_jit² + w_bloom²
    (four independent contributions).
  - Single-count turbulence: w_turb² enters w_total; NO S_turb Strehl.
    S_total = S_TB · S_opt only (S_opt = 1 in v1).
  - Gaussian peak with factor 2: I_peak = 2·P/(π·w²).

M6↔M7 fixed-point iteration is driven by the orchestrator — M7 exposes
the single-pass kernel and is a pure function of its inputs.

References:
  - Siegman, *Lasers* (1986) Ch. 17 (M² propagation)
  - Andrews & Phillips, Ch. 6 (Gaussian-beam propagation in turbulence)
  - Born & Wolf, Ch. 8 (closed-form Gaussian PIB)
  - Perram et al., *An Introduction to Laser Weapon Systems* (DEPS)
    for HEL engineering conventions.
"""

import math

from physics.common import validate_positive, validate_range


def compute(inputs: dict) -> dict:
    """Compute w_total, I_peak, PIB_fraction, and derived per SPEC §3 M7.

    Inputs (required keys):
      - P_exit (W): power at beam-director exit (from M2)
      - tau_atm (—): atmospheric transmission (from M4), 0 ≤ τ ≤ 1
      - w0 (m): launch 1/e² radius (from M1)
      - zR (m): Rayleigh range (from M1)
      - M2 (—): beam-quality factor (from M1)
      - wavelength (m): laser wavelength (from M1)
      - R_slant (m): path length (from M3)
      - sigma_jit (rad): per-axis jitter RMS (user input)
      - r0_sph (m): spherical-wave Fried length (from M5); math.inf
        for the turbulence-free limit
      - S_TB (—): thermal-blooming Strehl (from M6), 0 ≤ S ≤ 1
      - w_bloom (m): blooming broadening (from M6), ≥ 0
      - d_aim (m): aimpoint disk DIAMETER (user input)

    Outputs (SPEC §3 M7 outputs table):
      - w_diff, w_turb, w_jit, w_total (m)
      - d_spot (m) = 2·w_total
      - I_peak (W/m²)
      - PIB_fraction (—), P_aim (W), I_avg_aim (W/m²)
      - assumptions_flagged (list[str])
    """
    _validate_inputs(inputs)

    P_exit = inputs["P_exit"]
    tau_atm = inputs["tau_atm"]
    w0 = inputs["w0"]
    zR = inputs["zR"]
    M2 = inputs["M2"]
    wavelength = inputs["wavelength"]
    L = inputs["R_slant"]
    sigma_jit = inputs["sigma_jit"]
    r0_sph = inputs["r0_sph"]
    S_TB = inputs["S_TB"]
    w_bloom = inputs["w_bloom"]
    d_aim = inputs["d_aim"]

    k = 2.0 * math.pi / wavelength

    # Exact-Gaussian diffraction (SPEC §3 M7 critical note #1 — NOT the
    # far-field asymptote).
    w_diff = w0 * math.sqrt(1.0 + (M2 * L / zR) ** 2)

    # Turbulence: engineering form w_turb = 2L/(k·r₀_sph). r0_sph = ∞
    # zeros this term (Python: 1/inf == 0).
    w_turb = 2.0 * L / (k * r0_sph)

    # Jitter: per-axis σ → 1/e² radius per axis (factor of 2 is the
    # σ→w conversion, NOT a 2D radial factor).
    w_jit = 2.0 * sigma_jit * L

    # Quadrature combination — four independent contributions.
    w_total = math.sqrt(w_diff ** 2 + w_turb ** 2 + w_jit ** 2 + w_bloom ** 2)
    d_spot = 2.0 * w_total

    # Strehl: ONLY S_TB (phase-only blooming) and S_opt (=1 in v1).
    # Turbulence is already in w_total — never double-count it as a
    # multiplicative Strehl factor.
    S_opt = 1.0
    S_total = S_TB * S_opt

    # Gaussian peak irradiance with factor 2.
    I_peak = 2.0 * P_exit * tau_atm * S_total / (math.pi * w_total ** 2)

    # Power-in-the-bucket: Gaussian beam, circular aperture, bucket
    # RADIUS (not diameter) in the exponent.
    R_aim = d_aim / 2.0
    PIB_fraction = 1.0 - math.exp(-2.0 * R_aim ** 2 / w_total ** 2)
    P_aim = P_exit * tau_atm * S_total * PIB_fraction
    I_avg_aim = P_aim / (math.pi * R_aim ** 2)

    assumptions_flagged: list[str] = [
        "spot-size convention: long-term 1/e² radius via quadrature of "
        "diffraction + turbulence + jitter + blooming; multiplicative "
        "Strehl = S_TB only (S_opt=1 in v1, no S_turb — turbulence enters "
        "via w_turb). CLAUDE §7.1 invariants.",
    ]

    # Regime guard: diffraction should not be dominated by a single
    # exotic term in a way that makes the quadrature misleading. Flag
    # when blooming broadening exceeds the diffraction term — this is
    # the blooming-limited regime and usually indicates the engagement
    # is not viable without beam-director mitigation.
    if w_bloom > w_diff:
        assumptions_flagged.append(
            f"blooming-limited regime: w_bloom ({w_bloom*100:.1f} cm) > "
            f"w_diff ({w_diff*100:.1f} cm); engagement viability is "
            f"governed by M6's 0.3 empirical broadening factor "
            f"(SPEC §10.4 HIGH UNCERTAINTY)"
        )

    return {
        "w_diff": w_diff,
        "w_turb": w_turb,
        "w_jit": w_jit,
        "w_total": w_total,
        "d_spot": d_spot,
        "I_peak": I_peak,
        "PIB_fraction": PIB_fraction,
        "P_aim": P_aim,
        "I_avg_aim": I_avg_aim,
        "assumptions_flagged": assumptions_flagged,
    }


def _validate_inputs(inputs: dict) -> None:
    """Raise ValueError with a descriptive message if any required input
    is missing or out of range. Ranges reflect SPEC §3 M1/M2/M3/M4/M5/M6
    upstream bounds and reasonable user-input bounds."""
    required = (
        "P_exit", "tau_atm", "w0", "zR", "M2", "wavelength",
        "R_slant", "sigma_jit", "r0_sph", "S_TB", "w_bloom", "d_aim",
    )
    missing = [k for k in required if k not in inputs]
    if missing:
        raise ValueError(f"M7 missing required inputs: {missing}")

    validate_positive(inputs["P_exit"], "P_exit")
    validate_range(inputs["tau_atm"], "tau_atm", 0.0, 1.0)
    validate_positive(inputs["w0"], "w0")
    validate_positive(inputs["zR"], "zR")
    validate_range(inputs["M2"], "M2", 1.0, 10.0)
    validate_range(inputs["wavelength"], "wavelength", 0.5e-6, 5.0e-6)
    validate_range(inputs["R_slant"], "R_slant", 50.0, 50_000.0)
    validate_range(inputs["sigma_jit"], "sigma_jit", 0.0, 1.0e-3)
    validate_positive(inputs["r0_sph"], "r0_sph")  # math.inf is allowed
    validate_range(inputs["S_TB"], "S_TB", 0.0, 1.0)
    validate_range(inputs["w_bloom"], "w_bloom", 0.0, 10.0)
    validate_range(inputs["d_aim"], "d_aim", 0.005, 1.0)
