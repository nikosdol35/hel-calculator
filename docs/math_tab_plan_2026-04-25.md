# Plan: "How it's calculated" tab — math, formulas, and traceable values

**Date:** 2026-04-25
**Author:** Claude (review pass complete; 12 issues from the first draft fixed)
**Status:** Plan ready for user approval; no implementation work has started.

## 1 · Context & goals

The tool today shows results as cards and plots — `tau_BT = 8.36 s`, `I_peak = 1.67 × 10⁵ W/cm²`, `NOHD = 743 km`. A junior engineer or a non-specialist reviewer who lands on the page has no path from the number on a card to **why that number is that number**. The validation campaign already produced this content (every formula traced, cited, dimensionally checked) but it lives in `validation/derivations/m*.md` — invisible to anyone who only opens the Streamlit UI.

This tab brings that evidence into the UI as a first-class surface: every metric the tool prints, with its formula in textbook notation, its live value for the user's current inputs, and a plain-language explanation. A reader who has never met "Strehl" or "NOHD" should be able to read down a row, learn what the term means, see the math, and check the number.

**Confirmed design decisions** (user-answered 2026-04-25):
- **Formula style:** LaTeX-rendered math (proper Greek, stacked fractions, subscripts/superscripts).
- **Values:** live, updated from the user's current run.
- **Audience tier:** mixed — default Simple view + expandable Full-derivation view.
- **Tab position:** last (after Diagnostics).

## 2 · Scope of metrics

The orchestrator emits **45 unique output keys** (verified against the `c_uas_1500m` golden JSON, which is the post-merge fixture):

- **41 numeric metrics** — each gets a row with a formula, value, and explanation
- **4 categorical outputs** — `failure_mode`, `laser_class`, `engagement_viable`, `m67_converged` — each gets a row in a per-module "Verdicts" sub-section with a different layout (no LaTeX, just the rule that produces the value)

Plus **one integer diagnostic** (`m67_iteration_count`), which surfaces in the M6↔M7 fixed-point row of M7 as context for the iterated values rather than a standalone row.

Per-module breakdown:

| Module | Numeric | Categorical | Notes |
|---|---|---|---|
| **M1 — Laser source** | 4 | 0 | All closed forms (Gaussian beam) |
| **M2 — Power link** | 1 | 0 | One-line scalar |
| **M3 — Geometry** | 4 | 0 | Trigonometry; `available_dwell` carries SPEC §10.5 simplification flag |
| **M4 — Atmosphere** | 6 | 0 | Beer–Lambert + Kruse; HIGH UNCERTAINTY on the McClatchey table values |
| **M5 — Turbulence** | 3 | 0 | HV-5/7 Cn² profile + Fried integral via `scipy.integrate.quad` |
| **M6 — Blooming** | 3 | 0 | Gebhardt + Smith Strehl; engineering 0.3 broadening factor flagged. Values are post-iteration |
| **M7 — Spot / PIB** | 8 | 0 | The integrating module (CLAUDE §7.1 invariants front-and-centre). `w_turb` here is M5's pass-through; deduped from the M5 row |
| **M8 — Burn-through** | 3 | 1 (`failure_mode`) | `tau_BT`, `T_surface_peak`, `E_delivered` come from a 1-D heat-PDE solver, not a closed-form formula — see §6 for how these rows are presented |
| **M9 — Safety** | 3 | 1 (`laser_class`) | ANSI piecewise; aperture correction; SPEC §10.3 conservative posture |
| **M10 — Power/thermal** | 5 | 1 (`engagement_viable`) | Lumped-mass thermal model; `engagement_viable` is `tau_BT < available_dwell` |
| **Orchestrator** | 1 (`m67_iteration_count`) | 1 (`m67_converged`) | Fixed-point loop diagnostics |
| **Total** | **41** | **4** | + 1 diagnostic = **45** keys |

### What `assumptions_flagged` does

