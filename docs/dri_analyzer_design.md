# Plan: DRI Analyzer tab (Detection / Recognition / Identification)

**Date:** 2026-04-25
**Status:** Draft v2, ready for user review. No code work has started.
**Author:** Claude. Self-review pass + numerical validation pass + independent physics-review pass; corrections folded in.
**File destination:** PR 4 will copy this content to `docs/dri_analyzer_design.md` (separate from `SPEC.md` — DRI is non-HEL physics; SPEC.md stays focused on the laser chain).

**Revision history:**
- **v1 → v2 (this revision):** caught and fixed three issues during a self-review pass:
  1. Added **aperture / f-number** as an explicit input (the v1 plan had no diffraction term — diffraction is comparable to IFOV at typical telephoto sensor configurations and must enter the IFOV-effective RSS).
  2. Updated the **Fried r₀ test case** from a wrong 5 cm reference to the correct **8.6 mm** at the canonical scenario (verified with closed-form arithmetic from the Andrews & Phillips formula).
  3. Updated the **TTPF probability table** (50 / 80 / 95 %) → **1.00 / 1.45 / 2.04** from a numerical solve of the canonical Driggers expression `P = N^E / (1+N^E)` with `E = 2.7 + 0.7·N`. The earlier 1.52 / 2.34 numbers were from a different E-formulation; we pin to the formula we actually implement.
  4. Added a **path-length self-consistency iteration** note — `θ_turb` depends on `L`, which is the answer; the inner kernel needs a fixed-point loop (2–3 iterations to converge).
  5. Added an explicit **§5 Math validation** section with a worked end-to-end numerical example.

---

## 1 · Context & motivation

The HEL Calculator currently models the laser-emitter side of a directed-energy engagement end-to-end (M1–M11 + the v2.0 trajectory chain that closed last week). The user wants a **second, independent analysis surface** in the same app: a passive-sensor DRI calculator. Given an electro-optical sensor's parameters and an atmosphere, it returns the ranges at which a human operator (or equivalent classifier) can **Detect**, **Recognise**, and **Identify** a target of given size — using the Johnson criteria as the discrimination rule.

Two reasons it earns a slot in the same tool rather than a sibling app:
1. The atmospheric and turbulence physics overlap conceptually with M4 / M5 (same Kruse-McClatchey, same Fried parameter), so the user benefits from one mental model across the two analyses.
2. The user is doing system-level trade studies. Pairing "can my laser kill at this range?" with "can my sensor see / identify at this range?" in one workspace is the natural workflow.

**The DRI math is not in the HEL physics contract.** Per `CLAUDE.md` §3, structural additions need a contract document. We chose `docs/dri_analyzer_design.md` (this plan, copied at PR 4) rather than extending `SPEC.md` so the laser contract stays cohesive. `ARCHITECTURE.md` gets a small additive edit for the new file paths.

---

## 2 · User-confirmed scope

The user reviewed and accepted:

- **Multi-band wavelength dropdown** — Visible (550 nm), NIR (850 nm), SWIR (1550 nm), MWIR (4 µm), LWIR (10 µm)
- **All four optional plots** — DRI vs target size, atmospheric transmission curve, DRI vs Cn², DRI heatmap (FOV × target size)
- **All three optional inputs** — inherent contrast C₀, Johnson cycles override (D / R / I), probability of discrimination (50 / 80 / 95 %)
- **Doc home** — `docs/dri_analyzer_design.md`, not `SPEC.md`
- Target presets must include a custom-dimension entry

Plus the originally-stated required inputs (sensor resolution, WFOV, NFOV, focal length, Cn², visibility) and the **f-number** I added for the diffraction calculation in this v2 revision (see §5).

---

## 3 · Architectural decisions

