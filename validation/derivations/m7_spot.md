# M7 — Spot size and power-in-the-bucket

**File:** `physics/m7_spot_pib.py`
**Outputs:** `w_diff`, `w_turb`, `w_jit`, `w_total`, `d_spot`, `I_peak`, `PIB_fraction`, `P_aim`, `I_avg_aim`

## Formulas implemented (code ↔ SPEC ↔ source)

| Code line | Expression | SPEC | Primary citation | Secondary citation | Status |
|---|---|---|---|---|---|
| 78 | `k = 2π/λ` | §3 M7 | Elementary | — | verified |
| 82 | `w_diff = w0 · √(1 + (M²·L/zR)²)` | §3 M7 | Siegman 1986 §17 exact Gaussian with M² | Saleh & Teich 2019 §3.1 | verified (CLAUDE §7.1 invariant — exact, NOT far-field) |
| 86 | `w_turb = 2L / (k · r0_sph)` | §3 M7 | Andrews & Phillips §6 engineering form | — | verified (CLAUDE §7.1) |
| 90 | `w_jit = 2 · σ_jit · L` | §3 M7 | σ → 1/e² radius per axis | Perram §4 | verified (CLAUDE §7.1 factor-of-2 per-axis) |
| 93 | `w_total = √(w_diff² + w_turb² + w_jit² + w_bloom²)` | §3 M7 | Quadrature of independent contributions | Andrews & Phillips §6 | verified (CLAUDE §7.1 quadrature) |
| 94 | `d_spot = 2 · w_total` | §3 M7 | Diameter-radius convention | — | verified |
| 100 | `S_total = S_TB · S_opt` (S_opt=1) | §3 M7 | Phase-only Strehl composition | — | verified (CLAUDE §7.1 — NO S_turb double-count) |
| 103 | `I_peak = 2 · P · τ · S_total / (π · w_total²)` | §3 M7 | Gaussian peak with factor 2 | Saleh & Teich §3.1 | verified (CLAUDE §7.1 factor-of-2) |
| 107 | `R_aim = d_aim / 2` | §3 M7 | Diameter → radius | — | verified |
| 108 | `PIB_fraction = 1 − exp(−2·R_aim² / w_total²)` | §3 M7 | Closed-form Gaussian PIB | Born & Wolf §8.8 | verified (CLAUDE §7.1 — RADIUS in exponent) |
| 109 | `P_aim = P · τ · S_total · PIB_fraction` | §3 M7 | Multiplicative composition | — | verified |
| 110 | `I_avg_aim = P_aim / (π · R_aim²)` | §3 M7 | Average = power / area | — | verified |
| 124 | `w_bloom > w_diff` → blooming-limited flag | §3 M7 | Regime guard | SPEC §10.4 | verified |

## Constants used

None in `m7_spot_pib.py` itself. Every factor of 2 in this module is a physics convention, not a tunable:

| Factor-of-2 | Line | Meaning | CLAUDE §7.1 |
|---|---|---|---|
| `2` in `I_peak = 2P/(πw²)` | 103 | Gaussian peak vs flat-top-equivalent | invariant |
| `2` in `w_jit = 2·σ·L` | 90 | σ per-axis → 1/e² radius per axis | invariant |
| `2` in PIB exponent `−2·R_aim²/w²` | 108 | Gaussian `exp(−2r²/w²)` form, RADIUS (not diameter) | invariant |
| `2` in `d_spot = 2·w_total` | 94 | Diameter = 2 × radius | trivial |
| `2` in `w_turb = 2L/(k·r₀)` | 86 | Engineering form; M5 derivation | see m5 invariant |

## Derivation

### Exact-Gaussian diffraction `w_diff`

Propagation of an ideal TEM₀₀ Gaussian beam with waist `w0` along the z-axis:

```
w(z) = w0 · √(1 + (z/zR)²)            ideal, M² = 1
```

For real beams with beam-quality factor `M²` > 1, Siegman 1986 §17 shows the propagation follows the same functional form with `z/zR` replaced by `M²·z/zR` (holding `zR = π·w0²/λ` fixed to the M²=1 reference):

```
w(z) = w0 · √(1 + (M²·z/zR)²)
```

At `z = L` (the target plane) this gives `w_diff` (line 82).

