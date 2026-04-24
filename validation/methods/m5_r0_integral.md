# M5 Cn² path integral — numerical-methods validation

**Scope.** This note validates the *numerics* of the Cn² path integral
that feeds the Fried spherical-wave coherence length `r0_sph` in
`physics/m5_turbulence.py`. The SPEC §3 M5 cases pin the *physics*
(constant-Cn² and HV-5/7 numerical values at two operating points) at
2 %; they do not, on their own, prove that the `scipy.integrate.quad`
adaptive quadrature the HV-5/7 branch uses is accurate well inside
that 2 % envelope, nor that the closed-form `3/8` constant-Cn² path
is algebraically exact. That's what this document and the tests in
`tests/test_m5_numerics.py` do.

The goal is the Package 3 acceptance gate from `validation/README.md`
Layer 3.3: **the spherical-wave path integral is accurate to ≤ 0.1 %
at the operating points SPEC specifies, well inside the 2 % physics
tolerance.**

---

## 1. The integral implemented

Per SPEC §3 M5 and CLAUDE §7.1 (spherical-wave, diverging HEL beam):

```
Cn2_integrated = ∫₀^L Cn²(z) · (z/L)^(5/3) dz

r0_sph         = (0.423 · k² · Cn2_integrated)^(-3/5)
w_turb         = 2·L / (k · r0_sph)
```

