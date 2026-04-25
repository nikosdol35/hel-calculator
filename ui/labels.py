"""Single source of truth for every user-visible string (ARCH v1.6 §6.10).

Every label, tooltip, unit symbol, section name, and tab name shown to
the user in the HEL calculator UI lives in this file. ``ui/panels.py``,
``ui/outputs.py``, ``ui/plots.py``, and ``ui/app.py`` read from here;
none of them hard-code a user-visible string.

``tests/test_copy_style.py`` enforces this by grepping those four files
for forbidden tokens (``SPEC §``, ``ARCH §``, ``M[0-9]`` module tags,
raw ``assumptions_flagged`` keys, emoji characters). ``ui/labels.py``
itself is exempt from the lint.

Redline discipline
------------------
This file is the surface the user redlines during PR 1 review. Entries
are grouped by origin (input sections → output result keys → section /
tab / button / status / advisory copy) and each entry is kept short:

    label    : 3–5 word title suitable for a card header or widget label
    tooltip  : one short sentence describing what the quantity means
    unit     : the Unicode unit symbol shown inline with the value

Anywhere a trade-off is made (concise vs. precise, engineering-jargon
vs. plain-English), a ``# REDLINE:`` comment explains the alternative so
the user can choose. Values without a REDLINE comment are defaults the
drafter is confident in but the user is welcome to overwrite.

References:
    ARCHITECTURE.md §6.10 — file contract.
    SPEC.md §5.1 — input dict key ↔ UI label mapping.
    SPEC.md §5.2 — output dict key ↔ UI label mapping, tab names.
    docs/phase3_ui_redesign_plan_2026-04-23.md §7 — original draft with
        per-entry rationale.
"""

from __future__ import annotations

from typing import TypedDict


class LabelEntry(TypedDict, total=False):
    label:   str   # 3–5 word UI title
    tooltip: str   # one-sentence description
    unit:    str   # Unicode unit symbol (inline, never bare)


# =============================================================================
# Sidebar section headers (SPEC §5.1, v1.9)
# =============================================================================
# The six collapsible sections in the sidebar, in top-to-bottom order.
# Default-open state is section 1, 3, 5 (Laser source / Engagement geometry /
# Target & aimpoint); sections 2, 4, 6 are collapsed by default.

SECTION_LABELS: dict[str, str] = {
    "laser_source":        "Laser source",
    "beam_director":       "Beam director",
    "engagement_geometry": "Engagement geometry",
    "atmosphere":          "Atmosphere",
    "target_aimpoint":     "Target & aimpoint",
    "system_resources":    "System resources",
}


# =============================================================================
# Main-area tab labels (SPEC §5.2, v1.9)
# =============================================================================
# Six tabs in reading order. **Text-only** per user decision on PR 1 open-items
# (2026-04-24): the original draft paired each tab label with a Lucide icon;
# the user chose text-only so the tab strip stays uncluttered. PR 3 renders
# `st.tabs(list(TAB_LABELS.values()))` directly — no icon wrapper.

TAB_LABELS: dict[str, str] = {
    "overview":       "Overview",
    "engagement":     "Engagement",
    "target_effects": "Target effects",
    "safety":         "Safety",
    "atmosphere":     "Atmosphere",
    "diagnostics":    "Diagnostics",
    # PR 1 of the math-tab plan (docs/math_tab_plan_2026-04-25.md). Tab is
    # the rightmost so it reads as "results, then the receipts behind them."
    "math":           "How it's calculated",
}


# =============================================================================
# Input-field labels (SPEC §5.1 v1.9 — same `user_inputs` dict keys as v1.8)
# =============================================================================

