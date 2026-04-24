# M9 — Ocular safety (MPE and NOHD)

**File:** `physics/m9_nohd.py`
**Outputs:** `MPE`, `NOHD_tophat`, `NOHD_gausspeak`, `laser_class`

## Formulas implemented (code ↔ SPEC ↔ source)

| Code line | Expression | SPEC | Primary citation | Status |
|---|---|---|---|---|
| 75 | Band A, t < 18 µs: `MPE = 5e-3 / t_exp` W/cm² | §3 M9 | ANSI Z136.1-2014 Table 5a | verified |
| 77 | Band A, 18 µs ≤ t ≤ 10 s: `MPE = 1.8e-3 · t^(−0.25)` W/cm² | §3 M9 | ANSI Z136.1-2014 Table 5a | verified (C_A=1 simplification — SPEC §10.3) |
| 79 | Band A, t > 10 s: `MPE = 1.0e-3` W/cm² (chronic) | §3 M9 | ANSI Z136.1-2014 Table 5a | verified |
| 83 | Band B, t ≤ 10 s: `MPE = 0.56 · t^(−0.75)` W/cm² | §3 M9 | ANSI Z136.1-2014 Table 5b | verified |
| 85 | Band B, t > 10 s: `MPE = 0.1` W/cm² (chronic) | §3 M9 | ANSI Z136.1-2014 Table 5b | verified |
| 98 | Unit conversion W/cm² → W/m² (`×1e4`) | §3 M9 | Elementary | verified |
| 155 | `range_tophat = (1/θ)·√(4·P0/(π·MPE))` | §3 M9 | ANSI Z136.1 formulas eq. 7(a) | verified (CLAUDE §7.1 dual-convention) |
| 156 | `range_gausspeak = (1/θ)·√(8·P0/(π·MPE))` | §3 M9 | Single-mode HEL on-axis peak (factor 2 in intensity) | verified (CLAUDE §7.1) |
| 157 | `aperture_correction = D/θ` | §3 M9 | Virtual-source aperture offset | verified |
| 159–160 | `NOHD_x = max(0, range_x − aperture_correction)` | §3 M9 | ANSI Z136.1 NOHD definition | verified |
| 101–112 | `_classify` — piecewise power thresholds | §3 M9 | ANSI Z136.1 / IEC 60825-1 CW NIR | verified |

## Constants used

| Constant | Value | Units | Source | Status |
|---|---|---|---|---|
| `_BAND_A_LO_M` (line 54) | 0.400e-6 | m | ANSI Z136.1 Band A lower edge | verified |
| `_BAND_A_HI_M` (line 55) | 1.400e-6 | m | ANSI Z136.1 Band A / B boundary | verified |
| `_BAND_B_HI_M` (line 56) | 4.000e-6 | m | ANSI Z136.1 Band B / C boundary | verified |
| `_CLASS4_W` (line 59) | 0.5 | W | ANSI / IEC Class 4 threshold | verified |
| `_CLASS3B_W` (line 60) | 0.005 | W | ANSI / IEC Class 3B threshold | verified |
| `_CLASS3R_W` (line 61) | 0.001 | W | ANSI / IEC Class 3R threshold | verified |
| `_CLASS1_W` (line 62) | 0.00039 | W | ANSI / IEC Class 1 threshold (AEL) | verified |
| Band A t<18µs coef `5e-3` | 5e-3 | W/cm² | ANSI Z136.1 Table 5a | verified |
| Band A 18µs≤t≤10s coef `1.8e-3` | 1.8e-3 | W/cm² | ANSI Z136.1 Table 5a | verified |
| Band A 18µs≤t≤10s expn `-0.25` | -0.25 | — | ANSI Z136.1 Table 5a time exponent | verified |
| Band A chronic `1.0e-3` | 1.0e-3 | W/cm² | ANSI Z136.1 Table 5a t > 10 s | verified |
| Band B coef `0.56` | 0.56 | W/cm² | ANSI Z136.1 Table 5b | verified |
| Band B expn `-0.75` | -0.75 | — | ANSI Z136.1 Table 5b time exponent | verified |
| Band B chronic `0.1` | 0.1 | W/cm² | ANSI Z136.1 Table 5b t > 10 s | verified |
| `10 s` break-point | 10 | s | ANSI Z136.1 acute/chronic boundary | verified |
| `18e-6 s` break-point | 18e-6 | s | ANSI Z136.1 CW/pulsed boundary | verified |
| NOHD factor-of-4 (tophat) | 4 | — | Top-hat: `I = P/(π·r²)`; `r = NOHD·θ/2 + D/2` | verified (CLAUDE §7.1 factor pairing) |
| NOHD factor-of-8 (gausspeak) | 8 | — | Gaussian peak on-axis: `I_peak = 2P/(π·w²)` gives factor √2 more than top-hat | verified (CLAUDE §7.1 factor pairing) |