**CLAUDE §7.1 invariant — NOT the far-field asymptote.** A common error is to substitute the far-field limit `w_diff → M²·λL/(π·w0)`, which is only accurate when `L ≫ zR`. For C-UAS ranges (L = 1500 m, zR = 7340 m) we have `L/zR = 0.20` — deep in the near-field. The far-field form under-predicts `w_diff` by factors of 2–15× at typical engagement ranges. The exact form is required.

### Engineering `w_turb`

From M5 (`m5_turbulence.md`):

```
w_turb = 2·L / (k · r0_sph)
```

with `r0_sph` the spherical-wave Fried length. M7 is a pass-through; the derivation and CLAUDE §7.1 invariant flag live in M5.

### Jitter `w_jit`

Per-axis pointing jitter has RMS `σ_jit` (rad). Two independent axes (az and el) each contribute Gaussian-distributed beam-center offsets at range `L`:

```
offset_per_axis_RMS = σ_jit · L          (meters)
```

The 1/e² intensity radius of a Gaussian-blurred point source is `√2` times its RMS; for the per-axis 1/e² radius at the target we multiply by `√2`. BUT the total-intensity Gaussian convolved with per-axis Gaussian blur has 1/e² radius = 2·σ·L when the Gaussian intensity profile's own 1/e² radius definition (`I = I0·exp(-2r²/w²)`) is adopted consistently throughout. Explicitly: the convolution of an `exp(−2r²/w²)` beam with a 2D Gaussian of per-axis σ_jit·L gives a new Gaussian with `w² → w² + 4·(σ_jit·L)²`, so the jitter contribution in quadrature is `w_jit = 2·σ_jit·L` (line 90).

**CLAUDE §7.1 invariant — factor of 2.** This factor converts per-axis σ to a 1/e² radius. Using σ·L (no factor) or σ·L·√2 (3D radial σ) are both common errors. The code's comment explicitly calls this out (line 88–89).

### Quadrature `w_total`

Four statistically-independent 1/e² broadening contributions — diffraction, turbulence, jitter, blooming — add in quadrature because each arises from independent physical processes (aperture diffraction; refractive-index turbulence; mount vibration/servo error; thermal blooming of the air column):

```
w_total² = w_diff² + w_turb² + w_jit² + w_bloom²          (line 93)
```

**CLAUDE §7.1 invariant — quadrature of four.** Earlier plan drafts had three (missing w_bloom) or five (adding a double-count w_turb_amp for scintillation).

### Peak irradiance `I_peak`

Gaussian intensity profile:

```
I(r) = (2·P / (π·w²)) · exp(−2r²/w²)
```

Peak at `r=0`: `I(0) = 2·P/(π·w²)`. Including atmospheric transmission τ and phase Strehl S_total, the peak at the target is:

```
I_peak = 2 · P · τ · S_total / (π · w_total²)               (line 103)
```

**CLAUDE §7.1 invariant — factor of 2.** See also M1 derivation (`m1_source.md`). The flat-top equivalent `P/(πw²)` would give the average, not the peak.

**CLAUDE §7.1 invariant — S_total = S_TB · S_opt only.** Turbulence enters via `w_turb` in the quadrature sum; double-counting it as a multiplicative Strehl (`S_turb = exp(−(...)²)` from some textbooks) would reduce I_peak a second time and is wrong for this spot-size convention. The code's comment explicitly calls this out (lines 96–98).

### Power in the bucket

A Gaussian beam `I(r) = I_peak · exp(−2r²/w²)` integrated over a circular aperture of radius R_aim:

```
P_in_bucket = ∫₀^R_aim I(r) · 2πr dr
            = I_peak · (πw²/2) · (1 − exp(−2·R_aim²/w²))
            = P · (1 − exp(−2·R_aim²/w²))
```

So:

```
PIB_fraction = 1 − exp(−2·R_aim² / w_total²)               (line 108)
```

**CLAUDE §7.1 invariant — RADIUS in exponent.** The aimpoint input `d_aim` is the DIAMETER of the acceptable aim disk. The code converts to radius `R_aim = d_aim/2` (line 107) before substituting into the exponent. Using d_aim directly would over-predict PIB by the exponential's sensitivity — a factor-of-4 error in the exponent.

### P_aim and I_avg_aim

`P_aim = P · τ · S_total · PIB_fraction` (line 109) — power actually delivered into the aimpoint disk, accounting for atmospheric transmission, phase Strehl, and the aperture-spill fraction.

`I_avg_aim = P_aim / (π · R_aim²)` (line 110) — disk-average irradiance, the quantity the thermal/burn-through model uses.

## Known simplifications