| Decision | Choice | Rationale |
|---|---|---|
| Module home | `physics/dri_analyzer.py` (flat) | One module today; `sensors/` subpackage is premature |
| Compute split | Many small kernels + a thin `compute(inputs)` wrapper | FOV / target / Cn² sweeps call the inner kernel 50–200× per render; inline kernels are essential for performance and testability |
| Atmosphere code reuse | **Don't reuse `m4_atmosphere.py`** | M4 is tied to the four HEL wavelengths {1.06 / 1.07 / 1.55 / 2.05 µm}; DRI spans 0.55 – 10 µm. We implement Kruse + Kim + a thermal-band table inside `dri_analyzer.py` |
| Turbulence code reuse | **Don't reuse `m5_turbulence.py`** | M5 emits *spherical*-wave r₀ (diverging laser). Passive imaging needs *plane*-wave r₀. We implement plane-wave Fried inside `dri_analyzer.py` |
| Sidebar layout | Three new collapsible expanders (DRI sensor / atmosphere / target), **collapsed by default** | Avoids cluttering the HEL workflow; a HEL-only user sees the same sidebar they had before |
| Preset coupling | DRI inputs **not** added to `_SI_TO_WIDGET` in `ui/presets.py` | Engagement-scenario presets remain HEL-only; selecting "C-UAS — short range" does not stomp the user's DRI inputs |
| Cache pattern | Each FOV / target / Cn² sweep is its own `@st.cache_data` helper in `ui/app.py` | Mirrors `run_sweep_cached`. Cheap (50–200 closed-form evaluations vs 30 orchestrator calls) |
| URL share | DRI inputs encode into `st.query_params` like HEL inputs | Consistent share-link behaviour |
| Path-length iteration | Inner range kernel does its own fixed-point on `L` | `θ_turb(L)` depends on the answer `R`; iterate 2–3 times until `|R_new − R_old|/R_old < 1 %` (cheap) |

---

## 4 · Inputs (final, after v2 revision)

| Group | Input | Default | Range / units | Notes |
|---|---|---|---|---|
| Sensor | Resolution horizontal `N_h` | 1920 px | 320 – 8192 | Used in IFOV |
| Sensor | Resolution vertical `N_v` | 1080 px | 240 – 8192 | Tooltip-display only (we use horizontal IFOV; assume square pixels) |
| Sensor | NFOV `θ_NFOV` | 1.5° | 0.05° – 60° | Used as the headline FOV |
| Sensor | WFOV `θ_WFOV` | 25° | 1° – 120° | Used as the FOV-sweep upper bound |
| Sensor | Focal length `f` | 200 mm | 5 – 5000 | Used with f-number to derive aperture |
| Sensor | F-number `f/#` | 2.8 | 1.0 – 22.0 | **NEW v2** — diffraction needs aperture; `D_aperture = f / (f/#)` |
| Atmosphere | Wavelength band | Visible | enum (5) | Visible 0.55 µm / NIR 0.85 / SWIR 1.55 / MWIR 4 / LWIR 10 |
| Atmosphere | Cn² preset | Moderate (1e-14) | enum (7) | See §7.2 |
| Atmosphere | Visibility `V` | 23 km | 0.5 – 100 km | Meteorological visual range |
| Atmosphere | Inherent contrast `C₀` | 0.30 | 0.05 – 1.00 | Daytime ground target ~0.3; high-contrast ~0.7 |
| Target | Target preset | NATO standard | enum (9) | See §7.1 |
| Target | Custom critical dim `h` | (—) | 0.05 – 50 m | Visible only when `Custom` selected |
| Criteria | Probability `P` | 50 % | enum {50, 80, 95} | Drives TTPF cycles multiplier |
| Criteria | Johnson cycles D / R / I | 1.0 / 4.0 / 8.0 | 0.1 – 30 each | Override Johnson 1958 defaults |

**Total: 14 inputs (3 atmosphere + 6 sensor + 2 target + 3 criteria).**

---

## 5 · Math validation — worked example end-to-end

> This section was added during the v2 self-review pass. It pins every formula in the plan to a number you can re-derive with a calculator. The numerical pass exposed one wrong test case (Fried r₀: was 5 cm, correct 8.6 mm) and one missing term (diffraction). Both folded in.

**Reference scenario:** `1920×1080, NFOV=1.5°, WFOV=25°, f=200 mm at f/2.8, V=23 km, Cn²=1×10⁻¹⁴, Visible (550 nm), NATO target h=2.3 m, C₀=0.30, C_t=0.02, Johnson 1/4/8, P=50 %.`

### 5.1 — IFOV (geometric pixel angle)

```
FOV_h_rad   = 1.5° × π/180 = 0.02618 rad
IFOV_pixel  = FOV_h_rad / N_h = 0.02618 / 1920 = 13.64 µrad / pixel
```

### 5.2 — Geometric Johnson range (no atmosphere, no turbulence, no diffraction)

```
R_geom(level) = h / (2 × N_cycles × IFOV)

Detection      (N=1) : 2.3 / (2·1·1.364e-5) = 84.34 km
Recognition    (N=4) : 2.3 / (2·4·1.364e-5) = 21.08 km
Identification (N=8) : 2.3 / (2·8·1.364e-5) = 10.54 km
```

These are the **upper bounds** before atmosphere / optics degrade the picture.

### 5.3 — Atmospheric extinction (Kruse, V > 6 km)