INPUT_LABELS: dict[str, LabelEntry] = {

    # -- Section 1 — Laser source → M1 ----------------------------------------
    "P0": {
        "label":   "Output power",
        "tooltip": "Laser output power at the exit aperture, before the beam director.",
        "unit":    "kW",
    },
    "M2": {
        "label":   "Beam quality (M²)",
        "tooltip": "Beam propagation factor. 1.0 is a diffraction-limited Gaussian; realistic HELs run 1.1–2.5.",
        "unit":    "",
    },
    "D": {
        "label":   "Exit aperture diameter",
        "tooltip": "Clear aperture diameter at the beam director exit.",
        "unit":    "cm",
    },
    "wavelength": {
        "label":   "Wavelength",
        "tooltip": "Operating wavelength. Four values contracted: 1.06, 1.07, 1.55, 2.05 µm.",
        "unit":    "µm",
    },

    # -- Section 2 — Beam director → M2, partially M7 -------------------------
    "eta_opt": {
        "label":   "Optical transmission",
        "tooltip": "Fraction of laser power transmitted through the director optics.",
        "unit":    "",
    },
    "sigma_jit": {
        "label":   "Pointing jitter (1-σ, per-axis)",
        "tooltip": "Per-axis one-sigma RMS angular jitter at the director output — the standard PTU/EO datasheet convention.",
        "unit":    "µrad",
    },

    # -- Section 3 — Engagement geometry → M3 ---------------------------------
    "H_e": {
        "label":   "Emplacement altitude",
        "tooltip": "Height of the beam director above ground level (AGL).",
        "unit":    "m",
    },
    "R": {
        "label":   "Slant range to target",
        "tooltip": "Line-of-sight distance from the beam director to the aimpoint. (v1.x backward-compat key; SPEC v2.0 uses R_detect.)",
        "unit":    "m",
    },
    "R_detect": {
        "label":   "Detection range R_detect",
        "tooltip": "Slant range at which the target is first detected and the laser begins engagement. The trajectory model integrates from here down to R_min as the target closes (head-on) or passes (lateral).",
        "unit":    "m",
    },
    "R_min": {
        "label":   "Standoff range R_min",
        "tooltip": "Engagement-end standoff. Head-on: the target's release / danger range — the engagement must close before the target gets this close. Lateral: the closest-approach distance — the perpendicular standoff from the director.",
        "unit":    "m",
    },
    "engagement_geometry": {
        "label":   "Engagement geometry",
        "tooltip": "Threat trajectory shape. Head-on: target closes along the line of sight at v_tgt. Lateral: target flies a perpendicular pass with closest-approach distance R_min.",
        "unit":    "",
    },
    "H_t": {
        "label":   "Target altitude",
        "tooltip": "Height of the target above ground level (AGL).",
        "unit":    "m",
    },
    "v_tgt": {
        "label":   "Target velocity",
        "tooltip": "Target velocity along the threat trajectory: closing speed for head-on, lateral speed for a pass-by.",
        "unit":    "m/s",
    },
    "v_perp": {
        "label":   "Crosswind (perpendicular)",
        "tooltip": "Wind component perpendicular to the line of sight; the dominant driver of thermal blooming.",
        "unit":    "m/s",
    },

    # -- Section 4 — Atmosphere → M4, M5 --------------------------------------
    "V": {
        "label":   "Visibility",
        "tooltip": "Meteorological surface visibility; sets aerosol extinction via the Kruse formula.",
        "unit":    "km",
    },
    "RH": {
        "label":   "Relative humidity",
        "tooltip": "Surface relative humidity; modulates molecular water-vapor absorption.",
        "unit":    "%",
    },
    "T_ambient": {
        "label":   "Ambient temperature",
        "tooltip": "Surface air temperature; feeds both the blooming dn/dT path and the atmospheric model.",
        "unit":    "°C",
    },
    "cn2_model": {
        "label":   "Turbulence profile",
        "tooltip": "Model for the refractive-index structure constant Cn² along the slant path.",
        "unit":    "",
    },
    "Cn2_value": {
        "label":   "Uniform Cn²",
        "tooltip": "Used when the profile is 'constant'. Ignored for Hufnagel–Valley profiles.",
        "unit":    "m⁻²ᐟ³",
    },
    "Cn2_ground": {
        "label":   "Ground-level Cn²",
        "tooltip": "Surface boundary value for the Hufnagel–Valley profile.",
        "unit":    "m⁻²ᐟ³",
    },
    "v_HV": {
        "label":   "Upper-level wind (HV)",
        "tooltip": "High-altitude wind parameter for the Hufnagel–Valley profile.",
        "unit":    "m/s",
    },

    # -- Section 5 — Target & aimpoint → M7, M8 -------------------------------
    "d_aim": {
        "label":   "Aimpoint diameter",
        "tooltip": "Target-plane diameter of the aimpoint region (bucket for power-in-the-bucket).",
        "unit":    "cm",
    },
    "material": {
        "label":   "Target material",
        "tooltip": "Front-face material — selects thermal, optical, and failure properties.",
        "unit":    "",
    },
    "thickness": {
        "label":   "Material thickness",
        "tooltip": "Through-thickness of the target face.",
        "unit":    "mm",
    },
    "A_lambda": {
        "label":   "Absorptivity (override)",
        "tooltip": "Wavelength-specific absorptivity; leave the tabulated value unless you have measured data.",
        "unit":    "",
    },
    "backside_BC": {
        "label":   "Backside boundary",
        "tooltip": "Thermal boundary condition on the rear face — insulated or convective.",
        "unit":    "",
    },

    # -- Section 6 — System resources → M9, M10 -------------------------------
    "eta_wallplug": {
        "label":   "Wall-plug efficiency",
        "tooltip": "Electrical-to-optical efficiency of the laser system.",
        "unit":    "",
    },
    "Q_cool": {
        "label":   "Cooling capacity",
        "tooltip": "Steady-state heat-rejection capability of the coolant loop.",
        "unit":    "kW",
    },
    "C_thermal": {
        "label":   "Coolant thermal mass",
        "tooltip": "Effective heat capacity of the coolant loop — buffer for short bursts.",
        "unit":    "kJ/K",
    },
    "dT_max": {
        "label":   "Maximum ΔT",
        "tooltip": "Allowable coolant temperature rise before the loop saturates.",
        "unit":    "K",
    },
    "t_exp": {
        "label":   "Exposure duration (MPE)",
        "tooltip": "Worst-case continuous exposure used for the ANSI Z136.1 maximum permissible exposure calculation.",
        "unit":    "s",
    },
}


