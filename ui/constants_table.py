"""Constants and physical sources for the math tab.

Structured Python mirror of ``validation/constants_audit.md`` —
every hard-coded numeric in ``physics/`` with its value, units,
primary source, and audit verdict. The math tab renders this as a
series of tables grouped by module.

Design choice (per plan §11): code references are file-only or
``file::function`` — line numbers drift with edits and are not
worth the maintenance burden. Where the constants_audit.md surfaced
specific lines they're omitted here; readers who need them can
``Ctrl-F`` the named constant in the cited file.

The total roster is ~160 constants (≈80 named scalars + the 8 α_mol
table cells + 28 A_λ table cells + 7-material × 6-property = 42
material-table values + assorted unit-conversion factors). Rendering
all of them as a flat table is unhelpful — we group by module and
collapse the multi-cell tables (α_mol, A_λ, material properties)
into single sub-table records that point the reader at
``physics/m4_data_tables.py`` and ``physics/m8_material_tables.py``
for the full numeric content.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConstantEntry:
    """One row in the constants table."""
    name: str            # e.g. "_FOV_DEG_DEFAULT" or "Fried coefficient"
    value: str           # rendered as text — supports symbolic forms like "4·√2"
    units: str           # e.g. "1/(s)" — empty string for dimensionless
    source: str          # primary citation
    verdict: str         # one of: verified / verified (engineering) /
                         # CLAUDE §7.1 invariant / HIGH UNCERTAINTY / deferred v2
    code_ref: str        # "physics/m3_geometry.py" or "::function" suffix


# Module → list of constant entries. Order mirrors the dependency
# chain (M1 → M10 → orchestrator) so the reader can walk through.
CONSTANTS_BY_MODULE: dict[str, list[ConstantEntry]] = {

    # ----------------------------------------------------------------- M1
    "M1 — Laser source": [
        ConstantEntry("Factor 4 in θ_diff", "4", "—",
                      "Siegman 1986 §17 full-angle M² divergence",
                      "CLAUDE §7.1 invariant",
                      "physics/m1_laser_source.py"),
        ConstantEntry("Factor ½ in w0 = D/2", "1/2", "—",
                      "Beam-fills-aperture convention",
                      "verified",
                      "physics/m1_laser_source.py"),
        ConstantEntry("Factor 2 in I_exit = 2P/(πw²)", "2", "—",
                      "Gaussian peak vs flat-top",
                      "CLAUDE §7.1 invariant",
                      "physics/m1_laser_source.py"),
    ],

    # ----------------------------------------------------------------- M3
    "M3 — Engagement geometry": [
        ConstantEntry("_FOV_DEG_DEFAULT", "5.0", "deg",
                      "Engagement-basket mid-range heuristic",
                      "HIGH UNCERTAINTY",
                      "physics/m3_geometry.py"),
    ],

    # ----------------------------------------------------------------- M4
    "M4 — Atmosphere": [
        ConstantEntry("_AER_SCAT_FRACTION", "0.95", "—",
                      "McClatchey 1971 marine-rural aerosol split",
                      "verified (engineering)",
                      "physics/m4_atmosphere.py"),
        ConstantEntry("_AER_ABS_FRACTION", "0.05", "—",
                      "Complement of _AER_SCAT_FRACTION",
                      "verified (engineering)",
                      "physics/m4_atmosphere.py"),
        ConstantEntry("_RH_BASELINE", "0.60", "—",
                      "Mid-latitude summer reference humidity",
                      "verified (engineering)",
                      "physics/m4_atmosphere.py"),
        ConstantEntry("Kruse prefactor", "3.91", "km",
                      "−ln(0.02) — meteorological 2 % visibility "
                      "contrast (Kruse 1962 eq. 6.14)",
                      "verified",
                      "physics/m4_atmosphere.py"),
        ConstantEntry("Kruse reference wavelength", "0.55", "µm",
                      "Photopic-peak (visibility convention)",
                      "verified",
                      "physics/m4_atmosphere.py"),
        ConstantEntry("Kruse q (V > 50 km)", "1.6", "—",
                      "Kruse 1962 — outside v1 input range "
                      "(unreachable)",
                      "verified",
                      "physics/m4_atmosphere.py"),
        ConstantEntry("Kruse q (V > 6 km)", "1.3", "—",
                      "Kruse 1962",
                      "verified",
                      "physics/m4_atmosphere.py"),
        ConstantEntry("Kruse q (1 ≤ V < 6)", "0.16·V + 0.34", "—",
                      "Kruse 1962",
                      "verified",
                      "physics/m4_atmosphere.py"),
        ConstantEntry("Kruse q (V < 1 km)", "V − 0.5", "—",
                      "McClatchey 1971 dense-haze extension",
                      "verified",
                      "physics/m4_atmosphere.py"),
    ],

    # ----------------------------------------------------------- M4 tables
    "M4 — Molecular extinction tables": [
        ConstantEntry("α_mol absorption (1.06 µm)", "0.045", "1/km",
                      "McClatchey AFCRL-TR-72-0497 1972",
                      "HIGH UNCERTAINTY",
                      "physics/m4_data_tables.py"),
        ConstantEntry("α_mol absorption (1.07 µm)", "0.065", "1/km",
                      "McClatchey AFCRL-TR-72-0497 1972",
                      "HIGH UNCERTAINTY",
                      "physics/m4_data_tables.py"),
        ConstantEntry("α_mol absorption (1.55 µm)", "0.190", "1/km",
                      "McClatchey AFCRL-TR-72-0497 1972",
                      "HIGH UNCERTAINTY",
                      "physics/m4_data_tables.py"),
        ConstantEntry("α_mol absorption (2.05 µm)", "0.490", "1/km",
                      "McClatchey AFCRL-TR-72-0497 1972",
                      "HIGH UNCERTAINTY",
                      "physics/m4_data_tables.py"),
        ConstantEntry("α_mol scattering (1.06 µm)", "0.005", "1/km",
                      "McClatchey AFCRL-TR-72-0497 1972",
                      "HIGH UNCERTAINTY",
                      "physics/m4_data_tables.py"),
        ConstantEntry("α_mol scattering (1.07 µm)", "0.005", "1/km",
                      "McClatchey AFCRL-TR-72-0497 1972",
                      "HIGH UNCERTAINTY",
                      "physics/m4_data_tables.py"),
        ConstantEntry("α_mol scattering (1.55 µm)", "0.010", "1/km",
                      "McClatchey AFCRL-TR-72-0497 1972",
                      "HIGH UNCERTAINTY",
                      "physics/m4_data_tables.py"),
        ConstantEntry("α_mol scattering (2.05 µm)", "0.010", "1/km",
                      "McClatchey AFCRL-TR-72-0497 1972",
                      "HIGH UNCERTAINTY",
                      "physics/m4_data_tables.py"),
    ],

    # ----------------------------------------------------------------- M5
    "M5 — Atmospheric turbulence": [
        ConstantEntry("Fried coefficient", "0.423", "—",
                      "Andrews & Phillips 2005 §6.5 eq. 6.91; "
                      "Fried 1967",
                      "CLAUDE §7.1 invariant",
                      "physics/m5_turbulence.py"),
        ConstantEntry("Engineering w_turb factor", "2", "—",
                      "Engineering form converting r₀ to 1/e² "
                      "radius",
                      "CLAUDE §7.1 invariant",
                      "physics/m5_turbulence.py"),
        ConstantEntry("Kolmogorov exponent", "5/3", "—",
                      "Kolmogorov inertial-range scaling",
                      "verified",
                      "physics/m5_turbulence.py"),
        ConstantEntry("Constant-Cn² closed-form coefficient", "3/8",
                      "—",
                      "∫₀¹ u^(5/3) du = 3/8",
                      "verified",
                      "physics/m5_turbulence.py"),
        ConstantEntry("HV high-altitude amplitude", "0.00594",
                      "m^(−2/3)·(s/m)²",
                      "Hufnagel 1974",
                      "verified",
                      "physics/m5_turbulence.py"),
        ConstantEntry("HV reference wind speed", "27.0", "m/s",
                      "Mid-latitude jet-stream baseline (Valley 1980)",
                      "verified",
                      "physics/m5_turbulence.py"),
        ConstantEntry("HV altitude exponent", "10", "—",
                      "Hufnagel profile",
                      "verified",
                      "physics/m5_turbulence.py"),
        ConstantEntry("HV high-alt scale height", "1000.0", "m",
                      "Hufnagel 1974",
                      "verified",
                      "physics/m5_turbulence.py"),
        ConstantEntry("HV boundary-layer amplitude", "2.7×10⁻¹⁶",
                      "m^(−2/3)",
                      "HV-5/7 surface-layer constant",
                      "verified",
                      "physics/m5_turbulence.py"),
        ConstantEntry("HV boundary-layer scale", "1500.0", "m",
                      "Hufnagel 1974",
                      "verified",
                      "physics/m5_turbulence.py"),
        ConstantEntry("HV ground scale", "100.0", "m",
                      "Near-surface thermal-plume layer",
                      "verified",
                      "physics/m5_turbulence.py"),
    ],

    # ----------------------------------------------------------------- M6
    "M6 — Thermal blooming": [
        ConstantEntry("_MOLAR_MASS_AIR", "0.029", "kg/mol",
                      "CIPM 2007 standard dry air",
                      "verified",
                      "physics/m6_blooming.py"),
        ConstantEntry("_R_UNIVERSAL", "8.314", "J/(mol·K)",
                      "CODATA 2018 exact",
                      "verified",
                      "physics/m6_blooming.py"),
        ConstantEntry("_C_P_AIR", "1005.0", "J/(kg·K)",
                      "Dry-air c_p at ~290 K (≤ 1 % T variation "
                      "across SPEC range)",
                      "verified (engineering)",
                      "physics/m6_blooming.py"),
        ConstantEntry("_N0_AIR", "1.000293", "—",
                      "Edlén 1966 (0 °C, 101.325 kPa, 500 nm) — "
                      "NIR approximation",
                      "verified",
                      "physics/m6_blooming.py"),
        ConstantEntry("_DNDT_STP", "−0.93×10⁻⁶", "1/K",
                      "Gladstone-Dale + ideal gas; Owens 1967",
                      "verified",
                      "physics/m6_blooming.py"),
        ConstantEntry("_T_REF", "288.0", "K",
                      "ISA 15 °C reference",
                      "verified",
                      "physics/m6_blooming.py"),
        ConstantEntry("_P_REF", "101325.0", "Pa",
                      "ISO 2533 sea-level reference",
                      "verified",
                      "physics/m6_blooming.py"),
        ConstantEntry("_N_CRIT", "5.0", "—",
                      "Smith Strehl half-power cutoff",
                      "verified",
                      "physics/m6_blooming.py"),
        ConstantEntry("_N_VALIDITY", "30.0", "—",
                      "Upper validity bound for the Gebhardt-"
                      "Smith fits",
                      "verified",
                      "physics/m6_blooming.py"),
        ConstantEntry("Gebhardt prefactor", "4·√2 ≈ 5.657", "—",
                      "Gebhardt 1990 *Proc. SPIE* 1221",
                      "CLAUDE §7.1 invariant",
                      "physics/m6_blooming.py"),
        ConstantEntry("Broadening empirical", "0.3", "—",
                      "Sprangle et al NRL/MR/6790-08-9141 — "
                      "post-fit to Gebhardt 1990 broadening table",
                      "HIGH UNCERTAINTY",
                      "physics/m6_blooming.py"),
    ],

    # ----------------------------------------------------------------- M7
    "M7 — Spot size and PIB": [
        ConstantEntry("Factor 2 in I_peak", "2", "—",
                      "Gaussian peak vs flat-top",
                      "CLAUDE §7.1 invariant",
                      "physics/m7_spot_pib.py"),
        ConstantEntry("Factor 2 in w_jit = 2·σ·L", "2", "—",
                      "Per-axis σ → 1/e² radius",
                      "CLAUDE §7.1 invariant",
                      "physics/m7_spot_pib.py"),
        ConstantEntry("Factor 2 in PIB exponent", "2", "—",
                      "Gaussian exp(−2r²/w²) form",
                      "CLAUDE §7.1 invariant",
                      "physics/m7_spot_pib.py"),
    ],

    # ----------------------------------------------------------------- M8
    "M8 — Burn-through (solver)": [
        ConstantEntry("_DX_TARGET", "5.0×10⁻⁵", "m",
                      "50 µm grid spacing",
                      "verified",
                      "physics/m8_burnthrough.py"),
        ConstantEntry("_N_MIN", "21", "—",
                      "Minimum 20-interval discretization",
                      "verified",
                      "physics/m8_burnthrough.py"),
        ConstantEntry("_STABILITY_SAFETY", "0.4", "—",
                      "Explicit-FD Fourier safety factor "
                      "(Δt = 0.4 × CFL limit)",
                      "verified",
                      "physics/m8_burnthrough.py"),
        ConstantEntry("_SIM_TIMEOUT_S", "60.0", "s",
                      "Solver wall-clock cap",
                      "verified",
                      "physics/m8_burnthrough.py"),
        ConstantEntry("_DECOMP_SUSTAIN_S", "0.05", "s",
                      "Decomposition hold-time before failure",
                      "verified",
                      "physics/m8_burnthrough.py"),
        ConstantEntry("Natural-convection floor", "10.0",
                      "W/(m²·K)",
                      "Incropera & DeWitt §9 free-convection",
                      "HIGH UNCERTAINTY",
                      "physics/m8_burnthrough.py"),
        ConstantEntry("Forced-convection coefficient", "6.2",
                      "W/(m²·K)·(s/m)^0.5",
                      "Flat-plate laminar-forced correlation",
                      "HIGH UNCERTAINTY",
                      "physics/m8_burnthrough.py"),
        ConstantEntry("EMISSIVITY_IR_DEFAULT", "0.85", "—",
                      "Engineering default for typical drone "
                      "skins / composites",
                      "verified (engineering)",
                      "physics/m8_material_tables.py"),
        ConstantEntry("SIGMA_SB", "5.670374419×10⁻⁸",
                      "W/(m²·K⁴)",
                      "CODATA 2018 exact",
                      "verified",
                      "physics/m8_material_tables.py"),
    ],

    # ------------------------------------------- M8 material + A_λ tables
    "M8 — Material + A_λ tables (see physics/m8_material_tables.py)": [
        ConstantEntry(
            "Material properties (7 × 6 = 42 values)",
            "see source file",
            "ρ, c_p, k, T_fail, L_f, mode",
            "ASM Vol. 2 (metals); Hexcel/Toray/SABIC/OCV "
            "datasheets (composites + polymers); "
            "Sandia SAND2014-18253 (LiPo)",
            "verified (engineering)",
            "physics/m8_material_tables.py",
        ),
        ConstantEntry(
            "A_λ matrix (7 materials × 4 wavelengths = 28 values)",
            "see source file",
            "—",
            "Steen & Mazumder Ch. 5; Bergstrom 2007 *J. Appl. "
            "Phys.* 101:043517; manufacturer datasheets",
            "HIGH UNCERTAINTY",
            "physics/m8_material_tables.py",
        ),
    ],

    # ----------------------------------------------------------------- M9
    "M9 — Eye safety (ANSI Z136.1-2014)": [
        ConstantEntry("Band A lower edge", "0.400×10⁻⁶", "m",
                      "ANSI Z136.1 Band A lower",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("Band A/B boundary", "1.400×10⁻⁶", "m",
                      "ANSI Z136.1 Band A/B boundary",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("Band B/C boundary", "4.000×10⁻⁶", "m",
                      "ANSI Z136.1 Band B/C boundary",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("Class 4 threshold", "0.5", "W",
                      "IEC 60825-1 Class 4 power threshold",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("Class 3B threshold", "0.005", "W",
                      "IEC 60825-1 Class 3B threshold",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("Class 3R threshold", "0.001", "W",
                      "IEC 60825-1 Class 3R threshold",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("Class 1 AEL", "0.00039", "W",
                      "IEC 60825-1 Class 1 accessible-emission limit",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("18 µs break-point", "18×10⁻⁶", "s",
                      "ANSI Z136.1 CW/pulsed boundary",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("Band A pulsed coefficient", "5×10⁻⁷",
                      "J/cm²",
                      "ANSI Z136.1-2014 Table 5a — fixed at v1.12 "
                      "from a typo of 5×10⁻³ that produced a 10⁴ "
                      "discontinuity at the 18 µs join",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("Band A 18 µs–10 s coefficient", "1.8×10⁻³",
                      "W/cm²",
                      "ANSI Z136.1-2014 Table 5a (C_A = 1, "
                      "conservative)",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("Band A 18 µs–10 s exponent", "−0.25", "—",
                      "ANSI Z136.1-2014 Table 5a",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("10 s break-point", "10.0", "s",
                      "ANSI Z136.1 acute/chronic boundary",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("Band A chronic limit", "1.0×10⁻³",
                      "W/cm²",
                      "ANSI Z136.1-2014 Table 5a chronic",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("Band B coefficient", "0.56", "W/cm²",
                      "ANSI Z136.1-2014 Table 5b",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("Band B exponent", "−0.75", "—",
                      "ANSI Z136.1-2014 Table 5b",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("Band B chronic limit", "0.1", "W/cm²",
                      "ANSI Z136.1-2014 Table 5b chronic",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("NOHD top-hat factor", "4", "—",
                      "I_avg = P/(πr²) inversion",
                      "verified",
                      "physics/m9_nohd.py"),
        ConstantEntry("NOHD Gaussian-peak factor", "8", "—",
                      "I_peak = 2P/(πw²) inversion",
                      "CLAUDE §7.1 invariant",
                      "physics/m9_nohd.py"),
    ],

    # ---------------------------------------------------------------- M10
    "M10 — Power and thermal resources": [
        ConstantEntry("Seconds per hour", "3600.0", "s/h",
                      "Elementary unit conversion",
                      "verified",
                      "physics/m10_power_thermal.py"),
    ],

    # --------------------------------------------------------- Orchestrator
    "Orchestrator (M6↔M7 fixed-point loop)": [
        ConstantEntry("_DEFAULT_MAX_ITER", "10", "—",
                      "Iteration cap for the blooming-focusing "
                      "loop",
                      "verified",
                      "physics/orchestrator.py"),
        ConstantEntry("_DEFAULT_TOL", "0.01", "—",
                      "Relative-convergence target on w_total "
                      "(1 %)",
                      "verified",
                      "physics/orchestrator.py"),
    ],
}


def total_constant_count() -> int:
    """Sum of all explicit entries across modules. Used by the
    rendering-side caption ("≈ N constants traced to source") and
    by the test that guards against accidental dropouts."""
    return sum(len(v) for v in CONSTANTS_BY_MODULE.values())


__all__ = [
    "ConstantEntry",
    "CONSTANTS_BY_MODULE",
    "total_constant_count",
]
