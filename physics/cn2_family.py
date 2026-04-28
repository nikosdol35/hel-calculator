"""Family of peak-irradiance vs detection-range curves at varying Cn².

Plot O consumes this module's output to overlay the user's current
scenario with 4-5 reference Cn² atmospheres, so the operator sees
how robust their engagement is to changing turbulence conditions.

Pure module — no Streamlit imports.

**Lightweight compute path** — same simplification spirit as
`physics.jitter_sensitivity`:

  1. **M1** (laser geometry: w0, zR) — read from chain output, no
     re-run. Independent of R and Cn².
  2. **M2** (beam-director power: P_exit) — read from chain output.
     Independent of R and Cn².
  3. **M4** (atmospheric transmission: tau_atm) — runs per R cell.
     Independent of Cn².
  4. **M5** (turbulence: r0_sph) — runs per (R, Cn²) cell.
  5. **M7** (spot / PIB / I_peak) — runs per (R, Cn²) cell with
     ``S_TB = 1.0`` and ``w_bloom = 0`` (skip M6 blooming).

  M3 (engagement timing), M6 (blooming), M8 (burn-through PDE), and
  M9-M11 (safety / power / validation) are all skipped because none
  of them affect I_peak directly.

Per-cell cost: ~5 ms. Total for 5 reference Cn² × 15 ranges = ~400 ms.

The user's actual Cn² (whatever they have set in the sidebar) is
returned as a 6th highlighted curve — UNLESS it's within 5 % of a
reference value, in which case the reference at that level is
suppressed and the user's curve replaces it (no duplicate lines).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from physics import m4_atmosphere, m5_turbulence, m7_spot_pib


# Reference Cn² values spanning ~3 decades of realistic conditions.
# Order matters — preserved in the returned dataclass for the plot.
_REFERENCE_CN2_LEVELS: tuple[tuple[str, float], ...] = (
    ("Pristine", 1.0e-15),
    ("Clear", 1.0e-14),
    ("Day", 1.0e-13),
    ("Strong", 5.0e-13),
    ("Severe", 1.0e-12),
)

# Relative tolerance for "user's Cn² ≈ a reference Cn²" duplicate
# suppression. 5 % is generous enough to absorb floating-point
# round-trip noise from URL-encoded inputs without merging genuinely
# different atmospheres.
_DUPLICATE_REL_TOL = 0.05


@dataclass(frozen=True)
class CN2FamilyCurves:
    """Output of `compute_cn2_family_curves`.

    Holds one curve per Cn² level. The reference levels are listed
    in `reference_curves` in the same order as ``_REFERENCE_CN2_LEVELS``;
    the user's actual curve is in `current_curve` (always populated).
    When the user's Cn² duplicates a reference, that reference is
    omitted from `reference_curves` (its label is in `suppressed_label`).
    """
    range_axis_km: tuple[float, ...]                    # x-axis values, common across curves
    reference_curves: tuple[tuple[str, float, tuple[float, ...]], ...]
    # ^^ tuple of (label, cn2_value, I_peak_wpcm2) per reference level
    current_curve: tuple[float, tuple[float, ...]]      # (user's cn2_value, I_peak_wpcm2)
    suppressed_label: str | None                        # label of any reference that was duplicate-suppressed
    current_R_km: float                                  # user's R_detect in km (for the star)
    current_I_peak_wpcm2: float | None                  # I_peak at user's R_detect on their curve (for star y)
    cn2_model: str                                       # "Constant" or "HV_5_7"


def _build_inputs_at_R(base_inputs: dict, R_m: float, cn2_override: float) -> dict:
    """Build a per-cell inputs dict with the user's R_detect replaced
    by the sweep R, and the user's active Cn² field replaced by the
    override. The other model-specific Cn² field stays at the user's
    setting (we don't change atmospheric MODEL, only the value).
    """
    inputs = dict(base_inputs)
    inputs["R_slant"] = float(R_m)
    cn2_model = inputs.get("cn2_model", "HV_5_7")
    # Constant-Cn² model uses Cn2_value; HV-family models use
    # Cn2_ground (since Cn² varies with altitude). Handle both
    # casings ("constant" lowercase per SPEC, plus defensive
    # "Constant").
    if cn2_model in ("constant", "Constant"):
        inputs["Cn2_value"] = float(cn2_override)
    else:
        inputs["Cn2_ground"] = float(cn2_override)
    return inputs


def _compute_one_cell(
    base_inputs: dict, R_m: float, cn2_override: float,
    w0: float, zR: float, P_exit: float,
) -> float | None:
    """Compute I_peak (W/cm²) at one (R, Cn²) cell using only
    M4 + M5 + M7 with S_TB = 1, w_bloom = 0.

    Returns None if any module rejects the inputs (out-of-range,
    bad combination) — caller treats this as a missing data point.
    """
    inputs_at_R = _build_inputs_at_R(base_inputs, R_m, cn2_override)
    try:
        # M4 — atmospheric transmission at this R (independent of Cn²,
        # but tau_atm is a per-R input to M7).
        m4_out = m4_atmosphere.compute({
            "wavelength": inputs_at_R["wavelength"],
            "R_slant": inputs_at_R["R_slant"],
            "V": inputs_at_R["V"],
            "RH": inputs_at_R["RH"],
            "T_ambient": inputs_at_R["T_ambient"],
            "P_atm": inputs_at_R["P_atm"],
            "H_e": inputs_at_R.get("H_e", 2.0),
            "H_t": inputs_at_R.get("H_t", 200.0),
        })
        # M5 — turbulence with the overridden Cn².
        m5_out = m5_turbulence.compute({
            "cn2_model": inputs_at_R["cn2_model"],
            "Cn2_value": inputs_at_R.get("Cn2_value", 1.0e-14),
            "Cn2_ground": inputs_at_R.get("Cn2_ground", 1.7e-14),
            "v_HV": inputs_at_R.get("v_HV", 21.0),
            "wavelength": inputs_at_R["wavelength"],
            "R_slant": inputs_at_R["R_slant"],
            "H_e": inputs_at_R.get("H_e", 2.0),
            "H_t": inputs_at_R.get("H_t", 200.0),
        })
        # M7 — spot / PIB / I_peak with S_TB=1, w_bloom=0.
        m7_out = m7_spot_pib.compute({
            "P_exit": P_exit,
            "tau_atm": m4_out["tau_atm"],
            "w0": w0,
            "zR": zR,
            "M2": inputs_at_R["M2"],
            "wavelength": inputs_at_R["wavelength"],
            "R_slant": inputs_at_R["R_slant"],
            "sigma_jit": inputs_at_R["sigma_jit"],
            "r0_sph": m5_out["r0_sph"],
            "S_TB": 1.0,
            "w_bloom": 0.0,
            "d_aim": inputs_at_R["d_aim"],
        })
    except (ValueError, KeyError):
        return None

    # I_peak from M7 is in W/m² — convert to W/cm² for display.
    I_peak_wpm2 = float(m7_out.get("I_peak", 0.0))
    return I_peak_wpm2 * 1.0e-4


def compute_cn2_family_curves(
    base_inputs: dict,
    ranges_m: tuple[float, ...] | None = None,
    cn2_levels: tuple[tuple[str, float], ...] | None = None,
) -> CN2FamilyCurves:
    """Compute peak irradiance vs detection range for a family of Cn² values.

    Args:
      base_inputs: merged orchestrator-result dict (the same shape
        passed to ``render_tab_engagement``). Must include the v2.0
        trajectory key ``engagement_geometry`` and ``by_module`` (so
        we can read M1's w0/zR and M2's P_exit without re-running them).
      ranges_m: tuple of slant ranges in metres. Defaults to a
        log-spaced sweep from 100 m to 2× R_detect (15 cells).
      cn2_levels: tuple of (label, Cn²) reference levels. Defaults
        to the 5 levels in ``_REFERENCE_CN2_LEVELS``.

    Returns:
      CN2FamilyCurves with reference curves + the user's current
      curve.

    Raises:
      KeyError: when ``base_inputs`` is missing the v2.0 trajectory
        keys or the chain output (`by_module`) — indicates the chain
        hasn't run yet.
    """
    if "engagement_geometry" not in base_inputs:
        raise KeyError(
            "compute_cn2_family_curves requires v2.0 inputs "
            "(engagement_geometry must be present)"
        )
    by = base_inputs.get("by_module") or {}
    m1 = by.get("m1", {})
    m2 = by.get("m2", {})
    if not m1 or not m2:
        raise KeyError(
            "compute_cn2_family_curves requires by_module['m1'] and "
            "by_module['m2'] in base_inputs (chain output)"
        )

    w0 = float(m1.get("w0") or 0.0)
    zR = float(m1.get("zR") or 0.0)
    P_exit = float(m2.get("P_exit") or 0.0)
    if w0 <= 0 or zR <= 0 or P_exit <= 0:
        raise KeyError("invalid M1/M2 outputs in by_module")

    cn2_model = base_inputs.get("cn2_model", "HV_5_7")
    # Pull the user's active Cn² value (the one driving M5 in their
    # current scenario). Match SPEC casing ("constant" lowercase)
    # plus a defensive title-case alias.
    if cn2_model in ("constant", "Constant"):
        current_cn2 = float(base_inputs.get("Cn2_value", 1.0e-14))
    else:
        current_cn2 = float(base_inputs.get("Cn2_ground", 1.7e-14))

    # Resolve range axis. Default: log-spaced from 100 m to 2× R_detect.
    if ranges_m is None:
        R_detect_m = float(
            base_inputs.get("R_detect")
            or base_inputs.get("R", 1500.0)
        )
        R_min_input = float(base_inputs.get("R_min", 100.0))
        R_low = max(100.0, R_detect_m * 0.1, R_min_input + 1.0)
        R_high = min(50_000.0, max(R_detect_m * 2.0, R_low + 500.0))
        n_cells = 15
        # Log-spaced for the wider visual range.
        if R_low <= 0:
            R_low = 100.0
        log_lo = math.log(R_low)
        log_hi = math.log(R_high)
        step = (log_hi - log_lo) / (n_cells - 1)
        ranges_m = tuple(
            math.exp(log_lo + i * step) for i in range(n_cells)
        )

    levels = cn2_levels if cn2_levels is not None else _REFERENCE_CN2_LEVELS

    # Detect duplicate suppression — if user's Cn² ≈ a reference,
    # drop that reference and let the current-scenario curve replace it.
    suppressed_label: str | None = None
    suppressed_index: int | None = None
    for idx, (label, ref_cn2) in enumerate(levels):
        if math.isclose(current_cn2, ref_cn2, rel_tol=_DUPLICATE_REL_TOL):
            suppressed_label = label
            suppressed_index = idx
            break

    # Compute reference curves.
    reference_curves: list[tuple[str, float, tuple[float, ...]]] = []
    for idx, (label, ref_cn2) in enumerate(levels):
        if idx == suppressed_index:
            continue
        per_R = tuple(
            _compute_one_cell(base_inputs, R, ref_cn2, w0, zR, P_exit) or float("nan")
            for R in ranges_m
        )
        reference_curves.append((label, ref_cn2, per_R))

    # Compute current-scenario curve.
    current_per_R = tuple(
        _compute_one_cell(base_inputs, R, current_cn2, w0, zR, P_exit) or float("nan")
        for R in ranges_m
    )

    # User's R_detect for the star, plus I_peak interpolated from
    # the current curve at that R.
    R_detect_m = float(
        base_inputs.get("R_detect")
        or base_inputs.get("R", 1500.0)
    )
    current_R_km = R_detect_m / 1000.0
    current_I_peak_at_R = _compute_one_cell(
        base_inputs, R_detect_m, current_cn2, w0, zR, P_exit,
    )

    return CN2FamilyCurves(
        range_axis_km=tuple(R / 1000.0 for R in ranges_m),
        reference_curves=tuple(reference_curves),
        current_curve=(current_cn2, current_per_R),
        suppressed_label=suppressed_label,
        current_R_km=current_R_km,
        current_I_peak_wpcm2=current_I_peak_at_R,
        cn2_model=cn2_model,
    )


__all__ = [
    "CN2FamilyCurves",
    "compute_cn2_family_curves",
    "_REFERENCE_CN2_LEVELS",
    "_DUPLICATE_REL_TOL",
]