# =============================================================================
# Output / result-dict-key labels (SPEC §5.2 v1.9)
# =============================================================================

OUTPUT_LABELS: dict[str, LabelEntry] = {

    # -- Angular-error split (Engagement tab, header row) ---------------------
    "theta_diff": {
        "label":   "Diffraction angle (total)",
        "tooltip": "Full-angle diffraction divergence including the M² excess. Siegman full-angle convention.",
        "unit":    "µrad",
    },
    "theta_diff_pure": {
        "label":   "Diffraction (M²=1)",
        "tooltip": "Diffraction divergence in the M²=1 (ideal Gaussian) limit.",
        "unit":    "µrad",
    },
    "theta_M2_excess": {
        "label":   "M² excess broadening",
        "tooltip": "Additional divergence beyond the ideal-Gaussian limit attributable to beam-quality M².",
        "unit":    "µrad",
    },
    "theta_turb": {
        "label":   "Turbulence broadening",
        "tooltip": "Full-angle broadening from atmospheric turbulence along the slant path.",
        "unit":    "µrad",
    },
    "theta_jit": {
        "label":   "Jitter broadening",
        "tooltip": "Full-angle broadening from pointing jitter (2·σ_jit).",
        "unit":    "µrad",
    },

    # -- Strehl (Engagement tab) ---------------------------------------------
    "S_TB": {
        "label":   "Strehl — thermal blooming",
        "tooltip": "Peak-on-axis irradiance ratio from thermal blooming alone. 1.0 means no blooming loss.",
        "unit":    "",
    },
    "S_opt": {
        "label":   "Strehl — optical",
        "tooltip": "Peak-on-axis irradiance ratio from optical aberrations. Fixed at 1.0 in v1.",
        "unit":    "",
    },
    "S_total": {
        "label":   "Strehl — total",
        "tooltip": "Combined Strehl factor applied to the on-axis irradiance.",
        "unit":    "",
    },

    # -- Spot radii (Engagement tab) -----------------------------------------
    "w_diff": {
        "label":   "Spot radius — diffraction",
        "tooltip": "1/e² beam radius from diffraction alone at the target plane.",
        "unit":    "cm",
    },
    "w_turb": {
        "label":   "Spot radius — turbulence",
        "tooltip": "1/e² beam-radius contribution from atmospheric turbulence.",
        "unit":    "cm",
    },
    "w_jit": {
        "label":   "Spot radius — jitter",
        "tooltip": "1/e² beam-radius contribution from pointing jitter.",
        "unit":    "cm",
    },
    "w_bloom": {
        "label":   "Spot radius — blooming",
        "tooltip": "1/e² beam-radius contribution from thermal blooming.",
        "unit":    "cm",
    },
    "w_total": {
        "label":   "Spot radius — total",
        "tooltip": "Quadrature sum of diffraction, turbulence, jitter, and blooming radii.",
        "unit":    "cm",
    },

    # -- Engagement KPIs (Overview + Engagement tabs) ------------------------
    "P_aim": {
        "label":   "Power in aimpoint",
        "tooltip": "Laser power delivered inside the aimpoint region at the target plane.",
        "unit":    "kW",
    },
    "I_avg_aim": {
        "label":   "Average irradiance (aimpoint)",
        "tooltip": "P_aim divided by the aimpoint area.",
        "unit":    "W/cm²",
    },
    "I_peak": {
        "label":   "Peak irradiance",
        "tooltip": "On-axis peak irradiance at the target plane, including Strehl reduction.",
        "unit":    "W/cm²",
    },
    "PIB": {
        "label":   "Power in the bucket",
        "tooltip": "Fraction of total power that falls inside the aimpoint radius.",
        "unit":    "",
    },

    # -- Target effects (Target-effects tab) ---------------------------------
    "tau_BT": {
        "label":   "Time to burn-through",
        "tooltip": "Time for the target front face to reach its failure criterion under the delivered flux.",
        "unit":    "s",
    },
    "T_surface_at_tau": {
        "label":   "Surface temperature (at τ)",
        "tooltip": "Front-face temperature at the moment of burn-through.",
        "unit":    "K",
    },
    "T_surface_peak": {
        "label":   "Peak surface temperature",
        "tooltip": "Maximum front-face temperature reached during the integration window.",
        "unit":    "°C",
    },
    "failure_mode": {
        "label":   "Failure mode",
        "tooltip": "Failure criterion triggered at burn-through (melt, decomposition, thermal-runaway, etc.).",
        "unit":    "",
    },

    # -- Dwell and verdict (Overview tab) ------------------------------------
    "available_dwell": {
        "label":   "Available dwell",
        "tooltip": "Maximum time the beam can hold the aimpoint given the engagement kinematics.",
        "unit":    "s",
    },
    "R_at_dwell_end": {
        "label":   "Slant at engagement-end",
        "tooltip": "Slant range at the moment the engagement window ends — the user's standoff range R_min for tracker-supported engagements; the unchanged slant range in backward-compat mode.",
        "unit":    "km",
    },
    "R_at_kill": {
        "label":   "Slant range at kill",
        "tooltip": "Slant range at the moment burn-through happens. None when no kill occurs within the engagement window.",
        "unit":    "km",
    },
    "margin": {
        "label":   "Engagement margin",
        "tooltip": "(available_dwell − time-to-burn-through) / time-to-burn-through. Positive means dwell exceeds the lethality requirement.",
        "unit":    "%",
    },

    # -- Safety (Safety tab) --------------------------------------------------
    "NOHD_tophat": {
        "label":   "NOHD (top-hat)",
        "tooltip": "Nominal Ocular Hazard Distance under the top-hat convention. Cite this for safety cases that use the uniform-irradiance assumption.",
        "unit":    "km",
    },
    "NOHD_gausspeak": {
        "label":   "NOHD (Gaussian-peak)",
        "tooltip": "Nominal Ocular Hazard Distance under the Gaussian on-axis peak convention. The more conservative of the two.",
        "unit":    "km",
    },
    "laser_class": {
        "label":   "Laser class",
        "tooltip": "ANSI Z136.1 laser hazard classification for the configured wavelength, power, and exposure duration.",
        "unit":    "",
    },

    # -- System feasibility (Overview + Diagnostics tabs) --------------------
    "P_in": {
        "label":   "Wall-plug input power",
        "tooltip": "Electrical input power to the laser system.",
        "unit":    "kW",
    },
    "Q_waste": {
        "label":   "Waste heat",
        "tooltip": "Heat dumped into the coolant loop during the engagement.",
        "unit":    "kW",
    },
    "t_sustain": {
        "label":   "Sustain time",
        "tooltip": "How long the system can keep firing before coolant ΔT exceeds the allowable limit. Infinite if Q_cool ≥ Q_waste.",
        "unit":    "s",
    },
    "engagements_per_hour": {
        "label":   "Engagements per hour",
        "tooltip": "How many back-to-back engagements the system can sustain in one hour, given cooling recovery.",
        "unit":    "",
    },
    # Categorical / verdict outputs surfaced in the math tab (PR 3 of
    # the math-tab plan). Engagement viability and the M6↔M7 iteration
    # diagnostics already render via dedicated cards on the Overview /
    # Diagnostics tabs but did not have OUTPUT_LABELS entries until the
    # math-tab coverage test required them.
    "engagement_viable": {
        "label":   "Engagement viable",
        "tooltip": "True when the system can sustain output long enough to defeat the target before the cooling loop saturates.",
        "unit":    "",
    },
    "m67_iteration_count": {
        "label":   "M6↔M7 iterations",
        "tooltip": "How many passes the blooming–focusing fixed-point loop took to converge to 1 % tolerance.",
        "unit":    "",
    },
    "m67_converged": {
        "label":   "M6↔M7 converged",
        "tooltip": "Whether the blooming–focusing loop reached its convergence tolerance within the 10-iteration cap.",
        "unit":    "",
    },

    # -- Atmosphere (Atmosphere tab) ------------------------------------------
    "alpha_atm": {
        "label":   "Total extinction (α)",
        "tooltip": "Sum of molecular + aerosol absorption and scattering along the slant path.",
        "unit":    "1/km",
    },
    "alpha_mol_abs": {
        "label":   "Molecular absorption",
        "tooltip": "Extinction from molecular water-vapor and mixed-gas absorption.",
        "unit":    "1/km",
    },
    "alpha_mol_scat": {
        "label":   "Molecular scattering",
        "tooltip": "Rayleigh scattering from air molecules.",
        "unit":    "1/km",
    },
    "alpha_aer_abs": {
        "label":   "Aerosol absorption",
        "tooltip": "Absorption by atmospheric aerosols (dust, soot, water droplets).",
        "unit":    "1/km",
    },
    "alpha_aer_scat": {
        "label":   "Aerosol scattering",
        "tooltip": "Scattering from atmospheric aerosols (Mie regime).",
        "unit":    "1/km",
    },
    "tau_atm": {
        "label":   "Atmospheric transmission",
        "tooltip": "Beer–Lambert transmission over the slant range at the operating wavelength.",
        "unit":    "",
    },

    # -- Blooming diagnostics (Engagement tab advanced) ----------------------
    "N_D": {
        "label":   "Blooming distortion number",
        "tooltip": "Gebhardt's dimensionless blooming distortion number. N_D ≳ 30 indicates the model is being pushed outside its validity range.",
        "unit":    "",
    },

    # -- M1 source-plane diagnostics (Diagnostics tab) -----------------------
    "w0": {
        "label":   "Exit waist radius",
        "tooltip": "1/e² radius of the Gaussian beam at the exit aperture (D/2 at full fill).",
        "unit":    "m",
    },
    "zR": {
        "label":   "Rayleigh range",
        "tooltip": "Rayleigh range z_R = π·w0²/(M²·λ). Beam radius √2·w0 at z_R.",
        "unit":    "m",
    },
    "I_exit": {
        "label":   "Exit irradiance",
        "tooltip": "On-axis irradiance at the exit aperture, 2·P0/(π·w0²).",
        "unit":    "W/m²",
    },

    # -- M2 power-link output (Diagnostics tab) ------------------------------
    "P_exit": {
        "label":   "Exit power",
        "tooltip": "Laser power leaving the beam-director aperture after optical-train efficiency.",
        "unit":    "W",
    },

    # -- M3 geometry outputs (Diagnostics tab) -------------------------------
    "R_slant": {
        "label":   "Slant range",
        "tooltip": "Line-of-sight distance from the emitter to the target, accounting for altitude difference.",
        "unit":    "m",
    },
    "R_h": {
        "label":   "Horizontal range",
        "tooltip": "Ground-plane distance from the emitter to the target foot-print.",
        "unit":    "m",
    },
    "elevation_angle": {
        "label":   "Elevation angle",
        "tooltip": "Look-up angle from horizontal to the target along the slant path.",
        "unit":    "rad",
    },

    # -- M5 turbulence diagnostics (Diagnostics tab) -------------------------
    "Cn2_integrated": {
        "label":   "Integrated Cn²",
        "tooltip": "Path-integrated Cn² along the slant range. Drives r0 and the turbulence spot broadening.",
        "unit":    "m⁻²ᐟ³·m",
    },
    "r0_sph": {
        "label":   "Fried parameter (spherical)",
        "tooltip": "Spherical-wave Fried coherence diameter r0. Beam diameter ≪ r0 → turbulence-limited.",
        "unit":    "m",
    },

    # -- M7 derived outputs (Diagnostics tab) --------------------------------
    "d_spot": {
        "label":   "Spot diameter",
        "tooltip": "2·w_total, the 1/e² spot diameter at the target plane.",
        "unit":    "cm",
    },
    "PIB_fraction": {
        "label":   "Power in the bucket",
        "tooltip": "Fraction of total power that falls inside the aimpoint radius.",
        "unit":    "",
    },

    # -- M8 target-effects diagnostics (Target-effects tab) ------------------
    "E_delivered": {
        "label":   "Energy delivered",
        "tooltip": "Cumulative absorbed energy at the target surface up to burn-through or the end of the integration window.",
        "unit":    "J",
    },

    # -- M9 safety diagnostics (Safety tab) ----------------------------------
    "MPE": {
        "label":   "Maximum Permissible Exposure",
        "tooltip": "ANSI Z136.1 maximum permissible ocular exposure irradiance for the configured wavelength and exposure time.",
        "unit":    "W/m²",
    },

    # -- M10 power-thermal diagnostics (Diagnostics tab) ---------------------
    "duty_cycle_limit": {
        "label":   "Duty-cycle limit",
        "tooltip": "Fraction of time the system can fire continuously given Q_cool / Q_waste.",
        "unit":    "",
    },
}


