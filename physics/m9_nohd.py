"""M9 — Nominal Ocular Hazard Distance per ANSI Z136.1-2014.

Reports BOTH the top-hat (ANSI general) and Gaussian-peak conventions.
For a single-mode low-M² HEL, the top-hat form under-predicts the on-axis
hazard by a factor of √2 and should NOT be used as the safety-case
number. CLAUDE §7.1 pins this dual-convention reporting as immutable.

Equations (SPEC §3 M9):
    NOHD_tophat    = (1/θ_diff) · sqrt(4·P0 / (π·MPE)) − D/θ_diff
    NOHD_gausspeak = (1/θ_diff) · sqrt(8·P0 / (π·MPE)) − D/θ_diff
                   = sqrt(2) · (tophat pre-aperture term)

MPE per ANSI Z136.1-2014, CW intrabeam viewing:
    Band A (0.400–1.400 µm):
      t <  18e-6 s    MPE = 5e-3 / t_exp                [W/cm²]
      t ≤  10    s    MPE = 1.8e-3 · t_exp^(-1/4)       [W/cm²]
      t >  10    s    MPE = 1.0e-3                      [W/cm²]  (chronic)
    Band B (1.400–4.000 µm):
      t ≤  10    s    MPE = 0.56 · t_exp^(-3/4)         [W/cm²]
      t >  10    s    MPE = 0.1                         [W/cm²]  (chronic)
    Band C (> 4.000 µm):
      out of scope for v1; falls back to Band B with SPEC §3 M9
      placeholder flag.

The Band A retinal formula here omits the C_A correction factor
(C_A = 10^(0.002·(λ_nm − 700)) saturating at 5.0 for λ ≥ 1050 nm in
strict ANSI usage). The SPEC §3 M9 validation value (25.5 W/m² at
1.07 µm, 0.25 s) matches the no-C_A interpretation, which yields a
LARGER MPE-inverse and hence a LARGER NOHD — conservative for a
safety case (wider hazard zone). An explicit `assumptions_flagged`
entry cites SPEC §10.3 so operators wanting the less-conservative
C_A-corrected value can apply it externally.

Laser classification (SPEC §3 M9): Class 4 for P0 > 500 mW, which is
always true for an HEL (sanity range 100 W – 100 kW per Panel A). The
full enumeration is implemented for completeness and to support unit
tests at lower power.

References:
    ANSI Z136.1-2014, *Safe Use of Lasers*.
    IEC 60825-1:2014, *Safety of laser products — Part 1: Equipment
        classification*.
"""

import math

from physics.common import (
    validate_positive,
    validate_range,
    wavelength_in_validated_set,
)

# Band edges per ANSI Z136.1 / SPEC §3 M9.
_BAND_A_LO_M = 0.400e-6
_BAND_A_HI_M = 1.400e-6
_BAND_B_HI_M = 4.000e-6

# Class 4 threshold (SPEC §3 M9, CW NIR convention).
_CLASS4_W = 0.5
_CLASS3B_W = 0.005
_CLASS3R_W = 0.001
_CLASS1_W = 0.00039


def _mpe_irradiance_wpm2(wavelength_m: float, t_exp: float) -> float:
    """Return MPE irradiance in W/m² for the given λ and CW exposure.

    See module docstring for the ANSI Z136.1-2014 formulas used."""
    lam = wavelength_m

    if _BAND_A_LO_M <= lam <= _BAND_A_HI_M:
        # Band A — retinal hazard.
        if t_exp < 18.0e-6:
            # Pulsed regime; v1 is CW-only but the branch is defensive.
            mpe_wpcm2 = 5.0e-3 / t_exp
        elif t_exp <= 10.0:
            mpe_wpcm2 = 1.8e-3 * t_exp ** (-0.25)
        else:
            mpe_wpcm2 = 1.0e-3
    elif _BAND_A_HI_M < lam <= _BAND_B_HI_M:
        # Band B — eye-safer NIR.
        if t_exp <= 10.0:
            mpe_wpcm2 = 0.56 * t_exp ** (-0.75)
        else:
            mpe_wpcm2 = 0.1
    elif lam > _BAND_B_HI_M:
        # Band C (λ > 4 µm) — out of scope for v1; use Band B as placeholder.
        if t_exp <= 10.0:
            mpe_wpcm2 = 0.56 * t_exp ** (-0.75)
        else:
            mpe_wpcm2 = 0.1
    else:
        raise ValueError(
            f"wavelength must be ≥ {_BAND_A_LO_M*1e6:.3f} µm (Band A lower "
            f"edge per ANSI Z136.1), got {lam*1e6:.4f} µm"
        )

    return mpe_wpcm2 * 1.0e4  # W/cm² → W/m²