```
q     = 1.3                                    (V in 6..50 km regime)
α(λ)  = (3.91 / V_km) × (550 nm / λ_nm)^q
α     = (3.91 / 23) × (550/550)^1.3 = 0.170 / km           ✓
```

### 5.4 — Atmospheric range (Koschmieder)

```
R_atm = (1 / α) × ln(C₀ / C_t)
      = (1 / 0.170) × ln(0.30 / 0.02)
      = 5.88 × 2.708
      = 15.93 km                                            ✓
```

### 5.5 — Plane-wave Fried r₀ (at L=5 km representative)

```
k       = 2π / λ = 2π / 550e-9 = 1.142×10⁷ /m
k²      = 1.305×10¹⁴ /m²
arg     = 0.423 · k² · Cn² · L
        = 0.423 · 1.305e14 · 1e-14 · 5000
        = 2760
r₀      = arg^(-3/5) = 2760^(-0.6) = 8.62 mm = 0.86 cm     ✓ (was wrongly 5 cm in v1)
θ_turb  = λ / r₀ = 550e-9 / 8.62e-3 = 63.8 µrad            ← bigger than IFOV_pixel
```

### 5.6 — Diffraction (Airy disk)

```
D_aperture = f / (f/#) = 200 mm / 2.8 = 71.4 mm
θ_diff     = 1.22 × λ / D_aperture
           = 1.22 × 550e-9 / 0.0714
           = 9.39 µrad                                      ← comparable to IFOV_pixel
```

### 5.7 — Effective IFOV (RSS of three contributions)

```
IFOV_eff² = IFOV_pixel² + θ_turb² + θ_diff²
         = 13.64² + 63.82² + 9.39²
         = 186 + 4072 + 88
         = 4346 (µrad²)
IFOV_eff  = 65.93 µrad                                      (turbulence dominates at 5 km)
```

### 5.8 — Final DRI ranges (with turbulence + diffraction at L=5 km representative)

```
R_geom_eff(level) = h / (2 × N_cycles × IFOV_eff)
R_final(level)    = min(R_geom_eff, R_atm)

Detection      : R_geom_eff = 17.44 km, R_atm = 15.93 km → 15.93 km (atmosphere-limited)
Recognition    : R_geom_eff =  4.36 km, R_atm = 15.93 km →  4.36 km (geometry-limited)
Identification : R_geom_eff =  2.18 km, R_atm = 15.93 km →  2.18 km (geometry-limited)
```

These are the headline numbers Plot DRI-1/2/3 will show at the NFOV endpoint, and the verdict chip will read **"Atmosphere-limited at Detection · Geometry-limited at R / I."**

> **Self-consistency note:** §5.5 used `L = 5 km` as the path length for the Fried calc, but the path length is what we are computing. In production, the inner kernel iterates: take `L = R_atm` as the initial guess, compute `θ_turb(L)`, derive `R_new`, set `L ← R_new`, repeat (typically 2–3 iterations to <1 % stability).

### 5.9 — TTPF probability cycles (canonical Driggers, my numerics)

```
P = N^E / (1 + N^E),    E = 2.7 + 0.7·(N/N50)

Inverse (numerical solve):
P = 50 % → N/N50 = 1.000     ✓ (identity)
P = 80 % → N/N50 = 1.452
P = 95 % → N/N50 = 2.041
```

> Different sources publish slightly different multipliers (because they use a different `E`). I implement and pin to the formula above — it is what `tests/test_dri_analyzer.py` will check. The user can override via the Johnson-cycles override input if they prefer the simpler 1.0 / 1.5 / 2.5 round numbers.

### 5.10 — Cross-checks

| Property | Expectation | Verified |
|---|---|---|
| `R_geom` linear in `h_target` | 2× target → 2× range | ✓ trivial in formula |
| `R_geom` linear in `N_pixels` | 2× pixels → 2× range | ✓ trivial in formula |
| `R_geom` inverse in `N_cycles` | D = 8× R_I (since 8× the cycles) | ✓ 84.34 / 8 = 10.54 ✓ |
| `r₀` scales as `λ^(6/5)` | 2λ → 2^1.2 × r₀ | ✓ from `r₀ = (k² · ...)^(-3/5)` |
| `θ_turb` scales as `λ^(-1/5)` | longer λ → slightly less blur | ✓ from `θ = λ/r₀` |
| `θ_diff` scales as `λ` | longer λ → more diffraction | ✓ from Airy formula |
| Atmosphere-limited regime | V=1 km clamps every level | ✓ R_atm at V=1 km = (1/3.91)·ln(15) = 0.69 km |
| Turbulence-limited regime | Cn²=5e-13 collapses headline | ✓ θ_turb scales as Cn²^(3/5), so 50× Cn² → 11× θ_turb |

