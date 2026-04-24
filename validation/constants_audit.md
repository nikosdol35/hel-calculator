# Constants audit

**Scope:** Every hard-coded numeric constant in `physics/` and `physics/*_tables.py`. One row per value, grouped by source file, with file + line + value + units + source + HIGH UNCERTAINTY status + audit verdict.

**How to read the verdict column:**
- **verified** — formula/constant matches the cited source at the stated precision.
- **verified (engineering)** — the value is a defensible engineering default, not a first-principles result. Deliberate choice, flagged in SPEC.
- **CLAUDE §7.1 invariant** — formula/constant is on the CLAUDE §7.1 audit-sensitive list; must not change without the §4.3 scope-change procedure.
- **HIGH UNCERTAINTY** — flagged in SPEC §10; see also `uncertainty_closeout.md` (Layer 4).
- **deferred v2** — known limitation, not fixed in v1 by design.

**Total constants in roster:** ≈ 160 (including each HV coefficient, each ANSI MPE coefficient, each material-property entry, each A_λ cell, each data-table value).

Revision history:
- 2026-04-24 — initial roster written during Package 1 validation campaign.

---

## `physics/common.py`

| Name/value | Line | Units | Source | Verdict |
|---|---|---|---|---|
| `tol_nm = 5.0` (default arg in `wavelength_in_validated_set`) | 29 | nm | ARCHITECTURE.md §4.3 wavelength-validation tolerance | verified |

No other constants — validators are parameter-driven.

---

## `physics/m1_laser_source.py`

No hard-coded constants. Every M1 output is algebraic in user inputs `(P0, M², D, λ)`.

| Implicit constants | Source | Verdict |
|---|---|---|
| Factor `4` in `θ_diff = M²·4λ/(πD)` | Siegman 1986 §17 full-angle M²-formalism divergence | CLAUDE §7.1 — verified |
| Factor `½` in `w0 = D/2` | Beam-fills-aperture convention | verified |
| Factor `π` in `zR = π·w0²/λ` | Elementary Gaussian beam (Siegman §16.2 eq. 16.2-8) | verified |
| Factor `2` in `I_exit = 2P/(πw0²)` | Gaussian peak irradiance | CLAUDE §7.1 invariant — verified |

---

## `physics/m2_beam_director.py`

No hard-coded constants. `P_exit = η_opt · P0` is a user-parameter product.

Recommended default `η_opt = 0.85` lives in SPEC §3 M2 rationale (5-mirror Coudé path, see `m2_power_link.md`). Not hard-coded — user always supplies.

---

## `physics/m3_geometry.py`

| Name | Line | Value | Units | Source | Verdict |
|---|---|---|---|---|---|
| `_FOV_DEG_DEFAULT` | 17 | 5.0 | deg | SPEC §10.5 engagement-basket mid-range heuristic | HIGH UNCERTAINTY — SPEC §10.5 |

Implicit:
| Factor `2` in `2·R·tan(FOV/2)` | Line 65 | basket diameter | Engineering-basket geometry | verified |

---

## `physics/m4_atmosphere.py`

| Name | Line | Value | Units | Source | Verdict |
|---|---|---|---|---|---|
| `_AER_SCAT_FRACTION` | 24 | 0.95 | — | McClatchey 1971 marine-rural aerosol split | verified (engineering) |
| `_AER_ABS_FRACTION` | 25 | 0.05 | — | Complement of above | verified (engineering) |
| `_RH_BASELINE` | 26 | 0.60 | — | SPEC §3 M4 table baseline | verified (engineering) |
| Kruse prefactor | 97 | 3.91 | km | `−ln(0.02)`, meteorological-visibility 2% contrast (Kruse 1962 eq. 6.14) | verified |
| Kruse reference wavelength | 97 | 0.55 | µm | Photopic-peak (visibility) | verified |
| Kruse q branch `V > 50 km` | 127 | 1.6 | — | Kruse 1962 | verified — dead code (outside SPEC V range) |
| Kruse q branch `V > 6 km` | 129 | 1.3 | — | Kruse 1962 | verified |
| Kruse q branch `1 ≤ V < 6` | 131 | `0.16·V + 0.34` | — | Kruse 1962 | verified |
| Kruse q branch `V < 1 km` | 133 | `V − 0.5` | — | McClatchey 1971 extension for dense haze/fog | verified |

Implicit:
| Factor `exp(−α·R)` | Line 112 | Beer-Lambert | verified |

---

## `physics/m4_data_tables.py`

**α_mol absorption table** (1/km, line 15–20):