The orchestrator's `assumptions_flagged` list is already surfaced on the Diagnostics tab. The math tab does NOT duplicate this — instead, each per-metric Full view shows the assumptions that specifically apply to *that* metric's formula (sourced from the metric's curated record, not the live aggregate list).

## 3 · What the tab looks like

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Tab bar:  Overview · Engagement · Target effects · Safety · Atmosphere ·  │
│           Diagnostics · How it's calculated  ← NEW (rightmost)             │
└────────────────────────────────────────────────────────────────────────────┘

┌─ How it's calculated ─────────────────────────────────────────────────────┐
│                                                                            │
│  [ Simple view  ●○  Full view ]   ← single complexity toggle              │
│                                                                            │
│  Search/filter: [_______________________________ ]                         │
│                                                                            │
│  Quick jump:                                                               │
│  [Glossary] [M1 Laser source] [M2 Power link] [M3 Geometry] [M4 Atm]      │
│  [M5 Turbulence] [M6 Blooming] [M7 Spot/PIB] [M8 Burn-through]            │
│  [M9 Safety] [M10 Resources] [Constants & sources] [Worked example]       │
│                                                                            │
│ ─────────────────────────────────────────────────────────────────────────  │
│  ▸ Glossary  (st.expander, top-level — opens on click)                    │
│ ─────────────────────────────────────────────────────────────────────────  │
│                                                                            │
│  ## M1 — Laser source           ← anchored markdown header (NOT expander, │
│                                    so per-metric expanders can nest below)│
│                                                                            │
│  ┌──────────────────────┬─────────────────────┬──────────┬──────────────┐ │
│  │ Metric               │ Formula             │ Value    │ What it means│ │
│  ├──────────────────────┼─────────────────────┼──────────┼──────────────┤ │
│  │ Diffraction-limited  │  ┌─────────────┐    │          │ How wide an  │ │
│  │ divergence (θ_diff)  │  │   M² · 4λ   │    │ 16.4     │ ideal beam   │ │
│  │ [rad, displayed µrad]│  │   ───────   │    │ µrad     │ would still  │ │
│  │                      │  │     π · D   │    │          │ be at the    │ │
│  │                      │  └─────────────┘    │          │ target …     │ │
│  │  ▸ Show full derivation                                                │
│  ├──────────────────────┼─────────────────────┼──────────┼──────────────┤ │
│  │ ... 3 more rows for w₀, zR, I_exit                                     │
│  └──────────────────────┴─────────────────────┴──────────┴──────────────┘ │
│                                                                            │
│  ## M7 — Spot size and power-in-the-bucket                                │
│  ... 8 numeric rows                                                       │
│                                                                            │
│  ## M8 — Burn-through                                                     │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │  Time to burn-through (τ_BT) [s]                                     │ │
│  │                                                                      │ │
│  │  Solver-based metric — no closed-form formula. The 1-D heat PDE     │ │
│  │     ∂T/∂t = α ∂²T/∂x²                                               │ │
│  │  is integrated forward in time with these boundary conditions:       │ │
│  │     Front:  -k ∂T/∂x|_{x=0} = A_λ I_aim - εσ(T⁴ - T_amb⁴)          │ │
│  │     Back:   -k ∂T/∂x|_{x=L} = h_conv (T - T_amb)                    │ │
│  │  τ_BT is the first time when T_surface ≥ T_fail.                    │ │
│  │                                                                      │ │
│  │  Value: 8.36 s.                                                      │ │
│  │  What it means: how long the laser must hold the target to defeat   │ │
│  │     it. If shorter than the dwell window, the engagement closes.    │ │
│  │                                                                      │ │
│  │  ▸ Show full derivation                                              │ │
│  │     Solver: explicit FD, dx = 50 µm, dt = 0.4 · dx² / (2α).         │ │
│  │     Stability: CFL safety factor 0.4 of the explicit-scheme limit.   │ │
│  │     Citation: Carslaw & Jaeger 1959 §2.3; Incropera & DeWitt §5.    │ │
│  │     Code: physics/m8_burnthrough.py (numerical integration loop)     │ │
│  │     Validated: validation/methods/m8_solver.md (analytic benchmark   │ │
│  │       within 1 %; grid refinement within 0.5 %)                      │ │
│  │     HIGH UNCERTAINTY: A_λ table values per SPEC §10.2.              │ │
│  │     Independently replicated: Layer 5 — agrees ≤ 3.4 %.              │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│  ... rest of M8                                                           │
│                                                                            │
│  ─────────────────────────────────────────────────────────────────────    │
│  ## Categorical outputs (verdicts)                                        │
│     failure_mode (M8) · laser_class (M9) · engagement_viable (M10) ·     │
│     m67_converged (orchestrator)                                          │
│                                                                            │
│  ─────────────────────────────────────────────────────────────────────    │
│  ## Constants & physical sources                                          │
│  ... constants table from validation/constants_audit.md                   │
│                                                                            │
│  ─────────────────────────────────────────────────────────────────────    │
│  ## Worked example — c_uas_1500m, 3 kW / 1.5 km / CFRP                   │
│  ... end-to-end walk through every formula with concrete numbers          │
│                                                                            │
│  [Download as Markdown]   [Download as PDF]                               │
└────────────────────────────────────────────────────────────────────────────┘
```

**Per-metric row in default Simple view:**

| Metric | Formula | Value | What it means |
|---|---|---|---|
| Peak irradiance · `I_peak` · W/cm² (formula in SI W/m²; ÷ 10⁴ for display) | $$I_\text{peak} = \dfrac{2 \, P_\text{exit} \, \tau_\text{atm} \, S_\text{TB}}{\pi \, w_\text{total}^{\,2}}$$ | 16.7 W/cm² | Brightest point in the beam at the target. Depends on how much power survives the optics + atmosphere, how much sits in the central peak vs the wings, and how big the spot has grown. |

**Same row when the user clicks "Show full derivation":**

The row expands (one nesting level — Streamlit's nested-expander limit respected) to reveal:
- **Formula in SI:** `I_peak [W/m²] = 2 · P_exit · tau_atm · S_TB / (π · w_total²)`
- **Substituted with this run's values:**
  $$\dfrac{2 \cdot 2550 \cdot 0.809 \cdot 0.472}{\pi \cdot (0.0602)^2} = 1.668 \times 10^{5} \text{ W/m}^2 = 16.7 \text{ W/cm}^2$$
- **Symbolic dependencies (depends on):** `P_exit` (M2), `τ_atm` (M4), `S_TB` (M6), `w_total` (M7 quadrature) — clickable badges scrolling to those rows.
- **Citation:** Siegman 1986 §17; SPEC §3 M7; CLAUDE §7.1 (factor-of-2 invariant).
- **Implemented at:** `physics/m7_spot_pib.py` (peak-irradiance line in `compute()`).
- **Assumptions:** none specific to this metric (Gaussian peak with factor 2 is exact for a Gaussian beam).
- **Provenance badges:** ✅ CLAUDE §7.1 invariant.
- **Sensitivity (±10 %):** small inline bar showing the % change in I_peak when each upstream input is perturbed by ±10 %.

## 4 · Where the content comes from

Most of the heavy lifting is already done in the validation campaign. New work is mostly **assembly**, not authoring.

| Source (already exists) | Used for |
|---|---|
| `validation/derivations/m1_*.md` … `m11_*.md` | Per-module formula + citation tables — Layer 1 deliverable |
| `validation/constants_audit.md` | Constants & sources table — Layer 1 deliverable |
| `validation/uncertainty_closeout.md` | HIGH UNCERTAINTY badges — Layer 4 deliverable |
| `validation/replication/replication_report.md` | "Independently replicated" badges — Layer 5 deliverable; covers ~13 of 41 numeric metrics |
| `validation/methods/m*.md` | Solver-recipe content for tau_BT and the M6↔M7 iteration |
| `ui/labels.py::OUTPUT_LABELS` | Display labels, units, tooltips — already covers all 45 keys |
| `ui/labels.py::EXPLANATIONS` | Plain-language explanations — needs ~30 new entries for per-metric short blurbs |
| SPEC §3 module specs | Validation-case tolerances → "expected accuracy" badge |

**New content to write:**
- "What it means" sentences for the 41 numeric metrics: ~30 new entries × 2 sentences = ~60 sentences (some metrics already have tooltips that can be reused).
- Glossary: ~22 entries × 3 sentences = ~66 sentences.
- LaTeX strings: about 38 distinct formulas (some metrics share formulas — e.g. `w_diff` in M1 vs M7 is the same Gaussian).
- Worked-example walkthrough for `c_uas_1500m`: ~41 cells, mechanical substitution. Static content (NOT live — see §9 deferred-decisions).

## 5 · "What it means" vs glossary — explicit distinction

These are different things and the tab keeps them separate:

- **Glossary** explains a *concept* — what is "diffraction"? what is "Strehl"? — with no reference to a specific metric. Targeted at readers who've never seen the term.
- **"What it means"** column explains the *role* of a particular metric in the engagement story — what does THIS specific number tell you about the engagement? Targeted at readers who understand the concept but need to know why this number matters.

Example contrast:

> **Glossary entry — Diffraction:**
> The unavoidable spreading of any beam of light as it propagates, set by the wavelength of light and the size of the aperture it came out of. Even a perfect optical system produces a diffraction-limited spot — physics, not an engineering imperfection.

> **"What it means" for `w_diff`:**
> How wide a perfect (diffraction-limited) beam would still be at the target. The minimum spot the system can ever achieve, the floor every other broadening source piles on top of.

## 6 · Special cases — solver-based and iterated metrics

Three metric types do not fit a one-line LaTeX cell and are presented differently:

### 6.1 · `tau_BT`, `T_surface_peak`, `E_delivered` — solver-based (M8)

These come from forward-time integration of a heat PDE. The "formula" cell shows:
- the heat equation,
- the front-face surface BC (absorbed flux − radiation),
- the backside BC (insulated or convective per user input),
- the stopping condition (T_surface ≥ T_fail or vent threshold),
- one line on the solver (explicit FD, dx = 50 µm, CFL safety = 0.4).

Full view adds the citation chain (Carslaw & Jaeger 1959 §2.3 + Incropera & DeWitt §5) and a link to `validation/methods/m8_solver.md` (analytic benchmark within 1 %; grid-refinement within 0.5 %).

### 6.2 · `S_TB`, `w_bloom`, `N_D`, `w_total` — post-iteration (M6↔M7 fixed point)

These are the converged values from the M6↔M7 fixed-point loop (Picard). Each row's formula cell shows the closed-form expression that's evaluated at every iteration, with a banner above:
> *Computed via the M6↔M7 fixed-point iteration (this run: N iterations to 1 % tolerance).*

The Full view links to `validation/methods/m6_m7_iteration.md` for the convergence proof. The banner also enables a click-to-jump to the `m67_iteration_count` row.

### 6.3 · `failure_mode`, `laser_class`, `engagement_viable`, `m67_converged` — categorical

These are not calculated values; they are decisions / classifications. Each gets a row in a "Verdicts" sub-section per module. The "formula" cell shows the rule that produces the verdict, in prose:

> **`failure_mode`** — Set by the M8 solver when the surface temperature first reaches the material's failure threshold. Value is the material's tabulated failure mode (`decomposition`, `melt`, or `vent`), or `no_failure_before_timeout` if the simulation reached the 60-s cap without failure.

> **`laser_class`** — Per ANSI Z136.1 / IEC 60825-1 power thresholds: P₀ ≤ 0.39 mW → Class 1; ≤ 1 mW → Class 1M; ≤ 5 mW → Class 3R; ≤ 500 mW → Class 3B; > 500 mW → Class 4. CW NIR convention; this tool's HEL P₀ values always classify as Class 4.

> **`engagement_viable`** — `tau_BT < available_dwell` AND M67 converged AND no infeasible-geometry error. Boolean.

> **`m67_converged`** — `True` when the M6↔M7 loop's relative change in `w_total` between successive iterations falls below 1 % within 10 iterations. The orchestrator sets it `False` and adds an `assumptions_flagged` entry when the budget is exhausted.

## 7 · Recommendations — what I'd add beyond the user's description

Seven features that significantly raise the value of the tab without bloating it:

### 7.1 · Per-metric Full view as the single nested expander

Streamlit's nested-expander rule means module sections cannot themselves be expanders. Module sections are **anchored Markdown headers** (with the quick-jump nav at the top of the tab); each per-metric Full view is a single `st.expander` that nests inside that section. Clean architecture and avoids the runtime warning.

### 7.2 · Inline "depends on" graph per metric

Every metric row shows the upstream metrics it depends on as small clickable badges. So `I_peak` shows `← P_exit (M2), τ_atm (M4), S_TB (M6), w_total (M7)`. Clicking a badge scrolls to that row. The reader walks the chain from any starting point.

### 7.3 · Side-by-side glossary tooltips

Wherever a Greek letter or symbol appears in a formula or "what it means" string, hovering reveals the glossary entry inline. Streamlit's `st.markdown` with HTML `<abbr title="...">` handles this without adding a dependency. The reader never leaves the row.

### 7.4 · Sensitivity bar — "why is my number what it is?"

Each numeric metric in Full view shows a one-line bar with the ±10 % sensitivity to each user input. **Cost: ~22 numeric user inputs × 2 perturbations = ~44 cached orchestrator runs total**, regardless of how many metrics depend on which input — the perturbation runs are shared across rows. At ~150 ms per run, that's ~7 s of one-time computation per session, then cached. (NOT 460 runs as a previous draft incorrectly stated — sensitivity perturbs raw user inputs, not symbolic intermediate dependencies.)

### 7.5 · Provenance badges

Three icons next to each row:
- ✅ **CLAUDE §7.1 invariant** — formula was a math-audit subject; immutable.
- ⚠️ **HIGH UNCERTAINTY** — values flagged in SPEC §10; click for the §10 disposition from `validation/uncertainty_closeout.md`.
- 🔬 **Independently replicated** — Layer 5 row agrees within ≤ 5 %; click for the agreement number.

The 🔬 badge applies to the 13 metrics in Layer 5's coverage (M1×4, M5×3, M7×3, M8×1, M9×2). The other 28 numeric metrics don't get the badge — visible asymmetry, but it's honest.

### 7.6 · Markdown / PDF export

**Markdown export** is in scope from PR 5: a button at the bottom downloads a self-contained Markdown file (formulas as fenced LaTeX blocks). Trivial to implement — pure string concatenation from the same `MATH_CONTENT` data structure.

**PDF export** is opt-in for a follow-on PR. The simplest path that preserves LaTeX rendering is `playwright`-render-to-PDF; the lower-effort alternative is a printable HTML view that the user prints to PDF themselves.

### 7.7 · Visual diagrams (follow-on PR — not in PRs 1–5)

A small set of curated SVG/matplotlib diagrams attached to specific module sections:
- M1: Gaussian beam profile with w₀, zR, θ_diff annotated.
- M3: engagement-geometry triangle with H_e, R, H_t, R_slant, R_h.
- M5: HV-5/7 Cn² profile vs altitude (log y).
- M8: 1-D heat-conduction slab cartoon with surface flux + backside BC.

Estimated 4 SVGs × ~80 lines each. Ships as a separate PR after the textual content is stable.

## 8 · Implementation breakdown

### New files

| File | Purpose | Est. lines |
|---|---|---|
| `ui/math_content.py` | Hand-curated structured records, one per metric (`MetricEntry` dataclass list with `formula_dependencies`, `sensitivity_inputs`, `formula_latex`, `formula_text`, `explanation_short`, `explanation_full`, `citation`, `code_ref`, `derivation_link`, `provenance` flags, `assumptions`). 41 numeric + 4 categorical = 45 entries. | ~700 |
| `ui/glossary.py` | `GLOSSARY: dict[str, str]` ~ 22 entries. | ~120 |
| `ui/sensitivity.py` | `compute_sensitivity(frozen_inputs, perturbation=0.10) → dict[input_key, dict[output_key, signed_pct_change]]`. Cached via `st.cache_data`. | ~80 |
| `ui/math_export.py` | `to_markdown(content, result) → str`. PDF export deferred to follow-on PR. | ~100 |
| `tests/test_math_tab.py` | (a) Coverage test: every orchestrator output key has a `MATH_CONTENT` entry. (b) LaTeX-validity test: every `formula_latex` string has balanced `{}` and `\(\)`/`$$$$` markers. (c) Smoke render test: `render_tab_math` doesn't crash on the canonical scenario or on `None` result. (d) Glossary cross-reference test: every Greek symbol used in a `formula_latex` has a `GLOSSARY` entry. | ~180 |

### Edited files

| File | Change |
|---|---|
| `ui/outputs.py` | New `render_tab_math(result)` function (~200 lines) plus a `_render_metric_row` helper. |
| `ui/app.py` | Add the seventh tab to the `st.tabs(...)` call; route the new tab to `outputs.render_tab_math(merged)`. (~5 lines.) |
| `ui/labels.py` | Add `TAB_LABELS["math"] = "How it's calculated"`. Add ~30 new `EXPLANATIONS["math_*"]` entries for per-metric short blurbs. (~60 lines.) |
| `tests/test_copy_style.py` | Add `ui/math_content.py` and `ui/glossary.py` to the scan list. (~5 lines.) |
| `tests/test_ui_numerics.py` | Add a sync test: every metric in `MATH_CONTENT` has a corresponding `OUTPUT_LABELS` entry. Mirrors the existing `test_every_numeric_output_has_label`. (~25 lines.) |

### Total scope

≈ **1,400 lines of new content + 200 lines of rendering code + 220 lines of tests**.
About **70 % of the new lines are content** (formula strings, citations, explanations) — most of it transposable from `validation/derivations/` rather than written from scratch.

## 9 · Tab-content data model

```python
# ui/math_content.py — schema (illustrative)

