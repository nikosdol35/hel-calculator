# M1 — Laser source

**File:** `physics/m1_laser_source.py`
**Outputs:** `theta_diff`, `w0`, `zR`, `I_exit`

## Formulas implemented (code ↔ SPEC ↔ source)

| Code line | Expression | SPEC | Primary citation | Secondary citation | Status |
|---|---|---|---|---|---|
| 45 | `theta_diff = M²·4·λ/(π·D)` | §3 M1 | Siegman 1986 §17 (M² formalism) | Saleh & Teich 2019 §3.1 | verified |
| 46 | `w0 = D/2` | §3 M1 | Siegman 1986 §17 (beam-fills-aperture convention) | — | verified |
| 47 | `zR = π·w0² / λ` | §3 M1 | Siegman 1986 §16.2 eq. (16.2-8) | Saleh & Teich 2019 §3.1 eq. (3.1-22) | verified |
| 48 | `I_exit = 2·P0 / (π·w0²)` | §3 M1 | Siegman 1986 §17 (Gaussian peak irradiance) | Saleh & Teich 2019 §3.1 | verified (CLAUDE §7.1 factor-of-2) |

## Constants used

None. All formulas are input-driven. The wavelength-validation tolerance (`5.0 nm`) lives in `common.py` and is audited in `constants_audit.md`.

## Derivation (from first principles)

A Gaussian beam's TEM₀₀-mode intensity profile at the beam waist is

```
I(r, z=0) = (2·P / (π·w0²)) · exp(−2·r² / w0²)
```

At `r = 0` and `z = 0` this gives the peak irradiance `I_exit = 2·P / (π·w0²)` (code line 48). The factor of 2 is **CLAUDE §7.1** invariant: the flat-top equivalent `P/(πw²)` is a common error.

The M²-formalism divergence (Siegman 1986 §17) relates the real-beam full divergence angle to the ideal diffraction-limited case:

```
θ_diff = M² · θ_diff_ideal = M² · (4·λ / (π·D))
```

Here we adopt the convention `D = 2·w0` (beam fills aperture at exit), so `θ_diff = M² · 2λ/(π·w0) = M² · 4λ/(π·D)` (code line 45). The factor 4 is the Siegman full-angle convention; half-angle form gives `θ_half = M²·2λ/(π·D)` and would differ by 2.

The Rayleigh range is the distance over which the beam radius grows to `√2·w0`:

```
zR = π·w0² / λ
```

This is the **M² = 1 reference** form (code line 47). Some texts use `zR = π·w0² / (M²·λ)` to absorb the M² degradation into the Rayleigh range; we keep M² out of `zR` and carry it explicitly in `w_diff(L)` in M7 (see `m7_spot.md`). The net beam radius at range L is identical either way; this is a convention choice, documented in SPEC §3 M1.

## Known simplifications

- Single transverse mode (TEM₀₀) — higher-order modes rolled into M².
- Beam fills exit aperture exactly — no central obscuration, no apodization.
- No polarization dependence — all derivations are scalar-field.

## Cross-check

Canonical scenario (C-UAS 1500 m preset): P0 = 3000 W, M² = 1.2, D = 0.10 m, λ = 1.07 µm.

Hand computation:
- w0 = 0.10 / 2 = 0.05 m = 50 mm.
- θ_diff = 1.2 · 4 · 1.07e-6 / (π · 0.10) = 1.2 · 4.276e-6 / 0.31416 = 1.635e-5 rad = 16.35 µrad.
- zR = π · (0.05)² / 1.07e-6 = π · 0.0025 / 1.07e-6 = 7.34e3 m = 7340 m.
- I_exit = 2 · 3000 / (π · 0.0025) = 6000 / 7.854e-3 = 7.64e5 W/m² = 76.4 W/cm².

Independent verification with `physics/m1_laser_source.py:compute`:
- θ_diff 1.635e-5 rad ✓
- w0 0.050 m ✓
- zR 7340 m ✓
- I_exit 7.64e5 W/m² ✓

All agree at 4 sig figs.

## Cross-reference to CLAUDE §7.1 invariants

- Factor-of-2 in `I_peak = 2P/(πw²)` (line 48) — CLAUDE §7.1.
- M²·4λ/(πD) is the full-angle diffraction divergence; the far-field asymptote `M²·λL/(πw0)` appears in M7 w_diff but NOT here; M1 is aperture-plane only.