The `(z/L)^(5/3)` weighting is the spherical-wave path-weighting factor
(Andrews & Phillips §6.5; Fried's 1966 derivation). It up-weights the
near-target end of the path, which is the physical reason a diverging
HEL beam is less sensitive to ground-level turbulence than a
collimated plane wave would be (the plane-wave integrand is
`(z/L)^0 = 1`). The resulting spherical/plane-wave r₀ ratio is
`(3/8)^(-3/5) ≈ 1.876` — an identity the CLAUDE §7.1 invariant list
pins explicitly.

### 1.1 constant-Cn² branch — closed form

When `cn2_model = "constant"`:

```
∫₀^L Cn² · (z/L)^(5/3) dz = Cn² · L · (3/8)
```

The `3/8` prefactor is the definite integral of `(z/L)^(5/3)` over
`[0, L]`:

```
∫₀^L (z/L)^(5/3) dz = L / (1 + 5/3) = L · 3/8
```

Evaluated in closed form. No quadrature.

### 1.2 HV-5/7 branch — adaptive quadrature

When `cn2_model = "HV_5_7"`:

```
h(z)   = H_e + (H_t − H_e) · z/L              [linear slant altitude]
Cn²(h) = 0.00594·(v_HV/27)²·(1e-5·h)^10·exp(-h/1000)
         + 2.7e-16·exp(-h/1500)
         + Cn2_ground·exp(-h/100)
integrand(z) = Cn²(h(z)) · (z/L)^(5/3)
```

`scipy.integrate.quad` uses adaptive Gauss-Kronrod quadrature (QUADPACK
`dqags`). The power-law weighting is continuous and zero at `z = 0`
(no singularity); the HV profile is smooth for `h ≥ 0`. Default
tolerances (`epsabs = 1.49e-8`, `epsrel = 1.49e-8`) are eight decades
inside the SPEC §3 M5 physics tolerance (2 %).

References:
- Fried, D. L., "Optical Resolution Through a Randomly Inhomogeneous
  Medium for Very Long and Very Short Exposures," *J. Opt. Soc. Am.*
  56, 1372–1379 (1966) — the 5/3 spherical-wave path weighting.
- Andrews, L. C. & Phillips, R. L., *Laser Beam Propagation through
  Random Media*, 2nd ed., SPIE Press (2005), Ch. 6 (spherical r₀) and
  Ch. 12 (HV-5/7 profile).
- Piessens, R. et al., *QUADPACK: A Subroutine Package for Automatic
  Integration*, Springer-Verlag (1983) — the adaptive algorithm `quad`
  wraps.

---

## 2. Validation checks

The tests that exercise the numerics live in `tests/test_m5_numerics.py`
(new in Package 3) and in the existing `tests/test_m5_turbulence.py`
SPEC §3 suite. Each subsection maps to either a new test here or a
pre-existing test we rely on as pre-established coverage.

### 2.1 Closed-form `3/8` coefficient — machine-precision identity

**Claim.** On the `cn2_model = "constant"` branch, `Cn2_integrated`
equals `Cn² · L · 3/8` at machine precision. No quadrature error,
no truncation, no path-weighting slip.

**Test.** `test_m5_numerics_constant_3_8_identity` in
`tests/test_m5_numerics.py` asserts the exact `3/8` coefficient at
`rel = 1e-12` — i.e., "this is one float multiply, any drift is
float64 noise." The existing SPEC §3 M5 test `test_m5_r0_uniform_cn2`
pins the downstream `r0_sph` at 2 % but does not directly check the
`3/8` coefficient; this new check adds the tight algebraic guard.

### 2.2 HV-5/7 ↔ constant degeneracy at `H_e = H_t`

**Claim.** With `H_e = H_t = 0`, the HV-5/7 profile is
height-independent and reduces to `Cn²(0) = Cn2_ground + 2.7e-16`.
The HV-5/7 adaptive-quadrature branch must then reproduce the closed-
form constant-branch answer to 0.1 % — which corresponds to `quad`
running well inside its default tolerance.

**Test.** `test_m5_hv_5_7_matches_constant_at_ground` in
`tests/test_m5_turbulence.py` (pre-existing SPEC v1.5 coverage)
asserts `hv.r0_sph == approx(const.r0_sph, rel=0.001)` and likewise
for `w_turb` and `Cn2_integrated`. 0.1 % is two decades tighter than
the SPEC 2 % physics tolerance; anything looser would let quadrature
error leak into the SPEC envelope.

### 2.3 Grid-refinement stability under tightened `epsrel`

**Claim.** Invoking `quad` with `epsrel = 1e-12` (≈ seven decades
tighter than the default) must change `Cn2_integrated` by less than
0.1 % on the SPEC §3 M5.5 HV-5/7 operating point. A larger delta
would mean default-tolerance quadrature is silently leaking error
inside the SPEC 2 % bound.

**Test.** `test_m5_numerics_hv_grid_refinement` in
`tests/test_m5_numerics.py` manually re-computes the HV-5/7 integral
via `scipy.integrate.quad(..., epsrel=1e-12, epsabs=1e-30)` and
compares to the default-tolerance result produced by
`m5_turbulence.compute`. `rel < 1e-6`: seven decades tighter than
0.1 %, and still well clear of the `quad` default tolerance floor.

### 2.4 Edge cases: minimum and maximum slant range

**Claim.** The HV-5/7 quadrature is stable across the full SPEC §3 M5
`R_slant ∈ [50 m, 50 km]` input range. The short-path limit exercises
the dominance of the `Cn2_ground · exp(-h/100)` ground-layer term;
the long-path limit exercises the `(1e-5·h)^10` high-altitude term
that turns on sharply near `h ≈ 10 km`.

**Test.** `test_m5_numerics_edge_case_short_path` and
`test_m5_numerics_edge_case_long_path` in `tests/test_m5_numerics.py`
call `m5_turbulence.compute` at the two endpoints and assert the
returned integral is finite, positive, and consistent with the SPEC
§3 M5 monotonicity (longer path → larger `Cn2_integrated`, smaller
`r0_sph`). No absolute-value pin — those would duplicate the SPEC
physics tests at 2 %; the guard here is on the solver not crashing
and producing sensible signs at the extremes.

### 2.5 Path-weighting 5/3 exponent — structural regression guard

**Claim.** The spherical/plane r₀ ratio `(3/8)^(-3/5)` is the CLAUDE
§7.1 invariant that pins the 5/3 exponent and the 3/8 normalisation
together. Any drift here would mean either the exponent or the
constant-branch coefficient has regressed.

**Test.** `test_m5_spherical_vs_plane_ratio` in
`tests/test_m5_turbulence.py` (pre-existing SPEC §3 M5 test)
asserts the ratio at `rel=0.001`. Pointed to here for completeness
— we do not add a duplicate in the Package 3 numerics file.

---

## 3. What this validation does not cover

- **Non-linear altitude profiles along the slant path.** M5 assumes
  `h(z) = H_e + (H_t − H_e) · z/L` (linear interpolation). A curved-
  Earth correction would put `h(z)` onto an arc; for `R ≤ 50 km` the
  deviation is centimetres-scale and negligible against the 2 %
  physics tolerance. Package 4 notes but does not close this.
- **Alternative Cn² profiles** (`HV_day`, `HV_night`, `custom`).
  Enumerated in SPEC §3 M5 but raise `NotImplementedError` in the
  current code. Their numerics will be validated alongside their own
  SPEC validation cases when they ship.
- **Quadrature-scheme migration.** SPEC §3 M5 specifies `scipy.quad`
  (adaptive Gauss-Kronrod). Alternative schemes (Simpson, fixed-order
  Gauss-Legendre, Clenshaw-Curtis) are not validated.

---

## 4. Acceptance

This note is green when `tests/test_m5_numerics.py` is green on CI
AND the pre-existing `test_m5_hv_5_7_matches_constant_at_ground` and
`test_m5_spherical_vs_plane_ratio` remain green. The numerics file
adds the coefficient-level tightness the SPEC physics suite did not
have; the SPEC suite continues to own the physics envelope.
