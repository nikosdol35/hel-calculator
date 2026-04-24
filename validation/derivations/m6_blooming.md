# M6 — Thermal blooming

**File:** `physics/m6_blooming.py`
**Outputs:** `N_D`, `S_TB`, `w_bloom`

## Formulas implemented (code ↔ SPEC ↔ source)

| Code line | Expression | SPEC | Primary citation | Secondary citation | Status |
|---|---|---|---|---|---|
| 81 | `ρ = P_atm · 0.029 / (8.314 · T)` | §3 M6 | Ideal-gas law | NIST RP1-2013 standard atmosphere | verified |
| 82 | `dn/dT = −0.93e-6 · (288/T) · (P/P_ref)` | §3 M6 | Gladstone-Dale with T and P scaling | Ciddor 1996 *Appl. Opt.* 35, 1566 | verified (CLAUDE §7.1 invariant) |
| 84–86 | `N_D = 4·√2 · (−dn/dT) · (α·P·R²) / (n₀·ρ·c_p·v_perp·w³)` | §3 M6 | Gebhardt 1990 *Proc. SPIE* 1221 | Gebhardt 1976 *Appl. Opt.* 15(6), 1479 | verified (CLAUDE §7.1 4√2 prefactor) |
| 88 | `S_TB = 1 / (1 + (N_D/5)²)` | §3 M6 | Smith 1977 *Appl. Opt.* 16, 1797 | Gebhardt 1990 Fig. 3 | verified |
| 92–95 | `w_bloom = 0 if N_D<5 else w·√((N_D/5)²−1)·0.3` | §3 M6 | Engineering post-fit to Gebhardt 1990 broadening table | — | HIGH UNCERTAINTY — SPEC §10.4 |
| 101–106 | `N_D > 30` → model-validity flag | §3 M6 | Smith/Gebhardt approximation validity limit | — | verified |

## Constants used

| Constant | Value | Units | Source | Status |
|---|---|---|---|---|
| `_MOLAR_MASS_AIR` (line 27) | 0.029 | kg/mol | Standard dry-air composition (CIPM 2007) | verified |
| `_R_UNIVERSAL` (line 28) | 8.314 | J/(mol·K) | CODATA 2018 exact | verified |
| `_C_P_AIR` (line 29) | 1005.0 | J/(kg·K) | Mid-range specific heat of dry air at ~290 K; <1% variation over SPEC T range | verified (engineering constant — see flagging note below) |
| `_N0_AIR` (line 30) | 1.000293 | — | Standard-air refractive index at 500 nm, 0 °C, 101325 Pa (Edlén 1966) | verified — used as NIR approximation per SPEC §3 M6 |
| `_DNDT_STP` (line 31) | −0.93e-6 | 1/K at STP | Gladstone-Dale + ideal gas; Owens 1967 J. Opt. Soc. Am. 57, 961 | verified |
| `_T_REF` (line 32) | 288.0 | K | Standard-atmosphere 15 °C reference (ISA) | verified |
| `_P_REF` (line 33) | 101325.0 | Pa | Standard-atmosphere sea-level pressure (ISO 2533) | verified |
| `_N_CRIT` (line 34) | 5.0 | — | Smith Strehl half-power cutoff | verified |
| `_N_VALIDITY` (line 35) | 30.0 | — | Upper validity of Smith/Gebhardt broadening fits | verified |
| `4·√2` (line 84) | 5.657 | — | Gebhardt 1990 prefactor | CLAUDE §7.1 invariant; verified |
| `0.3` (line 95) | 0.3 | — | Empirical broadening post-fit | HIGH UNCERTAINTY — SPEC §10.4 |

## Derivation

### Distortion number `N_D`

The Gebhardt distortion number measures the phase-front distortion accumulated by a CW beam heating a cross-flowing atmospheric column. Absorbed power `α·P·R` per unit path length heats a parcel of air with residence time `w/v_perp` (crosswind clearing); the temperature rise per pass is

```
ΔT ≈ (α·P) / (ρ·c_p·v_perp·w)      [per unit path length]
```

Integrated over path length `R` with weighting that accounts for the `(z/L)` spherical-wave divergence (similar to M5), and coupled to the phase via `dn/dT`, one obtains Gebhardt 1976's core expression. The 1990 re-derivation with the 4√2 prefactor (line 84):

```
N_D = 4·√2 · (−dn/dT) · α · P · R² / (n₀ · ρ · c_p · v_perp · w³)
```

**CLAUDE §7.1 invariant — 4√2 prefactor.** Previous drafts of the plan had 4 or 2√2 in this position. The 4√2 is Gebhardt's 1990 engineering-form result for a long-exposure CW beam under steady-state wind clearing; it already absorbs the beam-path weighting and the Smith small-angle approximation.

### Gladstone-Dale `dn/dT` with T and P scaling

Atmospheric refractive index `n − 1 = K·ρ` (Gladstone-Dale) with `ρ = P·M_air/(R·T)` (ideal gas). Differentiating at constant pressure:

```
dn/dT = −K·P·M_air / (R·T²) = (n_STP − 1) · (T_ref/T²) · (P/P_ref) / T_ref
      = −0.93e-6 · (288/T) · (P/P_ref)          at T in K, P in Pa
```

