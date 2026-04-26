"""DRI Analyzer — Detection / Recognition / Identification range model.

Independent of the HEL physics chain. Computes the range at which a
passive electro-optical sensor allows a human operator (or equivalent
classifier) to discriminate a target at the Detection, Recognition or
Identification level, per the Johnson criteria.

This module is pure (no Streamlit, no I/O); the UI layer in ``ui/``
calls ``compute()`` and the per-sweep helpers, then renders.

Design doc: ``docs/dri_analyzer_design.md`` (PR 4 in the campaign;
also lives in the canonical plan file at the repo root).

Physics — full derivation lives in §5 of the design doc; the formulas
below cite the equation that produced them:

    R_geom (level) = h_target / (2 · N_cycles_eff · IFOV_eff(L))      [§6.1]
    IFOV_eff (L)   = √(IFOV_pixel² + θ_turb(L)² + θ_diff²)            [§6.7]
    IFOV_pixel     = FOV_h_rad / N_h
    θ_turb (L)     = λ / r₀(L),  r₀ = (0.423 · k² · Cn² · L)^(-3/5)   [§6.5]
    θ_diff         = 1.22 · λ / D_aperture                            [§6.6]
    α(λ, V)        = (3.91 / V_km) · (550 / λ_nm)^q                   [§6.3]
    R_atm          = (1 / α) · ln(C₀ / C_threshold)                   [§6.4]
    R_final        = min(R_geom_eff, R_atm)                           [§6.8]

The path-length self-consistency loop (because θ_turb depends on L,
which is the answer) iterates 2–3 times to <1 %.

References:
    Johnson 1958 — original cycle criteria.
    Driggers et al. — TTPF probability adjustment.
    Kruse 1962, Kim 2001 — atmospheric extinction.
    Andrews & Phillips 2005 §6.2 — plane-wave Fried parameter.
    Blackwell 1946 — visual-contrast threshold C_t = 0.02.
"""
from __future__ import annotations

import math
from typing import Iterable

from physics.common import validate_enum, validate_positive, validate_range


# ---------------------------------------------------------------------------
# Catalogues — design doc §7
# ---------------------------------------------------------------------------

#: Target presets (design doc §7.1). Critical dim h = √(W·H), per the
#: NV-IPM convention (geometric mean of width and height).
TARGET_PRESETS: dict[str, dict[str, float]] = {
    "NATO standard":             {"W": 2.30, "H": 2.30},
    "Person standing":           {"W": 0.50, "H": 1.80},
    "Car / sedan":               {"W": 1.50, "H": 4.50},
    "Light truck / APC":         {"W": 2.30, "H": 6.00},
    "Group-3 UAS / Shahed-class": {"W": 2.50, "H": 3.50},
    "DJI Mavic 4 (Group-1 UAS)": {"W": 0.40, "H": 0.30},
    "DJI Mini-class":            {"W": 0.25, "H": 0.20},
    "Quadcopter swarm element":  {"W": 0.15, "H": 0.15},
    # "Custom" handled by user-entered W,H or h directly — not in this dict.
}


def target_critical_dim(
    preset: str | None = None,
    *,
    W: float | None = None,
    H: float | None = None,
) -> float:
    """Return the critical dimension h = √(W·H).

    Two modes:
      - target_critical_dim("NATO standard")        — preset lookup
      - target_critical_dim(W=1.5, H=4.5)           — explicit W·H

    Custom targets pass W and H directly. The geometric-mean convention
    matches NV-IPM (modern Johnson criterion descendant).
    """
    if preset is not None and (W is not None or H is not None):
        raise ValueError(
            "Pass either a preset name OR W and H — not both."
        )
    if preset is not None:
        if preset not in TARGET_PRESETS:
            raise ValueError(
                f"Unknown target preset {preset!r}; valid: "
                f"{sorted(TARGET_PRESETS.keys())} or supply W=, H=."
            )
        entry = TARGET_PRESETS[preset]
        return math.sqrt(entry["W"] * entry["H"])
    if W is None or H is None:
        raise ValueError(
            "target_critical_dim requires either a preset name or both "
            "W= and H= keyword arguments."
        )
    validate_positive(float(W), "W")
    validate_positive(float(H), "H")
    return math.sqrt(float(W) * float(H))


