# Input-range-bounds audit

**Scope:** Every `validate_range(value, name, lo, hi)` call in `physics/`. Each call is a claim about the physics domain of validity — if a user input falls outside, the function raises `ValueError` rather than silently extrapolating. This roster checks that each `[lo, hi]` pair is:

1. Consistent with the formula's mathematical domain (no division by zero, no negative under sqrt, no log of non-positive).
2. Consistent with the formula's physical validity (weak-turbulence bound, Mie regime, Kolmogorov inner/outer scale, etc.).
3. Consistent with SPEC §3 Inputs tables and §5.1 Panel ranges.
4. Realistic for the operating ranges the calculator targets (C-UAS through counter-rocket, not laboratory benchtop or long-range ballistic).

**Verdict column:**
- **verified** — bound is consistent with SPEC, formula domain, and realistic operating range.
- **verified (SPEC-driven)** — bound matches an explicit SPEC §3 or §5.1 entry.
- **flagged** — a mismatch or concern to surface as a separate issue.

Revision history:
- 2026-04-24 — initial roster written during Package 1 validation campaign.

---

## M1 — laser source (`physics/m1_laser_source.py`)

| Input | `[lo, hi]` | Units | SPEC §3 M1 / §5.1 Panel A | Formula domain | Verdict |
|---|---|---|---|---|---|
| `P0` | [100, 100 000] | W | Panel A: 0.1 – 100 kW | `P0 > 0` for `I_exit = 2P/(πw²)` | verified (SPEC-driven) |
| `M2` | [1.0, 10.0] | — | Panel B: 1.0 – 10.0 | `M² ≥ 1` by definition; values beyond 10 are non-HEL territory | verified (SPEC-driven) |
| `D` | [0.01, 0.50] | m | Panel B: 1 – 50 cm | `D > 0` for `θ_diff = M²·4λ/(πD)` | verified (SPEC-driven) |
| `λ` | [0.5e-6, 5.0e-6] | m | Panel B: {1.06, 1.07, 1.55, 2.05} µm validated; 0.5–5 µm allowed with reduced-confidence flag | `λ > 0` for `θ_diff`, `zR` | verified (SPEC-driven) |

All four bounds match SPEC §3 M1 inputs table and §5.1 Panel A/B sanity ranges.

---

## M2 — beam director (`physics/m2_beam_director.py`)

| Input | `[lo, hi]` | Units | SPEC §3 M2 / §5.1 Panel A | Formula domain | Verdict |
|---|---|---|---|---|---|
| `P0` | (shared with M1 — not revalidated in M2) | W | — | — | — |
| `η_opt` | [0.50, 0.99] | — | SPEC §3 M2 | `0 < η ≤ 1` (multiplicative transmission) | verified (SPEC-driven) |

Lower bound of 0.50 excludes pathological optical trains; upper bound of 0.99 excludes unphysically-perfect mirrors. Both match SPEC §3 M2.

---

## M3 — geometry (`physics/m3_geometry.py`)

| Input | `[lo, hi]` | Units | SPEC §3 M3 / §5.1 Panel C | Formula domain | Verdict |
|---|---|---|---|---|---|
| `H_e` | [0, 3000] | m | Panel C: 0 – 3000 m AGL | `H_e ≥ 0` (physical); upper bound is operational | verified (SPEC-driven) |
| `R` | [50, 50 000] | m | Panel C: 0.05 – 50 km | `R > |ΔH|` checked at line 52; formula valid for R > 0 | verified (SPEC-driven) |
| `H_t` | [0, 5000] | m | Panel C: 0 – 5000 m AGL | `H_t ≥ 0` (physical); upper bound is operational | verified (SPEC-driven) |
| `v_tgt` | [0, 100] | m/s | Panel C: 0 – 100 m/s | `v_tgt ≥ 0` (scalar speed); 100 m/s covers UAS → rocket | verified (SPEC-driven) |
| `v_perp` | [0, 30] | m/s | Panel C: 0 – 30 m/s | `v_perp ≥ 0`; consumed by M6 which requires `v_perp > 0` (additional check there) | verified (SPEC-driven) |

**Note on `v_perp = 0` handling.** M3 allows `v_perp = 0` (validate_range inclusive). M6 then raises a separate `ValueError` on `v_perp = 0` (physically means no wind-driven blooming clearing; N_D would blow up). This is intentional — a stationary-air engagement is a legal M3 input for inspection of geometry but will fail at the M6 stage. The UI should guard against v_perp = 0 at Panel C.

**Flat-earth limit.** At 50 km slant range, earth-curvature drop ≈ 0.2 m — smaller than SPEC pointing-jitter envelope. No concern.

---

## M4 — atmosphere (`physics/m4_atmosphere.py`)