def _classify(p0_w: float) -> str:
    """Laser class per ANSI Z136.1-2014 / IEC 60825-1:2014 CW NIR
    convention. HEL (P0 > 500 mW) is always Class 4."""
    if p0_w > _CLASS4_W:
        return "Class 4"
    if p0_w > _CLASS3B_W:
        return "Class 3B"
    if p0_w > _CLASS3R_W:
        return "Class 3R"
    if p0_w > _CLASS1_W:
        return "Class 1M"
    return "Class 1"


def _validate_inputs(inputs: dict) -> None:
    required = ("P0", "D", "theta_diff", "wavelength", "t_exp")
    missing = [k for k in required if k not in inputs]
    if missing:
        raise ValueError(f"M9 missing required inputs: {missing}")

    validate_positive(inputs["P0"], "P0")
    validate_positive(inputs["D"], "D")
    validate_positive(inputs["theta_diff"], "theta_diff")
    validate_positive(inputs["wavelength"], "wavelength")
    # t_exp range from Panel F sanity (SPEC §5.1).
    validate_range(inputs["t_exp"], "t_exp", 0.25, 100.0)


def compute(inputs: dict) -> dict:
    """Compute MPE, both NOHD conventions, and the laser classification.

    Args:
        inputs: dict with keys P0 [W], D [m], theta_diff [rad, full-angle],
            wavelength [m], t_exp [s].

    Returns:
        dict with keys MPE [W/m²], NOHD_tophat [m], NOHD_gausspeak [m],
        laser_class [str], assumptions_flagged [list[str]].
    """
    _validate_inputs(inputs)

    p0 = inputs["P0"]
    d_ap = inputs["D"]
    theta = inputs["theta_diff"]
    lam = inputs["wavelength"]
    t_exp = inputs["t_exp"]

    mpe = _mpe_irradiance_wpm2(lam, t_exp)

    # SPEC §3 M9 NOHD formulas. The sqrt term is the range at which the
    # average-power irradiance (top-hat) or the on-axis peak (gausspeak)
    # first falls to MPE; D/θ is the aperture correction (the beam is
    # diverging from a real aperture, not a point).
    inv_theta = 1.0 / theta
    range_tophat = inv_theta * math.sqrt(4.0 * p0 / (math.pi * mpe))
    range_gausspeak = inv_theta * math.sqrt(8.0 * p0 / (math.pi * mpe))
    aperture_correction = d_ap * inv_theta

    nohd_tophat = max(0.0, range_tophat - aperture_correction)
    nohd_gausspeak = max(0.0, range_gausspeak - aperture_correction)

    laser_class = _classify(p0)

    flags: list[str] = []

    # CLAUDE §4.5 always-on: the NOHD convention choice is the first-order
    # discriminator for the safety case; the user must see both and make
    # the explicit choice. CLAUDE §7.1 pins this as immutable.
    flags.append(
        "NOHD reported under BOTH conventions (top-hat ANSI general; "
        "Gaussian-peak). Cite NOHD_gausspeak for single-mode HEL safety "
        "cases — top-hat under-predicts on-axis hazard by √2 for low-M² "
        "beams (SPEC §3 M9)."
    )

    # SPEC §10.3 HIGH UNCERTAINTY: MPE values and C_A correction.
    flags.append(
        "MPE per ANSI Z136.1-2014; C_A retinal correction (up to 5.0 at "
        "λ ≥ 1050 nm) NOT applied — gives a conservative (larger) NOHD. "
        "Cross-check against ANSI revision in force at release and apply "
        "C_A externally for operational (less-conservative) numbers "
        "(SPEC §10.3 HIGH UNCERTAINTY)."
    )

    # Wavelength outside SPEC-validated set.
    if not wavelength_in_validated_set(lam):
        flags.append(
            f"wavelength {lam*1e6:.3f} µm outside SPEC-validated set "
            "{1.06, 1.07, 1.55, 2.05} µm — reduced confidence "
            "(ARCH §4.3)."
        )

    # Band C placeholder.
    if lam > _BAND_B_HI_M:
        flags.append(
            "MPE for λ > 4 µm deferred to v2; using Band B formulas as "
            "placeholder (SPEC §3 M9 Band C)."
        )

    # t_exp < 18 µs enters the pulsed branch, which is outside v1 CW scope.
    if t_exp < 18.0e-6:
        flags.append(
            "t_exp < 18 µs uses pulsed-energy MPE (v1 is CW-only); "
            "result is a best-effort limit."
        )

    return {
        "MPE": mpe,
        "NOHD_tophat": nohd_tophat,
        "NOHD_gausspeak": nohd_gausspeak,
        "laser_class": laser_class,
        "assumptions_flagged": flags,
    }