#: Cn² presets — design doc §7.2. Seven discrete levels covering the
#: realistic range from "sunny midday hot desert" (5e-13) to
#: "high-altitude / deep night" (1e-16).
CN2_PRESETS: dict[str, float] = {
    "Very strong (sunny midday, hot desert surface)": 5.0e-13,
    "Strong (clear day, near surface)":               1.0e-13,
    "Moderate-strong (warm afternoon)":               5.0e-14,
    "Moderate (canonical mid-altitude)":              1.0e-14,
    "Weak-moderate (cool morning)":                   5.0e-15,
    "Weak (overcast / dawn)":                         1.0e-15,
    "Very weak (high altitude / night)":              1.0e-16,
}


#: Wavelength bands — design doc §7.3. Visible / NIR / SWIR use the
#: Kruse + Kim aerosol model; MWIR / LWIR use a tabulated band-averaged
#: extinction (MODTRAN mid-latitude summer, V = 23 km baseline).
WAVELENGTH_BANDS: dict[str, dict] = {
    "Visible": {"lambda_nm": 550.0,   "thermal": False},
    "NIR":     {"lambda_nm": 850.0,   "thermal": False},
    "SWIR":    {"lambda_nm": 1550.0,  "thermal": False},
    "MWIR":    {"lambda_nm": 4000.0,  "thermal": True, "alpha_baseline_per_km": 0.10},
    "LWIR":    {"lambda_nm": 10000.0, "thermal": True, "alpha_baseline_per_km": 0.30},
}


#: Default Johnson cycles for D / R / I at 50 % probability (Johnson 1958).
DEFAULT_N_CYCLES_50: dict[str, float] = {
    "Detection":      1.0,
    "Recognition":    4.0,
    "Identification": 8.0,
}


#: Allowed probability values for the TTPF adjustment.
PROBABILITIES = (0.50, 0.80, 0.95)


#: Blackwell visual-contrast threshold for the Koschmieder formula.
C_THRESHOLD_BLACKWELL: float = 0.02


#: Hard upper bound on the path-length fixed-point iteration count.
MAX_PATH_LEN_ITER: int = 8


# ---------------------------------------------------------------------------
# Probability adjustment — TTPF (Driggers, design doc §6.2)
# ---------------------------------------------------------------------------

def ttpf_cycles(probability: float, N50: float) -> float:
    """Cycles-across-target needed for `probability` discrimination, given
    the 50 %-probability cycle count `N50`.

    Inverts the Driggers TTPF: ``P = N^E / (1 + N^E)`` with
    ``E = 2.7 + 0.7·N`` (where N here is N/N50, dimensionless) by
    Newton's method. Identity at P=0.50 (returns N50). Validation
    against the §5.9 worked example yields:
        P = 0.50 → 1.000 · N50
        P = 0.80 → 1.452 · N50
        P = 0.95 → 2.041 · N50
    """
    if not (0.0 < probability < 1.0):
        raise ValueError(
            f"probability must be in (0, 1), got {probability}"
        )
    validate_positive(N50, "N50")

    if abs(probability - 0.5) < 1e-12:
        return N50

    # Solve f(n) = P, where n = N/N50 and P = n^E / (1+n^E),
    # E = 2.7 + 0.7·n. Newton's method with a numerical derivative
    # (analytical d/dn would also work but the numerical form keeps
    # the implementation short and unambiguous).
    n = 1.0
    for _ in range(50):
        E = 2.7 + 0.7 * n
        n_e = n ** E
        f = n_e / (1.0 + n_e) - probability
        if abs(f) < 1e-9:
            break
        # Numerical derivative on a tiny step.
        dn = 1e-5 * max(n, 1.0)
        n2 = n + dn
        E2 = 2.7 + 0.7 * n2
        n_e2 = n2 ** E2
        f2 = n_e2 / (1.0 + n_e2) - probability
        df = (f2 - f) / dn
        if df == 0:
            break
        n = max(1e-6, n - f / df)

    return N50 * n


