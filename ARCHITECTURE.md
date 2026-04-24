# ARCHITECTURE.md — HEL Engineering Calculator

**Version:** 1.9 (Phase 3 UI redesign PR 5: `ui/plots.py` gains six new figure constructors — `plot_overview_dwell_vs_burnthrough`, `plot_target_temperature_envelope`, `plot_target_material_comparison`, `plot_safety_nohd_zones`, `plot_atmosphere_extinction_breakdown`, `plot_atmosphere_transmission_vs_range` — so every tab finally has its plot surface; `ui/outputs.py` renders these plots inside the existing `render_tab_overview / _target_effects / _safety / _atmosphere` entry points and memoizes the M8 material-comparison fan-out with `@st.cache_data`; `ui/app.py` threads the existing `sweep` list into `render_tab_atmosphere`; `ui/labels.py` grows three new `ADVISORY` keys and a `MATERIAL_DISPLAY_NAMES` dict. No physics changes — every new plot consumes already-computed outputs from the existing orchestrator chain.)
**Complements:** `SPEC.md` §6 (file layout) and project plan v0.8 §2.3 (three-layer separation)
**Scope:** Concrete implementation map — file paths, function signatures, import rules, data flow.

**Revision history:**
- v1.9 (2026-04-24) — **Phase 3 UI redesign, PR 5 of six: new plots land on every tab that was previously plotless.** No physics changes, no module I/O changes, no new files. (a) `ui/plots.py` gains six new figure constructors under the same template / modebar / advisory pattern set up in PR 4. `plot_overview_dwell_vs_burnthrough(dwell, tau_bt) -> Figure` renders a grouped vertical-bar comparison (dwell vs burn-through, log-y, margin annotation). `plot_target_temperature_envelope(*, t_amb_c, t_peak_c, t_fail_c, tau_bt, dwell) -> Figure` draws a two-point surface-temperature envelope from `(0, T_amb)` to `(τ_BT, T_surface_peak)` with a horizontal failure-threshold reference and a vertical dwell marker — explicitly labelled as the simplified two-point envelope the physics layer actually reports (M8 does not expose an intermediate `T(t)` trajectory, only scalar `τ_BT` and `T_surface_peak`; the caption cites `ADVISORY["temperature_schematic"]`). `plot_target_material_comparison(*, material_tau_bt, material_labels, current_material, dwell) -> Figure` draws one horizontal bar per tabulated v1 material, tints the currently selected material in `data.a` and the rest in `data.reference`, and renders "no failure before timeout" entries at `max(τ_BT)*1.2` with a flagged label. `plot_safety_nohd_zones(*, nohd_tophat, nohd_gausspeak) -> Figure` draws the three-zone hazard cross-section (inner hazard / caution band / safe) using shaded rectangles and vertical markers at each NOHD value, with the axis extending to `outer * 1.5`. `plot_atmosphere_extinction_breakdown(*, alpha_mol_abs_si, alpha_mol_scat_si, alpha_aer_abs_si, alpha_aer_scat_si) -> Figure` draws a horizontal stacked bar of the four extinction channels with the legend below the chart. `plot_atmosphere_transmission_vs_range(sweep) -> Figure` draws atmospheric transmission τ(L) across the sweep with a horizontal `1/e` reference. All six constructors honor the PR 4 contract: `hel_dark`/`hel_light` template, `PLOTLY_MODEBAR_CONFIG`, advisory-frame branch when inputs are missing / non-finite. (b) `ui/outputs.py` wires the new plots: `render_tab_overview` appends the dwell-vs-burnthrough hero chart under a new `"Engagement margin"` section header; `render_tab_target_effects` is rewritten to emit the temperature envelope and material-comparison plots after the existing metric cards, with a new helper `_material_t_fail(material)` (lazy-imports `MATERIAL_PROPERTIES` from `physics.m8_material_tables`) and a `@st.cache_data(max_entries=32, show_spinner=False)`-wrapped `_material_comparison_cached(key)` that iterates the seven v1 materials through `physics.m8_burnthrough.compute`, mapping `failure_mode == "no_failure_before_timeout"` or `ValueError` to `math.nan` so the plot's always-render-frame branch is never triggered by a per-material failure; `render_tab_safety` appends the NOHD-zones schematic after the existing metric cards and caption; `render_tab_atmosphere` is rewritten to keep the atmospheric-summary cards, drop the previous numeric `st.table` rows, and emit the extinction breakdown followed by transmission-vs-range — it now accepts `*, sweep: list[dict] | None = None` so the transmission curve can consume the same sweep the plot-layer panels already use. (c) `ui/app.py` threads `sweep=sweep` into the `outputs.render_tab_atmosphere(...)` call site; no other `render_tab_*` signature changes. (d) `ui/labels.py` adds three `ADVISORY` keys — `temperature_schematic`, `material_comparison_unavailable`, `no_hazard_data` — and a `MATERIAL_DISPLAY_NAMES` dict mapping the seven SPEC material keys to engineer-legible display names (`anodized_Al → "Anodized aluminium"`, `CFRP → "Carbon-fibre composite"`, etc.). The `__all__` export list grows accordingly. (e) §6.5 `ui/plots.py` entry is rewritten below to list all nine constructors (three from PR 4 + six from PR 5) with final signatures, and the v1.8 trailing "PR 5 adds five new figure constructors" sentence is removed now that PR 5 is the active state. No change to `physics/`, no change to `tests/` (the existing validation suite and `tests/test_copy_style.py` scan list cover the new strings already; the new `ADVISORY` copy and `MATERIAL_DISPLAY_NAMES` values were drafted to pass the forbidden-token lint unchanged). Companion SPEC edits land in `SPEC.md v1.11`.
- v1.0 — initial draft
- v1.1 — post-audit fixes: (a) M9 moved earlier in orchestrator pseudocode to reflect its true independence from the propagation chain; (b) timing estimates in §5.2 explicitly flagged as pre-implementation, to be replaced with Phase 1 benchmark; (c) §6 extended to cover all UI files (added §6.6 orchestrator, §6.7 style, §6.8 __init__); (d) M11 row in §4.2 aligned with SPEC.md v1.1 explicit signature.
- v1.2 — UI alignment with SPEC v1.2: cross-references added so that each of the four UI enhancements added in SPEC v1.2 has a corresponding structural anchor in this document. (a) §6.1 (app.py) now lists URL state encode/decode and the cross-plot hover-sync callback as responsibilities; (b) §6.3 (panels.py) notes default expansion state, emoji iconography, and that initial values come from URL params if present; (c) §6.4 (outputs.py) cross-references the three-tier verdict in SPEC §5.2 Panel 2; (d) §6.5 (plots.py) notes that figures use Plotly `hovermode='x unified'` per SPEC §5.2; (e) §5.1 page-load sequence note added (URL decode happens before panel rendering on first run). No file structure changes, no function-signature changes, no new files. Color constants in §6.7 already aligned (`COLOR_SUCCESS / COLOR_WARNING / COLOR_CAUTION` were defined in v1.0 and are now consumed by SPEC v1.2 verdict logic).
- v1.5 (2026-04-23) — **§5.1 page-load sequence gains an explicit `st.session_state['_url_decoded']` latch** (SPEC v1.7 improvement #1), preventing subsequent Streamlit reruns from re-applying stale URL-parameter values on top of the user's edits. §6.1 (app.py) responsibilities unchanged structurally but the share-URL behavior is now "display in `st.code` block" not "copy to clipboard" per SPEC v1.7 improvement #3. No function-signature, file-layout, or import-rule change.
- v1.4 (2026-04-23) — **cross-plot hover-sync callback removed from §6.1 and §6.5** to match SPEC v1.6. The bespoke Streamlit ↔ Plotly JS callback that would have propagated the hovered x-coordinate across Plots A/B/C is descoped; each plot now relies on Plotly's built-in `hovermode='x unified'` (which was already required by §6.5, so that line is unchanged). §6.1 step 6 (hover-sync wiring) is deleted; step count 1–6 → 1–5. The "Total expected length" for app.py drops from 80–120 to 70–110 lines. §6.5 loses the "lives in `ui/app.py`" trailing sentence about the cross-plot callback. No file changes, no signature changes, no new files. Rationale lives in SPEC v1.6.
- v1.3 (2026-04-23) — **orchestrator relocated from `ui/` to `physics/`.** The chain coordinator is pure Python (no Streamlit imports) and the M6↔M7 fixed-point loop is physics-critical, so it belongs in Layer 1 where `tests/` can import it directly under the §2 import rules. Updates: (a) §3 repo tree moves `orchestrator.py` under `physics/` and drops it from `ui/`; (b) §5.1 step 2 and §5.3 pseudocode headers updated to the new path; (c) §6.1 (app.py) gains a responsibility to wrap `physics.orchestrator.run_full_chain` in `@st.cache_data` (the caching wrapper lives in `app.py` so `orchestrator.py` stays pure); (d) §6.6 deleted, §6.7 renumbered to §6.6, §6.8 renumbered to §6.7; (e) UI layer file count corrected from 8 to 7 (6 functional + 1 `__init__.py`). No function-signature changes, no physics behavior changes. Resolves the self-contradiction in v1.1–1.2 §6.6 which said the orchestrator was "testable without Streamlit running" while §2 forbade `tests/` from importing from `ui/`.
- v1.8 (2026-04-24) — **Phase 3 UI redesign, PR 4 of six: plot theme + always-render chart frames + MATLAB-style interactivity.** No physics changes, no module I/O changes, no new files. (a) `ui/plots.py` rewritten onto the shared `hel_dark` / `hel_light` Plotly template — paper / plot-area backgrounds, gridlines, axes, spike lines, hover-box styling, tick fonts, and default margins all come from `ui.theme` now; figures no longer override any of those. (b) Multi-series data traces use hue + dash + marker-shape dual-encoding (series A: amber / solid / circle; series B: teal / dash / square; series C: purple / dot / diamond) so a viewer with any single color-vision deficiency distinguishes the three series by the remaining two channels. (c) Every constructor accepts `sweep=None` (or an empty list) and returns a frame-only figure with a centered advisory from `ui/labels.ADVISORY` instead of silently failing — "infeasible geometry" for a missing sweep, "no burn-through" when every burn-through time is NaN. The layout slot keeps the same pixel footprint it will when data becomes available. (d) Hover templates use English labels and display units (Peak irradiance, Time to burn-through, Atmospheric transmission, …) rather than SPEC dict keys. (e) `plot_a_on_target_performance` gains an optional `log_y` kwarg; `ui/outputs.py` renders a linear / log radio above the peak-irradiance panel and passes the selection through. (f) `ui/outputs.py` now passes `PLOTLY_MODEBAR_CONFIG` (from `ui.theme`) to every `st.plotly_chart` call — curated modebar (zoom / pan / reset / PNG only), logo stripped, visible on hover, PNG export at 2× DPI. (g) `ui/app.py` reads `session_state["_app_mode"]` before the `theme.apply(...)` bootstrap so the sidebar-footer toggle button (added in PR 4 per the plan's "light-mode toggle in sidebar footer" line) can flip dark / light across reruns — both the app CSS and the registered Plotly template swap in one action. (h) §6.5 `ui/plots.py` entry updated to reflect the new signatures (constructors accept `sweep: list[dict] | None`; Plot A adds `log_y: bool = False`) and the always-render-frame behavior. (i) `tests/test_copy_style.py` extends `SCANNED_FILES` to include `ui/plots.py` (the copy-style lint now covers it) and the scan-list guard is renamed `test_scan_list_covers_phase3_pr4_surface`. No companion `SPEC.md` edit is needed — `§5.3 item 10` ("always-render chart frames on infeasible geometry") was already written behaviorally in v1.9; PR 4 is the implementation. UI layer file count unchanged.
- v1.7 (2026-04-24) — **Phase 3 UI redesign, PR 2 of six: component system + metric-card surface + formatter + status chips.** No physics changes, no module I/O changes, no new files. (a) `ui/components.py` (introduced as a scaffold in v1.6) is now materialized with the six render helpers the rest of PR 2 builds on: `format_value(value, unit, *, sig_figs=3) -> str` (single gate for every number — 3 sig figs default, comma thousands-separator, scientific notation for |v|<0.01 or |v|≥1e5, non-breaking-space before unit, em-dash for non-finite), `metric_card(label, value, unit, *, tooltip, flag_est, size, sig_figs)`, `status_chip(text, severity)` (severity ∈ ok/warn/error/info; hue + Lucide icon + text dual-encoded), `section_header(title, *, icon)`, `skeleton_card(*, height_px, label)`, `footer_strip(spec, arch, build_date)`. (b) `ui/outputs.py` rewritten: every section emits `metric_card(...)` inside `st.columns(...)` cells (12-column grid), SI → display-unit scaling centralized in a single `_DISPLAY_SCALE` dict, inline verdict banner replaced with `status_chip`, section 4 assumption-flag bullet wall replaced with a severity-sorted chip list (`error → warn → info` order; keyword heuristic classifies each flag string without adding fields to `assumptions_flagged`). (c) `ui/style.py` compatibility shim deleted; `ui/plots.py` imports `COLOR_CAUTION / COLOR_PRIMARY / COLOR_REFERENCE / PLOT_HEIGHT_PX` directly from `ui.theme`. UI layer file count 12 → 11 (10 functional + 1 `__init__.py`). (d) §6.9 `ui/components.py` signatures updated to match the implementation (final kwargs, size variants). §6.6 deleted (shim gone); §6.7–§6.12 renumbered down one. Companion SPEC edits: §5.3 items 8–11 restated behaviorally with the final numeric-display and severity rules; §5.2 Overview verdict contract retained unchanged. Released as `SPEC.md v1.10`.
- v1.6 (2026-04-24) — **Phase 3 UI redesign, structural scaffolding for PR 1 of six.** Adds five new UI files and two repo-level additions, and re-shapes the main area from single-scroll to tabbed. (a) §3 repo tree adds `ui/theme.py` (shared palette + CSS + Plotly template + font loader), `ui/components.py` (reusable metric card, status chip, section header, skeleton frame, numeric formatter, footer strip), `ui/labels.py` (single source of truth for SPEC-key → UI-label → tooltip mapping; every user-visible string in `ui/` reads from this file), `ui/icons.py` (Lucide SVG inline helper — ~12 icons bundled, no npm/CDN), and `ui/presets.py` (named scenario dicts driving the sidebar preset dropdown). Also adds `tests/test_copy_style.py` (copy-style lint that fails CI if forbidden tokens — `SPEC §`, `M[0-9]`, `_flagged`, emoji ranges — appear in user-visible `ui/` strings) and `scripts/check_contrast.py` (one-shot WCAG-AA verifier, NOT in CI; run once per palette change) alongside the plan-of-record `docs/phase3_ui_redesign_plan_2026-04-23.md` (reference document). UI layer file count 7 → 12 (11 functional + 1 `__init__.py`); total test files gain `test_copy_style.py` for a total of 13 test files. (b) §5.1 step 3 page-layout description changes from "main area = plots + output panels" to "main area = six tabs (Overview / Engagement / Target effects / Safety / Atmosphere / Diagnostics) + footer provenance strip"; the tabbed structure is a SPEC §5.2 re-mapping of the same five numeric panels and three plots plus three new plots — **no physics, no orchestrator, no module-output-key change**. (c) §6.1 app.py responsibilities gain: load theme via `ui.theme.apply(app_mode: 'dark' | 'light')`; render the footer provenance strip (`HEL Engineering Calculator · SPEC v1.9 · ARCH v1.6 · build YYYY-MM-DD`) on every page; the tab container replaces the single-scroll result flow. App.py line-count budget 70–110 → 100–160 to absorb the tab wiring and theme bootstrap. (d) New §6.8 `ui/theme.py`, §6.9 `ui/components.py`, §6.10 `ui/labels.py`, §6.11 `ui/icons.py`, §6.12 `ui/presets.py`. §6.6 `ui/style.py` is retained as a **compatibility shim** that re-exports `COLOR_SUCCESS / COLOR_WARNING / COLOR_CAUTION / PLOT_HEIGHT_PX` from `ui.theme` so existing `ui/outputs.py` and `ui/plots.py` imports keep working until PR 2 migrates them. (e) §6.5 `ui/plots.py` gains a responsibility line: every figure applies the shared Plotly template from `ui.theme.PLOTLY_TEMPLATE` (which encodes palette, gridline, axis, spike, and hover-box tokens) so one edit re-themes every chart. No function signatures changed for existing plot constructors. **No physics, no module I/O, no `assumptions_flagged` semantics, and no CLAUDE §7.1 formula is touched.** Companion SPEC edits: §5.1 sidebar layout restated behaviorally (preset dropdown + six sections + Run Analysis + Validate button + Share button + light/dark toggle), §5.2 re-mapped to the six tabs with three new plot specifications, §5.3 UI behavior contract extended with the compute-time-feedback, always-render-plot-frame, and copy-style-lint commitments. Released as `SPEC.md v1.9`.

---

## 1. Purpose

Where SPEC.md says *what* each module computes and plan §2.3 says *why* the three layers are separate, this document says *how* the code is organized on disk: which file contains which function, what each function's exact Python signature looks like, what each file is allowed to import, and how data flows end-to-end from a button click in the browser to a number rendered on screen.

Claude Code reads this document when navigating the repository to make changes. A change that would violate an import rule or add a file outside the defined structure requires updating this document first.

---

## 2. Three-Layer Architecture — Concrete Form

The three layers from plan §2.3 are realized as three top-level directories under the repository root:

```
hel-calculator/
├── physics/          ← Layer 1: Physics core (pure functions, no UI, no I/O)
├── tests/            ← Layer 2: Validation suite (imports from physics/ only)
└── ui/               ← Layer 3: Web interface (imports from physics/ only)
```

**Import rules are strict and one-directional:**

| Directory | May import from | May NOT import from |
|---|---|---|
| `physics/` | stdlib, numpy, scipy | `ui/`, `tests/`, anything with side effects |
| `tests/` | `physics/`, pytest, numpy | `ui/` |
| `ui/` | `physics/`, streamlit, plotly, pandas | `tests/` |

A CI check (see §9) verifies these rules automatically on every commit. Any import-rule violation blocks the commit.

---

## 3. Complete Repository Layout

```
hel-calculator/
│
├── README.md                       ← Landing page (shown on GitHub repo home)
├── CLAUDE.md                       ← Rules for Claude Code (read every session)
├── SPEC.md                         ← Implementation contract
├── ARCHITECTURE.md                 ← THIS DOCUMENT
├── TESTING.md                      ← Validation-suite guide
│
├── requirements.txt                ← Pinned Python dependencies
├── .streamlit/
│   └── config.toml                 ← Streamlit configuration (theme, auth)
├── .github/
│   └── workflows/
│       └── test.yml                ← GitHub Actions CI
│
├── physics/                        ← LAYER 1: Physics core
│   ├── __init__.py                 ← Public API exports only
│   ├── m1_laser_source.py          ← M1 module
│   ├── m2_beam_director.py         ← M2 module
│   ├── m3_geometry.py              ← M3 module
│   ├── m4_atmosphere.py            ← M4 module (imports m4_data_tables)
│   ├── m4_data_tables.py           ← α_mol and α_aer tables (constants only)
│   ├── m5_turbulence.py            ← M5 module
│   ├── m6_blooming.py              ← M6 module
│   ├── m7_spot_pib.py              ← M7 module
│   ├── m8_burnthrough.py           ← M8 module (imports m8_material_tables)
│   ├── m8_material_tables.py       ← Material properties and A_λ table
│   ├── m9_nohd.py                  ← M9 module
│   ├── m10_power_thermal.py        ← M10 module
│   ├── m11_validation.py           ← Self-test runner (invokes pytest)
│   ├── orchestrator.py             ← Chain coordinator (M1→M10, M6↔M7 iter); called by ui/app.py
│   └── common.py                   ← Shared helpers (unit conversions, validators)
│
├── tests/                          ← LAYER 2: Validation suite
│   ├── __init__.py
│   ├── conftest.py                 ← pytest fixtures (default parameter sets)
│   ├── test_m1_laser_source.py
│   ├── test_m2_beam_director.py
│   ├── test_m3_geometry.py
│   ├── test_m4_atmosphere.py
│   ├── test_m5_turbulence.py
│   ├── test_m6_blooming.py
│   ├── test_m7_spot_pib.py
│   ├── test_m8_burnthrough.py
│   ├── test_m9_nohd.py
│   ├── test_m10_power_thermal.py
│   ├── test_convention_consistency.py   ← Cross-module structural tests (M7.4)
│   ├── test_import_rules.py             ← Verifies Layer 1 has no UI imports
│   └── test_copy_style.py               ← Copy-style lint: forbidden tokens in user-visible ui/ strings (v1.6)
│
├── ui/                             ← LAYER 3: Streamlit interface
│   ├── __init__.py
│   ├── app.py                      ← Streamlit entry point (run with `streamlit run`)
│   ├── auth.py                     ← Shared-credential login gate
│   ├── panels.py                   ← The 6 input sections (sidebar)
│   ├── outputs.py                  ← Numeric-panel renderers (per-tab)
│   ├── plots.py                    ← Plotly chart constructors (shared template from theme.py)
│   ├── theme.py                    ← Palette + CSS + Plotly template + font loader (v1.6)
│   ├── components.py               ← metric_card / status_chip / section_header / skeleton_card / format_value / footer_strip (v1.6)
│   ├── labels.py                   ← SPEC-key → UI-label → tooltip mapping (single source of truth, v1.6)
│   ├── icons.py                    ← Lucide SVG inline helper (~12 icons bundled, v1.6)
│   └── presets.py                  ← Named scenario dicts for sidebar preset dropdown (v1.6)
│
├── scripts/                        ← One-shot developer utilities (NOT in CI)
│   └── check_contrast.py           ← WCAG-AA verifier for ui/theme.py palette pairs (v1.6)
│
└── docs/                           ← Reference material
    ├── Plan_v0p8.docx              ← The project plan (read-only reference)
    ├── references.md               ← Bibliography (matches SPEC Appendix B)
    ├── phase3_ui_redesign_plan_2026-04-23.md   ← Phase 3 design document (v1.6 reference)
    └── CHANGELOG.md                ← Human-readable version history (optional)
```

**Total files:** roughly 49 (v1.7 — the v1.6 `ui/style.py` compatibility shim was deleted in PR 2), most of them small (one module = one file, one test file per module, one UI file per concern). Every file has a single, clearly named purpose.

---

## 4. Module Function Signatures

Every physics module follows the same function signature pattern, per SPEC.md §2 "Module Interface Contract." This section makes those signatures concrete.

### 4.1 Standard signature pattern

```python
def compute(inputs: dict) -> dict:
    """
    [Module description, one sentence.]

    Inputs (required keys):
      - key_name (unit): description, valid range

    Outputs (returned keys):
      - key_name (unit): description
      - assumptions_flagged (list[str]): active modeling assumptions

    Reference: [citation]
    """
    _validate_inputs(inputs)      # raises ValueError if out-of-range
    # ... computation ...
    return {
        "output_key_1": value_1,
        "output_key_2": value_2,
        "assumptions_flagged": assumptions,
    }


def _validate_inputs(inputs: dict) -> None:
    """Private — raises ValueError with descriptive message if any input is invalid."""
    # check types, check ranges
```

Every module file exports exactly one public function (`compute`) and may have any number of private helpers (prefixed with `_`). The `_validate_inputs` helper is per-module because each module has different valid ranges.

### 4.2 Per-module function signatures

| Module | File | Public function | Returns |
|---|---|---|---|
| M1 | `m1_laser_source.py` | `compute(inputs)` | `theta_diff, w0, zR, I_exit, assumptions_flagged` |
| M2 | `m2_beam_director.py` | `compute(inputs)` | `P_exit, assumptions_flagged` |
| M3 | `m3_geometry.py` | `compute(inputs)` | `R_slant, R_h, elevation_angle, available_dwell, assumptions_flagged` |
| M4 | `m4_atmosphere.py` | `compute(inputs)` | `alpha_atm, tau_atm, alpha_mol_abs, alpha_mol_scat, alpha_aer_abs, alpha_aer_scat, assumptions_flagged` |
| M5 | `m5_turbulence.py` | `compute(inputs)` | `Cn2_integrated, r0_sph, w_turb, assumptions_flagged` |
| M6 | `m6_blooming.py` | `compute(inputs)` | `N_D, S_TB, w_bloom, assumptions_flagged` |
| M7 | `m7_spot_pib.py` | `compute(inputs)` | `w_diff, w_turb, w_jit, w_total, d_spot, I_peak, PIB_fraction, P_aim, I_avg_aim, assumptions_flagged` |
| M8 | `m8_burnthrough.py` | `compute(inputs)` | `tau_BT, T_surface_peak, E_delivered, failure_mode, assumptions_flagged` |
| M9 | `m9_nohd.py` | `compute(inputs)` | `MPE, NOHD_tophat, NOHD_gausspeak, laser_class, assumptions_flagged` |
| M10 | `m10_power_thermal.py` | `compute(inputs)` | `P_in, Q_waste, t_sustain, engagement_viable, duty_cycle_limit, engagements_per_hour, assumptions_flagged` |
| M11 | `m11_validation.py` | `run_validation_suite()` | structured report dict per SPEC M11 (test_id → {status, expected, actual, tolerance, reference, error_message}) |

**Exact input/output keys are specified in SPEC.md §3.** This file keeps the interface surface view; SPEC is the authority on keys.

### 4.3 The `common.py` helpers

```python
# physics/common.py

def validate_positive(value: float, name: str) -> None:
    """Raise ValueError if value is not strictly positive."""

def validate_range(value: float, name: str, lo: float, hi: float) -> None:
    """Raise ValueError if value is outside [lo, hi]."""

def validate_enum(value: str, name: str, allowed: list[str]) -> None:
    """Raise ValueError if value is not in allowed list."""

def wavelength_in_validated_set(wavelength_m: float, tol_nm: float = 5.0) -> bool:
    """True iff wavelength is within tol_nm of {1.06, 1.07, 1.55, 2.05} µm."""

def interp_log_space(x: float, x_table: list[float], y_table: list[float]) -> float:
    """Log-space linear interpolation between tabulated values."""
```

These helpers are imported by every physics module. They are pure functions, no state.

---

## 5. Data Flow — End-to-End

This section traces a single user interaction through the three layers.

### 5.1 User clicks "Run Analysis"

1. `ui/app.py` has registered a Streamlit button. Click handler in `ui/app.py`:
   ```python
   from physics.orchestrator import run_full_chain
   ...
   if st.button("Run Analysis"):
       result = run_full_chain(user_inputs)          # cached wrapper in app.py per §5.3
       outputs.render_all(result)
   ```

2. `physics/orchestrator.py` has a single public function:
   ```python
   def run_full_chain(user_inputs: dict) -> dict:
       """
       Executes M1 → M9 (independent branch) and M1 → M2 → M3 → M4 → M5
       → [M6 ↔ M7 iter] → M8 → M10 (propagation+lethality chain).
       M9 depends only on M1, so it is executed early; order of M9 vs downstream
       modules is not functionally significant in single-threaded Python.
       Returns a single dict with all module outputs merged.
       """
   ```

3. Inside `run_full_chain`:
   ```python
   from physics import (m1_laser_source, m2_beam_director, m3_geometry,
                        m4_atmosphere, m5_turbulence, m6_blooming,
                        m7_spot_pib, m8_burnthrough, m9_nohd, m10_power_thermal)

   out1 = m1_laser_source.compute(inputs_for_m1(user_inputs))
   out9 = m9_nohd.compute(inputs_for_m9(user_inputs, out1))    # independent of propagation chain (only needs M1)
   out2 = m2_beam_director.compute(inputs_for_m2(user_inputs, out1))
   out3 = m3_geometry.compute(inputs_for_m3(user_inputs))
   out4 = m4_atmosphere.compute(inputs_for_m4(user_inputs, out1, out3))
   out5 = m5_turbulence.compute(inputs_for_m5(user_inputs, out1, out3))
   out7, out6 = _iterate_m6_m7(user_inputs, out1, out2, out3, out4, out5)
   out8 = m8_burnthrough.compute(inputs_for_m8(user_inputs, out7))
   out10 = m10_power_thermal.compute(inputs_for_m10(user_inputs, out1, out8))

   return {**out1, **out2, **out3, **out4, **out5, **out6, **out7, **out8, **out9, **out10}
   ```

4. The `_iterate_m6_m7` helper handles the fixed-point loop:
   ```python
   def _iterate_m6_m7(user_inputs, out1, out2, out3, out4, out5,
                     max_iter=10, tol=0.01):
       """
       Starting with S_TB=1, w_bloom=0, alternate M6↔M7 until w_total converges.
       """
       S_TB, w_bloom = 1.0, 0.0
       w_total_prev = None
       for i in range(max_iter):
           out7 = m7_spot_pib.compute(_build_m7_inputs(..., S_TB, w_bloom))
           out6 = m6_blooming.compute(_build_m6_inputs(..., out7['w_total']))
           S_TB, w_bloom = out6['S_TB'], out6['w_bloom']
           if w_total_prev is not None:
               if abs(out7['w_total'] - w_total_prev) / w_total_prev < tol:
                   break
           w_total_prev = out7['w_total']
       else:
           out6['assumptions_flagged'].append("blooming iteration did not converge")
       return out7, out6
   ```

5. Result dict flows to `ui/outputs.py` and `ui/plots.py`. **Since v1.6** the main area is a `st.tabs([...])` container with six tabs in reading order — **Overview / Engagement / Target effects / Safety / Atmosphere / Diagnostics** (per SPEC v1.9 §5.2). `ui/outputs.py` provides per-tab renderers; `ui/plots.py` provides the Plotly figures each tab embeds. The same merged-result dict is passed to every tab; tabs render independently and without cross-tab callbacks. A footer provenance strip (`HEL Engineering Calculator · SPEC v1.9 · ARCH v1.6 · build YYYY-MM-DD`) rendered by `ui.components.footer_strip()` sits below the tab container on every page — that is where the version provenance that previously lived in the page subtitle now resides.

**Page-load sequence (first run, before any user click):** before §5.1 step 1 above can apply, `ui/app.py` performs URL-parameter decoding **exactly once per Streamlit session**, guarded by the `st.session_state['_url_decoded']` latch (per SPEC §5.3 item 7, v1.7). If `st.query_params` is non-empty and the latch is unset, each parameter is parsed, range-checked against the SPEC §5.1 sanity ranges, and either accepted (becoming the panel's initial value) or silently dropped with a flag added to the assumptions panel ("Input X out of range from URL, using default"). If `st.query_params` is empty, all panels initialize from the SPEC §5.1 defaults. After decoding (or on the first-load skip), `st.session_state['_url_decoded']` is set to `True` so subsequent reruns triggered by widget edits do not re-apply the now-stale URL values on top of the user's changes. Only after this initialization do the panel widgets render in the sidebar.

### 5.2 Timing characteristics (estimates pending Phase 1 benchmark)

The numbers in this section are pre-implementation estimates based on typical numpy/scipy performance; they will be replaced with measured values during Phase 1 once the modules are implemented and benchmarked. For a single-point evaluation at one range, the full chain is estimated to run in approximately 50–200 ms (dominated by M8's finite-difference heat solver). For a sweep across 50 range points (Plots A, B, C), this is estimated at 2.5–10 seconds total. If actual measured values fall far outside these estimates (e.g., sweep takes >30 s), it is a signal that either (a) M8's spatial or temporal discretization is too fine, or (b) the orchestrator is redundantly recomputing modules that could be cached. Streamlit's `@st.cache_data` decorator wraps the orchestrator call so that changing only the plot's reference-range slider does not trigger recomputation — only changing Panel A–F inputs does.

### 5.3 Caching strategy

The caching wrappers live in `ui/app.py` (not in `physics/orchestrator.py`) so the orchestrator stays pure Python — no Streamlit import, directly unit-testable from `tests/`.

```python
# ui/app.py — caching wrappers around physics.orchestrator
from physics.orchestrator import run_full_chain


@st.cache_data(max_entries=50)
def run_full_chain_cached(user_inputs_tuple):
    """
    Streamlit caches by input. Inputs must be hashable → convert dict to tuple.
    Changing any input key invalidates the cache; Streamlit handles this.
    """
    return run_full_chain(dict(user_inputs_tuple))


@st.cache_data(max_entries=10)
def run_sweep_cached(user_inputs_tuple, range_array_tuple):
    """
    Sweep computation across R values for plots. Cached separately.
    """
    return [run_full_chain({**dict(user_inputs_tuple), 'R': R})
            for R in range_array_tuple]
```

M11's validation suite is NOT cached — it should re-run on demand every time the user clicks the "Run Validation Suite" button, so that any environment-sensitive failure surfaces.

---

## 6. UI Layer Structure

### 6.1 `ui/app.py` — entry point

The one file Streamlit Cloud runs with `streamlit run ui/app.py`. Responsibilities:

1. Apply the app-wide theme via `ui.theme.apply(app_mode)` immediately after `st.set_page_config` (v1.6). The theme module injects the palette CSS, loads the Inter + JetBrains Mono font stack, and registers the shared Plotly template that every figure in `ui/plots.py` consumes. `app_mode` defaults to `'dark'` and is toggled by a sidebar footer control (per SPEC §5.2, §5.3 item 8).
2. Check authentication (`ui/auth.py`).
3. On first page load, decode any `st.query_params` present in the URL into an initial input dict (per SPEC §5.3 item 1); fall back to defaults for missing or malformed parameters and flag any out-of-range values for the diagnostics tab. Guard the decode with `st.session_state['_url_decoded']` so it runs exactly once per session (per SPEC v1.7 improvement #1).
4. Lay out the page: **left sidebar** = preset dropdown (`ui.presets`) + six input sections (`ui.panels`) + "Run Analysis" button + "Validate" button + "Share this analysis" button + light/dark toggle; **main area** = `st.tabs([...])` with six tabs in SPEC §5.2 order (Overview / Engagement / Target effects / Safety / Atmosphere / Diagnostics); **footer** = a single-line provenance strip rendered by `ui.components.footer_strip()`.
5. Wire up the "Run Analysis" button and per-tab result rendering; the click handler calls `physics.orchestrator.run_full_chain` via the `@st.cache_data`-wrapped helpers defined in §5.3 — the wrappers live in `app.py` (not in `orchestrator.py`) so the orchestrator stays pure Python and directly testable from `tests/`. The button wires the SPEC §5.3 item 9 compute-time-feedback sequence (button-disable pulse → thin progress bar → fade-in) via `ui.components.progress_bar()`.
6. Wire up the "Share this analysis" sidebar button (per SPEC §5.3 item 7) which encodes the current input dict to `st.query_params` and renders the resulting URL in an `st.code(url)` block for manual copy (per SPEC v1.7 improvement #3).

Total expected length: 100–160 lines (v1.6; expanded from 70–110 to absorb theme bootstrap, tab container wiring, and footer strip).

### 6.2 `ui/auth.py` — login gate

Uses Streamlit's secrets management to check a shared username/password pair. Credentials live in Streamlit Cloud's web UI as secrets (not in code, never committed to git). If wrong credentials, show a login form and halt. Total: ~30 lines.

### 6.3 `ui/panels.py` — input panels

One function per panel, each returning a dict of that panel's inputs:

```python
def panel_a_laser_source() -> dict:
    """Panel A: laser output, beam quality, aperture, wavelength."""

def panel_b_beam_director() -> dict: ...
def panel_c_geometry() -> dict: ...
def panel_d_atmosphere() -> dict: ...
def panel_e_aimpoint_material() -> dict: ...
def panel_f_resources_safety() -> dict: ...

def collect_all() -> dict:
    """Calls all panel functions and returns merged user_inputs dict."""
```

All six panels are Streamlit `st.expander` widgets in the sidebar. Per SPEC §5.1 (v1.9), each expander's label is a plain-English section name with no emoji: "Laser source", "Beam director", "Engagement geometry", "Atmosphere", "Target & aimpoint", "System resources". Default expansion state on first load is **Laser source, Engagement geometry, Target & aimpoint expanded; Beam director, Atmosphere, System resources collapsed** — the same first/third/fifth-open pattern as v1.2 but keyed off the new section names. Each input is a `st.number_input` or `st.selectbox` with explicit min/max matching SPEC sanity ranges; **every input's visible label and tooltip are read from `ui.labels`** (v1.6) — no user-visible string is hard-coded inside `panels.py`. Initial values for each input come from the URL-decoded dict produced by `ui/app.py` on page load (per SPEC §5.3 item 1) when present, otherwise from the defaults in SPEC.md §5.1 or from a preset selected via the sidebar preset dropdown (`ui.presets`).

### 6.4 `ui/outputs.py` — numeric panels

```python
def render_panel_1_spot_strehl(result: dict, reference_range: float) -> None:
    """Panel 1: spot broadening + Strehl decomposition at selected range."""

def render_panel_2_engagement(result: dict) -> None: ...
def render_panel_3_feasibility(result: dict) -> None: ...
def render_panel_4_assumptions(result: dict) -> None: ...
def render_panel_5_atmosphere_breakdown(result: dict) -> None: ...

def render_all(result: dict, reference_range: float) -> None:
    """Renders all 5 panels in sequence."""
```

`render_panel_2_engagement` implements the three-tier verdict (ENGAGEABLE / MARGINAL / NOT ENGAGEABLE) per SPEC §5.2 Panel 2, using the status-token palette from `ui.theme` (green / amber / red) for the verdict chip. **Since v1.6** the verdict is rendered via `ui.components.status_chip(...)` (hue + Lucide icon + text — color-blind dual-encoded), not the v1.5 inline-HTML banner. **Every label and caption emitted by these panel functions is read from `ui.labels`**; no user-visible string is hard-coded inside `outputs.py`. Function signatures are unchanged from v1.1; what changes in v1.6 is the rendering idiom (metric cards via `ui.components.metric_card`) and the per-tab dispatch: `render_all(result, reference_range)` is replaced by six per-tab functions called by the tab container in `ui/app.py`. The existing `render_panel_N_*` functions continue to exist during PR 1 as internal helpers; PR 2 rewrites them to emit metric cards.

### 6.5 `ui/plots.py` — Plotly constructors

```python
# Plot-layer panels (PR 4 — sweep-driven, slant-range x-axis)
def plot_a_on_target_performance(
    sweep: list[dict] | None,
    *,
    log_y: bool = False,
) -> plotly.graph_objects.Figure:
    """Peak irradiance and aimpoint-throughput curves vs slant range."""

def plot_b_time_to_burnthrough(
    sweep: list[dict] | None,
) -> plotly.graph_objects.Figure: ...

def plot_c_beam_diameter_breakdown(
    sweep: list[dict] | None,
) -> plotly.graph_objects.Figure: ...


# Overview tab (PR 5)
def plot_overview_dwell_vs_burnthrough(
    dwell: float | None,
    tau_bt: float | None,
) -> plotly.graph_objects.Figure:
    """Grouped-bar comparison of dwell vs time-to-burn-through, log-y."""


# Target-effects tab (PR 5)
def plot_target_temperature_envelope(
    *,
    t_amb_c: float | None,
    t_peak_c: float | None,
    t_fail_c: float | None,
    tau_bt: float | None,
    dwell: float | None,
) -> plotly.graph_objects.Figure:
    """Two-point simplified surface-temperature envelope with threshold line."""

def plot_target_material_comparison(
    *,
    material_tau_bt: dict[str, float],
    material_labels: dict[str, str],
    current_material: str,
    dwell: float | None,
) -> plotly.graph_objects.Figure:
    """Horizontal bar chart of burn-through time across the v1 material set."""


# Safety tab (PR 5)
def plot_safety_nohd_zones(
    *,
    nohd_tophat: float | None,
    nohd_gausspeak: float | None,
) -> plotly.graph_objects.Figure:
    """Hazard-zone cross-section with shaded bands and NOHD markers."""


# Atmosphere tab (PR 5)
def plot_atmosphere_extinction_breakdown(
    *,
    alpha_mol_abs_si: float | None,
    alpha_mol_scat_si: float | None,
    alpha_aer_abs_si: float | None,
    alpha_aer_scat_si: float | None,
) -> plotly.graph_objects.Figure:
    """Horizontal stacked bar of the four extinction channels."""

def plot_atmosphere_transmission_vs_range(
    sweep: list[dict] | None,
) -> plotly.graph_objects.Figure:
    """Atmospheric transmission τ(L) across the range sweep with 1/e reference."""
```

Each returns a Plotly `Figure` object that `ui/outputs.py` passes to `st.plotly_chart`. No global state; pure constructors. Per SPEC §5.2, each figure sets `hovermode='x unified'` (or `'closest'` for the horizontal-bar / cross-section constructors where a unified-per-x hover does not apply) and populates hover tooltips with the per-plot content specified there. Cross-plot hover synchronization was considered for v1 but descoped in SPEC v1.6 / ARCH v1.4 — each plot's unified hover is entirely self-contained within its Plotly figure and no app-level callback is required.

**Shared Plotly template (v1.6 → v1.8).** Every figure picks up the template registered in `ui/theme.py` under the name `hel_dark` / `hel_light` and set as default by `ui.theme.apply(app_mode)`. The template encodes paper background, plot-area background, gridline colors and widths, axis lines, spike-line styling (both axes, `spikedash='dot'`, `spikemode='across'`, `spikesnap='cursor'`), hover-label styling, tabular-nums tick fonts, legend placement (top-right inside the frame), and default margins `l=56, r=32, t=40, b=48`. Plot constructors in v1.8 do **not** override any of those — they rely on the template for every visual property that is not specific to the individual chart. One edit in `ui/theme.py` re-themes every chart in the app.

**Always-render chart frames (v1.8).** Each constructor accepts `sweep=None` (or an empty list) and returns a frame-only figure with a centered advisory annotation from `ui/labels.ADVISORY` — "infeasible geometry" for a missing sweep, "no burn-through" when every burn-through time is NaN — instead of silently failing. The axes are still drawn (titles retained, tick labels hidden, spike lines suppressed in the empty-frame branch) so the layout slot reserves the same pixel footprint it will when real data becomes available. This implements SPEC §5.3 item 10 ("no silent plot skip on infeasible geometry").

**Color-blind dual-encoding (v1.8).** Multi-series data traces combine three visual channels: hue + dash pattern + marker shape. Series A uses the amber `data.a` palette token with `dash="solid"` and circle markers; series B uses teal `data.b` with `dash="dash"` and square markers; series C uses purple `data.c` with `dash="dot"` and diamond markers. A viewer with any single dichromatic color-vision deficiency distinguishes the three series by the remaining two channels. Supporting reference curves (diffraction limit, atmospheric transmission, jitter contribution) use the `data.reference` gray with distinct dash patterns so they read as "reference" rather than "fourth data series".

**Curated modebar (v1.8).** `ui/outputs.py` passes `config=ui.theme.PLOTLY_MODEBAR_CONFIG` to every `st.plotly_chart` call. The config keeps `zoom / pan / zoom-in / zoom-out / reset / PNG export` and drops `lasso / select / spike-toggle / auto-scale` (spikes always on; auto-scale is redundant with reset). The Plotly logo is stripped. `displayModeBar="hover"` makes the bar visible on chart hover only so the chart at rest is uncluttered. `toImageButtonOptions` bakes the PNG export at `scale=2` (2× DPI) with the current theme already applied.

**Log / linear toggle (v1.8).** `plot_a_on_target_performance` accepts an optional `log_y: bool = False` keyword; `ui/outputs.py` renders a small horizontal `st.radio` above the peak-irradiance panel and threads the selection through. The toggle sits outside the modebar so it is visible by default — an engineer-legible control rather than a hidden preference. PR 5 will add similar toggles above the extinction-breakdown and transmission-vs-range plots as those constructors land.

**PR 5 plots (v1.9).** The six new constructors above follow the same contract as the PR 4 plot-layer panels: shared template, `PLOTLY_MODEBAR_CONFIG` modebar, centered `ui/labels.ADVISORY` text in an empty-frame branch when inputs are missing or non-finite, hue + dash + marker-shape dual-encoding on any multi-series trace, and fixed heights from `ui.theme.PLOT_HEIGHTS`. `plot_target_temperature_envelope` is deliberately a two-point envelope (ambient → peak at τ_BT), not a solver-produced T(t) trajectory — the physics layer's M8 module exposes only scalar `τ_BT` and `T_surface_peak`, and the envelope is captioned under `ADVISORY["temperature_schematic"]` so the simplification is visible to the user. `plot_target_material_comparison` consumes a pre-computed `{material_key: τ_BT}` dict assembled and memoized in `ui/outputs.py` (the fan-out calls `physics.m8_burnthrough.compute(...)` once per v1 material; the helper is wrapped in `@st.cache_data(max_entries=32, show_spinner=False)` with a hashable input tuple so seven M8 solves do not re-run on every Streamlit rerun). `plot_safety_nohd_zones` sizes its x-axis to `outer * 1.5` where `outer` is the larger of the top-hat and Gaussian-peak NOHD values.

### 6.6 `ui/__init__.py`

Empty (by convention) — marks `ui/` as a Python package. No exports at the package level; all code is reached via explicit module imports (`from ui import app`, `from ui.panels import collect_all`, etc.). Cross-layer imports follow the same idiom: `from physics.orchestrator import run_full_chain`.

### 6.7 `ui/theme.py` — shared visual tokens, CSS, Plotly template (v1.7)

Single source of truth for every visual token used in the app. Exports:

- **`PALETTE_DARK` / `PALETTE_LIGHT`** — dict of token → hex for every surface, foreground, accent, status, and plot-only token (`bg.base`, `bg.surface`, `fg.primary`, `fg.secondary`, `accent.primary`, `status.ok`, `plot.gridline`, etc., per Phase 3 plan §3).
- **`COLOR_PRIMARY / COLOR_REFERENCE / COLOR_SUCCESS / COLOR_WARNING / COLOR_CAUTION / PLOT_HEIGHT_PX`** — legacy names consumed by `ui/plots.py`. These are canonical public names (not shim exports) in v1.7; the short `ui/style.py` re-export path shipped in v1.6 was deleted when PR 2 migrated `ui/plots.py` to import them directly from `ui.theme`.
- **`PLOT_HEIGHTS`** — dict of named plot sizes (`default: 360`, `hero: 420`, `paired: 320`, `cross-section: 280`) so each tab's figure picks a fixed height and the layout does not jump during the loading transition.
- **`PLOTLY_TEMPLATE_DARK` / `PLOTLY_TEMPLATE_LIGHT` / `PLOTLY_TEMPLATE`** — `plotly.graph_objects.layout.Template` presets with paper bg, plot-area bg, gridlines, axes, spike lines, hover-box styling, tabular-nums tick labels, and default margins (`l=56, r=32, t=40, b=48`). `PLOTLY_TEMPLATE` is a back-compat alias for `PLOTLY_TEMPLATE_DARK`.
- **`PLOTLY_MODEBAR_CONFIG`** — the `config=` dict passed to `st.plotly_chart` to keep only `zoom2d / pan2d / zoomIn2d / zoomOut2d / resetScale2d / toImage`, strip the Plotly logo, set `displayModeBar='hover'` so the modebar appears only on chart hover, and set `modeBarButtonsToRemove=['lasso2d','select2d','toggleSpikelines','autoScale2d']`. PNG exports at 2× DPI.
- **`apply(app_mode: Literal['dark', 'light'] = 'dark') -> None`** — the bootstrap call made once by `ui/app.py`. Injects the CSS for Inter + JetBrains Mono font loading, the palette custom properties, the card / chip / section-header / focus-ring / scrollbar / skeleton-pulse / chip-list / card-label / card-value / card-unit / card-est rules, and the `prefers-reduced-motion` overrides. Registers the matching Plotly template under the `hel_dark` / `hel_light` name and sets it as the default via `plotly.io.templates.default`.

No logic beyond palette tables, template construction, and CSS string injection. Imports: `streamlit`, `plotly.graph_objects`, `plotly.io`. No imports from elsewhere in `ui/`.

### 6.8 `ui/components.py` — reusable UI primitives (v1.7)

Small, pure render helpers used by `ui/outputs.py`, `ui/panels.py`, and `ui/app.py`. Materialized in PR 2 with these signatures:

```python
def format_value(
    value: float | int | None,
    unit: str = "",
    *,
    sig_figs: int = 3,
) -> str:
    """Single gate for every number on screen. 3 sig figs default; scientific
    notation when |v| < 0.01 or |v| >= 1e5 (Unicode `×` + superscript digits);
    comma thousands-separator at magnitudes >= 1000; non-breaking space before
    the unit; em-dash (—) for None / NaN / inf.
    """

def metric_card(
    label: str,
    value: float | int | str | None,
    unit: str = "",
    *,
    tooltip: str | None = None,
    flag_est: bool = False,
    size: Literal["lg", "md"] = "lg",
    sig_figs: int = 3,
) -> None:
    """KPI card: big tabular-nums value + label + unit; optional tooltip (rendered
    as the card's title attribute) and optional 'est.' superscript linking to
    #diagnostics for HIGH UNCERTAINTY values (SPEC §10). `value` may be a
    pre-formatted string (material name, laser class) — routed through without
    format_value / unit append. `size='md'` drops the value font size 28px → 20px.
    """

def status_chip(text: str, severity: Literal["ok", "warn", "error", "info"]) -> None:
    """Hue + Lucide icon + text. Icon is check-circle / alert-triangle / x-circle /
    info respectively — color-blind triple-encoding means a viewer can still read
    the severity from the icon and the written label with the hue removed.
    """

def section_header(title: str, *, icon: str | None = None) -> None:
    """h3-styled section title for use inside a tab. Optional Lucide icon rendered
    16px left of the title in accent.primary.
    """

def skeleton_card(*, height_px: int = 88, label: str = "Pending first run") -> None:
    """Placeholder card rendered before first Run Analysis. Same silhouette as a
    real metric card with a soft pulsing gradient; prefers-reduced-motion
    shortens the pulse to the 50ms floor.
    """

def footer_strip(spec_version: str, arch_version: str, build_date: str) -> None:
    """One-line provenance strip rendered on every page. Reads the one-line
    template from `ui.labels.FOOTER_TEMPLATE` and wraps it in `.hel-footer`.
    """
```

Imports: `streamlit`, `ui.icons`, `ui.labels` (inside `footer_strip` only, to keep the module boundary cheap). No physics imports. `progress_bar` (v1.6 draft) is deferred to PR 3 where the compute-time-feedback sequence actually wires it.

### 6.9 `ui/labels.py` — single source of truth for user-visible strings (v1.6)

Two dicts:

```python
INPUT_LABELS: dict[str, dict] = {
    # "<input_key>": {"label": "<3–5 word title>", "tooltip": "<1 sentence>", "unit": "<ui unit symbol>"}
}
OUTPUT_LABELS: dict[str, dict] = {
    # "<result_key>": {"label": "...", "tooltip": "...", "unit": "..."}
}
```

Every label used in `ui/panels.py` and `ui/outputs.py` is looked up here — no user-visible string is hard-coded anywhere else in `ui/`. The `tests/test_copy_style.py` lint enforces this by grepping the other `ui/` files for forbidden tokens (`SPEC §`, `M[0-9]`, `_flagged`, emoji ranges, raw SPEC input keys like `θ_diff_pure`). `ui/labels.py` itself is exempt from the lint.

### 6.10 `ui/icons.py` — Lucide SVG inline helper (v1.6)

Tiny helper module that returns inline SVG markup for the ~12 Lucide icons actually used in the app (`check-circle`, `alert-triangle`, `x-circle`, `info`, `layout-dashboard`, `target`, `flame`, `shield`, `cloud`, `activity`, `chevron-down`, `sun-moon`). Each icon is a string constant containing the Lucide SVG path; `icon(name, size=16, stroke=1.5)` wraps it with the requested attributes and an `aria-hidden="true"` so screen readers skip decorative instances. For icon-only interactive controls the caller supplies an `aria-label` on the surrounding button. No network fetch, no npm, no runtime dependency on the Lucide package.

### 6.11 `ui/presets.py` — named scenario dicts (v1.6)

```python
PRESETS: dict[str, dict] = {
    "C-UAS short range":         {...},   # defaults tuned for the SPEC canonical 3 kW / 1.5 km case
    "Counter-rocket":            {...},
    "Long-range surveillance":   {...},
    "Custom":                    {...},   # equal to SPEC §5.1 defaults
}
```

The sidebar preset dropdown writes the selected dict into `st.session_state` and reruns; each input widget reads its initial value from `st.session_state` if present. No physics, no computation — this is a shorthand for common input configurations.

**UI layer total: 12 files** (11 functional + 1 `__init__.py`).

---

## 7. Data Tables (Constants)

Two files hold large constant tables to keep the module files focused on logic:

### 7.1 `physics/m4_data_tables.py`

```python
# α_mol absorption and scattering coefficients
# Sea-level, mid-latitude summer, 60% RH baseline
# HIGH UNCERTAINTY — engineering placeholders; refine against HITRAN/MODTRAN before v1.0

ALPHA_MOL_ABSORPTION_1_PER_KM = {
    1.06e-6: 0.045,
    1.07e-6: 0.065,
    1.55e-6: 0.190,
    2.05e-6: 0.490,
}

ALPHA_MOL_SCATTERING_1_PER_KM = {
    1.06e-6: 0.005,
    1.07e-6: 0.005,
    1.55e-6: 0.010,
    2.05e-6: 0.010,
}

VALIDATED_WAVELENGTHS_M = (1.06e-6, 1.07e-6, 1.55e-6, 2.05e-6)
```

### 7.2 `physics/m8_material_tables.py`

```python
# Material properties per SPEC.md §3 M8 table
# HIGH UNCERTAINTY on A_λ values — should be overridden with measured data

MATERIAL_PROPERTIES = {
    'anodized_Al':   {'rho': 2700, 'c_p': 900,  'k': 200.0, 'T_fail': 933, 'L_f': 397e3, 'mode': 'melt'},
    'CFRP':          {'rho': 1600, 'c_p': 1000, 'k': 7.0,   'T_fail': 600, 'L_f': None,  'mode': 'decomposition'},
    'GFRP':          {'rho': 1900, 'c_p': 800,  'k': 0.4,   'T_fail': 600, 'L_f': None,  'mode': 'decomposition'},
    'polycarbonate': {'rho': 1200, 'c_p': 1200, 'k': 0.2,   'T_fail': 700, 'L_f': None,  'mode': 'decomposition'},
    'ABS':           {'rho': 1050, 'c_p': 1400, 'k': 0.17,  'T_fail': 670, 'L_f': None,  'mode': 'decomposition'},
    'EPP_foam':      {'rho': 30,   'c_p': 1900, 'k': 0.04,  'T_fail': 620, 'L_f': None,  'mode': 'decomposition'},
    'LiPo':          {'rho': 1800, 'c_p': 1000, 'k': 0.5,   'T_fail': 420, 'L_f': None,  'mode': 'vent'},
}

A_LAMBDA_TABLE = {
    # Keyed by (material, wavelength_m)
    ('anodized_Al',   1.06e-6): 0.30, ('anodized_Al',   1.07e-6): 0.30,
    ('anodized_Al',   1.55e-6): 0.25, ('anodized_Al',   2.05e-6): 0.20,
    ('CFRP',          1.06e-6): 0.85, ('CFRP',          1.07e-6): 0.85,
    ('CFRP',          1.55e-6): 0.85, ('CFRP',          2.05e-6): 0.85,
    # ... remaining 20 entries per SPEC.md §3 M8 A_λ table
}
```

Data tables are module constants (uppercase names), not functions. They are imported read-only by their parent module and never mutated.

---

## 8. Testing Layer Structure

### 8.1 One test file per physics module

`tests/test_mX_<module>.py` mirrors `physics/mX_<module>.py`. Each test file implements the validation cases listed in SPEC.md §3 for that module. Function names match SPEC: e.g., `test_m1_divergence`, `test_m7_typical_c_uas_1500m`.

### 8.2 `tests/conftest.py` — shared fixtures

```python
import pytest

@pytest.fixture
def canonical_inputs():
    """SPEC-default parameter set used across multiple tests."""
    return {
        'P0': 3000, 'M2': 1.2, 'D': 0.10, 'wavelength': 1.07e-6,
        # ... all other Panel A–F defaults from SPEC §5.1
    }
```

### 8.3 Cross-module structural tests

- `test_convention_consistency.py` — SPEC M7.4: verifies that PIB computed via w-convention equals PIB via σ-convention with σ=w/2; verifies I_peak=2P/(πw²)=P/(2πσ²) consistency. This is the structural guard against convention-mixing bugs (the class of error that caused plan v0.3/v0.4 fixes).

- `test_import_rules.py` — verifies that no file under `physics/` imports anything from `ui/` or `tests/`. Runs via ast parsing of each .py file under physics/. Fails fast if the three-layer separation is violated.

### 8.4 Tolerance conventions

Tolerances are per SPEC.md §3 per test. Summary:

- **Structural (exact)**: 0% — integer counts, enum values, presence/absence checks
- **Tight (0.1%)**: arithmetic, closed-form formulas, geometry
- **Normal (1–2%)**: first-principles physics computations
- **Loose (5–25%)**: engineering-model tests where model uncertainty dominates (M4 atmosphere, M8 burn-through)
- **Structural-only (no numerical tolerance)**: dimensional checks, limit behavior (e.g., low-power limit of M6)

---

## 9. CI Configuration

### 9.1 `.github/workflows/test.yml`

```yaml
name: Validation Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v --tb=short
      - run: python -c "from tests import test_import_rules; test_import_rules.check()"
```

### 9.2 What CI enforces

- All 29 validation tests pass within stated tolerances (SPEC M11 inventory)
- Import rules upheld (physics/ has no ui/ imports; ui/ has no tests/ imports)
- Python 3.11 compatibility
- Dependency pins resolve cleanly

CI runs in ~2–3 minutes. A failing CI status is visible in the GitHub UI and is treated by Claude Code as a block on claiming a commit "done."

### 9.3 What CI does NOT do

- Deploy to Streamlit Cloud (Streamlit Cloud watches the main branch independently and deploys on push regardless)
- Run performance benchmarks (not needed for v1)
- Generate documentation (docs are hand-maintained markdown files, not autogenerated)
- Security scans (not applicable for this project's threat model)

---

## 10. Deployment Architecture

### 10.1 Streamlit Cloud configuration

Streamlit Cloud connects to the GitHub repository via its web dashboard (configured once, by Claude Code, during Phase 1). The relevant settings:

| Setting | Value |
|---|---|
| Repository | `hel-calculator` (private) |
| Branch | `main` |
| Main file path | `ui/app.py` |
| Python version | `3.11` |
| Secrets | `APP_USERNAME`, `APP_PASSWORD` (set via Streamlit dashboard) |

### 10.2 `.streamlit/config.toml`

```toml
[server]
headless = true

[theme]
primaryColor = "#1f4e79"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f5f5f5"
textColor = "#1a1a1a"
```

No personal identification, no branding, no third-party tracking. The theme is chosen to be readable and neutral.

### 10.3 Secrets handling

Never committed to git:
- Streamlit shared credentials (`APP_USERNAME`, `APP_PASSWORD`) live only in Streamlit Cloud's dashboard
- No API keys needed (no external services called at runtime)
- No user data persisted (every session is independent; nothing stored)

### 10.4 Update cycle

1. Claude Code commits a change to `main` branch of the GitHub repo.
2. GitHub Actions CI runs. If tests fail, the commit is flagged but Streamlit Cloud still deploys (Claude Code treats CI failure as a block and reverts if needed).
3. Streamlit Cloud detects the push, rebuilds the container (~30–60 seconds), and redeploys.
4. User refreshes the browser tab; new version is live.

Rollback, if ever needed: `git revert` the bad commit and push. Streamlit Cloud auto-redeploys the reverted state in the same ~60 seconds. Maintained as release tags in Git so any prior version can be restored by tag name.

---

## 11. What Does Not Exist in v1

Per plan §10.2 and SPEC §10, the following are deliberately out of scope:

- No database (every session starts from defaults; no persistence)
- No user accounts (shared credentials only)
- No role-based access control
- No telemetry or analytics
- No error-tracking service integration (Streamlit's built-in logs only; Sentry optional for later)
- No auto-generated documentation (hand-maintained Markdown)
- No API endpoint for programmatic access (UI-only)
- No mobile-specific layout (Streamlit's default responsive design is sufficient)

These are "not yet" items rather than "never" items. Adding any of them is a SPEC update plus a new phase, not a v1 task.

---

## 12. Change-Management Rules

When Claude Code needs to make a change that would alter anything in this document — a new module, a new file, a different import rule, a different function signature — the procedure is:

1. Update ARCHITECTURE.md first, with a dated note describing the change and rationale.
2. Get user approval on the ARCHITECTURE change.
3. Update SPEC.md if the interface (input/output keys) changes.
4. Implement the code change.
5. Update tests.

Do not make silent architectural changes in code. The architecture is the contract between layers; divergence from this document creates the class of problem where "the code does something the spec doesn't describe" — exactly the situation the three-layer separation is designed to prevent.

---

**END OF ARCHITECTURE.md v1.6**