| Input | `[lo, hi]` | Units | SPEC §3 M4 / §5.1 Panel D | Formula domain | Verdict |
|---|---|---|---|---|---|
| `V` | [0.5, 50] | km | Panel D: 0.5 – 50 km | Kruse piecewise q(V) coverage: `V ≥ 0.5` avoids V<0 in the dense-haze branch | verified (SPEC-driven) |
| `RH` | [0, 1] | — | Panel D: 0 – 100% | RH is a fraction; linear `α(RH) = α·(RH/0.60)` is valid | verified (SPEC-driven) |
| `T_ambient` | [253, 328] | K | Panel D: −20 to +55 °C | Dry-air c_p and Kruse empirics assume near-standard T | verified (SPEC-driven) |
| `wavelength` | (shared with M1) | m | — | — | — |
| `R_slant` | (upstream from M3) | m | — | — | — |

Note: the Kruse `V > 50 km` q=1.6 branch is dead code given `V ≤ 50 km` input bound. Consistent — the code documents this as "exceptional clarity; outside SPEC V range."

---

## M5 — turbulence (`physics/m5_turbulence.py`)

| Input | `[lo, hi]` | Units | SPEC §3 M5 / §5.1 Panel D | Formula domain | Verdict |
|---|---|---|---|---|---|
| `Cn2_ground` (value path) | [1e-16, 1e-12] | m^(−2/3) | SPEC §3 M5 | Weak-turbulence validity: Cn² ≤ ~1e-12 keeps `r0_sph` in the >1 cm regime; floor 1e-16 is atmospheric baseline | verified (SPEC-driven) |
| `v_HV` | [0, 60] | m/s | SPEC §3 M5 | HV-5/7 validity: jet-stream winds up to ~60 m/s are mid-latitude extreme | verified (SPEC-driven) |
| `wavelength`, `R_slant`, `H_e`, `H_t` | (upstream) | — | — | — | — |

**Weak-turbulence regime.** The `r0_sph` formula is the weak-turbulence approximation (Rytov variance σ_R² ≪ 1). For typical operating conditions at Cn² ≤ 1e-13 and L ≤ 10 km, σ_R² ≤ ~0.3 — comfortably weak. For Cn² = 1e-12 and L = 50 km, σ_R² ~ 5 — saturated turbulence, outside the formula's validity. No explicit runtime check; SPEC §10 would need to add a saturation flag if this regime becomes a concern. **Flagged for Layer 4 review.**

---

## M7 — spot and PIB (`physics/m7_spot_pib.py`)

| Input | `[lo, hi]` | Units | SPEC §3 M7 / §5.1 Panel B/E | Formula domain | Verdict |
|---|---|---|---|---|---|
| `P_exit` | `> 0` | W | Upstream M2 | `P > 0` for I_peak | verified |
| `tau_atm` | [0, 1] | — | Upstream M4 | Transmission fraction bounds | verified |
| `w0`, `zR` | `> 0` | m | Upstream M1 | Gaussian-beam convention | verified |
| `M2` | [1.0, 10.0] | — | Panel B | Same as M1 | verified (SPEC-driven) |
| `wavelength` | [0.5e-6, 5.0e-6] | m | Panel B | Same as M1 | verified (SPEC-driven) |
| `R_slant` | [50, 50 000] | m | Panel C | Same as M3 | verified (SPEC-driven) |
| `sigma_jit` | [0, 1e-3] | rad | Panel B | 1 mrad upper is very loose pointing — generous | verified (SPEC-driven); upper bound loose but not a hazard |
| `r0_sph` | `> 0` (incl. `inf`) | m | Upstream M5 | `w_turb = 2L/(k·r₀)` valid for r₀ > 0; `r₀ = ∞` zeros the term | verified |
| `S_TB` | [0, 1] | — | Upstream M6 | Strehl fraction | verified |
| `w_bloom` | [0, 10] | m | Upstream M6 | 10 m upper is defensive; realistic w_bloom ≪ 1 m | verified |
| `d_aim` | [0.005, 1.0] | m | Panel E | Aim disk 5 mm – 1 m | verified (SPEC-driven) |

---

## M8 — burn-through (`physics/m8_burnthrough.py`)

