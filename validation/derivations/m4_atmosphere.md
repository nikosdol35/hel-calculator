# M4 — Atmospheric attenuation

**Files:** `physics/m4_atmosphere.py`, `physics/m4_data_tables.py`
**Outputs:** `alpha_atm`, `tau_atm`, `alpha_mol_abs`, `alpha_mol_scat`, `alpha_aer_abs`, `alpha_aer_scat`

## Formulas implemented (code ↔ SPEC ↔ source)

| Code line | Expression | SPEC | Primary citation | Secondary citation | Status |
|---|---|---|---|---|---|
| 90–92 | `α_mol_abs = interp_log_space(λ, table) · (RH/0.60)` | §3 M4 | McClatchey AFCRL-TR-72-0497 (1971) | Andrews & Phillips §12 | HIGH UNCERTAINTY — SPEC §10.1 |
| 93 | `α_mol_scat = interp_log_space(λ, table)` | §3 M4 | McClatchey 1971 | — | HIGH UNCERTAINTY — SPEC §10.1 |
| 97 | `α_aer_total = (3.91/V_km)·(λ_µm/0.55)^(-q)` | §3 M4 | Kruse 1962, *Elements of Infrared Technology* | Andrews & Phillips §12 eq. 12.7 | verified |
| 98 | `α_aer_abs = 0.05 · α_aer_total` | §3 M4 | McClatchey 1971 (typical marine-rural split) | — | verified (engineering) |
| 99 | `α_aer_scat = 0.95 · α_aer_total` | §3 M4 | McClatchey 1971 | — | verified (engineering) |
| 101–104 | `α_atm = Σ all four` | §3 M4 | Beer-Lambert extinction | — | verified |
| 112 | `τ_atm = exp(−α_atm·R)` | §3 M4 | Beer-Lambert | Andrews & Phillips §12 | verified |
| 125–133 | Kruse piecewise `q(V)` | §3 M4 | Kruse 1962 | McClatchey 1971 (V<1 extension) | verified |

## Constants used

| Constant | Value | Units | Source | HIGH UNCERTAINTY |
|---|---|---|---|---|
| `_AER_SCAT_FRACTION` (line 24) | 0.95 | — | McClatchey 1971 marine-rural split; user can reset by changing the two fractions in lockstep | engineering default |
| `_AER_ABS_FRACTION` (line 25) | 0.05 | — | McClatchey 1971; sums to 1.00 with scat fraction | engineering default |
| `_RH_BASELINE` (line 26) | 0.60 | — | SPEC §3 M4 baseline; table values computed at 60% RH | engineering default |
| Kruse aerosol prefactor | 3.91 | km | Kruse 1962 eq. 6.14; `3.91 = ln(50)` meteorological-visibility definition | verified |
| Kruse reference wavelength | 0.55 | µm | Photopic visibility reference | verified |
| Kruse q piecewise (line 127–133) | 1.6 / 1.3 / 0.16V+0.34 / V−0.5 | — | Kruse 1962 + McClatchey 1971 V<1 extension | verified; V>50 branch is dead code (outside input bounds) |
| `ALPHA_MOL_ABSORPTION_1_PER_KM` (m4_data_tables.py) | {0.045, 0.065, 0.190, 0.490} at {1.06, 1.07, 1.55, 2.05} µm | 1/km | Engineering baseline from McClatchey 1971; refine vs HITRAN/MODTRAN | HIGH UNCERTAINTY — SPEC §10.1 |
| `ALPHA_MOL_SCATTERING_1_PER_KM` | {0.005, 0.005, 0.010, 0.010} at same wavelengths | 1/km | Engineering baseline — Rayleigh-scattering scaling | HIGH UNCERTAINTY — SPEC §10.1 |

## Derivation

### Beer-Lambert

Along a path of length L with (possibly range-varying) extinction coefficient α(z), transmission is

```
τ = exp(−∫₀^L α(z) dz)
```

Under the sea-level approximation (v1 simplification, flagged in `assumptions_flagged`) we use a range-independent α, giving `τ = exp(−α·L)` (line 112).

### Four-way decomposition

Total extinction is the sum of four independent processes:

```
α_atm = α_mol_abs + α_mol_scat + α_aer_abs + α_aer_scat
```