# ---------------------------------------------------------------------------
# Atmospheric extinction (design doc §6.3)
# ---------------------------------------------------------------------------

def kruse_alpha(V_km: float, lambda_nm: float) -> float:
    """Kruse-McClatchey aerosol extinction with Kim 2001 low-vis correction.

    Returns α in 1/km. Valid for vis / NIR / SWIR bands. For thermal
    bands (MWIR / LWIR) Kruse is invalid; the dispatcher in
    ``atmospheric_alpha`` routes those bands to a tabulated model.

    q-regimes (design doc §6.3):
        V > 50 km          → q = 1.6
        6 < V ≤ 50 km      → q = 1.3
        1 < V ≤ 6 km       → q = 0.16·V + 0.34   (Kim 2001)
        0.5 < V ≤ 1 km     → q = V − 0.5         (Kim 2001)
        V ≤ 0.5 km         → q = 0               (Kim 2001 fog limit)
    """
    validate_positive(V_km, "V_km")
    validate_positive(lambda_nm, "lambda_nm")

    if V_km > 50.0:
        q = 1.6
    elif V_km > 6.0:
        q = 1.3
    elif V_km > 1.0:
        q = 0.16 * V_km + 0.34
    elif V_km > 0.5:
        q = V_km - 0.5
    else:
        q = 0.0

    return (3.91 / V_km) * (550.0 / lambda_nm) ** q


def thermal_alpha(band: str, V_km: float) -> float:
    """Thermal-band extinction (MWIR / LWIR), 1/km.

    First-order: take the band's V=23 km baseline α and add a linear
    aerosol term scaled from the SWIR Kruse value at the user's
    visibility. Cleaner than extrapolating Kruse to thermal — that
    underestimates molecular absorption by orders of magnitude — and
    cheaper than a MODTRAN integration.
    """
    if band not in WAVELENGTH_BANDS or not WAVELENGTH_BANDS[band].get("thermal"):
        raise ValueError(
            f"thermal_alpha called with non-thermal band {band!r}; "
            f"thermal bands: "
            f"{[b for b, d in WAVELENGTH_BANDS.items() if d.get('thermal')]}"
        )
    validate_positive(V_km, "V_km")
    alpha_baseline = WAVELENGTH_BANDS[band]["alpha_baseline_per_km"]
    # Aerosol scaling: take SWIR Kruse @ V_user vs V=23 km as a
    # first-order proxy for "less visibility → more aerosol absorption".
    swir_lambda_nm = WAVELENGTH_BANDS["SWIR"]["lambda_nm"]
    alpha_swir_user = kruse_alpha(V_km, swir_lambda_nm)
    alpha_swir_23 = kruse_alpha(23.0, swir_lambda_nm)
    aerosol_scale = alpha_swir_user / alpha_swir_23
    return alpha_baseline * aerosol_scale


def atmospheric_alpha(band: str, lambda_nm: float, V_km: float) -> float:
    """Dispatcher: Kruse for non-thermal bands, tabulated for thermal."""
    if band not in WAVELENGTH_BANDS:
        raise ValueError(
            f"Unknown wavelength band {band!r}; valid: "
            f"{sorted(WAVELENGTH_BANDS.keys())}"
        )
    if WAVELENGTH_BANDS[band].get("thermal"):
        return thermal_alpha(band, V_km)
    return kruse_alpha(V_km, lambda_nm)