All formulas closed-form, all multiplications match.

---

## 6 · Physics — formulas as implemented (after validation)

### 6.1 — Geometric (Johnson) range

```
R_geom = h_target / (2 × N_cycles_eff × IFOV_eff)
```

### 6.2 — Probability adjustment (TTPF)

Inverse of `P = N^E / (1+N^E)` with `E = 2.7 + 0.7·(N/N50)`. Solved by Newton's method
(< 10 iterations, converges quadratically). Returns `N_cycles_eff = N_cycles_50 × (N/N50)`.

### 6.3 — Atmospheric extinction (Kruse + Kim 2001 low-vis correction)

```
α(λ_nm, V_km) = (3.91 / V_km) × (550 / λ_nm)^q

q = 1.6                       for V > 50 km
  = 1.3                       for 6 < V ≤ 50 km
  = 0.16·V_km + 0.34          for 1 < V ≤ 6 km        (Kim 2001, replaces Kruse)
  = V_km − 0.5                for 0.5 < V ≤ 1 km      (Kim 2001)
  = 0                         for V ≤ 0.5 km          (Kim 2001 fog limit)
```

For thermal bands (MWIR 4 µm, LWIR 10 µm), Kruse is invalid. We use band-averaged
constants (mid-latitude summer, MODTRAN-derived, V=23 km baseline):

| Band | α₀ (/ km) at V = 23 km | Scaling for V ≠ 23 km |
|---|---|---|
| MWIR (4 µm) | 0.10 | linear with α_aer at SWIR (first-order) |
| LWIR (10 µm) | 0.30 | linear with α_aer at SWIR (first-order) |

Thermal-band runs flag `thermal_extinction_first_order` in `assumptions_flagged`.

### 6.4 — Atmospheric range (Koschmieder)

```
R_atm = (1 / α) × ln(C₀ / C_threshold),   C_threshold = 0.02 (Blackwell)
```

### 6.5 — Plane-wave Fried r₀ (uniform Cn² along horizontal path)

```
k       = 2π / λ
r₀(L)   = (0.423 × k² × Cn² × L)^(-3/5)
θ_turb(L) = λ / r₀(L)
```

### 6.6 — Diffraction (Airy disk angular radius)

```
D_aperture = f / (f/#)
θ_diff     = 1.22 × λ / D_aperture
```

### 6.7 — Effective IFOV (RSS quadrature of three blur terms)

```
IFOV_eff(L) = √(IFOV_pixel² + θ_turb(L)² + θ_diff²)
```

### 6.8 — Final DRI range (with self-consistent path length)

```
L₀         = R_atm                                     (initial guess)
for i in 1..5:
    Lᵢ     = h_target / (2 × N_cycles_eff × IFOV_eff(L_{i-1}))
    if |Lᵢ - L_{i-1}| / L_{i-1} < 0.01: break
R_geom_eff = Lᵢ
R_final    = min(R_geom_eff, R_atm)
```

The fixed-point converges in 2–3 iterations on every realistic scenario.

---

## 7 · Catalogues (built into `physics/dri_analyzer.py`)

### 7.1 — Target catalog

| Preset | Width × Height (m) | Critical dim h = √(W·H) (m) |
|---|---|---|
| NATO standard | 2.3 × 2.3 | 2.30 |
| Person standing | 0.50 × 1.80 | 0.95 |
| Car / sedan | 1.50 × 4.50 | 2.60 |
| Light truck / APC | 2.30 × 6.00 | 3.71 |
| Group-3 UAS / Shahed-class | 2.50 × 3.50 | 2.96 |
| DJI Mavic 4 (Group-1 UAS) | 0.40 × 0.30 | 0.35 |
| DJI Mini-class | 0.25 × 0.20 | 0.22 |
| Quadcopter swarm element | 0.15 × 0.15 | 0.15 |
| Custom | (user-entered W × H, or h directly) | user-entered |

(Boat dropped — non-priority for the C-UAS / overland focus this calculator already serves.)

### 7.2 — Cn² presets

| Label | Cn² (m^(−2/3)) |
|---|---|
| Very strong (sunny midday, hot desert surface) | 5 × 10⁻¹³ |
| Strong (clear day, near surface) | 1 × 10⁻¹³ |
| Moderate-strong (warm afternoon) | 5 × 10⁻¹⁴ |
| Moderate (canonical mid-altitude) | 1 × 10⁻¹⁴ |
| Weak-moderate (cool morning) | 5 × 10⁻¹⁵ |
| Weak (overcast / dawn) | 1 × 10⁻¹⁵ |
| Very weak (high altitude / night) | 1 × 10⁻¹⁶ |