# =============================================================================
# Material display names (SPEC v1 material set; raw enum values are
# technical identifiers — these are their English-prose chart labels).
# =============================================================================

MATERIAL_DISPLAY_NAMES: dict[str, str] = {
    "anodized_Al":   "Anodized aluminium",
    "CFRP":          "Carbon-fibre composite",
    "GFRP":          "Glass-fibre composite",
    "polycarbonate": "Polycarbonate",
    "ABS":           "ABS plastic",
    "EPP_foam":      "Expanded polypropylene foam",
    "LiPo":          "Lithium-polymer cell",
}


# =============================================================================
# Preset names (sidebar dropdown — populated from ui/presets.py)
# =============================================================================

PRESET_LABELS: dict[str, str] = {
    # Approved on PR 1 (2026-04-24). Underlying parameter sets land in
    # ui/presets.py with PR 6 per the Phase 3 rollout plan.
    "c_uas_short_range":      "C-UAS — short range",
    "counter_rocket":         "Counter-rocket",
    "long_range_surveillance": "Long-range surveillance",
    "custom":                 "Custom",
}

# Sidebar preset-dropdown chrome.
PRESET_PICKER_LABEL: str = "Engagement scenario"
PRESET_PICKER_HELP: str = (
    "Load a defensible reference input set. Selecting any named scenario "
    "overwrites every sidebar field; selecting Custom leaves your current "
    "edits in place."
)