def atmospheric_range(
    alpha_per_km: float,
    C0: float = 0.30,
    C_threshold: float = C_THRESHOLD_BLACKWELL,
) -> float:
    """Koschmieder range: R_atm = (1/α) · ln(C₀ / C_t), in km.

    The maximum range at which a target with inherent contrast C₀
    against the sky / background is detectable above the visual
    threshold C_t. Returns +∞ when α → 0 (perfect transparency).
    """
    validate_positive(alpha_per_km, "alpha_per_km")
    validate_range(C0, "C0", 1e-3, 1.0)
    validate_range(C_threshold, "C_threshold", 1e-4, 0.5)
    if C0 <= C_threshold:
        # Target indistinguishable from background at any range.
        return 0.0
    return (1.0 / alpha_per_km) * math.log(C0 / C_threshold)


# ---------------------------------------------------------------------------
# Optical degradations (design doc §6.5–6.7)
# ---------------------------------------------------------------------------

def fried_r0_plane(cn2: float, L_m: float, lambda_m: float) -> float:
    """Plane-wave Fried parameter r₀ (m) for uniform Cn² over a
    horizontal path of length L.

    Andrews & Phillips 2005 §6.2:
        r₀ = (0.423 · k² · Cn² · L)^(-3/5),    k = 2π / λ
    """
    validate_positive(cn2, "cn2")
    validate_positive(L_m, "L_m")
    validate_positive(lambda_m, "lambda_m")
    k = 2.0 * math.pi / lambda_m
    arg = 0.423 * (k ** 2) * cn2 * L_m
    return arg ** (-3.0 / 5.0)


def turbulence_theta(cn2: float, L_m: float, lambda_m: float) -> float:
    """Turbulence-limited angular blur θ_turb = λ / r₀ (rad)."""
    return lambda_m / fried_r0_plane(cn2, L_m, lambda_m)


def airy_theta_diff(lambda_m: float, f_mm: float, f_number: float) -> float:
    """Airy-disk angular radius θ_diff = 1.22 · λ / D, in rad.

    D = aperture diameter = focal_length / f-number.
    """
    validate_positive(lambda_m, "lambda_m")
    validate_positive(f_mm, "f_mm")
    validate_positive(f_number, "f_number")
    D_aperture_m = (f_mm * 1e-3) / f_number
    return 1.22 * lambda_m / D_aperture_m


def effective_ifov(
    ifov_pixel: float, theta_turb: float, theta_diff: float,
) -> float:
    """RSS quadrature of three independent angular blur contributions."""
    return math.sqrt(ifov_pixel * ifov_pixel
                     + theta_turb * theta_turb
                     + theta_diff * theta_diff)


# ---------------------------------------------------------------------------
# Geometric Johnson range and the path-length fixed-point (§6.1, §6.8)
# ---------------------------------------------------------------------------

def johnson_range(h_target: float, n_cycles: float, ifov_eff: float) -> float:
    """Closed-form Johnson geometric range, in m:
        R = h_target / (2 · n_cycles · IFOV_eff)
    """
    validate_positive(h_target, "h_target")
    validate_positive(n_cycles, "n_cycles")
    validate_positive(ifov_eff, "ifov_eff")
    return h_target / (2.0 * n_cycles * ifov_eff)