## Derivation

### MPE — piecewise structure

ANSI Z136.1-2014 tabulates maximum permissible exposure (MPE) for intrabeam viewing as a piecewise function of wavelength band and exposure duration. Two bands matter for the v1 HEL wavelengths {1.06, 1.07, 1.55, 2.05 µm}:

- **Band A (0.400–1.400 µm)** — retinal hazard. Light passes through the cornea/lens and focuses on the retina; damage threshold is set by retinal irradiance and photoreceptor sensitivity.
- **Band B (1.400–4.000 µm)** — eye-safer NIR. Cornea absorbs before focus onto retina; damage threshold is set by corneal thermal injury (much higher than retinal).

Wavelengths 1.06 and 1.07 µm sit in Band A (retinal). 1.55 and 2.05 µm sit in Band B (corneal).

The time dependence reflects biological thermal-integration timescales:
- `t < 18 µs` — below thermal-confinement time; treat as single pulse (MPE ∝ 1/t).
- `18 µs ≤ t ≤ 10 s` — thermal-integration regime; MPE ∝ t^(−0.25) (retinal) or t^(−0.75) (corneal).
- `t > 10 s` — chronic exposure; MPE plateaus at the chronic threshold.

### Band A continuity check

At `t = 18 µs` boundary:
- Left (pulsed): `MPE = 5e-3 / 18e-6 = 277.8 W/cm²`.
- Right (retinal thermal): `MPE = 1.8e-3 · (18e-6)^(-0.25) = 1.8e-3 · 15.44 = 0.0278 W/cm²`.

These do NOT match — the joins are intentionally step discontinuities in ANSI (different physical mechanisms). Code takes the lower of the relevant branch at each side. Layer 2 helper tests will verify both branches return the correct ANSI table value at the boundary.

At `t = 10 s` boundary:
- Acute: `MPE = 1.8e-3 · 10^(-0.25) = 1.8e-3 · 0.5623 = 1.01e-3 W/cm²`.
- Chronic: `MPE = 1.0e-3 W/cm²`.

Continuous to 0.5% — the chronic value is deliberately set to match the acute formula at t = 10 s.

### Band B continuity check

At `t = 10 s`:
- Acute: `MPE = 0.56 · 10^(-0.75) = 0.56 · 0.1778 = 0.0996 W/cm²`.
- Chronic: `MPE = 0.1 W/cm²`.

Continuous to 0.5% — same design.

### NOHD derivation (top-hat)

An expanding beam from a finite aperture of diameter D diverging at full angle θ has a top-hat-equivalent radius at range R:

```
r(R) = D/2 + (θ/2)·R
```

Mean irradiance (top-hat): `I = P / (π·r²)`. Setting `I = MPE` and solving for R:

```
MPE = P / (π · (D/2 + θ·R/2)²)
π·MPE · (D/2 + θ·R/2)² = P
D/2 + θ·R/2 = √(P / (π·MPE))
θ·R/2 = √(P / (π·MPE)) − D/2
R = (2/θ) · √(P / (π·MPE)) − D/θ
  = (1/θ) · √(4·P / (π·MPE)) − D/θ                   (line 155, 157, 159)
```

The factor of 4 inside the sqrt is the 2² from folding the factor-of-2 into the radius→diameter conversion. `NOHD_tophat = max(0, ...)` clamps the at-aperture-plane case where D is already large enough.

### NOHD derivation (Gaussian peak)

For a single-mode Gaussian with `I_peak = 2·P / (π·w²)`, on-axis irradiance at range R is:

```
I_peak(R) = 2·P / (π · (w₀ + (θ/2)·R)²)          (approximately, for beams that fill the aperture)
```

With `w ≈ D/2 + θ·R/2` (same geometrical expansion; beam-waist convention):

```
MPE = 2·P / (π · (D/2 + θ·R/2)²)
π·MPE · (D/2 + θ·R/2)² = 2·P
D/2 + θ·R/2 = √(2·P / (π·MPE))
R = (2/θ) · √(2·P / (π·MPE)) − D/θ
  = (1/θ) · √(8·P / (π·MPE)) − D/θ                   (line 156, 157, 160)
```

**CLAUDE §7.1 invariant — factor of 2 between conventions.** Note `range_gausspeak = √2 · range_tophat` (module docstring line 12). For a low-M² HEL the Gaussian-peak form is the correct on-axis hazard number; using the top-hat form (ANSI general recommendation) would UNDER-report the hazard zone by √2. SPEC v1 reports BOTH and flags the convention choice as an operator decision.

### C_A retinal correction (deliberate omission)

