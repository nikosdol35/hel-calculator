"""M3 — Engagement Geometry.

SPEC v2.0 §3 M3 — tracker-supported dwell + threat-trajectory model.

Two operating modes (selected by which inputs are present):

* **v2.0 contract** (preferred): inputs include ``R_detect``,
  ``R_min``, and ``engagement_geometry``. Available dwell is the
  trajectory closure time per ``physics.m_trajectory``.

* **v1.x backward-compat** (transitional): inputs include the
  pre-v2.0 ``R`` and ``v_perp``. ``R_detect`` is taken to equal
  ``R``; ``R_min`` defaults to 100 m; ``engagement_geometry``
  defaults to ``"head_on"``. The v1 FOV-based dwell formula
  ``2·R·tan(FOV/2)/v_tgt`` is also retained so existing callers
  continue to see identical numbers.

The backward-compat path is removed in PR 5–6 of
``docs/tracker_dwell_plan_2026-04-25.md`` once the orchestrator and
UI have migrated to the v2.0 contract. Until then, v1 callers (the
existing orchestrator chain and golden fixtures) continue to work
without modification.

Reference: plain Euclidean geometry; SPEC §3 M3 v2.0.
"""

import math

from physics.common import validate_range
from physics.m_trajectory import (
    available_dwell as _trajectory_dwell,
    R_at_dwell_end as _trajectory_R_end,
    validate_trajectory_inputs,
)


_FOV_DEG_DEFAULT = 5.0  # v1.x FOV for backward-compat dwell formula
_R_MIN_DEFAULT_M = 100.0  # v2.0 default standoff (per plan §14)


def compute(inputs: dict) -> dict:
    """Compute slant-range geometry per SPEC §3 M3 v2.0.

    Inputs are accepted in either the v2.0 or the v1.x shape; the
    presence of ``engagement_geometry`` selects v2.0 mode.

    v2.0 inputs (required when engagement_geometry is present):
      - ``H_e`` (m): emplacement altitude AGL, 0 – 3000
      - ``R_detect`` (m): initial slant range at detection, 50 – 50 000
      - ``R_min`` (m): engagement-end standoff, 10 – 5 000
      - ``H_t`` (m): target altitude AGL (constant during engagement),
        0 – 5000
      - ``v_tgt`` (m/s): target velocity along the threat trajectory,
        0 – 100
      - ``engagement_geometry`` (str): ``"head_on"`` | ``"lateral"``

    v1.x backward-compat inputs (when ``engagement_geometry`` absent):
      - ``H_e``, ``R``, ``H_t``, ``v_tgt``, ``v_perp``: as in v1.12.

    Outputs (identical key set for both modes):
      - ``R_slant`` (m): initial slant range (= R_detect at t=0)
      - ``R_h`` (m): horizontal component at t=0
      - ``elevation_angle`` (rad): beam elevation at t=0 (positive up)
      - ``available_dwell`` (s): trajectory dwell window (v2.0) or
        FOV-crossing heuristic (v1.x)
      - ``R_at_dwell_end`` (m): slant range at the engagement-end
        moment (R_min for v2.0 moving targets; R_detect for stationary
        and for v1.x mode where there is no trajectory)
      - ``assumptions_flagged`` (list[str])
    """
    if "engagement_geometry" in inputs:
        return _compute_v2(inputs)
    return _compute_v1_backward_compat(inputs)


# ---------------------------------------------------------------------------
# v2.0 path — trajectory-supported dwell
# ---------------------------------------------------------------------------

def _compute_v2(inputs: dict) -> dict:
    _validate_v2_inputs(inputs)

    H_e = inputs["H_e"]
    R_detect = inputs["R_detect"]
    R_min = inputs.get("R_min", _R_MIN_DEFAULT_M)
    H_t = inputs["H_t"]
    v_tgt = inputs["v_tgt"]
    geometry = inputs["engagement_geometry"]

    # Trajectory-level validators (R_detect ≥ R_min, etc.) — raise
    # ValueError on contract violations.
    validate_trajectory_inputs(R_detect, R_min, v_tgt, geometry)

    dH = H_t - H_e
    if R_detect < abs(dH):
        raise ValueError(
            f"R_detect={R_detect} m must be >= |H_t - H_e|={abs(dH)} m "
            f"(geometry infeasible)"
        )

    R_slant = R_detect
    R_h = math.sqrt(R_detect ** 2 - dH ** 2)
    elevation_angle = math.atan2(dH, R_h)

    available_dwell = _trajectory_dwell(R_detect, R_min, v_tgt, geometry)
    R_at_end = _trajectory_R_end(R_min, v_tgt, R_detect=R_detect)

    flags: list[str] = [
        "tracker-supported trajectory; pre-engagement detection at R_detect "
        "(SPEC v2.0 §3 M3)",
    ]

    return {
        "R_slant": R_slant,
        "R_h": R_h,
        "elevation_angle": elevation_angle,
        "available_dwell": available_dwell,
        "R_at_dwell_end": R_at_end,
        "assumptions_flagged": flags,
    }


def _validate_v2_inputs(inputs: dict) -> None:
    """v2.0 mode validators. Trajectory-specific bounds are enforced
    by ``validate_trajectory_inputs`` after this passes."""
    required = ("H_e", "R_detect", "H_t", "v_tgt", "engagement_geometry")
    missing = [k for k in required if k not in inputs]
    if missing:
        raise ValueError(f"M3 (v2.0 mode) missing required inputs: {missing}")

    validate_range(inputs["H_e"], "H_e", 0.0, 3000.0)
    validate_range(inputs["R_detect"], "R_detect", 50.0, 50_000.0)
    R_min = inputs.get("R_min", _R_MIN_DEFAULT_M)
    validate_range(R_min, "R_min", 10.0, 5_000.0)
    validate_range(inputs["H_t"], "H_t", 0.0, 5000.0)
    validate_range(inputs["v_tgt"], "v_tgt", 0.0, 100.0)


# ---------------------------------------------------------------------------
# v1.x backward-compat path — preserved bit-for-bit until PR 5-6
# ---------------------------------------------------------------------------

def _compute_v1_backward_compat(inputs: dict) -> dict:
    _validate_v1_inputs(inputs)

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

    flags: list[str] = [
        "v2 tracker-dependent dwell model deferred; heuristic used "
        "(SPEC §10.5)",
    ]

    return {
        "R_slant": R_slant,
        "R_h": R_h,
        "elevation_angle": elevation_angle,
        "available_dwell": available_dwell,
        # In v1.x mode there is no trajectory; the engagement happens
        # at R = R_detect. Reporting R_at_dwell_end = R_slant matches
        # that interpretation.
        "R_at_dwell_end": R_slant,
        "assumptions_flagged": flags,
    }


def _validate_v1_inputs(inputs: dict) -> None:
    """v1.x mode validators (preserved verbatim from v1.12 for
    backward compatibility). Removed in PR 5-6."""
    required = ("H_e", "R", "H_t", "v_tgt", "v_perp")
    missing = [k for k in required if k not in inputs]
    if missing:
        raise ValueError(
            f"M3 (v1.x backward-compat) missing required inputs: {missing}"
        )

    validate_range(inputs["H_e"], "H_e", 0.0, 3000.0)
    validate_range(inputs["R"], "R", 50.0, 50_000.0)
    validate_range(inputs["H_t"], "H_t", 0.0, 5000.0)
    validate_range(inputs["v_tgt"], "v_tgt", 0.0, 100.0)
    validate_range(inputs["v_perp"], "v_perp", 0.0, 30.0)