# =============================================================================
# Button / control labels
# =============================================================================

BUTTON_LABELS: dict[str, str] = {
    "run_analysis":      "Run Analysis",
    "validate":          "Run Validation Suite",
    "share":             "Share this analysis",
    "export_csv":        "Export results (CSV)",
    "theme_toggle_dark": "Switch to light mode",
    "theme_toggle_light": "Switch to dark mode",
    "login_submit":      "Sign in",
}


# =============================================================================
# Status-chip text templates (SPEC §5.2 Overview verdict)
# =============================================================================

VERDICT_TEMPLATES: dict[str, str] = {
    "ok":       "ENGAGEABLE — {margin:.0f}% margin",
    "warn":     "MARGINAL — {margin:.0f}% margin",
    "error":    "NOT ENGAGEABLE — exceeds dwell by {shortfall:.0f}%",
    "instant":  "ENGAGEABLE — instantaneous",
    "no_dwell": "NOT ENGAGEABLE — no dwell available",
}


# =============================================================================
# Advisory / infeasibility copy (SPEC §5.3 item 10 — always-render plot frames)
# =============================================================================

ADVISORY: dict[str, str] = {
    "infeasible_geometry": (
        "No feasible engagement at the current geometry. "
        "Reduce slant range or adjust the target / emplacement altitudes."
    ),
    "no_dwell_available": (
        "No dwell window available. The target kinematics leave no time to "
        "engage — reduce target velocity or increase the aimpoint diameter."
    ),
    "no_burnthrough": (
        "Burn-through not reached within the available dwell. Increase "
        "output power, reduce range, or select a thinner / lower-threshold target."
    ),
    "vacuum_path": (
        "Atmospheric extinction is effectively zero on this path — molecular "
        "and aerosol components both negligible."
    ),
    "first_run_skeleton": (
        "Click Run Analysis in the sidebar to populate the tabs."
    ),
    "welcome_title": "Ready to run",
    "welcome_body": (
        "Pick an Engagement scenario in the sidebar to load a reference "
        "input set, or adjust the six sections directly. Click Run "
        "Analysis when the configuration is ready — every tab populates "
        "together."
    ),
    "temperature_schematic": (
        "Temperature-vs-time view is a simplified two-point envelope — the "
        "physics solver reports only the ambient baseline and the peak "
        "surface temperature at burn-through, not the intermediate trajectory."
    ),
    "material_comparison_unavailable": (
        "Material comparison could not be computed — the reference-range "
        "flux is below the threshold for every tabulated v1 material."
    ),
    "no_hazard_data": (
        "Hazard-zone schematic unavailable — Nominal Ocular Hazard Distance "
        "values were not produced for this input set."
    ),
}