### 7.3 — Wavelength bands

| Band | λ (µm) | Atmospheric model | Note |
|---|---|---|---|
| Visible | 0.55 | Kruse + Kim | Naked-eye and CCD daylight cameras |
| NIR | 0.85 | Kruse + Kim | NIR illuminator-assisted |
| SWIR | 1.55 | Kruse + Kim | Eye-safe LIDAR/NV |
| MWIR | 4.0 | Tabulated (first-order) | Thermal — flagged |
| LWIR | 10.0 | Tabulated (first-order) | Thermal — flagged |

---

## 8 · Module layout

```
physics/dri_analyzer.py          ← new — pure module, no Streamlit imports
  TARGET_PRESETS:    dict[str, dict]      (catalog from §7.1)
  CN2_PRESETS:       dict[str, float]     (catalog from §7.2)
  WAVELENGTH_BANDS:  dict[str, dict]      (catalog from §7.3)

  johnson_range(h, N_cycles, ifov_eff)        → float
  ttpf_cycles(probability, N50)               → float       (Newton solver)
  kruse_alpha(V_km, lambda_nm)                → float       (Vis/NIR/SWIR)
  thermal_alpha(band, V_km)                   → float       (MWIR/LWIR)
  atmospheric_alpha(band, lambda_nm, V_km)    → float       (dispatcher)
  atmospheric_range(alpha, C0, C_threshold)   → float
  fried_r0_plane(cn2, L_m, lambda_m)          → float
  airy_theta_diff(lambda_m, f_mm, f_number)   → float
  effective_ifov(ifov_pix, theta_turb, theta_diff) → float  (RSS)
  dri_range(level, **kwargs)                  → dict        (one D/R/I number, w/ path-length iteration)
  fov_sweep(level, n_pts, **kwargs)           → list[dict]  (used by Plot DRI-1/2/3)
  target_size_sweep(level, sizes_m, **kwargs) → list[dict]  (used by Plot DRI-4)
  cn2_sweep(level, **kwargs)                  → list[dict]  (used by Plot DRI-6)
  heatmap(fov_grid, target_grid, **kwargs)    → 2D array    (used by Plot DRI-7)

  compute(inputs: dict) → dict                (HEL-style wrapper, returns ~30 keys)

tests/test_dri_analyzer.py       ← new — unit tests, see §10

ui/labels.py                     ← edit
  TAB_LABELS                              += {"dri_analyzer": "DRI Analyzer"}
  SECTION_LABELS                          += {"dri_sensor", "dri_atmosphere", "dri_target"}
  INPUT_LABELS                            += DRI input rows (~14 keys)
  OUTPUT_LABELS                           += DRI output rows (~10 keys)
  EXPLANATIONS                            += dri_intro, dri_plot_*_intro, dri_methodology

ui/panels.py                     ← edit
  section_7_dri_sensor(initial)           → dict
  section_8_dri_atmosphere(initial)       → dict
  section_9_dri_target(initial)           → dict
  collect_all()                           merges the three new dicts at the end

ui/plots.py                      ← edit
  plot_dri_distance_vs_fov(sweep, level)  → go.Figure       (3 used: D/R/I)
  plot_dri_distance_vs_target_size(...)   → go.Figure       (1 figure, 3 traces)
  plot_dri_atmospheric_transmission(...)  → go.Figure
  plot_dri_distance_vs_cn2(...)           → go.Figure       (1 figure, 3 traces)
  plot_dri_heatmap_fov_vs_target(...)     → go.Figure

ui/outputs.py                    ← edit
  render_tab_dri_analyzer(merged) → None
  Helpers for the three sweep precomputes (cached at the app.py level)

ui/app.py                        ← edit
  Tab dispatch: add the "dri_analyzer" branch (one ~5-line block).
  3 new @st.cache_data sweep helpers: run_dri_fov_sweep_cached,
    run_dri_target_sweep_cached, run_dri_cn2_sweep_cached.
  Heatmap is computed inline inside its own cached helper at 20×20.

ARCHITECTURE.md                  ← edit (small)
  §3 file tree: add physics/dri_analyzer.py and tests/test_dri_analyzer.py.
  §4 (function signatures): add the dri_analyzer.compute signature row.
  Note: ui/app.py and ui/outputs.py rules unchanged (DRI tab follows the
  same import contract as every other tab).

docs/dri_analyzer_design.md      ← new (PR 4)
  Copy of this plan file with revisions from review.
```