- **Molecular absorption (α_mol_abs)** — H₂O, CO₂ line absorption in the NIR/SWIR transparency windows. Taken from tabulated mid-latitude summer 60%-RH values. Linear RH scaling `(RH / 0.60)` applied to absorption (first-order approximation for water vapor column scaling near baseline).
- **Molecular scattering (α_mol_scat)** — Rayleigh scattering from atmospheric gases. Largely RH-independent; ∝ λ⁻⁴ in principle, but over the 1.06 → 2.05 µm range scattering is dominated by aerosol, so tabulated values suffice.
- **Aerosol absorption (α_aer_abs) + scattering (α_aer_scat)** — Kruse aerosol model (below).

### Kruse aerosol extinction

Kruse 1962, building on visual-range measurements, established:

```
α_aer_total(λ) = (3.91 / V_km) · (λ / 0.55 µm)^(−q)
```

The 3.91 prefactor is exactly `−ln(0.02)` (2% contrast threshold) divided by 1 km — the definition of meteorological visibility V. The reference wavelength 0.55 µm is the photopic peak.

The wavelength exponent `q` captures the size-distribution dependence: for large clear-air droplets q → 1.6 (Mie regime); for small urban haze q → 0 (Rayleigh-limited). Kruse's piecewise rule (lines 127–133):

- `V > 50 km`: q = 1.6 (exceptional clarity; outside SPEC V range).
- `6 km ≤ V ≤ 50 km`: q = 1.3 (clear air).
- `1 km ≤ V < 6 km`: q = 0.16·V + 0.34 (intermediate haze).
- `V < 1 km`: q = V − 0.5 (fog/dense haze; McClatchey extension).

The `V > 50 km` branch is dead code — SPEC §3 M4 input range is `V ∈ [0.5, 50] km`.

### Aerosol absorption/scattering split

The 5%/95% split (absorption/scattering) reflects typical marine and rural aerosol composition. For urban aerosols the absorption fraction can rise to 10–20% (Bergstrom 2007); users should override if modeling an urban engagement. This is flagged as an engineering default, not a precision claim.

## Known simplifications

- **Sea-level atmosphere along the slant path.** SPEC v1 does not integrate over altitude-varying molecular concentrations. For slant paths through the boundary layer this is conservative (overestimates extinction at altitude). Flagged per SPEC §10 entry.
- **α_mol tables are engineering placeholders** — SPEC §10.1 HIGH UNCERTAINTY. Real line-by-line HITRAN calculation gives significantly different values especially at 1.55 and 2.05 µm (CO₂ band edges).
- **Linear RH scaling** of molecular absorption is first-order only; near saturation (RH > 90%) water vapor continuum effects depart significantly.
- **Kruse q(V) is empirical** for natural atmospheres at visible wavelengths; extrapolating to 2.05 µm pushes beyond the original validation range.
- **No wavelength dependence in the 5%/95% aerosol split** — single value used across all wavelengths.

## Cross-check

Canonical scenario: λ = 1.07 µm, V = 23 km, RH = 0.60 (baseline), R = 1500 m.

Hand computation:
- `q` at V = 23 km: q = 1.3 (second branch).
- `α_aer_total = (3.91 / 23) · (1.07/0.55)^(−1.3) = 0.1700 · (1.945)^(−1.3) = 0.1700 · 0.4236 = 0.0720 1/km`.
- `α_aer_abs = 0.05 · 0.0720 = 0.00360 1/km`; `α_aer_scat = 0.95 · 0.0720 = 0.06840 1/km`.
- `α_mol_abs = 0.065 · (0.60/0.60) = 0.065 1/km` (table lookup at 1.07 µm).
- `α_mol_scat = 0.005 1/km` (table lookup at 1.07 µm).
- `α_atm_per_km = 0.065 + 0.005 + 0.00360 + 0.06840 = 0.1420 1/km = 1.420e-4 1/m`.
- `τ_atm = exp(−1.420e-4 · 1500) = exp(−0.2130) = 0.808`.

Independent verification with `physics/m4_atmosphere.py:compute` produces the same values to 4 sig figs.

## Cross-reference to CLAUDE §7.1

M4 has no explicitly-listed audit-sensitive formulas in CLAUDE §7.1. Attention points: the `(RH / _RH_BASELINE)` scaling assumes `_RH_BASELINE = 0.60`; if `_RH_BASELINE` is edited without refreshing the tables, `α_mol_abs` becomes systematically wrong. The values 0.60 and the tables must change together — flagged for `constants_audit.md`.