# =============================================================================
# Login-screen copy (PR 1 ui/auth.py redesign)
# =============================================================================

LOGIN_COPY: dict[str, str] = {
    "wordmark":         "HEL Engineering Calculator",
    "password_label":   "Access code",
    "password_help":    "Contact owner for access.",
    # User decision on PR 1 open-items (2026-04-24): minimal help-line copy.
    "submit":           "Sign in",
    "auth_failure":     "Invalid access code. Try again.",
}


# =============================================================================
# Footer provenance (SPEC §5.3 item 12)
# =============================================================================

FOOTER_TEMPLATE: str = (
    "HEL Engineering Calculator · SPEC {spec_version} · ARCH {arch_version} · build {build_date}"
)


# =============================================================================
# Helpers
# =============================================================================

def input_label(key: str) -> str:
    """Return the user-visible label for an input key."""
    return INPUT_LABELS[key]["label"]


def input_tooltip(key: str) -> str:
    """Return the tooltip text for an input key."""
    return INPUT_LABELS[key].get("tooltip", "")


def input_unit(key: str) -> str:
    """Return the unit symbol for an input key."""
    return INPUT_LABELS[key].get("unit", "")


# =============================================================================
# Plain-language explanation copy
# =============================================================================
# Short prose passages that sit under section headers and plots to tell a
# non-specialist viewer what they are looking at, in a few sentences.
# Engineer voice per the Phase 3 UI-redesign plan §"Voice and tone":
# specific, active, unit every quantity, no hype. These strings are
# user-visible copy; the copy-style lint in tests/test_copy_style.py will
# reject any SPEC / ARCH / module-tag citations or emoji found here.
#
# VERDICT_EXPLANATIONS carries the five verdict-tier explanations. Keys
# match VERDICT_TEMPLATES above; the ``ok``/``warn``/``error`` entries
# accept ``dwell_s``, ``tau_s``, and either ``margin_pct`` or
# ``shortfall_pct`` for a context-aware sentence.
#
# EXPLANATIONS carries static passages (no substitutions) for the section
# headers and plots.