---

## 9 · UI layout

> **Updated 2026-04-26 (multipage refactor).** The DRI Analyzer was originally specified as one tab inside the HEL Calculator. After three follow-up PRs (multipage PR 1 / 2 / 3) it lives on its own dedicated page under Streamlit's `st.navigation` system at `ui/tools/dri_analyzer.py`. This section reflects the post-multipage layout. The HEL Calculator page (`ui/tools/hel_calculator.py`) carries no DRI inputs at all; the DRI page carries no HEL inputs.

### 9.1 — DRI page sidebar

The DRI page sidebar contains, top to bottom:

**Sensor preset** dropdown — 5 starter sets (EO daytime surveillance · EO long-range surveillance · SWIR night-vision · MWIR thermal imager · LWIR thermal imager) plus Custom. Selecting any named preset overwrites every DRI sidebar field; Custom leaves the user's edits in place.

**Expander: DRI sensor**
- Resolution horizontal (px) — default 1920
- Resolution vertical (px) — default 1080
- WFOV (deg) — default 25
- NFOV (deg) — default 1.5
- Focal length (mm) — default 200
- F-number — default 2.8

**Expander: DRI atmosphere**
- Wavelength band — dropdown of 5 (Visible / NIR / SWIR / MWIR / LWIR)
- Cn² preset — dropdown of 7
- Visibility (km) — default 23
- Inherent contrast C₀ — default 0.30, advanced

**Expander: DRI target & criteria**
- Target preset — dropdown of 9
- Custom critical dimension (m) — visible only when "Custom" selected
- Probability of discrimination — dropdown {50 %, 80 %, 95 %}
- Johnson cycles override — three numeric inputs (D, R, I) — defaults 1.0 / 4.0 / 8.0

**Sidebar footer:** "Share this analysis" button (encodes only `dri_*` keys) and a dark / light theme toggle. **No Run button** — the DRI analysis is closed-form arithmetic (sub-100 ms full sweep) and recomputes reactively on every sidebar widget change.

### 9.2 — DRI page main content

```
┌────────────────────────────────────────────────────────────────┐
│  DRI Analyzer — sensor classification ranges                   │
├────────────────────────────────────────────────────────────────┤
│  Headline (NFOV configuration)                                 │
│  ┌──────────────┬──────────────┬──────────────┐               │
│  │ Detection    │ Recognition  │ Identification│              │
│  │   15.93 km   │    4.36 km   │   2.18 km    │               │
│  └──────────────┴──────────────┴──────────────┘               │
│  Verdict chip: "Atmosphere-limited at Detection · Geometry-    │
│                 limited at Recognition / Identification"       │
├────────────────────────────────────────────────────────────────┤
│  Required FOV-sweep plots (3, stacked vertically)              │
│    Plot DRI-1  Detection range vs FOV  (NFOV → WFOV)           │
│    Plot DRI-2  Recognition range vs FOV                        │
│    Plot DRI-3  Identification range vs FOV                     │
│    Each plots: R_geom_eff (solid), R_atm (dashed), and         │
│                R_final (filled, color-coded by limiting term). │
├────────────────────────────────────────────────────────────────┤
│  Optional plots (4)                                            │
│    Plot DRI-4  DRI vs target size (3 curves, log-x)            │
│    Plot DRI-5  Atmospheric transmission vs range               │
│    Plot DRI-6  DRI vs Cn² (3 curves, 7 grid points)            │
│    Plot DRI-7  Heatmap: FOV × target size, color = Detection R │
│                Behind a "Compute heatmap" button (~3 s on a    │
│                20×20 grid; like Plot K's compute-on-click).    │
├────────────────────────────────────────────────────────────────┤
│  Diagnostics                                                   │
│    assumptions_flagged list (HIGH UNCERTAINTY items)           │
│    "Show methodology" expander → docs/dri_analyzer_design.md   │
└────────────────────────────────────────────────────────────────┘
```

---

## 10 · Test plan

`tests/test_dri_analyzer.py` — pinned numerical cases (every value checked by the §5 worked example):

