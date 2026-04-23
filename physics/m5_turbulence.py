"""M5 — Cn² and Atmospheric Turbulence.

Computes the refractive-turbulence contribution to beam spreading via
the Fried coherence length r₀ (spherical-wave form, appropriate for
diverging HEL beams from a finite aperture) and the resulting
long-term beam radius via the engineering form `w_turb = 2L/(k·r₀)`.

Immutable SPEC formulas per CLAUDE §7.1:
  - spherical-wave r₀:  r0_sph = (0.423·k²·∫Cn²·(z/L)^(5/3) dz)^(-3/5)
  - engineering w_turb: w_turb = 2L/(k·r0_sph)

Supported `cn2_model` values in this commit: 'constant'.
Other SPEC-enumerated values ('HV_5_7', 'HV_day', 'HV_night', 'custom')
raise NotImplementedError pending their own SPEC §3 M5 validation cases.

Reference: Andrews & Phillips, *Laser Beam Propagation through Random
Media* (2nd ed., 2005), Ch. 6 and Ch. 12.
"""

import math

from physics.common import validate_enum, validate_range


_CN2_MODELS = ["constant", "HV_5_7", "HV_day", "HV_night", "custom"]


def compute(inputs: dict) -> dict:
    """Compute Cn²-path integral, Fried r₀_sph, and w_turb per SPEC §3 M5.

    Inputs (required keys):
      - cn2_model (str): one of {'constant','HV_5_7','HV_day','HV_night','custom'}
      - Cn2_value (m^-2/3): constant-model Cn², 1e-17 – 1e-12
      - Cn2_ground (m^-2/3): HV-model ground Cn², 1e-16 – 1e-12
      - v_HV (m/s): HV-model high-altitude wind, 0 – 60
      - wavelength (m): laser wavelength, from M1
      - R_slant (m): path length, from M3
      - H_e (m): emplacement altitude, from M3
      - H_t (m): target altitude, from M3

    Outputs:
      - Cn2_integrated (m^(1/3)): ∫₀^L Cn²(z) · (z/L)^(5/3) dz
      - r0_sph (m): spherical-wave Fried coherence length
      - w_turb (m): long-term turbulent 1/e² radius at target
      - assumptions_flagged (list[str])

    Equations (SPEC §3 M5, immutable per CLAUDE §7.1):
        k              = 2π / λ
        Cn2_integrated = ∫₀^L Cn²(z) · (z/L)^(5/3) dz
        r0_sph         = (0.423 · k² · Cn2_integrated)^(-3/5)
        w_turb         = 2·L / (k · r0_sph)

    For cn2_model='constant':
        ∫ = Cn² · L · (3/8)   [closed form, no numerical integration]
    """
    _validate_inputs(inputs)

    cn2_model = inputs["cn2_model"]
    wavelength = inputs["wavelength"]
    L = inputs["R_slant"]

    k = 2.0 * math.pi / wavelength

    if cn2_model == "constant":
        Cn2 = inputs["Cn2_value"]
        Cn2_integrated = Cn2 * L * (3.0 / 8.0)
    else:
        raise NotImplementedError(
            f"cn2_model={cn2_model!r} is enumerated in SPEC §3 M5 but has no "
            f"validation case in this commit; implement alongside its SPEC §3 "
            f"M5 validation case."
        )

    r0_sph = (0.423 * k ** 2 * Cn2_integrated) ** (-3.0 / 5.0)
    w_turb = 2.0 * L / (k * r0_sph)

    assumptions_flagged: list[str] = [
        "spherical-wave r₀ form used (diverging HEL from finite aperture; "
        "Andrews & Phillips §6.5)",
        "engineering form w_turb = 2L/(k·r₀) used (conservative; Andrews & "
        "Phillips §6.5, CLAUDE §7.1)",
    ]

    return {
        "Cn2_integrated": Cn2_integrated,
        "r0_sph": r0_sph,
        "w_turb": w_turb,
        "assumptions_flagged": assumptions_flagged,
    }


def _validate_inputs(inputs: dict) -> None:
    """Raise ValueError with a descriptive message if any required input
    is missing or out of range. Ranges from SPEC §3 M5 Inputs table."""
    required = (
        "cn2_model", "Cn2_value", "Cn2_ground", "v_HV",
        "wavelength", "R_slant", "H_e", "H_t",
    )
    missing = [k for k in required if k not in inputs]
    if missing:
        raise ValueError(f"M5 missing required inputs: {missing}")

    validate_enum(inputs["cn2_model"], "cn2_model", _CN2_MODELS)
    validate_range(inputs["Cn2_value"], "Cn2_value", 1e-17, 1e-12)
    validate_range(inputs["Cn2_ground"], "Cn2_ground", 1e-16, 1e-12)
    validate_range(inputs["v_HV"], "v_HV", 0.0, 60.0)
    validate_range(inputs["wavelength"], "wavelength", 0.5e-6, 5.0e-6)
    validate_range(inputs["R_slant"], "R_slant", 50.0, 50_000.0)
    validate_range(inputs["H_e"], "H_e", 0.0, 3000.0)
    validate_range(inputs["H_t"], "H_t", 0.0, 5000.0)