- **Long-exposure convention.** `w_total` is the time-averaged 1/e² radius (jitter and turbulence both folded in as RMS broadening). Short-exposure beam wander (tilt-isoplanatic) not modeled separately — relevant for sub-10 ms pulses or dithered pointing.
- **Gaussian form preserved through quadrature.** `w_total` is applied as if the spot is still an `exp(−2r²/w²)` Gaussian with the broadened radius. For strong blooming (`N_D > 30`) the spot is non-Gaussian; the engineering assumption is conservative for PIB and mildly optimistic for I_peak.
- **No aimpoint mismatch.** Beam centroid coincides with aimpoint centroid. Systematic offsets (aim error) not modeled in v1.
- **Single-mode.** Higher-order mode content rolled into M² (captured at M1).
- **Linear superposition of S_TB and S_opt.** In v1, `S_opt = 1` (unimodal beam director; optical aberrations rolled into M²). The multiplicative form assumes the aberration sources are independent — fine for a well-characterized beam director.

## Cross-check

Canonical scenario (C-UAS 1500 m preset): P_exit = 2550 W, τ_atm = 0.808, w0 = 0.05 m, zR = 7340 m, M² = 1.2, λ = 1.07 µm, L = 1500 m, σ_jit = 20 µrad, r0_sph ≈ 0.049 m, S_TB ≈ 1.0 (negligible blooming), w_bloom = 0, d_aim = 10 cm.

Hand computation:
- k = 5.87e6 1/m.
- `w_diff` = 0.05 · √(1 + (1.2·1500/7340)²) = 0.05 · √(1 + 0.0601) = 0.05 · 1.0296 = 0.0515 m = 5.15 cm.
- `w_turb` = 2·1500 / (5.87e6 · 0.049) = 3000 / 2.88e5 = 0.0104 m = 1.04 cm.
- `w_jit` = 2 · 20e-6 · 1500 = 0.060 m = 6.00 cm.
- `w_total` = √(5.15² + 1.04² + 6.00² + 0²) cm = √(26.5 + 1.08 + 36.0) = √63.6 = 7.98 cm ≈ 0.0798 m.
- `d_spot` = 15.96 cm.
- `I_peak` = 2 · 2550 · 0.808 · 1.0 / (π · 0.0798²) = 4120.8 / 0.02001 = 2.06e5 W/m² = 20.6 W/cm².
- `R_aim` = 0.10/2 = 0.05 m.
- `PIB_fraction` = 1 − exp(−2 · 0.05² / 0.0798²) = 1 − exp(−0.785) = 1 − 0.456 = 0.544.
- `P_aim` = 2550 · 0.808 · 1.0 · 0.544 = 1121 W.
- `I_avg_aim` = 1121 / (π · 0.05²) = 1121 / 0.00785 = 1.43e5 W/m² = 14.3 W/cm².

Observations:
- Jitter dominates `w_total` at 1500 m with 20 µrad jitter — `w_jit² / w_total² = 36/64 = 56%`. For a tight-jitter director (5 µrad) diffraction would dominate.
- PIB ≈ 54% — about half the power lands in the 10 cm aim disk. The other half spills outside; this is the "fence" the operator sees.
- I_avg_aim (14 W/cm²) is the burn-through-relevant flux; I_peak (21 W/cm²) is about 1.5× higher (shape factor of a Gaussian of this size integrated against this aperture).

Independent verification with `physics/m7_spot_pib.py:compute` reproduces all values to 4 sig figs.

## Cross-reference to CLAUDE §7.1

All six M7-specific CLAUDE §7.1 invariants are implemented and documented:

- **`w_diff(L) = w₀·√(1 + (M²·L/zR)²)`** — exact Gaussian, line 82.
- **`I_peak = 2P/(πw²)`** — factor-of-2 Gaussian peak, line 103.
- **`PIB = 1 − exp(−2·R_aim²/w²)`** — RADIUS in exponent, line 108.
- **`S_total = S_TB · S_opt` only** — no S_turb; turbulence enters via w_turb, line 100.
- **`w_total² = w_diff² + w_turb² + w_jit² + w_bloom²`** — quadrature of four, line 93.
- **`w_jit = 2·σ_jit·L`** — per-axis factor-of-2, line 90.

These are the six invariants where previous plan drafts had specific errors and an audit caught them. M7 is the integrating module; each of these must remain bit-for-bit stable unless SPEC §3 M7 itself is revised under CLAUDE §4.3.