| # | Test | Expected | Tol | Source |
|---|---|---|---|---|
| 1 | TTPF inverse — `ttpf_cycles(0.50, 4.0) == 4.0` | 4.000 | 1e-9 | identity |
| 2 | TTPF inverse — `ttpf_cycles(0.80, 4.0) ≈ 5.81` | 5.810 | 1 % | numerical solve in §5.9 |
| 3 | TTPF inverse — `ttpf_cycles(0.95, 4.0) ≈ 8.16` | 8.160 | 1 % | numerical solve in §5.9 |
| 4 | Kruse @ V=23 km, λ=550 nm | 0.170 / km | 1 % | §5.3 |
| 5 | Kim @ V=2 km, λ=850 nm | per closed form | 1 % | §6.3 |
| 6 | Koschmieder @ V=23 km, C₀=0.3, C_t=0.02 | 15.93 km | 1 % | §5.4 |
| 7 | Johnson NATO @ IFOV=1 mrad, level=I (8 cycles) | 143.75 m | 1e-6 | identity |
| 8 | Johnson NATO @ IFOV=1 mrad, level=D (1 cycle) | 1150 m | 1e-6 | identity |
| 9 | **Plane-wave Fried r₀** @ Cn²=1e-14, L=5 km, λ=550 nm | 8.62 mm | 5 % | §5.5 (corrected from 5 cm in v1) |
| 10 | Fried r₀ scales as λ^(6/5) | ratio at λ=2λ₁ = 2^1.2 = 2.297 | 1 % | exact |
| 11 | **Airy θ_diff** @ D=71.4 mm, λ=550 nm | 9.39 µrad | 1 % | §5.6 |
| 12 | RSS IFOV adds in quadrature | √(13.64²+63.82²+9.39²) = 65.93 µrad | 1 % | §5.7 |
| 13 | dri_range path-length fixed-point converges | <5 iterations always | — | structural |
| 14 | Headline scenario — Detection | 15.93 km | 5 % | §5.8 |
| 15 | Headline scenario — Recognition | 4.36 km | 5 % | §5.8 |
| 16 | Headline scenario — Identification | 2.18 km | 5 % | §5.8 |
| 17 | dri_range monotone in target size | larger target → longer range | — | monotonicity |
| 18 | dri_range monotone in resolution | more pixels → longer range (geometry regime) | — | monotonicity |
| 19 | dri_range hits atmospheric ceiling at low V | V=1 km caps R_DRI at ~0.69 km | 5 % | regime check |
| 20 | dri_range turbulence-dominated at strong Cn² | Cn²=5e-13, L=5km → IFOV_eff ≈ θ_turb | 10 % | regime check |
| 21 | compute() emits every expected key | full key inventory | — | structural |
| 22 | compute() flags MWIR/LWIR thermal first-order | flag present | — | flag check |
| 23 | compute() flags Cn² out of validity | flag present at Cn² > 1e-12 | — | flag check |

Plus property tests via Hypothesis:
- `dri_range ≥ 0` for any validator-accepted input set
- `R_atm > 0` whenever `α > 0` and `C₀ > C_threshold`
- `dri_range(D) ≥ dri_range(R) ≥ dri_range(I)` for any inputs (Detection requires fewer cycles)

UI tests (extending `tests/test_ui_numerics.py`) — smoke-only for the five plot constructors, including the "no feasible" frame fallback (V → 0).

---

## 11 · Implementation as four PRs

| PR | Scope | Lines (≈ code + tests) |
|---|---|---|
| **PR 1 — Physics core** | `physics/dri_analyzer.py` + `tests/test_dri_analyzer.py`. All math kernels, target / Cn² / band catalogues, `compute()` wrapper, fixed-point inner loop. No UI. **App still runs.** | 400 + 350 |
| **PR 2 — UI scaffold + headline numerics** | New tab, three sidebar expanders, `render_tab_dri_analyzer` shell with the three D / R / I metric cards and the verdict chip. No plots yet. Manual smoke test in Streamlit. | 250 + 80 |
| **PR 3 — Required FOV-sweep plots** | Three `plot_dri_*_vs_fov` constructors + the `run_dri_fov_sweep_cached` helper in `ui/app.py`. Three-row stack on the tab. Plot tests. | 250 + 80 |
| **PR 4 — Optional plots + design doc** | Plot DRI-4 (target-size sweep), DRI-5 (atm transmission), DRI-6 (Cn² sweep), DRI-7 (heatmap, compute-on-click). Plus `docs/dri_analyzer_design.md` and the `ARCHITECTURE.md` edit. | 350 + 100 |

**Total:** ~1 250 lines code + ~610 lines tests ≈ 1 860 lines. About a third of the v2.0 tracker-dwell campaign — appropriate scope for an isolated feature.

---

## 12 · Out of scope (v1)

