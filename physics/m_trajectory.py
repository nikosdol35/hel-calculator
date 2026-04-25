"""Threat-trajectory model — closed-form R(t) and t_dwell.

SPEC v2.0 §3 M3 (post-tracker-dwell rework). The director is
assumed to track the target perfectly; the available dwell window
is bounded by the time the target takes to traverse the trajectory
from initial detection at ``R_detect`` to engagement-end at
``R_min``.

Two engagement geometries are supported:

* **head-on** — target closes along the line of sight at constant
  ``v_tgt``. Slant range decreases linearly:
      R(t)    = R_detect − v_tgt · t
      t_dwell = (R_detect − R_min) / v_tgt

* **lateral** — target flies a straight perpendicular line past the
  director with closest-approach distance ``R_min``. Engagement
  window runs from R_detect inbound to closest approach (per the
  v2.0 design decision). Define x_0 = √(R_detect² − R_min²) — the
  axial distance from closest approach at t=0:
      R(t)    = √(R_min² + (x_0 − v_tgt · t)²)
      t_dwell = x_0 / v_tgt = √(R_detect² − R_min²) / v_tgt

Stationary edge case: ``v_tgt < STATIONARY_THRESHOLD`` (0.1 m/s) is
treated as a single-point engagement at R = R_detect with
t_dwell = STATIONARY_DWELL_S (60 s, the M8 timeout). Preserves the
v1 single-point analysis as the hovering-target case.

Pure module — no streamlit, no orchestrator dependency. Imports
only ``math``. Validators raise ``ValueError`` with descriptive
messages on contract violations.
"""
from __future__ import annotations

import math
from typing import Callable, Literal


# --- Constants --------------------------------------------------------------

#: Targets slower than this are treated as stationary (in m/s). The
#: floor is set so that any small non-zero v_tgt produces a finite
#: t_dwell on the trajectory; below it, the linear or hyperbolic
#: trajectory time would diverge or be numerically unstable.
STATIONARY_THRESHOLD_MPS: float = 0.1

#: Dwell-window length applied to stationary engagements (in s).
#: Matches the M8 PDE-solver timeout per ``physics/m8_burnthrough.py``
#: ``_SIM_TIMEOUT_S``; the engagement integrates the heat PDE at
#: constant range R = R_detect for up to this long.
STATIONARY_DWELL_S: float = 60.0


EngagementGeometry = Literal["head_on", "lateral"]


# --- Validation -------------------------------------------------------------

def validate_trajectory_inputs(
    R_detect: float,
    R_min: float,
    v_tgt: float,
    engagement_geometry: str,
) -> None:
    """Raise ``ValueError`` if any input is outside the v2.0 contract.

    SPEC v2.0 §3 M3 validator constraints:
      - ``R_detect ≥ R_min`` (geometrically required for both geometries;
        lateral derivation needs ``R_detect² ≥ R_min²`` since slant =
        √(R_min² + axial²)).
      - ``v_tgt ≥ 0``. Below ``STATIONARY_THRESHOLD_MPS`` the trajectory
        is treated as stationary (handled in `available_dwell`).
      - ``engagement_geometry`` ∈ {``"head_on"``, ``"lateral"``}.
      - ``R_detect``, ``R_min`` strictly positive.
    """
    if engagement_geometry not in ("head_on", "lateral"):
        raise ValueError(
            f"engagement_geometry must be 'head_on' or 'lateral', "
            f"got {engagement_geometry!r}"
        )
    if not (R_detect > 0):
        raise ValueError(f"R_detect must be > 0 m, got {R_detect}")
    if not (R_min > 0):
        raise ValueError(f"R_min must be > 0 m, got {R_min}")
    if R_detect < R_min:
        raise ValueError(
            f"R_detect ({R_detect} m) must be >= R_min ({R_min} m); "
            f"target cannot start inside the engagement-end range"
        )
    if v_tgt < 0:
        raise ValueError(f"v_tgt must be >= 0, got {v_tgt}")


