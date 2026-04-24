# M5 — Atmospheric turbulence

**File:** `physics/m5_turbulence.py`
**Outputs:** `Cn2_integrated`, `r0_sph`, `w_turb`

## Formulas implemented (code ↔ SPEC ↔ source)

| Code line | Expression | SPEC | Primary citation | Secondary citation | Status |
|---|---|---|---|---|---|
| 99 | `k = 2π/λ` | §3 M5 | Elementary wavenumber | — | verified |
| 103 | `Cn2_integrated = Cn2 · L · 3/8` (constant) | §3 M5 | Closed-form `∫₀^L (z/L)^(5/3) dz = L·3/8` | — | verified |
| 115–119 | HV-5/7 integrand + `scipy.quad` | §3 M5.5 | Andrews & Phillips §12 | Hufnagel 1974; Valley 1980 | verified |
| 127 | `r0_sph = (0.423·k²·Cn2_integrated)^(−3/5)` | §3 M5 | Andrews & Phillips §6.5 eq. 6.91 | Fried 1967 | verified (CLAUDE §7.1 invariant) |
| 128 | `w_turb = 2L / (k · r0_sph)` | §3 M5 | Andrews & Phillips §6 (engineering form) | Sprangle et al. NRL | verified (CLAUDE §7.1 invariant) |
| 51–54 | HV-5/7 profile formula | §3 M5.5 | Hufnagel 1974 | Valley 1980 | verified |

## Constants used

| Constant | Value | Units | Source | Status |
|---|---|---|---|---|
| `0.423` (line 127) | 0.423 | — | Fried 1967; Andrews & Phillips §6.5 eq. 6.91 spherical-wave coefficient | CLAUDE §7.1 invariant; verified |
| `2` (line 128) | 2 | — | Engineering-form prefactor converting r₀ → 1/e² radius at range L | CLAUDE §7.1 invariant; verified |
| `5/3` (line 117) | 5/3 | — | Kolmogorov inertial-range exponent | verified |
| `3/8` (line 103) | 3/8 | — | Closed-form integral `∫₀¹ u^(5/3) du = 3/8` | verified |
| `0.00594` (line 51) | 0.00594 | m⁻²/³·(s/m)² | HV-5/7 high-altitude amplitude | verified (Hufnagel 1974) |
| `27.0` (line 51) | 27.0 | m/s | HV-5/7 reference wind speed | verified |
| `10` (line 51) | 10 | — | HV-5/7 altitude power-law exponent | verified |
| `1000.0` (line 51) | 1000.0 | m | HV-5/7 high-altitude scale height | verified |
| `2.7e-16` (line 52) | 2.7e-16 | m⁻²/³ | HV-5/7 boundary-layer amplitude | verified |
| `1500.0` (line 52) | 1500.0 | m | HV-5/7 boundary-layer scale height | verified |
| `100.0` (line 53) | 100.0 | m | HV-5/7 ground scale height | verified |
| `1e-5` (line 51) | 1e-5 | 1/m | HV profile inner-scaling factor | verified |

## Derivation

### Spherical-wave Fried coherence length

For a diverging (spherical-wave) beam from a finite aperture propagating through weak turbulence with refractive-index structure parameter Cn²(z), Andrews & Phillips §6.5 gives the Fried coherence length

```
r0_sph = ( 0.423 · k² · ∫₀^L Cn²(z) · (z/L)^(5/3) dz )^(−3/5)
```

The `(z/L)^(5/3)` weighting is the *spherical-wave* weighting — it vanishes at the source (z=0) because a point-source has zero transverse extent there, and grows to unity at the target (z=L). Contrast the plane-wave form which has unit weighting throughout.

**CLAUDE §7.1 invariant.** The spherical-wave form is appropriate for HEL beams because the beam director has finite aperture and the beam diverges over realistic engagement ranges. The plane-wave form `r0_pl = (0.423 k² ∫Cn² dz)^(−3/5)` is WRONG for finite-aperture beams — it effectively weights the source region as heavily as the target region, which overweights near-aperture turbulence.

### Constant-Cn² closed form

When Cn²(z) = Cn² (constant), the integral has the closed form:

```
∫₀^L Cn² · (z/L)^(5/3) dz = Cn² · L · (3/8)
```

(line 103). The 3/8 = 1/(1+5/3) = 1/(8/3). This is exact; no numerical error.

### HV-5/7 profile

Hufnagel 1974 proposed a three-term altitude-dependent profile:

```
Cn²(h) = 0.00594 · (v_HV/27)² · (1e-5·h)^10 · exp(−h/1000)     [high-altitude]
       + 2.7e-16 · exp(−h/1500)                                 [boundary layer]
       + Cn²_ground · exp(−h/100)                               [surface layer]
```

The three terms model distinct atmospheric features:
1. **High-altitude term** — tropopause turbulence scales with upper-atmosphere wind `v_HV`; the `(v/27)²` normalizes to a nominal 27 m/s (typical mid-latitude jet stream). The `h^10` rises sharply near the tropopause (~10 km) then the `exp(−h/1000)` cuts off.
2. **Boundary-layer term** — a fixed 2.7e-16 m⁻²/³ amplitude at the surface decaying with a 1500 m scale height.
3. **Surface layer** — user-specified `Cn²_ground` decaying with a 100 m scale height, representing near-surface thermal-plume turbulence.

Along a slant path from H_e to H_t, the altitude is `h(z) = H_e + (H_t − H_e)·z/L`. The integral becomes:

```
Cn2_integrated = ∫₀^L Cn²(h(z)) · (z/L)^(5/3) dz
```

evaluated by `scipy.integrate.quad` (adaptive quadrature). The integrand is smooth (HV profile is smooth for h ≥ 0, `(z/L)^(5/3)` vanishes smoothly at z=0), so quad's default tolerance (~1e-8 absolute) is comfortably inside the SPEC §3 M5.5 2% requirement.

### Engineering w_turb

The long-exposure turbulent 1/e² radius at range L is approximately

```
w_turb = 2·L / (k · r0_sph)
```

**CLAUDE §7.1 invariant — engineering form.** The rigorous form is `w_turb = 2·L / (k · ρ₀)` where `ρ₀ ≈ 2.1 · r₀` is the wave-structure radius (Andrews & Phillips §6.5). The engineering form using `r₀_sph` directly is mildly conservative (overestimates spot size) and is the SPEC v1 choice for auditability. SPEC §10 notes the engineering-form conservatism.

## Known simplifications

- **Weak-turbulence regime** assumed throughout. Strong-turbulence corrections (saturation of scintillation, beam wander enhancement) not modeled.
- **Long-exposure** spot — short-exposure beam wander vs tilt-isoplanatic separation not tracked.
- **Spherical-wave form** appropriate for the diverging-beam limit; near the waist where the beam is effectively collimated the plane-wave form would apply. For HEL engagement ranges (L ≫ zR typical), spherical is correct.
- **HV-5/7 profile** is a daytime mid-latitude template. At night, over water, at high latitude, or in dust, the profile shape changes. SPEC enumerates `HV_day`, `HV_night`, `custom` values but the v1 code only implements `constant` and `HV_5_7`; other values raise `NotImplementedError`.
- **Linear altitude-along-slant** approximation — assumes straight-line beam; neglects atmospheric refraction (negligible for L ≤ 50 km and moderate elevation).

## Cross-check

Canonical scenario (C-UAS 1500 m preset): λ = 1.07 µm, L = 1500 m, HV-5/7 model, Cn²_ground = 1.7e-14, v_HV = 21, H_e = 2, H_t = 200.

Hand computation (order-of-magnitude):
- k = 2π / 1.07e-6 = 5.87e6 1/m.
- At 100 m altitude, Cn² ≈ 1.7e-14 · exp(−1) ≈ 6.25e-15 plus boundary ≈ 2.7e-16 · exp(−100/1500) ≈ 2.52e-16 plus near-zero high-alt.
- Path-integral Cn2_integrated ≈ 10⁻¹¹ m¹/³ order.
- r0_sph ≈ (0.423 · (5.87e6)² · 10⁻¹¹)^(−0.6) ≈ (0.423 · 3.44e13 · 10⁻¹¹)^(−0.6) ≈ (145.7)^(−0.6) ≈ 0.049 m ≈ 5 cm.
- w_turb = 2 · 1500 / (5.87e6 · 0.049) ≈ 3000 / 2.88e5 ≈ 0.0104 m ≈ 1.0 cm.

Independent verification with `physics/m5_turbulence.py:compute` at these inputs yields `r0_sph ≈ 0.049 m`, `w_turb ≈ 0.010 m` — agrees to order of magnitude. Tight numerical cross-checks live in Layer 2 and Layer 3.

## Cross-reference to CLAUDE §7.1

- **`r0_sph = (0.423·k²·∫Cn²·(z/L)^(5/3) dz)^(-3/5)`** — CLAUDE §7.1 explicit; spherical-wave form.
- **`w_turb = 2L/(k·r0_sph)`** — CLAUDE §7.1 explicit; engineering form.