| Wavelength | Value | HIGH UNCERTAINTY |
|---|---|---|
| 1.06 µm | 0.045 | SPEC §10.1 — refine vs HITRAN |
| 1.07 µm | 0.065 | SPEC §10.1 — refine vs HITRAN |
| 1.55 µm | 0.190 | SPEC §10.1 — refine vs HITRAN |
| 2.05 µm | 0.490 | SPEC §10.1 — refine vs HITRAN |

**α_mol scattering table** (1/km, line 23–28):

| Wavelength | Value | HIGH UNCERTAINTY |
|---|---|---|
| 1.06 µm | 0.005 | SPEC §10.1 |
| 1.07 µm | 0.005 | SPEC §10.1 |
| 1.55 µm | 0.010 | SPEC §10.1 |
| 2.05 µm | 0.010 | SPEC §10.1 |

**Validated wavelength set** (line 12): `(1.06e-6, 1.07e-6, 1.55e-6, 2.05e-6)` m — SPEC §3 scope-fixed.

---

## `physics/m5_turbulence.py`

| Name | Line | Value | Units | Source | Verdict |
|---|---|---|---|---|---|
| Fried coefficient | 127 | 0.423 | — | Andrews & Phillips §6.5 eq. 6.91; Fried 1967 | CLAUDE §7.1 — verified |
| Engineering `w_turb` factor | 128 | 2 | — | Engineering form → 1/e² radius | CLAUDE §7.1 — verified |
| Kolmogorov exponent | 117 | 5/3 | — | Kolmogorov inertial range | verified |
| Closed-form integral coefficient | 103 | 3/8 | — | `∫₀¹ u^(5/3) du = 3/8` | verified |
| HV-5/7 high-altitude amplitude | 51 | 0.00594 | m⁻²/³·(s/m)² | Hufnagel 1974 | verified |
| HV reference wind speed | 51 | 27.0 | m/s | Mid-latitude jet-stream baseline | verified |
| HV altitude exponent | 51 | 10 | — | Hufnagel profile | verified |
| HV high-altitude scale height | 51 | 1000.0 | m | Hufnagel 1974 | verified |
| HV boundary-layer amplitude | 52 | 2.7e-16 | m⁻²/³ | HV-5/7 surface-layer constant | verified |
| HV boundary-layer scale height | 52 | 1500.0 | m | Hufnagel 1974 | verified |
| HV ground scale height | 53 | 100.0 | m | Near-surface thermal plume | verified |
| HV inner-scale scaling | 51 | 1e-5 | 1/m | HV profile scaling | verified |

---

## `physics/m6_blooming.py`

| Name | Line | Value | Units | Source | Verdict |
|---|---|---|---|---|---|
| `_MOLAR_MASS_AIR` | 27 | 0.029 | kg/mol | CIPM 2007 standard dry air | verified |
| `_R_UNIVERSAL` | 28 | 8.314 | J/(mol·K) | CODATA 2018 exact | verified |
| `_C_P_AIR` | 29 | 1005.0 | J/(kg·K) | Dry-air c_p at ~290 K | verified (engineering — ≤1% T variation) |
| `_N0_AIR` | 30 | 1.000293 | — | Edlén 1966 (0°C, 101.325 kPa, 500 nm) | verified (NIR approx per SPEC) |
| `_DNDT_STP` | 31 | −0.93e-6 | 1/K at STP | Gladstone-Dale + ideal gas; Owens 1967 | verified |
| `_T_REF` | 32 | 288.0 | K | ISA 15 °C reference | verified |
| `_P_REF` | 33 | 101325.0 | Pa | ISO 2533 sea-level reference | verified |
| `_N_CRIT` | 34 | 5.0 | — | Smith Strehl half-power cutoff | verified |
| `_N_VALIDITY` | 35 | 30.0 | — | Upper validity of Smith/Gebhardt fits | verified |
| Gebhardt prefactor | 84 | `4·√2` ≈ 5.657 | — | Gebhardt 1990 Proc. SPIE 1221 | CLAUDE §7.1 — verified |
| Broadening empirical | 95 | 0.3 | — | Post-fit to Gebhardt 1990 broadening table | HIGH UNCERTAINTY — SPEC §10.4 |

---

## `physics/m7_spot_pib.py`

No hard-coded constants. Every factor-of-2 is a physics invariant (see `m7_spot.md` table). Each is a CLAUDE §7.1 item:

| Factor-of-2 | Line | Meaning | Verdict |
|---|---|---|---|
| `2` in `I_peak = 2P/(πw²)` | 103 | Gaussian peak vs flat-top | CLAUDE §7.1 — verified |
| `2` in `w_jit = 2·σ·L` | 90 | σ per-axis → 1/e² radius | CLAUDE §7.1 — verified |
| `2` in PIB exponent `−2·R_aim²/w²` | 108 | Gaussian `exp(−2r²/w²)` form | CLAUDE §7.1 — verified |
| `2` in `d_spot = 2·w_total` | 94 | Diameter = 2 × radius | verified (trivial) |
| `2` in `w_turb = 2L/(k·r₀)` | 86 | M5 engineering-form pass-through | CLAUDE §7.1 — verified (see m5) |

---

## `physics/m8_burnthrough.py`

| Name | Line | Value | Units | Source | Verdict |
|---|---|---|---|---|---|
| `_DX_TARGET` | 41 | 5.0e-5 | m | SPEC §3 M8 — 50 µm grid | verified |
| `_N_MIN` | 42 | 21 | — | 20 intervals minimum | verified |
| `_STABILITY_SAFETY` | 43 | 0.4 | — | Explicit-FD Fourier safety factor (r < 0.5) | verified |
| `_SIM_TIMEOUT_S` | 44 | 60.0 | s | SPEC §3 M8 integration timeout | verified |
| `_DECOMP_SUSTAIN_S` | 45 | 0.05 | s | SPEC §3 M8 decomposition hold | verified |
| Natural-convection floor | 136 | 10.0 | W/(m²·K) | Incropera & DeWitt §9 free-convection | HIGH UNCERTAINTY — SPEC §10.6 |
| Forced-convection coef | 136 | 6.2 | W/(m²·K)·(s/m)^0.5 | Flat-plate laminar-forced correlation | HIGH UNCERTAINTY — SPEC §10.6 |

---

## `physics/m8_material_tables.py`

| Name | Line | Value | Units | Source | Verdict |
|---|---|---|---|---|---|
| `EMISSIVITY_IR_DEFAULT` | 22 | 0.85 | — | SPEC §3 M8 default | verified (engineering) |
| `SIGMA_SB` | 25 | 5.670374419e-8 | W/(m²·K⁴) | CODATA 2018 exact | verified |

**Material properties** (lines 30–87). Seven materials × six fields = 42 values:

| Material | ρ (kg/m³) | c_p (J/kg·K) | k (W/m·K) | T_fail (K) | L_f (J/kg) | mode | Source |
|---|---|---|---|---|---|---|---|
| anodized_Al | 2700 | 900 | 200 | 933 | 397 000 | melt | ASM Vol. 2 (6061-T6) |
| CFRP | 1600 | 1000 | 7.0 | 600 | — | decomposition | Hexcel 8552 / Toray T700 |
| GFRP | 1900 | 800 | 0.4 | 600 | — | decomposition | OCV E-glass |
| polycarbonate | 1200 | 1200 | 0.2 | 700 | — | decomposition | ASM Eng. Plastics |
| ABS | 1050 | 1400 | 0.17 | 670 | — | decomposition | Matweb aggregated |
| EPP_foam | 30 | 1900 | 0.04 | 620 | — | decomposition | ASM Eng. Plastics |
| LiPo | 1800 | 1000 | 0.5 | 420 | — | vent | Sandia SAND2014-18253 |

All material-property values: verified (engineering; vendor variance ±20–40% for composites). Adding an eighth material requires SPEC update per CLAUDE §7.3.

**A_λ table** (line 97–105). Seven materials × four wavelengths = 28 values. ALL 28 flagged SPEC §10.2 HIGH UNCERTAINTY:

| Material | 1.06 µm | 1.07 µm | 1.55 µm | 2.05 µm |
|---|---|---|---|---|
| anodized_Al | 0.30 | 0.30 | 0.25 | 0.20 |
| CFRP | 0.85 | 0.85 | 0.85 | 0.85 |
| GFRP | 0.40 | 0.40 | 0.45 | 0.55 |
| polycarbonate | 0.10 | 0.10 | 0.30 | 0.60 |
| ABS | 0.70 | 0.70 | 0.75 | 0.85 |
| EPP_foam | 0.50 | 0.50 | 0.55 | 0.70 |
| LiPo | 0.30 | 0.30 | 0.35 | 0.45 |

---

## `physics/m9_nohd.py`