def _self_consistent_range(
    h_target: float,
    n_cycles_eff: float,
    ifov_pixel: float,
    cn2: float,
    lambda_m: float,
    theta_diff: float,
    L_initial_m: float,
    rel_tol: float = 0.01,
    max_iter: int = MAX_PATH_LEN_ITER,
) -> tuple[float, int]:
    """Fixed-point iteration on the path length L.

    θ_turb depends on L, which is the answer. Iterate until R stabilises.
    Returns (R_m, iter_count). The iterate is damped (last-two average)
    so heavy turbulence regimes do not oscillate.
    """
    L = max(L_initial_m, 1.0)
    R = L
    converged_at = 1
    for i in range(1, max_iter + 1):
        theta_turb = turbulence_theta(cn2, L, lambda_m)
        ifov_eff = effective_ifov(ifov_pixel, theta_turb, theta_diff)
        R_new = johnson_range(h_target, n_cycles_eff, ifov_eff)
        # Damp by averaging with previous iterate to suppress oscillation.
        R_damped = 0.5 * (R + R_new) if i > 1 else R_new
        if abs(R_damped - R) <= rel_tol * R:
            R = R_damped
            converged_at = i
            break
        R = R_damped
        L = max(R, 1.0)
    return R, converged_at


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def dri_range(
    *,
    level: str,
    h_target: float,
    fov_h_deg: float,
    n_pixels_h: int,
    band: str,
    cn2: float,
    V_km: float,
    f_mm: float,
    f_number: float,
    C0: float = 0.30,
    probability: float = 0.50,
    n_cycles_50: float | None = None,
) -> dict:
    """Compute one DRI range (m) for the given level + sensor + atmosphere.

    Returns a dict with the components so the caller can label
    "atmosphere-limited" vs "geometry-limited" on the UI:

        {
          "level": str,
          "R_geom_eff_m": float,
          "R_atm_m": float,
          "R_final_m": float,
          "binding": "atmosphere" | "geometry",
          "ifov_pixel_rad": float,
          "theta_turb_rad": float,
          "theta_diff_rad": float,
          "ifov_eff_rad": float,
          "alpha_per_km": float,
          "n_cycles_eff": float,
          "iter_count": int,
        }
    """
    # ----- Validation -----
    validate_enum(level, "level", list(DEFAULT_N_CYCLES_50.keys()))
    validate_enum(band, "band", list(WAVELENGTH_BANDS.keys()))
    validate_positive(h_target, "h_target")
    validate_positive(fov_h_deg, "fov_h_deg")
    validate_positive(cn2, "cn2")
    validate_positive(V_km, "V_km")
    if not isinstance(n_pixels_h, int) or n_pixels_h < 1:
        raise ValueError(f"n_pixels_h must be a positive int, got {n_pixels_h}")

    if n_cycles_50 is None:
        n_cycles_50 = DEFAULT_N_CYCLES_50[level]
    n_cycles_eff = ttpf_cycles(probability, n_cycles_50)

    # ----- Sensor angular geometry -----
    fov_h_rad = fov_h_deg * math.pi / 180.0
    ifov_pixel = fov_h_rad / n_pixels_h

    # ----- Wavelength + diffraction -----
    lambda_nm = WAVELENGTH_BANDS[band]["lambda_nm"]
    lambda_m = lambda_nm * 1e-9
    theta_diff = airy_theta_diff(lambda_m, f_mm, f_number)

    # ----- Atmospheric range -----
    alpha_per_km = atmospheric_alpha(band, lambda_nm, V_km)
    if alpha_per_km <= 0:
        # Vacuum — Koschmieder inapplicable; pick a huge cap.
        R_atm_m = 1.0e9
    else:
        R_atm_m = atmospheric_range(alpha_per_km, C0=C0) * 1000.0

    # ----- Geometric range with self-consistent turbulence -----
    L_initial_m = max(R_atm_m, 100.0)
    R_geom_eff_m, iter_count = _self_consistent_range(
        h_target=h_target,
        n_cycles_eff=n_cycles_eff,
        ifov_pixel=ifov_pixel,
        cn2=cn2,
        lambda_m=lambda_m,
        theta_diff=theta_diff,
        L_initial_m=L_initial_m,
    )

    # ----- Final = min of the two limits -----
    R_final_m = min(R_geom_eff_m, R_atm_m)
    binding = "atmosphere" if R_atm_m < R_geom_eff_m else "geometry"

    # Re-evaluate the angular blurs at the converged path length
    # so the diagnostics reflect what the final range used.
    theta_turb_final = turbulence_theta(cn2, max(R_final_m, 1.0), lambda_m)
    ifov_eff_final = effective_ifov(ifov_pixel, theta_turb_final, theta_diff)

    return {
        "level": level,
        "R_geom_eff_m": R_geom_eff_m,
        "R_atm_m": R_atm_m,
        "R_final_m": R_final_m,
        "binding": binding,
        "ifov_pixel_rad": ifov_pixel,
        "theta_turb_rad": theta_turb_final,
        "theta_diff_rad": theta_diff,
        "ifov_eff_rad": ifov_eff_final,
        "alpha_per_km": alpha_per_km,
        "n_cycles_eff": n_cycles_eff,
        "iter_count": iter_count,
    }