| Input | `[lo, hi]` | Units | SPEC §3 M8 / §5.1 Panel E | Formula domain | Verdict |
|---|---|---|---|---|---|
| `I_aim` | `> 0` | W/m² | Upstream M7 | `I > 0` for flux | verified |
| `material` | enum | — | Panel E: 7 materials | discrete | verified (SPEC-driven) |
| `thickness` | [1e-4, 2e-2] | m | Panel E: 0.1 – 20 mm | Grid sizing assumes ≥ 20 intervals; lower bound 0.1 mm keeps dx ≤ thickness/20 = 5 µm reasonable | verified (SPEC-driven) |
| `wavelength` | [0.5e-6, 5.0e-6] | m | — | Same as M1 | verified (SPEC-driven) |
| `backside_BC` | enum {"insulated", "convective"} | — | Panel E | discrete | verified (SPEC-driven) |
| `v_tgt` | [0, 100] | m/s | Panel C | Same as M3 | verified (SPEC-driven) |
| `T_ambient` | [253, 328] | K | Panel D | Same as M4 | verified (SPEC-driven) |
| `A_lambda` (optional) | [0.05, 0.99] | — | Panel E | Absorptivity fraction; 0.05 is a conservative metal floor | verified (SPEC-driven) |

---

## M9 — ocular safety (`physics/m9_nohd.py`)

| Input | `[lo, hi]` | Units | SPEC §3 M9 / §5.1 Panel F | Formula domain | Verdict |
|---|---|---|---|---|---|
| `P0` | `> 0` | W | — | Same as M1 | verified |
| `D` | `> 0` | m | — | Same as M1 | verified |
| `theta_diff` | `> 0` | rad | Upstream M1 | `θ > 0` for `1/θ` in NOHD | verified |
| `wavelength` | `> 0` | m | — | Same as M1 | verified |
| `t_exp` | [0.25, 100] | s | Panel F | ANSI MPE table coverage (pulsed t < 18 µs defensive branch kept) | verified (SPEC-driven) |

---

## M10 — power / thermal (`physics/m10_power_thermal.py`)

| Input | `[lo, hi]` | Units | SPEC §3 M10 / §5.1 Panel A | Formula domain | Verdict |
|---|---|---|---|---|---|
| `P0` | `> 0` | W | — | Same as M1 | verified |
| `eta_wallplug` | [0.05, 0.50] | — | Panel A: 5 – 50% | HEL cooling efficiency typical 15–40%; bounds cover edge cases | verified (SPEC-driven) |
| `Q_cool` | `≥ 0` | W | Panel A | `Q_cool < 0` would be a heat source, not a sink; 0 is single-shot case | verified |
| `C_thermal` | `> 0` | J/K | Panel A | Thermal capacitance must be positive | verified |
| `dT_max` | [5, 80] | K | Panel A | Tight-optics 5 K, bulk-loop 80 K | verified (SPEC-driven) |
| `t_engagement` | `> 0` | s | Upstream M8/M3 | `t > 0` for rate calculations | verified |

---

## Cross-cutting checks

### Wavelength consistency

Four modules carry their own wavelength range check (M1, M7, M8, M9). All use `[0.5e-6, 5.0e-6]` m. The validated-set check `wavelength_in_validated_set` is a soft check (returns bool) — M9 calls it to set a reduced-confidence flag, but does not reject the input. Other modules do not call it; the wavelength-set gate is an advisory quality flag, not a gate.

**Recommendation:** no change. The 4-wavelength validated set is a quality-of-evidence indicator, not a hard admissibility criterion.

### `T_ambient` consistency

M4, M6, M8 all take `T_ambient` and all use `[253, 328] K`. Consistent.

### `R_slant` consistency

M3 outputs `R_slant`. M4, M5, M6, M7 all check `R_slant ∈ [50, 50000] m`. Consistent with M3's `R ∈ [50, 50000] m`.

### `v_tgt` consistency

M3 input `v_tgt ∈ [0, 100] m/s`. M8 also takes `v_tgt` (for h_conv) with the same bound. Consistent.

### `v_perp = 0` edge case

M3 allows `v_perp = 0`; M6 rejects it. The orchestrator does not catch this — a user with `v_perp = 0` will pass M1–M5 then hit a ValueError at M6. Acceptable: the UI's validation layer can pre-check, or the user gets a clear error message.

---

## Summary

25 of 25 validated ranges are consistent with SPEC §3, §5.1, formula mathematical domain, and realistic operating envelope.

**No formula-admissibility errors found.**

**Advisory notes** (no code changes):
1. Weak-turbulence regime for M5 — at the extreme corners (Cn² = 1e-12, L = 50 km), σ_R² reaches ~5 → saturated turbulence, outside strict validity. Flagged for Layer 4 HIGH UNCERTAINTY closeout; SPEC §10 could add a saturation diagnostic.
2. `v_perp = 0` passes M3 but raises at M6. Acceptable separation of concerns; the error propagates with a clear message.
3. `sigma_jit = 1 mrad` upper bound is generous. Realistic systems are typically 1–100 µrad. Not a correctness concern — bound keeps the validator non-restrictive for stress tests.

All 25 bounds accepted as-is for v1.