def is_stationary(v_tgt: float) -> bool:
    """True when the target is slow enough to treat as stationary."""
    return v_tgt < STATIONARY_THRESHOLD_MPS


# --- Available dwell --------------------------------------------------------

def available_dwell(
    R_detect: float,
    R_min: float,
    v_tgt: float,
    engagement_geometry: EngagementGeometry,
) -> float:
    """Trajectory dwell window in seconds.

    Returns ``STATIONARY_DWELL_S`` when ``v_tgt`` is below the
    stationary threshold (0.1 m/s). Otherwise computes the closed-form
    trajectory closure time from R_detect to R_min per the geometry:

        head-on: (R_detect − R_min) / v_tgt
        lateral: √(R_detect² − R_min²) / v_tgt

    Inputs are NOT re-validated here; call
    ``validate_trajectory_inputs`` first or pass already-validated
    values. Both formulas degenerate to 0 when R_detect = R_min, which
    the validator rejects as a contract error before reaching this
    function.
    """
    if is_stationary(v_tgt):
        return STATIONARY_DWELL_S
    if engagement_geometry == "head_on":
        return (R_detect - R_min) / v_tgt
    if engagement_geometry == "lateral":
        return math.sqrt(R_detect * R_detect - R_min * R_min) / v_tgt
    # Validator above already rejects unknown geometry; defensive only.
    raise ValueError(f"Unknown engagement_geometry: {engagement_geometry!r}")


# --- Trajectory R(t) -------------------------------------------------------

def trajectory_R_of_t(
    R_detect: float,
    R_min: float,
    v_tgt: float,
    engagement_geometry: EngagementGeometry,
) -> Callable[[float], float]:
    """Return a callable R(t) for ``t ∈ [0, t_dwell]``.

    For the **stationary** case (``v_tgt`` below the threshold) the
    returned callable is the constant function ``lambda t: R_detect``
    — single-point analysis at the initial detection range.

    For **head-on**: linear closure.
    For **lateral**: hyperbolic distance from the perpendicular line.

    The callable does NOT clamp to ``[0, t_dwell]``; callers may
    sample beyond the engagement window for diagnostic plotting (e.g.,
    showing what would have happened if the engagement could have
    continued). The orchestrator's PDE loop is responsible for stopping
    at ``t = t_dwell``.
    """
    if is_stationary(v_tgt):
        constant_R = R_detect

        def R_stationary(_t: float) -> float:
            return constant_R

        return R_stationary

    if engagement_geometry == "head_on":
        R_d = R_detect
        v = v_tgt

        def R_head_on(t: float) -> float:
            return R_d - v * t

        return R_head_on

    if engagement_geometry == "lateral":
        R_m_sq = R_min * R_min
        x_0 = math.sqrt(R_detect * R_detect - R_m_sq)
        v = v_tgt

        def R_lateral(t: float) -> float:
            x_remaining = x_0 - v * t
            return math.sqrt(R_m_sq + x_remaining * x_remaining)

        return R_lateral

    raise ValueError(f"Unknown engagement_geometry: {engagement_geometry!r}")


# --- Convenience: R at engagement-end --------------------------------------

def R_at_dwell_end(
    R_min: float,
    v_tgt: float,
    R_detect: float | None = None,
) -> float:
    """Slant range at the engagement-end moment (= R_min by construction
    for both head-on and lateral, except in the stationary case).

    The stationary case has no closure: the engagement runs at constant
    R = R_detect, so the "end" range is the same as the start. We
    return R_detect in that case; if the caller hasn't supplied it the
    stationary case is unrepresentable and we raise.
    """
    if is_stationary(v_tgt):
        if R_detect is None:
            raise ValueError(
                "R_at_dwell_end for a stationary target requires R_detect"
            )
        return R_detect
    return R_min


__all__ = [
    "EngagementGeometry",
    "STATIONARY_THRESHOLD_MPS",
    "STATIONARY_DWELL_S",
    "available_dwell",
    "is_stationary",
    "R_at_dwell_end",
    "trajectory_R_of_t",
    "validate_trajectory_inputs",
]
