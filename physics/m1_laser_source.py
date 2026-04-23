"""M1 — Laser Source.

Defines the physical beam at the exit aperture of the laser head, before
the beam director. Pure Gaussian-beam characterization using the Siegman
M² formalism.

Reference: Siegman, A. E., *Lasers* (University Science Books, 1986),
Ch. 17 (M² formalism).
"""

import math

from physics.common import validate_range, wavelength_in_validated_set


def compute(inputs: dict) -> dict:
    """Compute exit-aperture beam parameters per SPEC §3 M1.

    Inputs (required keys):
      - P0 (W): output power at laser head, 100 – 100_000
      - M2 (—): beam-quality factor, 1.0 – 10.0
      - D (m): exit aperture diameter, 0.01 – 0.50
      - wavelength (m): laser wavelength, 0.5e-6 – 5.0e-6

    Outputs:
      - theta_diff (rad): full-angle diffraction-limited divergence
      - w0 (m): initial 1/e² beam radius at exit
      - zR (m): Rayleigh range (M²=1 reference form)
      - I_exit (W/m²): peak Gaussian irradiance at exit aperture
      - assumptions_flagged (list[str]): active modeling flags

    Equations (SPEC §3 M1):
        theta_diff = M² · 4·λ / (π·D)       [full-angle, Siegman convention]
        w0         = D / 2                   [beam fills aperture]
        zR         = π·w0² / λ               [Rayleigh range, M²=1 reference]
        I_exit     = 2·P0 / (π·w0²)          [Gaussian peak]
    """
    _validate_inputs(inputs)

    P0 = inputs["P0"]
    M2 = inputs["M2"]
    D = inputs["D"]
    wavelength = inputs["wavelength"]

    theta_diff = M2 * 4.0 * wavelength / (math.pi * D)
    w0 = D / 2.0
    zR = math.pi * w0 ** 2 / wavelength
    I_exit = 2.0 * P0 / (math.pi * w0 ** 2)

    assumptions_flagged: list[str] = []
    if not wavelength_in_validated_set(wavelength):
        assumptions_flagged.append(
            "wavelength outside validated set {1.06, 1.07, 1.55, 2.05 µm} "
            "— reduced confidence"
        )

    return {
        "theta_diff": theta_diff,
        "w0": w0,
        "zR": zR,
        "I_exit": I_exit,
        "assumptions_flagged": assumptions_flagged,
    }


def _validate_inputs(inputs: dict) -> None:
    """Raise ValueError with a descriptive message if any required input
    is missing or out of range. Ranges from SPEC §3 M1 Inputs table."""
    required = ("P0", "M2", "D", "wavelength")
    missing = [k for k in required if k not in inputs]
    if missing:
        raise ValueError(f"M1 missing required inputs: {missing}")

    validate_range(inputs["P0"], "P0", 100.0, 100_000.0)
    validate_range(inputs["M2"], "M2", 1.0, 10.0)
    validate_range(inputs["D"], "D", 0.01, 0.50)
    validate_range(inputs["wavelength"], "wavelength", 0.5e-6, 5.0e-6)
