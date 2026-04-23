"""M3 — Engagement Geometry.

Computes slant-range geometry from user-specified emplacement, target
altitude, and horizontal range. Also defines the target dwell window
for lethality analysis (Plot B). The `available_dwell` output is the
SPEC §10.5 engagement-basket heuristic; the full tracker-dependent
dwell model is deferred to v2.

Reference: plain Euclidean geometry; SPEC §3 M3.
"""

import math

from physics.common import validate_range


_FOV_DEG_DEFAULT = 5.0


def compute(inputs: dict) -> dict:
    """Compute slant-range geometry per SPEC §3 M3.

    Inputs (required keys):
      - H_e (m): emplacement altitude AGL, 0 – 3000
      - R (m): slant range to target, 50 – 50_000
      - H_t (m): target altitude AGL, 0 – 5000
      - v_tgt (m/s): target velocity, 0 – 100
      - v_perp (m/s): crosswind perpendicular to beam, 0 – 30
        (listed here as M3 input per SPEC §3 M3; consumed by M6)

    Outputs:
      - R_slant (m): slant path length (equal to R for v1)
      - R_h (m): horizontal component of range
      - elevation_angle (rad): beam elevation angle (positive = looking up)
      - available_dwell (s): target time-in-basket heuristic (Plot B)
      - assumptions_flagged (list[str]): always includes the SPEC §10.5
        dwell-heuristic flag

    Equations (SPEC §3 M3):
        R_h             = sqrt(R² − (H_t − H_e)²)     [requires R ≥ |ΔH|]
        elevation_angle = arctan((H_t − H_e) / R_h)
        available_dwell = 2·R · tan(FOV/2) / v_tgt    [FOV = 5° default]
    """
    _validate_inputs(inputs)

    H_e = inputs["H_e"]
    R = inputs["R"]
    H_t = inputs["H_t"]
    v_tgt = inputs["v_tgt"]

    dH = H_t - H_e
    if R < abs(dH):
        raise ValueError(
            f"R={R} m must be >= |H_t - H_e|={abs(dH)} m (geometry infeasible)"
        )

    R_slant = R
    R_h = math.sqrt(R ** 2 - dH ** 2)
    elevation_angle = math.atan2(dH, R_h)

    fov_rad = math.radians(_FOV_DEG_DEFAULT)
    if v_tgt == 0:
        available_dwell = float("inf")
    else:
        available_dwell = 2.0 * R * math.tan(fov_rad / 2.0) / v_tgt

    assumptions_flagged: list[str] = [
        "v2 tracker-dependent dwell model deferred; heuristic used (SPEC §10.5)"
    ]

    return {
        "R_slant": R_slant,
        "R_h": R_h,
        "elevation_angle": elevation_angle,
        "available_dwell": available_dwell,
        "assumptions_flagged": assumptions_flagged,
    }


def _validate_inputs(inputs: dict) -> None:
    """Raise ValueError with a descriptive message if any required input
    is missing or out of range. Ranges from SPEC §3 M3 Inputs table."""
    required = ("H_e", "R", "H_t", "v_tgt", "v_perp")
    missing = [k for k in required if k not in inputs]
    if missing:
        raise ValueError(f"M3 missing required inputs: {missing}")

    validate_range(inputs["H_e"], "H_e", 0.0, 3000.0)
    validate_range(inputs["R"], "R", 50.0, 50_000.0)
    validate_range(inputs["H_t"], "H_t", 0.0, 5000.0)
    validate_range(inputs["v_tgt"], "v_tgt", 0.0, 100.0)
    validate_range(inputs["v_perp"], "v_perp", 0.0, 30.0)
