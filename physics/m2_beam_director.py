"""M2 — Beam Director Transmission.

Applies a single end-to-end optical-train transmission factor to account
for Coudé-path mirror losses, exit-window absorption, and contamination
margin. Per SPEC §3 M2, no external citation is required — η_opt = 0.85
is a typical value for a 5–7 mirror Coudé path with a protected exit
window; the user may override.
"""

from physics.common import validate_range


def compute(inputs: dict) -> dict:
    """Compute post-director exit power per SPEC §3 M2.

    Inputs (required keys):
      - P0 (W): power at laser head, 100 – 100_000 (from M1 chain)
      - eta_opt (—): end-to-end transmission, 0.50 – 0.99

    Outputs:
      - P_exit (W): power at beam-director exit aperture
      - assumptions_flagged (list[str]): typically empty for M2

    Equation (SPEC §3 M2):
        P_exit = η_opt · P₀
    """
    _validate_inputs(inputs)

    P0 = inputs["P0"]
    eta_opt = inputs["eta_opt"]

    P_exit = eta_opt * P0

    assumptions_flagged: list[str] = []

    return {
        "P_exit": P_exit,
        "assumptions_flagged": assumptions_flagged,
    }


def _validate_inputs(inputs: dict) -> None:
    """Raise ValueError with a descriptive message if any required input
    is missing or out of range. Ranges from SPEC §3 M2 Inputs table
    (P0 range inherited from SPEC §3 M1)."""
    required = ("P0", "eta_opt")
    missing = [k for k in required if k not in inputs]
    if missing:
        raise ValueError(f"M2 missing required inputs: {missing}")

    validate_range(inputs["P0"], "P0", 100.0, 100_000.0)
    validate_range(inputs["eta_opt"], "eta_opt", 0.50, 0.99)