def fov_sweep(
    *,
    level: str,
    fov_low_deg: float,
    fov_high_deg: float,
    n_points: int = 30,
    **kwargs,
) -> list[dict]:
    """Sweep R_DRI vs FOV (deg) for one level, NFOV → WFOV.

    Returns a list of dicts compatible with the ``plot_dri_*`` constructors:
    each entry has ``"fov_deg"`` plus the keys from ``dri_range``.
    """
    validate_positive(fov_low_deg, "fov_low_deg")
    validate_positive(fov_high_deg, "fov_high_deg")
    if fov_high_deg <= fov_low_deg:
        raise ValueError(
            f"fov_high_deg ({fov_high_deg}) must be > fov_low_deg "
            f"({fov_low_deg}); pass NFOV as fov_low and WFOV as fov_high."
        )
    if n_points < 2:
        raise ValueError(f"n_points must be >= 2, got {n_points}")

    fovs = _linspace(fov_low_deg, fov_high_deg, n_points)
    out: list[dict] = []
    for fov in fovs:
        r = dri_range(level=level, fov_h_deg=fov, **kwargs)
        r["fov_deg"] = fov
        out.append(r)
    return out


def target_size_sweep(
    *,
    level: str,
    sizes_m: Iterable[float],
    **kwargs,
) -> list[dict]:
    """Sweep R_DRI vs target critical dimension."""
    out: list[dict] = []
    for h in sizes_m:
        r = dri_range(level=level, h_target=float(h), **kwargs)
        r["h_target_m"] = float(h)
        out.append(r)
    return out


def cn2_sweep(
    *,
    level: str,
    cn2_values: Iterable[float] | None = None,
    **kwargs,
) -> list[dict]:
    """Sweep R_DRI across the seven Cn² preset levels (or a custom list)."""
    if cn2_values is None:
        cn2_values = list(CN2_PRESETS.values())
    out: list[dict] = []
    for cn2 in cn2_values:
        r = dri_range(level=level, cn2=float(cn2), **kwargs)
        r["cn2"] = float(cn2)
        out.append(r)
    return out


def heatmap(
    *,
    fov_grid_deg: list[float],
    target_grid_m: list[float],
    level: str = "Detection",
    **kwargs,
) -> list[list[float]]:
    """2D grid of R_final (m) over (FOV × target size). Used by Plot
    DRI-7 (2D heatmap) and Plot DRI-8 (3D surface — same data lifted
    into Z)."""
    grid: list[list[float]] = []
    for h in target_grid_m:
        row: list[float] = []
        for fov in fov_grid_deg:
            r = dri_range(
                level=level, h_target=float(h), fov_h_deg=float(fov), **kwargs,
            )
            row.append(r["R_final_m"])
        grid.append(row)
    return grid


def atmospheric_heatmap(
    *,
    cn2_grid: list[float],
    visibility_grid: list[float],
    level: str = "Detection",
    **kwargs,
) -> list[list[float]]:
    """2D grid of R_final (m) over (Cn² × visibility) at fixed FOV /
    target / band. Rows iterate over visibility (Y axis); columns
    iterate over Cn² (X axis). Used by Plot DRI-9 (3D atmospheric
    envelope surface).

    Visualises where the two atmospheric extinction mechanisms — the
    Fried-parameter turbulence MTF and the Koschmieder visual range —
    each dominate. Strong Cn² + clear visibility is turbulence-
    limited; weak Cn² + low visibility is contrast-limited; the
    surface shows the interaction.
    """
    grid: list[list[float]] = []
    for V_km in visibility_grid:
        row: list[float] = []
        for cn2 in cn2_grid:
            r = dri_range(
                level=level, cn2=float(cn2), V_km=float(V_km), **kwargs,
            )
            row.append(r["R_final_m"])
        grid.append(row)
    return grid