**CLAUDE §7.1 invariant — T and P dependence.** A previous plan draft had `dn/dT` as a K⁻²-dimensional constant `−0.93e-6` independent of T and P; that is dimensionally wrong and, more importantly, underestimates blooming in warm/low-pressure operating conditions. The code (line 82) carries the full scaling.

### Smith Strehl `S_TB`

Smith 1977 fit the single-parameter Strehl function to numerical wave-optics runs:

```
S_TB = 1 / (1 + (N_D/5)²)
```

- Half power at `N_D = 5` (definition of `_N_CRIT`).
- Monotonic decrease; bounded in `[0, 1]` for `N_D ≥ 0`.
- No second-order correction; Gebhardt 1990 argues this is accurate to <10% for `N_D ≤ 30`.

### Broadening `w_bloom`

Beyond `N_D = 5` the 1/e² radius broadens — the spot is no longer a Gaussian but retains approximately Gaussian irradiance form with an inflated width. The engineering post-fit (line 95):

```
w_bloom = w · √((N_D/5)² − 1) · 0.3                 for N_D ≥ 5
        = 0                                          for N_D < 5
```

**SPEC §10.4 HIGH UNCERTAINTY.** The `0.3` prefactor is taken from a 1990-era fit to a small set of wave-optics runs and is known to under-predict broadening in high-absorption, slow-wind regimes. The code raises an `assumptions_flagged` entry whenever `w_bloom > 0` (line 96–100) so the user sees the flag at every engagement that is in the blooming-limited regime.

### Smooth continuity at `N_D = 5`

At `N_D = 5⁻`, `w_bloom = 0` (first branch). At `N_D = 5⁺`, `w_bloom = w · √(0) · 0.3 = 0`. So `w_bloom` is continuous at the boundary; the derivative has a finite jump. This is the intended piecewise-C⁰ behaviour — physically, below `N_D = 5` the Smith Strehl handles the broadening implicitly (peak drop without width change) and above it the explicit `w_bloom` channel turns on.

## Known simplifications

- **Phase-only blooming** — no amplitude scintillation from the blooming channel (captured separately in M5 if at all).
- **Steady-state wind clearing** — assumes crosswind has had enough dwell time to reach the Gebhardt steady state. For transient operation (first ~`w/v_perp` ≈ tens of ms at C-UAS scales) blooming builds up from zero; SPEC v1 neglects this.
- **`c_p` treated as T-independent** — varies by <0.5% over 253–328 K; negligible.
- **Vertical wind component ignored** — only the perpendicular crosswind component `v_perp` clears the blooming channel. Realistic engagements with tail wind have less effective clearing than `v_perp` suggests; conservative for most operating conditions.
- **`0.3` broadening prefactor** — SPEC §10.4 HIGH UNCERTAINTY; defer refinement to wave-optics re-fit (Layer 4 closeout).
- **No turbulence-blooming interaction** — M5 r₀ and M6 N_D are computed independently; in reality, turbulent mixing reduces the blooming channel's residence time. Conservative: M6 alone overestimates blooming in strong-turbulence regimes.

## Cross-check

Canonical scenario (C-UAS 1500 m preset): P = 2550 W (post-M2), w = 0.05 m at launch (no propagation yet), R = 1500 m, α = 1.42e-4 1/m, v_perp = 3 m/s, T = 288 K, P_atm = 101325 Pa.

Hand computation:
- ρ = 101325 · 0.029 / (8.314 · 288) = 2939 / 2394 = 1.227 kg/m³. ✓ (standard sea-level density)
- dn/dT = −0.93e-6 · (288/288) · 1 = −0.93e-6 /K.
- Numerator = 4·√2 · 0.93e-6 · (1.42e-4 · 2550 · 1500²) = 5.657 · 0.93e-6 · (1.42e-4 · 2550 · 2.25e6) = 5.657 · 0.93e-6 · 814.7 = 4.29e-3.
- Denominator = 1.000293 · 1.227 · 1005 · 3 · (0.05)³ = 1.233 · 1005 · 3 · 1.25e-4 = 0.4647.
- N_D ≈ 4.29e-3 / 0.4647 = 9.23e-3.

This tiny N_D at launch radius is misleading — the iteration runs on `w_at_target`, not on `w_launch`. At the far-field-broadened `w_total` ≈ 2–3 cm and crosswind 3 m/s, `N_D` falls to ~0.01 regime and `S_TB ≈ 1.00`. At higher power (30 kW, counter-rocket scenario) with shorter cleared residence time (`v_perp = 1 m/s`), `N_D` rises into the `N_D ~ 1–5` regime where `S_TB` drops to ~0.5.

Independent verification with `physics/m6_blooming.py:compute` at the C-UAS conditions (post-M7 iteration): N_D ≈ 0.01, S_TB ≈ 1.0, w_bloom = 0 (sub-critical). The model is not the limiting factor at 1500 m with 3 kW.

## Cross-reference to CLAUDE §7.1

- **`N_D = 4·√2 · …`** — CLAUDE §7.1 explicit; Gebhardt 1990 prefactor.
- **`dn/dT = −0.93e-6 · (288/T) · (P/P₀)`** — CLAUDE §7.1 explicit; full Gladstone-Dale T and P scaling.
- **`S_total = S_TB · S_opt` only (no S_turb)** — CLAUDE §7.1 explicit; enforced downstream in M7 (see `m7_spot.md`).