VERDICT_EXPLANATIONS: dict[str, str] = {
    "instant": (
        "The target meets its failure criterion essentially the moment the "
        "beam lands — any available dwell is more than enough."
    ),
    "no_dwell": (
        "No dwell window is available for this geometry. The target "
        "kinematics leave no interval in which the beam can hold its aim. "
        "Reduce target velocity, widen the aimpoint, or adjust the "
        "emplacement and target altitudes so the line-of-sight rate "
        "stays within trackable limits."
    ),
    "ok": (
        "The beam can hold the target for {dwell_s:.1f} s before the "
        "geometry changes (available dwell), and the target needs only "
        "{tau_s:.1f} s of that flux to be defeated (time to burn-through). "
        "The {margin_pct:.0f}% margin leaves comfortable headroom — "
        "realistic pointing errors or mid-engagement re-aims are unlikely "
        "to compromise the kill."
    ),
    "warn": (
        "The beam can hold the target for {dwell_s:.1f} s (available "
        "dwell), and the target needs {tau_s:.1f} s to be defeated (time "
        "to burn-through). The {margin_pct:.0f}% margin is positive but "
        "thin — extra jitter, worse weather, or a tougher material lot "
        "could push the engagement below zero margin."
    ),
    "error": (
        "The beam can only hold the target for {dwell_s:.1f} s before the "
        "geometry changes (available dwell), but the target needs "
        "{tau_s:.1f} s to be defeated (time to burn-through). The dwell "
        "falls short by {shortfall_pct:.0f}%. To close the gap: increase "
        "output power, shorten the engagement range, improve beam "
        "quality, or pick a thinner or lower-threshold target material."
    ),
}


EXPLANATIONS: dict[str, str] = {
    # --- Overview tab -----------------------------------------------------
    "overview_summary": (
        "These six numbers summarise the whole engagement. Power at the "
        "aimpoint is what actually lands on the target after atmospheric "
        "losses and beam spreading; peak irradiance is the brightest point "
        "in that spot. Time to burn-through is how long that flux must be "
        "held to defeat the target; available dwell is how long the "
        "geometry lets you hold the aim. Wall-plug input power and waste "
        "heat size the generator and cooling plant."
    ),
    "overview_headroom": (
        "Sustain time is how long the laser can keep shooting before "
        "battery or thermal limits force a stand-down. Engagements per "
        "hour is the repeat rate the energy budget supports — a system "
        "that can defeat one drone but needs ten minutes to cool between "
        "shots is a very different capability from one that can "
        "volley-engage."
    ),
    "overview_margin_plot": (
        "The two bars compare the same quantity (time, seconds) side by "
        "side: available dwell on the left, time to burn-through on the "
        "right. When the right bar is shorter, the beam defeats the "
        "target before the geometry runs out and the engagement is "
        "feasible; when it is taller, the dwell runs out first and the "
        "engagement is not."
    ),
    # --- Engagement tab ---------------------------------------------------
    "engagement_spot_strehl": (
        "This section splits the delivered spot at the reference range "
        "into its four angular-error sources and compares the achieved "
        "peak intensity against a perfect beam. Diffraction is the "
        "floor every beam has; the other three — beam-quality excess "
        "(imperfect optics), turbulence (atmosphere), and jitter (mount "
        "shake) — add on top of it. The final card shows how close the "
        "system gets to a diffraction-limited, turbulence-free, "
        "blooming-free baseline: a ratio of 1.0 is perfect; the value "
        "shown is this system's share of theoretical best."
    ),
    "plot_a_intro": (
        "This chart shows the brightest point in the beam spot at every "
        "range along the engagement. The gray reference line is what a "
        "perfect diffraction-limited beam would deliver; the solid curve "
        "is what this system actually delivers after atmosphere and "
        "broadening. The three right-axis curves (dimensionless, 0 to 1) "
        "are the fraction of power that lands inside the aimpoint, the "
        "thermal-blooming Strehl (how much blooming dims the peak), and "
        "atmospheric transmission."
    ),
    "plot_b_intro": (
        "This chart shows how long the beam must hold the target to "
        "defeat it at every range along the engagement. The horizontal "
        "reference is the available dwell — wherever the burn-through "
        "curve sits below that line, the engagement is feasible; where "
        "it rises above, the dwell runs out first."
    ),
    "plot_c_intro": (
        "This chart decomposes the beam spot at the target into its five "
        "physical contributors: diffraction (an ideal beam spreads too), "
        "beam-quality excess (imperfect optics), turbulence (atmosphere), "
        "thermal blooming (the beam heats the air it passes through), "
        "and jitter (mount shake). At short range the diffraction floor "
        "dominates; at long range turbulence and jitter grow fastest, "
        "with blooming kicking in once the on-path power density is high."
    ),
    "plot_c_v2_intro": (
        "This chart shows how the beam spot at the target tightens as the "
        "target closes during the engagement. The horizontal reference is "
        "the aimpoint bucket diameter; the amber band marks the part of "
        "the trajectory where the spot is wider than the bucket and most "
        "of the beam is missing the aimpoint. As the target gets closer, "
        "the diffraction-limited spot shrinks and the spot eventually "
        "fits inside the bucket — at which point on-target intensity "
        "rises rapidly."
    ),
    "plot_d_intro": (
        "This chart shows the thermal-blooming distortion number across "
        "range. Below the green band the air doesn't heat enough to bend "
        "the beam appreciably. Inside the unshaded middle band, blooming "
        "scaling is well-understood. The red band marks where the model "
        "stops being trustworthy — if the curve enters it, the spot-size "
        "and Strehl numbers above are best-effort engineering estimates."
    ),
    "plot_e_intro": (
        "This chart turns the time budget from the burn-through plot into "
        "a pass-or-fail margin at every range. Green means the dwell window "
        "comfortably exceeds the burn-through time; amber means it just "
        "barely covers it (small disturbance and the engagement fails); "
        "red means the target moves through the field before the laser "
        "can finish the job."
    ),
    "plot_g_intro": (
        "This chart compares the beam's 1/e² spot diameter at the target "
        "to the aimpoint bucket the user is shooting for. The amber band "
        "marks where the spot has grown larger than the bucket — beyond "
        "that range less than 86 % of the energy is hitting the part of "
        "the target that matters, and the engagement is wasting power on "
        "the surroundings."
    ),
    "math_intro": (
        "Every number this tool prints has a formula behind it, a citation "
        "behind that formula, and an assumption set you should know about. "
        "This tab shows them all in one place: each metric, its formula in "
        "textbook notation, its value for your current run, and a "
        "plain-language explanation. Toggle to Full view for the substituted "
        "values, the literature citation, the line of code that computes it, "
        "and any flagged assumptions."
    ),
}