| Name | Line | Value | Units | Source | Verdict |
|---|---|---|---|---|---|
| `_BAND_A_LO_M` | 54 | 0.400e-6 | m | ANSI Z136.1 Band A lower | verified |
| `_BAND_A_HI_M` | 55 | 1.400e-6 | m | ANSI Z136.1 Band A/B boundary | verified |
| `_BAND_B_HI_M` | 56 | 4.000e-6 | m | ANSI Z136.1 Band B/C boundary | verified |
| `_CLASS4_W` | 59 | 0.5 | W | IEC 60825-1 Class 4 threshold | verified |
| `_CLASS3B_W` | 60 | 0.005 | W | IEC 60825-1 Class 3B threshold | verified |
| `_CLASS3R_W` | 61 | 0.001 | W | IEC 60825-1 Class 3R threshold | verified |
| `_CLASS1_W` | 62 | 0.00039 | W | IEC 60825-1 Class 1 AEL | verified |
| Band A t<18µs coef | 75 | 5e-3 | W/cm² | ANSI Z136.1-2014 Table 5a | verified |
| 18 µs break-point | 73 | 18e-6 | s | ANSI Z136.1 CW/pulsed boundary | verified |
| Band A 18µs–10s coef | 77 | 1.8e-3 | W/cm² | ANSI Z136.1-2014 Table 5a | verified (C_A=1 — SPEC §10.3) |
| Band A 18µs–10s exp | 77 | −0.25 | — | ANSI Z136.1-2014 Table 5a | verified |
| 10 s break-point | 76, 82 | 10.0 | s | ANSI Z136.1 acute/chronic boundary | verified |
| Band A chronic | 79 | 1.0e-3 | W/cm² | ANSI Z136.1-2014 Table 5a chronic | verified |
| Band B coef | 83 | 0.56 | W/cm² | ANSI Z136.1-2014 Table 5b | verified |
| Band B exp | 83 | −0.75 | — | ANSI Z136.1-2014 Table 5b | verified |
| Band B chronic | 85 | 0.1 | W/cm² | ANSI Z136.1-2014 Table 5b chronic | verified |
| Unit conversion | 98 | 1.0e4 | (W/cm²)/(W/m²) | Elementary | verified |
| NOHD top-hat factor | 155 | 4 | — | `I_avg = P/(πr²)` inversion | verified |
| NOHD Gaussian-peak factor | 156 | 8 | — | `I_peak = 2P/(πw²)` inversion | CLAUDE §7.1 — verified |

**C_A omission:** deliberate conservative choice per SPEC §10.3 HIGH UNCERTAINTY. Flagged in every call.

---

## `physics/m10_power_thermal.py`

| Name | Line | Value | Units | Source | Verdict |
|---|---|---|---|---|---|
| Seconds-per-hour | 88, 105 | 3600.0 | s/hour | Elementary | verified |

No other constants.

---

## `physics/orchestrator.py`

| Name | Line | Value | Units | Source | Verdict |
|---|---|---|---|---|---|
| `_DEFAULT_MAX_ITER` | 74 | 10 | — | SPEC §3 M6 iteration cap | verified |
| `_DEFAULT_TOL` | 75 | 0.01 | — | SPEC §3 M6 relative-convergence target | verified |

Fallback `t_engagement = 1.0 s` (line 286) for the degenerate case where both M8 and M3 fail to provide a valid dwell — defensive, not a physical number. Documented inline.

---

## Summary by status

| Status | Count (approx) |
|---|---|
| CLAUDE §7.1 invariants | 11 (see CLAUDE §7.1) |
| HIGH UNCERTAINTY (SPEC §10) | 8 α_mol + 28 A_λ + 1 FOV + 1 broadening + 2 h_conv + MPE C_A convention = **40+ values** |
| verified (primary source) | majority — every ANSI MPE coefficient, every material property, every fluid constant, every geometric factor |
| verified (engineering) | 0.85 emissivity, 0.60 RH baseline, 0.95/0.05 aerosol split, 1005 J/kg·K c_p |
| dead code | Kruse `V > 50 km` branch (outside SPEC V range) |

## Action items surfaced by the audit

No formula-level errors surfaced. All values agree with their cited primary sources at the precision carried in code.

**Flagged for Layer 4 HIGH UNCERTAINTY closeout** (Package 4):
1. α_mol tables (8 values) — refresh against HITRAN / MODTRAN.
2. A_λ matrix (28 values) — refresh per-material.
3. MPE C_A convention — reconfirm choice.
4. Blooming `0.3` broadening — refresh against wave-optics.
5. `_FOV_DEG_DEFAULT = 5°` — defend or defer.
6. `h_conv = 10 + 6.2·√v` — verify forced-convection correlation.

**Flagged for documentation only** (no code change):
- `_C_P_AIR = 1005.0` treats c_p as T-independent — <1% variation over SPEC T range; note in m6 derivation file.
- Kruse `V > 50 km` branch is dead code — outside SPEC input bounds. Note in m4 derivation file.
- `_N0_AIR = 1.000293` is a 500 nm value applied as NIR approximation — flagged in SPEC §3 M6 and in m6 derivation file.

All documentation notes are already captured in the per-module derivation files.