- **Sensor noise / NETD / MRTD / SNR** — full EO/IR sensor performance model. v1 is geometry + atmosphere + Johnson cycles only.
- **Scintillation, temporal effects, scene clutter.**
- **Day/night transitions, illumination model, BRDF.**
- **Polarisation, multi-spectral fusion, super-resolution.**
- **Active illumination (LIDAR / SWIR illuminator + sensor).** — possibly v2.
- **Atmospheric path with vertical Cn² profile (HV-5/7).** — v1 uses uniform Cn² along a horizontal path. (HEL's M5 has the HV profile; if needed in v2 the plane-wave Fried integral generalises trivially.)
- **Full multiplicative MTF integration.** v1 uses RSS quadrature of IFOV + θ_turb + θ_diff; full MTF cascade is v2.
- **Comparing simultaneous DRI on multiple sensors / mosaicked sensors.**
- **Probability false-alarm rate** — only probability-of-correct-classification (TTPF) is modelled.

---

## 13 · Risks & open decisions

- **MWIR / LWIR atmospheric model is first-order.** Tabulated band-averaged α from MODTRAN mid-latitude summer; flagged in `assumptions_flagged`. Acceptable for trade-study work; for safety analysis or specification work a MODTRAN/LOWTRAN integration is required.
- **Probability adjustment via 3-row table** (50 / 80 / 95 %). A continuous slider would be smoother but the lookup is traceable to the formula in §5.9; adjust at PR 1 if user prefers.
- **Heatmap compute cost.** 20×20 = 400 closed-form evaluations of `dri_range` (each does the path-length fixed-point); <500 ms total. Compute-on-click pattern preserved for UX consistency with Plot K, not because it's slow.
- **Sidebar sprawl.** Three new collapsible expanders. Defaults collapsed; existing HEL workflow unaffected.
- **Path-length self-consistency edge cases.** When θ_turb dominates IFOV_pixel by many orders of magnitude (e.g. very strong Cn² at long range), the fixed-point can oscillate. We damp by averaging the last two iterates; structural test #13 catches non-convergence.

---

## 14 · Verification

### Per-PR
- `pytest tests/` green at the new count
- Pyflakes + mypy permissive clean on all touched files
- Streamlit local-run smoke against the canonical scenario (1920×1080, NFOV=1.5°, WFOV=25°, V=23 km, Cn²=1e-14, NATO target, visible)

### Campaign-level (after PR 4)
- The user's stated scenario (sensor + 5 target presets + visible band) produces sensible numbers in all three regimes:
  - **Geometry-limited** (clear V=50 km, large NATO target): D/R/I scale linearly with target size at fixed FOV.
  - **Atmosphere-limited** (V=1 km, any target): all three ranges clamp to R_atm.
  - **Turbulence-limited** (Cn²=5e-13, long range): IFOV_eff ≈ θ_turb dominates the geometric IFOV.
- Cross-check Plot DRI-1 endpoints against the headline numerics (curve at NFOV must equal the headline D number; curve at WFOV must equal D-with-WFOV).
- Heatmap diagonal (target size = critical scale × FOV) reads off as constant range — closed-form invariant.
- Export the DRI tab via the share-URL — round-trip reproduces the same DRI ranges to within numerical noise.

---

## 15 · Self-review pass — items caught and folded in

A self-review pass plus an independent physics-review pass plus a numerical validation pass caught the following items, all reflected in the v2 plan above:

| # | Item | v1 status | v2 status |
|---|---|---|---|
| 1 | Diffraction (Airy disk) was missing from the IFOV blur | Not modelled | Added §6.6 + f-number input (§4) |
| 2 | Fried r₀ test case wrong | "5 cm" reference (Plan agent error) | **8.62 mm** verified (§5.5, Test 9) |
| 3 | TTPF table values wrong | 1.52 / 2.34 (different E formula) | **1.45 / 2.04** verified (§5.9, Tests 2-3) |
| 4 | Path-length self-consistency missing | not noted | Fixed-point loop (§6.8); §11 risk note |
| 5 | Aperture / f-number missing as input | not in input list | Added (§4 row 6) |
| 6 | MWIR / LWIR atmospheric model | flagged | Tabulated + first-order scaling (§6.3) |
| 7 | Critical-dim convention not pinned | implicit | sqrt(W·H) (NV-IPM, §7.1) — explicit |
| 8 | Plane-wave vs spherical-wave r₀ | not differentiated | Plane-wave for passive imaging (§3 + §6.5) |
| 9 | k² factor missing in r₀ formula | none | **0.423 · k² · Cn² · L** verified (§5.5) |
| 10 | Math validation worked example | none | Full §5 added with 10 sub-sections |

**Plan ready for user approval.**