ANSI Z136.1 includes a wavelength-dependent multiplier `C_A = 10^(0.002·(λ_nm − 700))` for Band A, saturating at `C_A = 5.0` for λ ≥ 1050 nm. At 1.06 µm this multiplies MPE by 5; at 1.07 µm also by 5.

The code **omits** C_A — MPE is computed without multiplying by C_A. This yields a SMALLER MPE, hence a LARGER NOHD — more conservative hazard zone. The rationale (per SPEC §3 M9 validation value 25.5 W/m² at 1.07 µm, 0.25 s):

- With C_A: MPE = 1.8e-3 · 0.25^(-0.25) · 5 = 1.27e-2 W/cm² = 127 W/m². — less conservative.
- Without C_A: MPE = 1.8e-3 · 0.25^(-0.25) = 2.55e-3 W/cm² = 25.5 W/m². — matches SPEC validation.

**SPEC §10.3 HIGH UNCERTAINTY.** The calculator reports the conservative (no-C_A) number. Users wanting the less-conservative operational number apply C_A externally. Code flags this with `assumptions_flagged` on every call (line 177–183).

### Laser classification

ANSI Z136.1 / IEC 60825-1 CW NIR thresholds (line 101–112):
- `P0 > 500 mW` → Class 4.
- `5–500 mW` → Class 3B.
- `1–5 mW` → Class 3R.
- `0.39–1 mW` → Class 1M.
- `≤ 0.39 mW` → Class 1.

HEL sanity range (Panel A) is 100 W – 100 kW — always Class 4. The enumeration is complete for testability at lower powers (pytest boundary tests).

## Known simplifications

- **No C_A correction** (retinal Band A) — conservative omission; SPEC §10.3.
- **Band C (λ > 4 µm) placeholder** — falls back to Band B formulas; flagged. Out of v1 scope per SPEC §3 M9.
- **CW only** — the `t < 18 µs` branch exists defensively but v1 does not validate pulsed results.
- **Single-wavelength per call** — no multi-wavelength combining (additivity rule not applied).
- **Top-hat and Gaussian-peak both reported** — user must cite the appropriate one; the code does not pick for them.
- **No blink-reflex multiplier** (ANSI option for intentional-viewing scenarios) — SPEC v1 assumes unblinked intrabeam viewing (most conservative).
- **No atmospheric attenuation of the NOHD itself** — NOHD is the free-space distance at which irradiance reaches MPE; atmospheric absorption would shorten it but is conservatively omitted.

## Cross-check

Canonical scenario: P0 = 3000 W, D = 0.10 m, θ_diff = 16.35 µrad, λ = 1.07 µm, t_exp = 0.25 s.

Hand computation:
- Band A (λ = 1.07 µm in [0.4, 1.4] µm).
- 18 µs ≤ 0.25 s ≤ 10 s → `MPE = 1.8e-3 · (0.25)^(-0.25) = 1.8e-3 · 1.414 = 2.546e-3 W/cm² = 25.46 W/m²`. ✓ matches SPEC validation (25.5 W/m²).
- `1/θ = 1 / 1.635e-5 = 6.116e4 m/rad`.
- `range_tophat = 6.116e4 · √(4·3000 / (π · 25.46)) = 6.116e4 · √(12000 / 80.00) = 6.116e4 · √150 = 6.116e4 · 12.247 = 7.49e5 m = 749 km`.
- `range_gausspeak = 6.116e4 · √(8·3000 / (π · 25.46)) = 6.116e4 · √300 = 6.116e4 · 17.32 = 1.059e6 m = 1059 km`.
- `aperture_correction = 0.10 · 6.116e4 = 6116 m = 6.12 km`.
- `NOHD_tophat = 749 − 6.12 = 743 km`.
- `NOHD_gausspeak = 1059 − 6.12 = 1053 km`.
- Ratio `NOHD_gausspeak / NOHD_tophat = 1053 / 743 = 1.417` ≈ √2 ✓.
- `laser_class = Class 4` ✓ (3000 W > 0.5 W).

These are enormous distances — an HEL has a multi-hundred-km ocular hazard zone at full CW. This is why operational use requires active beam-interlock and range safety; the tool just reports the free-space NOHD.

Independent verification with `physics/m9_nohd.py:compute` reproduces `MPE = 25.46 W/m²`, `NOHD_tophat ≈ 743 km`, `NOHD_gausspeak ≈ 1053 km`.

## Cross-reference to CLAUDE §7.1

- **NOHD reports BOTH top-hat AND Gaussian-peak** — CLAUDE §7.1 explicit. Factor-of-4 vs factor-of-8 inside the sqrt; ratio √2.

No other CLAUDE §7.1 items for M9. Every ANSI coefficient traces to the 2014 revision of Z136.1; if the operator cites a newer revision those coefficients must be updated via SPEC §4.3 scope-change procedure. The C_A omission is flagged in every M9 call (SPEC §10.3).