class ProvenanceFlag(Enum):
    CLAUDE_71_INVARIANT = "claude_71"        # CLAUDE §7.1 audit-sensitive
    HIGH_UNCERTAINTY    = "high_uncertainty" # SPEC §10
    REPLICATED          = "replicated"       # Package 5 agreement ≤ 5 %

@dataclass(frozen=True)
class MetricEntry:
    key: str                  # orchestrator output key, e.g. "I_peak"
    module: str               # "M7"
    display_name: str         # "Peak irradiance"
    symbol: str               # LaTeX, e.g. "I_\\text{peak}"
    unit_si: str              # "W/m^2"
    unit_display: str         # "W/cm^2" (matches OUTPUT_LABELS)
    is_categorical: bool      # True for failure_mode, laser_class, etc.
    is_solver_based: bool     # True for tau_BT, T_surface_peak, E_delivered
    is_iterated: bool         # True for S_TB, w_bloom, N_D, w_total

    formula_latex: str | None         # None for categorical
    formula_text: str | None          # ASCII fallback, None for categorical
    formula_dependencies: tuple[str, ...]  # OUTPUT KEYS this formula uses
                                            # (for symbolic substitution)
    sensitivity_inputs: tuple[str, ...]    # USER INPUT KEYS to perturb
                                            # (for §7.4 ±10% sensitivity bar)

    explanation_short: str    # 1-2 sentence "what it means"
    explanation_full: str     # 3-5 sentence expert version
    citation: str             # "Siegman 1986 §17; SPEC §3 M7; CLAUDE §7.1"
    code_ref: str             # "physics/m7_spot_pib.py" (no line number; see §11)
    derivation_link: str      # "validation/derivations/m7_spot.md"
    provenance: tuple[ProvenanceFlag, ...]
    assumptions: tuple[str, ...]