def verdict_explanation(
    result: dict,
) -> str:
    """Return the plain-language explanation sentence for the current verdict.

    Reads ``by_module.m8.tau_BT`` and ``by_module.m3.available_dwell`` from
    ``result`` and picks the matching entry in ``VERDICT_EXPLANATIONS``,
    substituting the concrete dwell, burn-through, and margin values so
    the explanation quotes specific numbers, not generic ranges.

    Mirrors the branching in ``_verdict_chip`` in ``ui/outputs.py`` so the
    chip and the prose always agree on which tier applies.

    Args:
        result: merged orchestrator-result dict (same shape rendered by
            the tabs).

    Returns:
        A single formatted sentence, ready to pass to
        ``st.markdown(...)``. Never raises; missing inputs fall back to
        the ``no_dwell`` branch.
    """
    by = result.get("by_module", {})
    tau_bt = by.get("m8", {}).get("tau_BT")
    dwell = by.get("m3", {}).get("available_dwell")

    if tau_bt is None or (isinstance(tau_bt, (int, float)) and tau_bt <= 0.0):
        return VERDICT_EXPLANATIONS["instant"]
    if dwell is None or (isinstance(dwell, (int, float)) and dwell <= 0.0):
        return VERDICT_EXPLANATIONS["no_dwell"]

    margin_frac = (dwell - tau_bt) / tau_bt
    tau_s = float(tau_bt)
    dwell_s = float(dwell)
    if margin_frac >= 0.30:
        return VERDICT_EXPLANATIONS["ok"].format(
            dwell_s=dwell_s, tau_s=tau_s, margin_pct=margin_frac * 100.0,
        )
    if margin_frac >= 0.0:
        return VERDICT_EXPLANATIONS["warn"].format(
            dwell_s=dwell_s, tau_s=tau_s, margin_pct=margin_frac * 100.0,
        )
    return VERDICT_EXPLANATIONS["error"].format(
        dwell_s=dwell_s, tau_s=tau_s, shortfall_pct=abs(margin_frac) * 100.0,
    )


def output_label(key: str) -> str:
    """Return the user-visible label for an output (result-dict) key."""
    return OUTPUT_LABELS[key]["label"]


def output_tooltip(key: str) -> str:
    """Return the tooltip text for an output key."""
    return OUTPUT_LABELS[key].get("tooltip", "")


def output_unit(key: str) -> str:
    """Return the unit symbol for an output key."""
    return OUTPUT_LABELS[key].get("unit", "")


__all__ = [
    "SECTION_LABELS",
    "TAB_LABELS",
    "INPUT_LABELS",
    "OUTPUT_LABELS",
    "MATERIAL_DISPLAY_NAMES",
    "PRESET_LABELS",
    "PRESET_PICKER_LABEL",
    "PRESET_PICKER_HELP",
    "BUTTON_LABELS",
    "VERDICT_TEMPLATES",
    "VERDICT_EXPLANATIONS",
    "EXPLANATIONS",
    "ADVISORY",
    "LOGIN_COPY",
    "FOOTER_TEMPLATE",
    "input_label",
    "input_tooltip",
    "input_unit",
    "output_label",
    "output_tooltip",
    "output_unit",
    "verdict_explanation",
]