# ---------------------------------------------------------------------------
# HEL-style top-level wrapper for the renderer
# ---------------------------------------------------------------------------

def compute(inputs: dict) -> dict:
    """Top-level DRI computation against a ``user_inputs``-shaped dict.

    Mirrors the HEL-module ``compute(inputs) → dict`` contract so the UI
    layer can call this once per "Run Analysis" click and merge the
    result into the result dict.

    Required keys (from `ui/panels.py` DRI sections — naming uses the
    `dri_` prefix to keep the namespace separate from HEL inputs):

        dri_n_pixels_h, dri_n_pixels_v, dri_nfov_deg, dri_wfov_deg,
        dri_focal_length_mm, dri_f_number,
        dri_band, dri_cn2_preset, dri_visibility_km, dri_C0,
        dri_target_preset, dri_target_h_m (only when preset == "Custom"),
        dri_probability, dri_n_cycles_D, dri_n_cycles_R, dri_n_cycles_I

    Returns a dict with three R_*_m keys (D / R / I), the per-level
    binding label, the input echoes, and ``assumptions_flagged``.
    """
    # ----- Parse + validate -----
    band = inputs["dri_band"]
    validate_enum(band, "dri_band", list(WAVELENGTH_BANDS.keys()))

    target_preset = inputs["dri_target_preset"]
    if target_preset == "Custom":
        h_target = float(inputs["dri_target_h_m"])
        validate_range(h_target, "dri_target_h_m", 0.05, 50.0)
    else:
        if target_preset not in TARGET_PRESETS:
            raise ValueError(
                f"Unknown dri_target_preset {target_preset!r}; valid: "
                f"{sorted(TARGET_PRESETS)} or 'Custom'."
            )
        h_target = target_critical_dim(target_preset)

    cn2_preset = inputs["dri_cn2_preset"]
    if cn2_preset not in CN2_PRESETS:
        raise ValueError(
            f"Unknown dri_cn2_preset {cn2_preset!r}; valid: "
            f"{sorted(CN2_PRESETS)}."
        )
    cn2 = CN2_PRESETS[cn2_preset]

    probability = float(inputs.get("dri_probability", 0.50))
    if probability not in PROBABILITIES:
        raise ValueError(
            f"dri_probability must be one of {PROBABILITIES}, "
            f"got {probability}"
        )

    common_kwargs = dict(
        h_target=h_target,
        n_pixels_h=int(inputs["dri_n_pixels_h"]),
        band=band,
        cn2=cn2,
        V_km=float(inputs["dri_visibility_km"]),
        f_mm=float(inputs["dri_focal_length_mm"]),
        f_number=float(inputs["dri_f_number"]),
        C0=float(inputs.get("dri_C0", 0.30)),
        probability=probability,
    )

    nfov_deg = float(inputs["dri_nfov_deg"])
    wfov_deg = float(inputs["dri_wfov_deg"])
    if wfov_deg <= nfov_deg:
        raise ValueError(
            f"dri_wfov_deg ({wfov_deg}) must be > dri_nfov_deg "
            f"({nfov_deg}); WFOV is the wide end of the zoom range."
        )

    cycles_inputs = {
        "Detection":      float(inputs.get("dri_n_cycles_D", DEFAULT_N_CYCLES_50["Detection"])),
        "Recognition":    float(inputs.get("dri_n_cycles_R", DEFAULT_N_CYCLES_50["Recognition"])),
        "Identification": float(inputs.get("dri_n_cycles_I", DEFAULT_N_CYCLES_50["Identification"])),
    }

    # ----- Headline DRI numbers at NFOV -----
    headlines: dict[str, dict] = {}
    for level, n50 in cycles_inputs.items():
        headlines[level] = dri_range(
            level=level, fov_h_deg=nfov_deg,
            n_cycles_50=n50, **common_kwargs,
        )

    # ----- Assumptions -----
    flagged: list[str] = []
    if WAVELENGTH_BANDS[band].get("thermal"):
        flagged.append(
            "thermal_extinction_first_order: MWIR/LWIR uses tabulated "
            "band-averaged α; use MODTRAN/LOWTRAN for production."
        )
    if cn2 > 1.0e-12:
        flagged.append(
            "cn2_outside_validated_range: Cn² > 1e-12 m^(−2/3) — "
            "Andrews & Phillips Fried formula is in the very-strong "
            "regime; results are first-order."
        )
    V_km = float(inputs["dri_visibility_km"])
    if V_km < 1.0:
        flagged.append(
            "kim_low_visibility_regime: V < 1 km — atmospheric "
            "extinction follows the Kim 2001 fog-onset branch; "
            "verify with field data."
        )

    # ----- Result dict (flat for easy UI consumption) -----
    result: dict = {
        "dri_h_target_m": h_target,
        "dri_cn2": cn2,
        "dri_band": band,
        "dri_lambda_nm": WAVELENGTH_BANDS[band]["lambda_nm"],
        "dri_alpha_per_km": headlines["Detection"]["alpha_per_km"],
        "dri_R_atm_m": headlines["Detection"]["R_atm_m"],

        "dri_R_detection_m":      headlines["Detection"]["R_final_m"],
        "dri_R_recognition_m":    headlines["Recognition"]["R_final_m"],
        "dri_R_identification_m": headlines["Identification"]["R_final_m"],

        "dri_R_geom_detection_m":      headlines["Detection"]["R_geom_eff_m"],
        "dri_R_geom_recognition_m":    headlines["Recognition"]["R_geom_eff_m"],
        "dri_R_geom_identification_m": headlines["Identification"]["R_geom_eff_m"],

        "dri_binding_detection":      headlines["Detection"]["binding"],
        "dri_binding_recognition":    headlines["Recognition"]["binding"],
        "dri_binding_identification": headlines["Identification"]["binding"],

        "dri_n_cycles_D_eff": headlines["Detection"]["n_cycles_eff"],
        "dri_n_cycles_R_eff": headlines["Recognition"]["n_cycles_eff"],
        "dri_n_cycles_I_eff": headlines["Identification"]["n_cycles_eff"],

        "dri_ifov_pixel_rad": headlines["Detection"]["ifov_pixel_rad"],
        "dri_theta_diff_rad": headlines["Detection"]["theta_diff_rad"],
        "dri_theta_turb_rad": headlines["Detection"]["theta_turb_rad"],
        "dri_ifov_eff_rad":   headlines["Detection"]["ifov_eff_rad"],

        "dri_assumptions_flagged": flagged,
    }
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _linspace(low: float, high: float, n: int) -> list[float]:
    if n < 2:
        return [low]
    step = (high - low) / (n - 1)
    return [low + i * step for i in range(n)]


__all__ = [
    # constants / presets
    "TARGET_PRESETS",
    "CN2_PRESETS",
    "WAVELENGTH_BANDS",
    "DEFAULT_N_CYCLES_50",
    "PROBABILITIES",
    "C_THRESHOLD_BLACKWELL",
    # kernels
    "ttpf_cycles",
    "kruse_alpha",
    "thermal_alpha",
    "atmospheric_alpha",
    "atmospheric_range",
    "fried_r0_plane",
    "turbulence_theta",
    "airy_theta_diff",
    "effective_ifov",
    "johnson_range",
    "target_critical_dim",
    # public API
    "dri_range",
    "fov_sweep",
    "target_size_sweep",
    "cn2_sweep",
    "heatmap",
    "atmospheric_heatmap",
    "compute",
]