```

The two name-disambiguated fields are intentional:
- `formula_dependencies` — *intermediate* values the formula references (e.g. `w_total` for `I_peak`'s formula).
- `sensitivity_inputs` — *raw user inputs* to perturb for the sensitivity bar (e.g. `P0`, `eta_opt`, `RH`).

A single dict `MATH_CONTENT: dict[str, MetricEntry]` keyed by output key holds all 45 records.

## 10 · Glossary — concrete starter list

22 entries. Each is 2-3 sentences. The list is closed for v1; new terms added only when the math tab introduces them in a "What it means" or formula label.

1. 1/e² radius (`w`)
2. Aimpoint
3. Beam-quality factor (M²)
4. Burn-through
5. Cn² — refractive-index structure parameter
6. Diffraction
7. Dwell time
8. Failure mode (decomposition / melt / vent)
9. Fried parameter (r₀)
10. Gebhardt distortion number (N_D)
11. Jitter (per-axis RMS)
12. Maximum permissible exposure (MPE)
13. Nominal ocular hazard distance (NOHD)
14. Power-in-the-bucket (PIB)
15. Rayleigh range (zR)
16. Slant range
17. Strehl ratio
18. Thermal blooming
19. Top-hat vs Gaussian-peak NOHD
20. Transmission (atmospheric, τ_atm)
21. Wallplug efficiency
22. Wavelength (λ) — note on the four SPEC-validated values

## 11 · File-path references and drift

Every `MetricEntry.code_ref` points at a file under `physics/` but **does not pin a line number** — line numbers drift. Citation format: `physics/m7_spot_pib.py` (file only). Where extra precision is desired, the reference points at the function name: `physics/m7_spot_pib.py::compute`. The `derivation_link` field uses the same convention against `validation/derivations/`.

The `tests/test_math_tab.py` coverage test ensures every output key has a `MATH_CONTENT` entry, but does NOT verify that the cited file/function exists (low value, high false-positive rate against transient renames). The user accepts that as a deliberate trade-off — line drift, in exchange for not needing to maintain pinned line numbers.

## 12 · Implementation order — five PRs

Each PR independently mergeable and shippable.

| PR | Scope | Approx lines | Why first |
|---|---|---|---|
| **1. Tab skeleton + glossary + 3 modules (M1, M2, M3)** | New tab in tab bar; render-tab function; `MATH_CONTENT` for 9 numeric entries; full Simple/Full toggle wired; glossary; quick-jump index; copy-style + LaTeX-validity tests. | ~600 | Smallest end-to-end demonstration of the design — user validates the shape before all 45 records are written. |
| **2. Modules M4–M7** | Adds 20 more entries (M4: 6, M5: 3, M6: 3, M7: 8); sensitivity bar (§7.4) wired in Full view. | ~500 | Most engineering-dense modules; if the design has a problem it surfaces here. |
| **3. Modules M8–M10 + orchestrator + categorical Verdicts** | Remaining 12 numeric entries + 4 categorical + 1 diagnostic; provenance badges (§7.5) wired. Special-case layouts for `tau_BT` (solver), iterated values (M6↔M7), and categorical verdicts. | ~400 | Completes the metric coverage. |
| **4. Constants & sources section + worked example** | Constants table from `validation/constants_audit.md`; worked-example walkthrough at the bottom for the `c_uas_1500m` preset (static content, not user-input-driven). | ~250 | Adds the "behind the scenes" material. Off the critical path. |
| **5. Markdown export** | `Download as Markdown` button wired against the same `MATH_CONTENT` structure; export tested against a fixture. PDF export deferred to a follow-on PR. | ~150 | Pure value-add; ship-when-ready. |

After each PR: `pytest tests/` green, `pyflakes` clean, `mypy` clean, manual Streamlit smoke at the `c_uas_1500m` preset.

## 13 · Out of scope (explicit)

- **No new physics.** Every formula is one already in `physics/m*.py`. CLAUDE §7.1 immutability holds.
- **No SPEC change.** UI-only, per CLAUDE §3 rule 1.
- **No new orchestrator output key.** Every value displayed is already in `result`. CLAUDE §7.2.
- **No interactive symbolic algebra.** The reader does not type a formula and see it evaluated. The formulas are static LaTeX strings curated against the implementation.
- **No paper-style diagrams in PRs 1–5.** Figures are a follow-on PR (§7.7).
- **No dynamic re-derivation.** Formulas are hand-typed in LaTeX, not auto-extracted from `physics/m*.py`. The coverage test in PR 1 enforces every output key has a curated entry, but that's the only enforcement.
- **No PDF export in v1.** PDF is opt-in for a follow-on PR; v1 ships the Markdown export which preserves enough fidelity for engineers to share via email or the wiki.
- **No glossary expansion via user request.** v1 ships 22 fixed terms; new terms wait for the next PR.

## 14 · Verification

Per PR:

1. `pytest tests/` green at the new count.
2. `pyflakes physics/ ui/ tests/` clean.
3. `mypy --ignore-missing-imports physics/ ui/` clean.
4. Streamlit local run with the `c_uas_1500m` preset:
   - Tab renders without crashing on Simple view, Full view, empty search, search "diff", search "turbulence".
   - Each module section's anchor / quick-jump scroll target works.
   - Glossary expander shows the 22 entries.
   - Each metric's "Value" column matches the same metric's card on its primary tab to within 1e-3 relative tolerance (it should be identical — both pull from the same `result` dict — but the tolerance acknowledges display rounding via `format_value`).
   - LaTeX renders correctly in dark mode AND light mode.
5. Smoke at the infeasible-geometry preset: tab still renders, every row shows `—` for live values that the orchestrator couldn't produce, no crashes.
6. `Download Markdown` button (PR 5 only) produces a file that opens cleanly in any markdown viewer and contains every formula and value.

## 15 · Decisions deferred — answer before PR 1 starts

These six are minor and don't block plan approval, but they need a decision before the first line of code:

| Question | My default if unanswered |
|---|---|
| Should the tab show metrics with no numeric value (categorical / verdict outputs)? | **Yes**, as a "Verdicts" sub-section per module with a different layout (no LaTeX) — see §6.3. |
| Glossary scope: every Greek symbol, or only physics terms? | **Physics terms only** — 22 entries enumerated in §10. Operator symbols (π, √, ·) excluded. |
| Citations as plain text or hyperlinks? | **Plain text** — keeps the air-gap-friendly posture (`ui/theme.py` Google-Fonts comment hints at this requirement). |
| Live values: recompute on math-tab toggle, or trust the existing cached `result`? | **Trust the cache** — `ui/app.py` already caches `run_full_chain`. |
| Should "Full view" expansion remember its state across reruns? | **Yes**, via session-state. Losing it on every rerun would be jarring. |
| Worked example: follows current inputs, or always c_uas_1500m? | **Always c_uas_1500m.** It's a teaching artifact; the user's live values are already in the per-metric "Value" column above. |

## 16 · Open requests of the user

Plan-level questions that I'd want answered before PR 1 lands:

1. **Worked-example preset.** Default is `c_uas_1500m`. If you'd rather the worked example be `counter_rocket_3000m` or `long_range_8000m`, say which.
2. **Sensitivity scope.** §7.4 caches ~44 perturbation runs. Acceptable? The alternative is to show the sensitivity bar only on the "headline" metrics (peak irradiance, tau_BT, NOHD, w_total, S_TB), which would cut the cache to ~10 runs.
3. **PDF export priority.** v1 ships only Markdown export. If you require PDF in v1, I'd promote it from "follow-on" to PR 5 and add `playwright` (~150 lines + a runtime dependency).
4. **Replication-badge asymmetry.** The 🔬 badge applies to ~13 of 41 numeric metrics. Acceptable visual asymmetry, or would you rather we only show the badge as a footnote at the end (less prominent but uniform)?

## 17 · Review log — corrections from the first draft

This plan supersedes the first draft delivered in chat. Twelve issues were caught in a self-review pass before this file was written:

1. **Metric count** corrected from 46 to 45 unique keys (`w_turb` is in both M5 and M7; the merge dedupes it).
2. **Categorical metrics** now have a dedicated handling path (§6.3 + a per-module Verdicts sub-section), not an undefined "verdict sub-section".
3. **Sensitivity scope** corrected from "up to 460 cached runs" to "~44 cached runs" — sensitivity perturbs raw user inputs, not symbolic intermediate dependencies, and the perturbation runs are shared across all metrics that depend on each input.
4. **M8 solver-based metrics** (`tau_BT`, `T_surface_peak`, `E_delivered`) now have an explicit special-case row layout (§6.1) — no attempt to fit a numerical solver into a one-line LaTeX cell.
5. **M6↔M7 iterated values** (`S_TB`, `w_bloom`, `N_D`, `w_total`) now disclose the post-iteration nature inline (§6.2) with a banner and a link to the iteration-count diagnostic.
6. **Streamlit nested-expander rule** respected — module sections are anchored Markdown headers, not expanders; only the per-metric Full view is the (single, top-level) expander (§3, §7.1).
7. **SI-vs-display-unit ambiguity** addressed — every metric row labels the unit explicitly in both the "Metric" column header and the substituted-formula box.
8. **Glossary term list** enumerated explicitly (§10 — 22 terms), not vague.
9. **"What it means" vs glossary** distinction made explicit (§5) with a worked example.
10. **Data-model field names** disambiguated (§9 — `formula_dependencies` vs `sensitivity_inputs`).
11. **LaTeX-validity test** added to `tests/test_math_tab.py` (§8).
12. **File-path drift** addressed (§11) — citations are file-only or file::function, no pinned line numbers.

---

**Plan ready for user approval.** No implementation work has started. Reply with answers to §16 (or "go with defaults") to authorize PR 1.
