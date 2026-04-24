# SPEC.md — HEL Engineering Calculator

**Version:** 1.11 (Phase 3 UI redesign PR 6 of six: preset dropdown materialized, CSV snapshot export added to Overview tab, calm `error_card` replaces the default `st.error` validator surface, centered `welcome_card` replaces the first-run `st.info` banner — **no physics, no module I/O, no validation-case expected values touched**)
**Supersedes:** `HEL_Calculator_Project_Plan_v0p8.docx` §3–§6 (which remains the plan-of-record; this SPEC is the implementation contract derived from it)
**Status:** Implementation contract. Any requested feature not described here requires a SPEC update before implementation.

**Revision history:**
- v1.11 (2026-04-24) — **Phase 3 UI redesign, PR 6 of six: preset dropdown materialized + CSV export + friendly validator-error / welcome surfaces + accessibility polish.** All edits are UI-only under CLAUDE §3 rule 1; no physics, no module I/O, no `assumptions_flagged` semantic, no validation-case expected value, no `pytest tests/` outcome is touched. (a) **§5.1 preset dropdown** — the sidebar's top-of-list `Engagement scenario` selectbox is now wired to three defensible reference configurations (`c_uas_short_range` mirroring the canonical 3 kW / 1.5 km / CFRP test case; `counter_rocket` at 30 kW / 3 km / 4 mm CFRP casing / 100 m/s terminal-speed target; `long_range_surveillance` at 10 kW / 10 km / polycarbonate sensor window) plus a `"custom"` entry that leaves every widget value in place. Selecting a named scenario writes all six input-panel values into `st.session_state` in a single `on_change` callback so every widget re-renders pre-filled on the same run. Preset parameters live in `ui/presets.py::PRESET_PARAMETERS` in SI units (the same dict shape the orchestrator consumes) with a dedicated `_SI_TO_WIDGET` conversion table that handles display-unit widget keys (kW, cm, µm, µrad, kJ/K, °C). Every preset also resets the `_A_lambda_override` session-state latch so presets always surface the M8 material-table default absorptivity (and any HIGH UNCERTAINTY flag attached to it). (b) **§5.2 Overview tab gains a CSV snapshot export** — a small `st.download_button` at the foot of the Overview tab produces a four-column CSV (`Label, Value, Unit, Flag`) containing: one verdict summary row reproducing the on-screen chip text; one row per curated metric in `ui/outputs.py::_CSV_METRIC_KEYS` that is present in the result dict (output labels drawn from `ui.labels.output_label`, units from `ui.labels.output_unit`, values scaled through the same `_scale(output_key, raw)` helper the tabs use so numbers match on-screen display units, formatted with `{:.6g}` for six significant figures of round-trip fidelity); and one row per active entry in `assumptions_flagged`. The CSV uses `csv.writer` so embedded commas and quotes in flag strings escape correctly; the file is offered under `hel-analysis-snapshot.csv` with `mime="text/csv"`. This is strictly a render of already-computed orchestrator outputs — no physics, no module, no orchestrator behavior is touched. (c) **§5.3 item 9 (validator error surface)** — when a physics module's input validator raises `ValueError`, `ui/app.py` now renders the exception through `ui/components.py::error_card(title, message, *, suggestion)` rather than Streamlit's default full-width red `st.error` banner. The card uses a 4 px `--status-error` left border, the `x-circle` Lucide icon next to the headline in the error hue, and a body + optional suggestion on standard surface tokens — "here is what went wrong, here is what to change" reads calmer than a shouting stripe while keeping the error severity unambiguous (hue + icon + headline three-channel encoding, same rule as status chips). The raw `ValueError` message is quoted verbatim in the body so the user can see the exact sanity-range violation. (d) **§5.3 item 10 (first-run welcome)** — before the user has clicked Run Analysis even once, `ui/app.py` renders a centered `.hel-welcome-card` (title `"Ready to run"`, body walking the user through the preset dropdown → sidebar edit → Run Analysis sequence) instead of the plain `st.info` banner used through PR 5. The card sits on the same elevated surface token as metric cards; the body is capped at 520 px for an engineer-friendly line-measure. (e) **§5.3 item 8 (accessibility polish)** — the `prefers-reduced-motion` media query shipped in PR 4 is verified to collapse the progress-bar sliding animation, error-card focus transitions, and welcome-card fade-in to the 50 ms floor; no other motion is introduced in PR 6. (f) **No change** to §1 conventions, §2 interface contract, §3 module specifications, §4 execution order, §5.1 input-panel contents / sanity ranges / default-expansion rules, §5.2 tab dispatch table / plot specifications / numeric-display conventions, §5.3 items 1–7 and 11–12, §6 file layout (covered by the companion ARCHITECTURE.md v2.0), §7 dependency pinning, §8 CI workflow, §9 implementation checklist, §10 disposition summary. **Test count unchanged at 30** for physics modules; `tests/test_copy_style.py` extends its `SCANNED_FILES` tuple to cover `ui/presets.py` and the scan-list guard is renamed `test_scan_list_covers_phase3_pr6_surface`.
- v1.0 — initial draft; post-audit fixes applied before first delivery (dn/dT formula corrected, M6.2 canonical case revised to 10 kW, test count 28→29)
- v1.1 — consistency fixes surfaced during ARCHITECTURE.md audit: (a) `assumptions_flagged` key added to M2, M3, M5 Outputs tables (previously missing — §2 interface contract requires every module to return this, but the per-module tables had drifted); (b) M11 now has an explicit function signature `run_validation_suite() -> dict` with a documented return schema, so ARCHITECTURE can reference it without inventing the contract.
- v1.2 — four UI enhancements added (no physics or module changes): (a) §5.1 introduction now specifies default panel expansion state and iconography conventions; (b) §5.2 Panel 2 verdict now includes a numeric margin and a traffic-light color in addition to the binary ENGAGEABLE/NOT ENGAGEABLE label; (c) §5.2 Plots A, B, C subsections now specify hover-tooltip content and cross-plot hover synchronization; (d) §5.3 adds URL-encoded parameter sharing as a v1 feature (was previously deferred to v1.2 as JSON only). All other content unchanged from v1.1.
- v1.3 (2026-04-23) — §3 M8 `test_m8_aluminum_standard` and `test_m8_cfrp_thin` input values corrected. Inputs in v1.2 were low by ~100× relative to the stated `tau_BT` targets (e.g. `I_aim=5e4 W/m²` on 2 mm Al with `A_λ=0.5` yields ~210 s to melt, not the stated 4–8 s; at T_melt the environmental losses actually exceed the 25 kW/m² absorbed flux so the surface would equilibrate below T_melt). Corrected inputs (`I_aim=2e6 W/m²` for Al, `I_aim=5e5 W/m²` for CFRP) are HEL-engagement realistic (= 200 W/cm² and 50 W/cm²) and reproduce the original SPEC tau_BT targets to within the stated 25% / < 2 s tolerances. No physics, PDE, or failure-criterion text changed — values only. Caught during M8 implementation per CLAUDE §4.3 procedure.
- v1.4 (2026-04-23) — **structural-only: orchestrator.py relocated from `ui/` to `physics/`** to enable direct unit-test coverage of the M6↔M7 fixed-point loop under the ARCHITECTURE §2 import rules. The chain coordinator has no Streamlit imports and no UI side effects, so it belongs in Layer 1. Caching (`@st.cache_data`) moves to `ui/app.py`, wrapping the orchestrator call at the UI boundary — the standard Streamlit pattern. §6 file-layout tree updated (orchestrator.py under `physics/`, dropped from `ui/`) and the import-rules bullet simplified (`ui/` imports from `physics/` only, no parenthetical about `orchestrator.py`). No physics, no equations, no validation cases touched.
- v1.7 (2026-04-23) — **UI-only: Share button displays URL in an `st.code` block (improvement #3); URL-decode latched to once per session (improvement #1).** Slice 4 of the UI layer. Two §5.3 item-7 clarifications: (a) the Share-this-analysis button no longer attempts `navigator.clipboard.writeText` (which depends on HTTPS + user gesture + permission and may silently fail); instead it renders the encoded URL in a visible `st.code(url)` code block for manual copy. The code block is deterministic across every Streamlit deployment mode (local dev, Streamlit Cloud, iframe embed). (b) On page load, the URL-parameter decode runs **exactly once per Streamlit session**, guarded by `st.session_state['_url_decoded'] = True`. Without this latch, any subsequent widget change triggers a Streamlit rerun that would re-apply the (now stale) URL-encoded values on top of the user's edits, silently reverting their changes. No physics, module, or validation-case change.
- v1.6 (2026-04-23) — **UI-only: cross-plot hover sync descoped to per-plot unified hover.** Slice 3 of the UI layer chose to drop the bespoke Streamlit ↔ Plotly JS callback that would have propagated the hovered x-coordinate across Plots A/B/C, and instead rely on Plotly's built-in `hovermode='x unified'` within each figure. Rationale: the cross-plot callback is brittle (relies on Plotly event hooks Streamlit does not expose cleanly), saves only a mouse-move between plots (the user already scrolls between them), and adds a dependency on JavaScript injection that `st.plotly_chart` officially discourages. Within-plot unified hover — vertical crosshair + one tooltip per curve at the hovered x — still gives the same multi-curve read that the original intent needed; the user just moves the mouse to each plot separately to read across plots. §5.2 "Cross-plot hover synchronization" paragraph softened to "Per-plot unified hover"; Plot A/B/C tooltip content tables unchanged. No physics, module, or validation-case change.
- v1.5 (2026-04-23) — **HV_5_7 Cn² model implemented.** SPEC v1.1–v1.4 enumerated `'HV_5_7'` as a valid `cn2_model` value (and §5.1 Panel D set it as the UI default), but `physics/m5_turbulence.py` shipped only the `'constant'` branch — the HV_5_7 branch raised `NotImplementedError`. Slice 2a of the UI layer surfaced this as a live contract gap (`tests/test_orchestrator.py` had to override `canonical_inputs['cn2_model']` to `'constant'` to exercise the chain). Resolved here per CLAUDE §4.3 by (a) adding a new §3 M5 validation case `test_m5_hv_5_7_ground_level` pinning the expected r₀_sph and w_turb for a ground-level slant path with the HV_5_7 profile at H_e=H_t=0, where the profile reduces analytically to a uniform Cn² = `Cn2_ground + 2.7e-16`; (b) implementing the Hufnagel-Valley 5/7 integral in `physics/m5_turbulence.py` via `scipy.integrate.quad` along the linear altitude path h(z) = H_e + (H_t−H_e)·z/L (Andrews & Phillips §12; Hufnagel 1974; Valley 1980); and (c) adding the new test case to `tests/test_m5_turbulence.py`. M5 test count 4→5; total test count 29→30. §3 M11 inventory table updated accordingly. No immutable CLAUDE §7.1 formula touched; this closes the `'HV_5_7'` enum entry against an implementation rather than a `NotImplementedError`.
- v1.8 (2026-04-23) — **§10 HIGH UNCERTAINTY dispositions applied per `docs/spec_section10_review_2026-04-23.md`.** Six items reviewed at Phase 2 closeout; user accepted all memo recommendations. Edits: (a) §3 M4 α_mol HIGH UNCERTAINTY wording tightened and explicitly scoped "sea-level only"; (b) §3 M4 reference line adds Thomas & Stamnes 2002 band-edge cross-check citation; (c) §3 M8 A_λ table gains a per-row `Primary source` column (Steen & Mazumder, Bergstrom 2007, SABIC/Hexcel/Toray datasheets, Sandia reports); (d) §3 M8 convective-BC inline citation adds Incropera & DeWitt Ch. 7 cross-check; (e) §3 M9 `test_m9_retinal_band_baseline` NOTE wording corrected — previously implied "C_A appropriate for 1.07 µm" was applied, now explicitly documents the conservative **C_A = 1** convention and the strict-ANSI conversion factor for operator use; (f) §10 rewritten as an accepted-disposition summary with item 3 (MPE) marked CLOSED and item 5 (dwell) marked DEFERRED TO v2; (g) M9 code behavior, every formula in §3, and every expected-value in the 29 SPEC tests unchanged — `pytest tests/` passes unchanged. No immutable CLAUDE §7.1 formula touched.
- v1.10 (2026-04-24) — **Phase 3 UI redesign, PR 2 of six: metric-card surface + severity-sorted flag list + status-chip verdict shipped in code.** All edits are UI-only under CLAUDE §3 rule 1; no physics, no module I/O, no `assumptions_flagged` semantic, no validation-case expected value, no `pytest tests/` outcome is touched. (a) **§5.3 item 8 (numerical display)** is pinned to the single gate in `ui/components.py::format_value(value, unit, *, sig_figs=3)`: 3 significant figures by default, comma thousands-separator at magnitudes ≥ 1000, scientific notation ("1.23 × 10⁻⁶" with Unicode × and superscript digits) when |value| < 0.01 or ≥ 1e5, non-breaking space between value and unit, em-dash (—) for `None` / `NaN` / `inf`. Every number on screen routes through this helper; callers do not format numerics inline. (b) **§5.3 item 9 (verdict chip)** is pinned to `status_chip(text, severity)` in `ui/components.py`: hue + Lucide icon + text (color-blind triple-encoding); `severity ∈ {ok, warn, error, info}` selects both hue (`--status-*` tokens in `ui/theme.py`) and icon (`check-circle`, `alert-triangle`, `x-circle`, `info`). The inline-HTML verdict banner that shipped in v1.9 PR 1 is retired. (c) **§5.3 item 11 (assumption flags)** is now a **severity-sorted chip list** in the Diagnostics roll-up: each string in `assumptions_flagged` is classified by a keyword heuristic into `error / warn / info` (in-code table in `ui/outputs.py::_SEVERITY_PATTERNS`; HIGH UNCERTAINTY → warn, "N_D > 30" / "reduced confidence" / "outside tabulated" / "clamped" → warn, "not viable" / "timeout" / "infeasible" → error, "assumed" / "HV-" / "1-D transient" / "sea-level" / "conv+rad" → info). Flags render in `error → warn → info` order so the most important reads first. The raw `assumptions_flagged` list — a `list[str]` on every module's output dict per §2 — is unchanged; no new fields, no new entries, no rewording of existing strings. (d) **§5.2 metric-card surface** pinned to `metric_card(label, value, unit, *, tooltip, flag_est, size, sig_figs)` in `ui/components.py`; the `flag_est=True` kwarg attaches a small superscript "est." link to `#diagnostics` for values that depend on a HIGH UNCERTAINTY input (SPEC §10). The HIGH UNCERTAINTY scope of PR 2 is mechanism-only; PR 6 threads `flag_est=True` through the specific cards (A_λ-dependent τ_BT, MPE-default-dependent NOHD) once the label-level mapping is finalized. (e) **No change** to §1 conventions, §2 interface contract, §3 module specifications, §4 execution order, §5.1 sidebar behavior, §5.2 tab dispatch, §5.3 items 1–7, §5.3 items 10 / 12 (always-render plot frames, provenance footer), §6 file layout (covered by ARCH v1.7), §7 dependency pinning, §8 CI workflow, §9 implementation checklist, §10 disposition summary. **Test count unchanged at 30.** `tests/test_copy_style.py` gains `ui/components.py` to its `SCANNED_FILES` tuple so forbidden tokens in the new component surface are caught by CI.
- v1.9 (2026-04-24) — **Phase 3 UI redesign, PR 1 of six: behaviorally-rewritten §5.1 / §5.2 / §5.3 for a premium engineering-instrument look.** Slice 1 of the Phase 3 rollout in `docs/phase3_ui_redesign_plan_2026-04-23.md`. Every edit is UI-only under CLAUDE §3 rule 1; no formula, no module I/O dict key, no `assumptions_flagged` entry, no validation-case expected value, and no `pytest tests/` outcome is touched. (a) **§5.1** — the six input panels (A–F) keep the same `user_inputs` dict contract exactly, but are renamed as sidebar **sections** with plain-English English headers ("Laser source" / "Beam director" / "Engagement geometry" / "Atmosphere" / "Target & aimpoint" / "System resources") and **no emoji iconography**. The sidebar gains a preset dropdown at the top (four named scenarios in `ui/presets.py`), keeps the Validate and Share buttons, and gains a light/dark theme toggle at the sidebar footer. Every input's visible label and tooltip is read from the `ui/labels.py` single-source-of-truth mapping. (b) **§5.2** — the five numeric panels and three plots are **re-mapped to six main-area tabs** (Overview / Engagement / Target effects / Safety / Atmosphere / Diagnostics). The same merged-result dict is passed to every tab; which tab renders which SPEC quantity is specified in the new §5.2 dispatch table. Three new plots are added (temperature vs time, τ_BT material comparison, NOHD cross-section / extinction breakdown horizontal stacked bar / transmission vs range — the last three replace the single Panel 5 stacked bar with a tab's worth of atmosphere insight). All new plots draw their data from existing M1–M10 outputs; **no new physics, no new material, no new wavelength, no new input dimension.** (c) **§5.2** visual conventions: every numeric value routes through a shared `format_value` helper (3 sig figs default, comma thousands separator, scientific-notation auto-switch for |value| < 0.01 or ≥ 1e5, non-breaking space before units, typographic `×`). Every multi-series plot uses hue + dash-pattern + marker-shape triple-encoding so deuteranopic / protanopic / tritanopic viewers can still distinguish series. Every status chip uses hue + Lucide icon + text label so color never carries meaning alone. (d) **§5.3** gains five behavioral commitments: (item 8) **light/dark toggle** — the sidebar-footer control flips both the Streamlit theme and the shared Plotly template in one action; all palette tokens come from `ui/theme.py` and have WCAG-AA contrast pairs verified by `scripts/check_contrast.py`; (item 9) **compute-time feedback** — clicking Run Analysis disables the button and renders a thin indeterminate progress bar below the tab strip; output cards fade in on completion; no modal, no whole-page spinner; (item 10) **always-render plot frames** — a plot with no feasible data (e.g., infeasible geometry, no dwell) renders its axis frame + an in-chart English advisory, never silently disappears; (item 11) **no internal references in user copy** — strings like `SPEC §…`, `M6↔M7 loop`, `_flagged`, and emoji ranges are forbidden in `ui/panels.py` / `ui/outputs.py` / `ui/plots.py` / `ui/app.py`, enforced by `tests/test_copy_style.py` in CI (internal references remain in physics docstrings and in `assumptions_flagged` strings, which are displayed to the user with their rendering cleaned up at render time in the Diagnostics tab); (item 12) **provenance footer** — every page renders a single-line strip at the bottom of the main area reading `HEL Engineering Calculator · SPEC v1.9 · ARCH v1.6 · build YYYY-MM-DD`; the version provenance that used to pollute the page subtitle now lives here. (e) **No change** to §1 conventions, §2 interface contract, §3 module specifications, §4 execution order, §6 file layout (covered by the companion ARCHITECTURE.md v1.6), §7 dependency pinning, §8 CI workflow, §9 implementation checklist, or §10 §10-disposition summary. **Test count unchanged at 30** for physics modules; the new `tests/test_copy_style.py` is an **infrastructure test** (grep-based static check over `ui/` source files, no physics input, zero dependency on physics module output).

---

## 0. Purpose of This Document

SPEC.md is the single source of truth for what Claude Code implements. For every module (M1 through M11), this document specifies:

- **Inputs:** exact parameters, types, units, and valid ranges
- **Outputs:** exact return values, types, and units
- **Equation(s):** the canonical form to implement, stated precisely
- **Reference:** the textbook or standard the equation is drawn from
- **Validation case:** the reference calculation the module must reproduce in pytest

The plan document (`v0p8.docx`) describes the *why* and the *design intent*. SPEC.md describes the *what* and the *exact contract*. Conflicts are resolved as follows: **plan describes intent; SPEC describes implementation. If the SPEC disagrees with the plan, update the SPEC. If the user wants behavior not described in the SPEC, update the SPEC before implementing.**

All numerical values in this SPEC have been independently verified via Python numerical checks against first-principles derivations. Any value flagged "[HIGH UNCERTAINTY]" is a literature-sourced engineering default that should be confirmed against program-specific data before the tool is used for formal trade studies.

---

## 1. Conventions

### 1.1 Beam-Size Convention

The 1/e² intensity radius `w` is the canonical beam-size measure throughout this SPEC. For a Gaussian intensity profile:

```
I(r) = I_peak · exp(-2 r² / w²)
```

- 1/e² diameter = `2·w`
- Total power = `(π/2) · I_peak · w²`
- Peak irradiance = `2·P / (π·w²)`
- Relation to RMS: `σ = w/2`

All equations below use `w`. Where user-facing labels report a beam diameter, they report `2·w` (the 1/e² diameter, matching vendor datasheet convention).

### 1.2 Units

All internal calculations use SI base units (W, m, s, K, radians, kg). Convenience conversions (kW, cm, km, µrad, °C, µm) are applied at the I/O boundaries only. Every user-facing numeric field displays its unit inline; units are never inferred.

### 1.3 Jitter Convention

Pointing jitter `σ_jit` is defined as **per-axis 1-σ angular RMS** (the standard PTU/EO datasheet convention). Users who enter a 2D radial RMS value would double-count — the UI label in the Beam director section makes the per-axis convention explicit.

### 1.4 Angle Convention

Angular divergence values (θ_diff, θ_total, etc.) are expressed as **full-angle** (Siegman convention). Some other trade-study tools use half-angle; the Panel 1 display legend states this explicitly to prevent confusion when comparing numbers across tools.

### 1.5 Beam Geometry

v1 assumes **collimated beam** (focus at infinity). Focus-on-target geometry is a v1.5 feature. The diffraction formula `w_diff(L) = w₀·sqrt(1 + (M²·L/z_R)²)` is the exact Gaussian propagation formula for a collimated launch beam.

### 1.6 Out-of-Regime Behavior

When the user provides inputs that are valid but outside the regime where a module's physics is reliable, the tool behaves as follows:

- **REFUSE** (red error, computation blocked): truly unphysical inputs (M² < 1.0, P ≤ 0, negative distances, etc.)
- **WARN + COMPUTE** (red banner, results shown with caveat): model-validity boundaries (N_D > 30, wavelength outside validated set, Cn² outside HV model range, etc.)
- **FLAG SILENTLY** (entry in assumptions panel only): routine default usage, wavelength interpolation within validated set, aimpoint smaller than beam waist, etc.

---

## 2. Module Interface Contract

Every physics module shall be a pure Python function with the signature pattern:

```python
def module_function(inputs_dict: dict) -> dict:
    """
    [module description and reference citation]
    
    Inputs (keys expected):
      - key_name (unit): description, valid range
      ...
    
    Outputs (keys returned):
      - key_name (unit): description
      ...
    
    Assumptions flagged:
      - [list of modeling assumptions active for this call]
    
    Reference: [citation]
    """
    # validation of input ranges
    # computation
    # return dict with outputs + assumptions_flagged list
```

Every module returns an `assumptions_flagged` list that the UI aggregates into the Panel 4 assumptions block. This is a first-class output, not an afterthought.

Modules shall **not** have side effects, shall **not** access files, shall **not** access the network, and shall **not** depend on UI state. They are pure functions.

---

## 3. Module Specifications

### M1 — Laser Source

**File:** `physics/m1_laser_source.py`

**Purpose:** Defines the physical beam at the exit aperture of the laser head, before the beam director.

**Inputs:**
| Key | Unit | Type | Valid Range | Description |
|---|---|---|---|---|
| `P0` | W | float | 100 – 100,000 | Output power at laser head |
| `M2` | — | float | 1.0 – 10.0 | Beam-quality factor |
| `D` | m | float | 0.01 – 0.50 | Exit aperture diameter |
| `wavelength` | m | float | 0.5e-6 – 5.0e-6 | Laser wavelength |

**Outputs:**
| Key | Unit | Description |
|---|---|---|
| `theta_diff` | rad | Full-angle diffraction-limited divergence |
| `w0` | m | Initial 1/e² beam radius at exit |
| `zR` | m | Rayleigh range |
| `I_exit` | W/m² | Peak irradiance at exit aperture |
| `assumptions_flagged` | list[str] | e.g., `["wavelength outside validated set"]` if applicable |

**Equations:**
```
θ_diff = M² · 4·λ / (π·D)       [full-angle, radians]
w₀     = D / 2                   [beam fills aperture]
z_R    = π·w₀² / λ               [Rayleigh range, M²=1 reference]
I_exit = 2·P₀ / (π·w₀²)         [Gaussian peak, matches §6.7.1 of plan]
```

**Reference:** Siegman, *Lasers* (1986), Ch. 17 (M² formalism).

**Validation case** (pytest: `test_m1_divergence`):
- Inputs: P0=1000, M2=1.0, D=0.10, wavelength=1.064e-6
- Expected: theta_diff ≈ 13.547 µrad
- Tolerance: 0.1%

**Validation case** (pytest: `test_m1_rayleigh_range`):
- Inputs: P0=3000, M2=1.2, D=0.10, wavelength=1.07e-6
- Expected: w0=0.05 m, zR ≈ 7340 m
- Tolerance: 1%

---

### M2 — Beam Director Transmission

**File:** `physics/m2_beam_director.py`

**Purpose:** Applies a single end-to-end optical-train transmission factor to account for Coudé-path mirror losses, exit-window absorption, and contamination margin.

**Inputs:**
| Key | Unit | Type | Valid Range | Description |
|---|---|---|---|---|
| `P0` | W | float | (from M1) | Source power |
| `eta_opt` | — | float | 0.50 – 0.99 | End-to-end transmission |

**Outputs:**
| Key | Unit | Description |
|---|---|---|
| `P_exit` | W | Power at beam director exit aperture |
| `assumptions_flagged` | list[str] | Per-module assumption flags (typically empty for M2) |

**Equation:**
```
P_exit = η_opt · P₀
```

**Reference:** No external citation required. Default `η_opt = 0.85` is a typical value for a 5–7 mirror Coudé path with a protected exit window; user may override.

**Validation case** (pytest: `test_m2_transmission`):
- Inputs: P0=3000, eta_opt=0.85
- Expected: P_exit = 2550 W (exact, arithmetic)
- Tolerance: 0.01%

---

### M3 — Engagement Geometry

**File:** `physics/m3_geometry.py`

**Purpose:** Computes slant-range geometry from user-specified emplacement, target altitude, and horizontal range. Also defines the target dwell window for lethality analysis (Plot B).

**Inputs:**
| Key | Unit | Type | Valid Range | Description |
|---|---|---|---|---|
| `H_e` | m | float | 0 – 3000 | Emplacement altitude AGL |
| `R` | m | float | 50 – 50,000 | Slant range to target |
| `H_t` | m | float | 0 – 5000 | Target altitude AGL |
| `v_tgt` | m/s | float | 0 – 100 | Target velocity |
| `v_perp` | m/s | float | 0 – 30 | Crosswind component perpendicular to beam |

**Outputs:**
| Key | Unit | Description |
|---|---|---|
| `R_slant` | m | Slant path length (equal to R for v1) |
| `R_h` | m | Horizontal component of range |
| `elevation_angle` | rad | Beam elevation angle |
| `available_dwell` | s | Target time-in-basket estimate (for Plot B) |
| `assumptions_flagged` | list[str] | e.g., `["v2 tracker-dependent dwell model deferred; heuristic used"]` |

**Equations:**
```
R_h             = sqrt(R² − (H_t − H_e)²)   [assumes R ≥ |H_t − H_e|]
elevation_angle = arctan((H_t − H_e) / R_h)
available_dwell = 2·R · tan(FOV/2) / v_tgt   [approximate, FOV=5° default]
```

**Reference:** Plain geometry. `available_dwell` is a conservative engagement-basket heuristic; the full tracker-dependent calculation is deferred to v2.

**Validation case** (pytest: `test_m3_geometry`):
- Inputs: H_e=2, R=5000, H_t=200, v_tgt=20, v_perp=3
- Expected: R_h ≈ 4996.1 m; elevation_angle ≈ 0.0396 rad (2.27°)
- Tolerance: 0.1%

---

### M4 — Atmospheric Attenuation

**File:** `physics/m4_atmosphere.py`

**Purpose:** Computes Beer-Lambert transmission through the lower atmosphere, combining molecular absorption (water vapor, CO₂) and aerosol extinction. Wavelength-dependent via both tabulated molecular data and the Kruse aerosol formula.

**Inputs:**
| Key | Unit | Type | Valid Range | Description |
|---|---|---|---|---|
| `V` | km | float | 0.5 – 50 | Meteorological visibility |
| `RH` | — | float | 0.0 – 1.0 | Relative humidity (0-1 fraction) |
| `T_ambient` | K | float | 253 – 328 | Ambient air temperature |
| `wavelength` | m | float | 0.5e-6 – 5.0e-6 | From M1 |
| `R_slant` | m | float | (from M3) | Path length |

**Outputs:**
| Key | Unit | Description |
|---|---|---|
| `alpha_atm` | 1/m | Total extinction coefficient |
| `tau_atm` | — | Transmission factor `exp(-α·R)` |
| `alpha_mol_abs` | 1/m | Molecular absorption component (for display Panel 5) |
| `alpha_mol_scat` | 1/m | Molecular scattering component |
| `alpha_aer_abs` | 1/m | Aerosol absorption component |
| `alpha_aer_scat` | 1/m | Aerosol scattering component |
| `assumptions_flagged` | list[str] | e.g., `["wavelength interpolated", "sea-level coefficients used along slant path"]` |

**Equations:**
```
τ_atm(R) = exp(-α_atm · R)

α_atm = α_mol_abs + α_mol_scat + α_aer_abs + α_aer_scat   [4-way decomposition for display]

α_aer_total = (3.91/V_km) · (λ_µm/0.55)^(-q)   [Kruse-McClatchey, converted to 1/m]

q rule (Kruse modified):
  V > 50 km:     q = 1.6
  6 ≤ V ≤ 50:    q = 1.3
  1 ≤ V < 6:     q = 0.16·V + 0.34
  V < 1 km:      q = V − 0.5
```

Aerosol scattering dominates aerosol absorption at near-IR wavelengths; for v1 we use `α_aer_scat = 0.95·α_aer_total` and `α_aer_abs = 0.05·α_aer_total` as engineering approximations. Full split into individual Mie components deferred to v2.

**Molecular absorption table** [HIGH UNCERTAINTY — McClatchey-family engineering placeholders (sea-level only); verified correct within ±50% and correct in ordering against band-edge structure per `docs/spec_section10_review_2026-04-23.md` §10.1. HITRAN/MODTRAN-derived replacement is a v2 refinement. Acceptable for tool-level trade studies where downstream ±25% test tolerances dominate; not acceptable for formal program safety cases — use program-measured or HITRAN-derived values there]:

Sea-level, mid-latitude summer, at 60% RH baseline, scaled linearly with RH:

| λ (µm) | α_mol_abs (1/km) | α_mol_scat (1/km) | Notes |
|---|---|---|---|
| 1.06 | 0.045 | 0.005 | Near-IR window, low H₂O absorption |
| 1.07 | 0.065 | 0.005 | Slight H₂O band edge |
| 1.55 | 0.190 | 0.010 | Within 1.5 µm atmospheric window |
| 2.05 | 0.490 | 0.010 | Edge of 2.0 µm H₂O band |

Linear RH scaling: `α_mol_abs(RH) = α_mol_abs(60%) · (RH/0.60)` for absorption component; scattering is RH-independent to first order.

**Wavelength interpolation:** Linear in log space between tabulated wavelengths. Wavelengths outside {1.06, 1.07, 1.55, 2.05 µm} trigger "reduced confidence" assumption flag.

**Multi-component display (for Panel 5):** The tool separately reports α_mol_abs, α_mol_scat, α_aer_abs, α_aer_scat so the user can see where extinction is coming from.

**Reference:** Kruse, *Elements of Infrared Technology* (1962) for aerosol formula; McClatchey et al., AFCRL-TR-72-0497 for molecular baselines (α_mol table drawn from this family; band-edge ordering cross-checked against Thomas & Stamnes 2002 fig. 3.14 per `docs/spec_section10_review_2026-04-23.md` §10.1); Andrews & Phillips Ch. 12 for engineering formulations.

**Validation cases:**

`test_m4_aerosol_clear` (clear air at 1.07 µm):
- Inputs: V=23, RH=0.6, T_ambient=300, wavelength=1.07e-6, R_slant=5000
- Expected: α_aer_total ≈ 0.0716 1/km; α_atm ≈ 0.137 1/km; τ_atm ≈ exp(-0.685) ≈ 0.504
- Tolerance: 5%

`test_m4_aerosol_hazy` (5 km visibility):
- Inputs: V=5, RH=0.6, wavelength=1.07e-6
- Expected: α_aer_total ≈ 0.366 1/km (using q = 0.16·5 + 0.34 = 1.14)
- Tolerance: 5%

`test_m4_wavelength_interpolation`:
- Input wavelength between tabulated points (e.g., 1.3 µm) should return a value interpolated from the 1.07 and 1.55 entries with "wavelength interpolated" flag.
- Tolerance on interpolation: exact match to log-space linear.

---

**[Continued in Part 2]**

### M5 — Cn² and Turbulence

**File:** `physics/m5_turbulence.py`

**Purpose:** Computes the refractive-turbulence contribution to beam spreading via the Fried coherence length `r₀` (spherical-wave form, appropriate for diverging beams from a finite source) and the resulting long-term beam radius.

**Inputs:**
| Key | Unit | Type | Valid Range | Description |
|---|---|---|---|---|
| `cn2_model` | — | enum | see below | Model selector |
| `Cn2_value` | m^(-2/3) | float | 1e-17 – 1e-12 | Constant Cn² (if model = 'constant') |
| `Cn2_ground` | m^(-2/3) | float | 1e-16 – 1e-12 | Ground-level Cn² (if HV model) |
| `v_HV` | m/s | float | 0 – 60 | High-altitude wind (HV models) |
| `wavelength` | m | float | (from M1) | Laser wavelength |
| `R_slant` | m | float | (from M3) | Path length |
| `H_e` | m | float | (from M3) | Emplacement altitude |
| `H_t` | m | float | (from M3) | Target altitude |

`cn2_model` enum values: `'constant'`, `'HV_5_7'`, `'HV_day'`, `'HV_night'`, `'custom'`.

**Outputs:**
| Key | Unit | Description |
|---|---|---|
| `Cn2_integrated` | m^(1/3) | Path-integrated Cn² with spherical-wave weighting |
| `r0_sph` | m | Spherical-wave Fried coherence length |
| `w_turb` | m | Long-term turbulent 1/e² radius contribution at target |
| `assumptions_flagged` | list[str] | e.g., `["spherical-wave r₀ form", "engineering form 2L/(k·r₀) used"]` |

**Equations:**

```
k = 2π/λ   [wavenumber, 1/m]

Path integration (spherical wave, appropriate for diverging HEL):
  Cn2_integrated = ∫₀^L Cn²(z) · (z/L)^(5/3) dz

Fried coherence length (spherical wave):
  r0_sph = (0.423 · k² · Cn2_integrated)^(-3/5)   [m]

Long-term turbulent 1/e² radius (engineering form, committed in v0.8):
  w_turb = 2·L / (k · r0_sph)   [m]
```

**HV-5/7 profile** (when cn2_model = 'HV_5_7'):
```
Cn²(h) = 0.00594·(v_HV/27)²·(1e-5·h)¹⁰·exp(-h/1000)
         + 2.7e-16·exp(-h/1500)
         + Cn2_ground·exp(-h/100)
```
where `h` is altitude in meters. Default `Cn2_ground = 1.7e-14`, default `v_HV = 21 m/s`.

For uniform Cn² (constant model):
```
∫₀^L Cn² · (z/L)^(5/3) dz = Cn² · L · (3/8)
```
so `r0_sph = (0.423 · k² · Cn² · L · 3/8)^(-3/5)`, which is exactly `1.86·r0_plane` (the factor-of-1.86 relationship between spherical and plane-wave forms for uniform turbulence).

**Reference:** Andrews & Phillips, *Laser Beam Propagation through Random Media* (2nd ed., 2005), Ch. 6 for `w_turb` (engineering form, §6.5); Ch. 12 for path-integrated r₀. Hufnagel 1974 and Valley 1980 for HV profile.

**Modeling choice flagged by this module:**
- Spherical-wave r₀ is used (not plane-wave) because the HEL beam originates from a finite aperture and propagates as a diverging beam, for which spherical-wave is the physically correct treatment.
- Engineering form `2L/(k·r₀)` is used for `w_turb` (not the rigorous Yura form with ρ₀ ≈ 2.1·r₀), because the engineering form is conservative (predicts more spread) and simpler to verify against textbook cases.

**Validation cases:**

`test_m5_r0_uniform_cn2`:
- Inputs: cn2_model='constant', Cn2_value=1e-14, wavelength=1.07e-6, R_slant=5000, H_e=0, H_t=0
- Expected: r0_sph ≈ 0.0345 m (3.45 cm)
- Tolerance: 2%

`test_m5_w_turb_5km`:
- Same inputs as above
- Expected: w_turb ≈ 0.0494 m (4.94 cm)
- Tolerance: 2%

`test_m5_spherical_vs_plane_ratio`:
- Verify that for uniform Cn², r0_sph / r0_plane = (3/8)^(-3/5) ≈ 1.801
- Tolerance: 0.1% (this is a structural test to prevent regression to plane-wave form)

`test_m5_r0_at_1500m`:
- Same Cn² and wavelength but R_slant=1500
- Expected: r0_sph ≈ 0.0711 m (7.11 cm); w_turb ≈ 0.00719 m (0.72 cm)
- Tolerance: 2%

`test_m5_hv_5_7_ground_level`:
- Inputs: cn2_model='HV_5_7', Cn2_ground=1.7e-14, v_HV=21, wavelength=1.07e-6, R_slant=5000, H_e=0, H_t=0
- Rationale: with both emplacement and target at ground level the altitude path h(z) ≡ 0, so the HV-5/7 profile reduces to `Cn²(0) = 2.7e-16 + Cn2_ground = 1.727e-14` — a uniform-Cn² case solvable in closed form against which the HV_5_7 numerical-integration branch is verified.
- Expected: r0_sph ≈ 0.0249 m (2.49 cm); w_turb ≈ 0.0685 m (6.85 cm)
- Tolerance: 2%
- Rationale for a structural companion check: the test file additionally asserts that HV_5_7 at H_e=H_t=0 matches the `'constant'` model with `Cn2_value = Cn2_ground + 2.7e-16` to within 0.1%, guarding against regression to a plane-wave integral or an incorrect profile-summation order.

---

### M6 — Thermal Blooming

**File:** `physics/m6_blooming.py`

**Purpose:** Computes the Gebhardt distortion number `N_D` and the associated Strehl loss from beam-induced heating of the atmospheric path. Outputs both the Strehl factor for peak-irradiance reduction and (for large N_D) a blooming-induced spot broadening contribution.

**Inputs:**
| Key | Unit | Type | Valid Range | Description |
|---|---|---|---|---|
| `P_propagating` | W | float | (computed) | Average power along path (after M4 attenuation) |
| `w_at_target` | m | float | (iterated) | Beam 1/e² radius at target (from M7, iterated) |
| `alpha_atm` | 1/m | float | (from M4) | Atmospheric absorption |
| `v_perp` | m/s | float | (from M3) | Crosswind |
| `R_slant` | m | float | (from M3) | Path length |
| `T_ambient` | K | float | (from M4) | Ambient air temperature |
| `P_atm` | Pa | float | 101325 | Atmospheric pressure (default sea level) |

**Outputs:**
| Key | Unit | Description |
|---|---|---|
| `N_D` | — | Gebhardt distortion number |
| `S_TB` | — | Thermal-blooming Strehl ratio (0–1, peak reduction) |
| `w_bloom` | m | Blooming-induced spot broadening contribution (0 if N_D < 5) |
| `assumptions_flagged` | list[str] | e.g., `["N_D > 30, model outside validity range"]` |

**Equations:**

```
# Air properties at T_ambient, P_atm (from ideal gas law + standard air):
ρ    = P_atm · 0.029 / (8.314 · T_ambient)     [kg/m³, molar mass air = 0.029 kg/mol]
c_p  = 1005                                     [J/(kg·K), dry air, weakly T-dependent]
n₀   = 1.000293                                 [standard index of air at ~500 nm, approx for NIR]
dn/dT = -0.93e-6 · (288/T_ambient) · (P_atm/101325)   [K⁻¹, from Gladstone-Dale; ≈ −0.93e-6 at STP]

# Gebhardt distortion number (4√2 prefactor, Gebhardt 1990 form):
N_D = 4·sqrt(2) · (-dn/dT) · (α_atm · P_propagating · R_slant²) 
      / (n₀ · ρ · c_p · v_perp · w_at_target³)

# Blooming Strehl (Smith approximation):
S_TB = 1 / (1 + (N_D / N_crit)²)   where N_crit = 5

# Blooming-induced broadening (nonzero only above N_D threshold):
if N_D < 5:
    w_bloom = 0
elif 5 ≤ N_D ≤ 30:
    w_bloom = w_at_target · sqrt((N_D/5)² − 1) · 0.3   [empirical scaling]
else:
    w_bloom = w_at_target · sqrt((N_D/5)² − 1) · 0.3
    flag "N_D > 30, model outside validity range"
```

Note on sign: `dn/dT` for air is negative (hot air has lower index); the leading `-dn/dT` makes N_D positive. Both signs are preserved in the equation for clarity.

**Iterative coupling with M7:** M6 and M7 form a fixed-point iteration. M7 computes `w_at_target` assuming some `S_TB`; M6 computes `S_TB` and `w_bloom` from `w_at_target`; loop until `w_at_target` changes by less than 1% between iterations. Maximum 10 iterations. If no convergence, flag "blooming iteration did not converge" and use last iterate.

**Reference:** Gebhardt, F. G., "High-power laser propagation," *Applied Optics* 15(6), 1479–1493 (1976); Gebhardt, F. G., "Twenty-five years of thermal blooming: an overview," *Proc. SPIE* 1221 (1990), 2–25 (current engineering form and 4√2 prefactor). Sprangle et al., NRL papers on maritime HEL propagation (e.g., NRL/MR/6790-08-9141) for multi-physics corrections.

**Validation cases:**

`test_m6_dimensional`:
- Verify N_D is dimensionless for any set of valid SI inputs. Structural test.

`test_m6_moderate_blooming`:
- Inputs: P_propagating=10e3, w_at_target=0.10, alpha_atm=1e-4 (=0.1 1/km), v_perp=5, R_slant=5000, T_ambient=300
- Expected: N_D ≈ 20 (interesting-regime check; actual blooming trade studies operate in this range); S_TB ≈ 0.05 using N_crit=5 (severe blooming — catastrophic peak-irradiance loss, illustrating why high-power engagement at this range with 5 m/s crosswind is not viable)
- Tolerance: ±30% on N_D (engineering-model tolerance)
- Rationale: At 100 kW / 5 km with standard atmosphere, N_D would be ~200 (catastrophic blooming — the tool correctly predicts you cannot operate there without beam director mitigation). This validation case exercises the interesting regime where blooming matters but is not yet catastrophic.

`test_m6_small_power_limit`:
- P_propagating=100 W: N_D should be ~0.001, S_TB ~1.0
- Validates low-power limit

---

### M7 — Spot Size and Power-in-the-Bucket

**File:** `physics/m7_spot_pib.py`

**Purpose:** The integrating module. Combines all upstream beam-quality losses — diffraction, M² scaling, turbulence, jitter, blooming broadening — into the 1/e² spot radius at the target and computes the power delivered inside a user-specified aimpoint disk.

**Inputs:**
| Key | Unit | Type | Description |
|---|---|---|---|
| `P_exit` | W | float | Power at beam director exit (from M2) |
| `tau_atm` | — | float | Atmospheric transmission (from M4) |
| `w0` | m | float | Launch beam 1/e² radius (from M1) |
| `zR` | m | float | Rayleigh range (from M1) |
| `M2` | — | float | Beam quality factor (from M1) |
| `wavelength` | m | float | From M1 |
| `R_slant` | m | float | From M3 |
| `sigma_jit` | rad | float | Per-axis jitter RMS (user input) |
| `r0_sph` | m | float | From M5 |
| `S_TB` | — | float | From M6 |
| `w_bloom` | m | float | From M6 |
| `d_aim` | m | float | Aimpoint diameter (user input) |

**Outputs:**
| Key | Unit | Description |
|---|---|---|
| `w_diff` | m | Exact-Gaussian diffraction 1/e² radius at target |
| `w_turb` | m | Turbulence contribution (reflected from M5 for convenience) |
| `w_jit` | m | Jitter contribution |
| `w_total` | m | Combined 1/e² radius (quadrature) |
| `d_spot` | m | 1/e² diameter = 2·w_total |
| `I_peak` | W/m² | Strehl-corrected peak irradiance at target |
| `PIB_fraction` | — | Power fraction inside aimpoint (0–1) |
| `P_aim` | W | Power delivered inside aimpoint |
| `I_avg_aim` | W/m² | Average irradiance inside aimpoint |

**Equations:**

```
# Diffraction (EXACT Gaussian propagation, NOT far-field asymptote):
w_diff(L) = w₀ · sqrt(1 + (M² · L / z_R)²)

# Turbulence (from M5):
w_turb = 2·L / (k · r0_sph)

# Jitter (per-axis RMS → 1/e² spatial radius):
w_jit = 2 · σ_jit · L

# Quadrature combination (diffraction, turbulence, jitter, blooming-broadening):
w_total² = w_diff² + w_turb² + w_jit² + w_bloom²

# Spot diameter (1/e², HEL-standard):
d_spot = 2 · w_total

# Peak irradiance with Strehl correction (S_TB for blooming; optics Strehl = 1 in v1):
# NOTE: turbulence broadening is captured in w_total (long-term convention);
#       multiplicative Strehl only covers phase-only effects (blooming, WFE).
S_total = S_TB · S_opt          [S_opt = 1 in v1]
I_peak  = 2 · P_exit · τ_atm · S_total / (π · w_total²)

# Power-in-the-bucket (Gaussian, circular aperture, bucket radius R_aim = d_aim/2):
R_aim         = d_aim / 2
PIB_fraction  = 1 - exp(-2 · R_aim² / w_total²)
P_aim         = P_exit · τ_atm · S_total · PIB_fraction
I_avg_aim     = P_aim / (π · R_aim²)
```

**Critical implementation notes:**

1. **Use the exact Gaussian formula for `w_diff`, not the far-field asymptote.** At realistic C-UAS engagement ranges (0.5–5 km with typical D = 10–30 cm), the beam is in the near-field or transition regime (L/z_R < 1). The far-field formula `w_diff = M²·λL/(π·w₀)` under-predicts spot size by 2× to 15× in this regime. This was the critical bug caught in v0.6 of the plan.

2. **Use the bucket RADIUS, not the diameter, in the PIB exponent.** `R_aim = d_aim / 2` is the HEL-standard Gaussian PIB formula. Using `d_aim` directly in place of `R_aim` produces a factor-of-4 error in the exponent (bug caught in v0.2 of the plan).

3. **Do NOT double-count turbulence.** Turbulence enters `w_total²` via `w_turb²` (spot broadening, long-term convention). It must NOT ALSO be applied as a Strehl factor `S_turb` on top of that — the two conventions are mutually exclusive. `S_total = S_TB · S_opt` only. Bug caught in v0.4 of the plan.

4. **Jitter is per-axis angular RMS.** The factor of 2 in `w_jit = 2·σ_jit·L` converts from σ (RMS) to w (1/e² radius) per axis. The resulting 2D time-averaged spot is axially symmetric because σ_x = σ_y = σ_jit.

**Reference:** Andrews & Phillips, Ch. 6 (Gaussian beam propagation in turbulence); Siegman, *Lasers* Ch. 17 (M² propagation); Born & Wolf, *Principles of Optics* Ch. 8 (Gaussian PIB closed form); Perram et al., *An Introduction to Laser Weapon Systems* (DEPS) for HEL engineering conventions.

**Validation cases:**

`test_m7_pure_diffraction_5km` (Case 1 from plan §6.7.5):
- Inputs: P_exit=2550, tau_atm=1, w0=0.05, zR=7340, M2=1.0, wavelength=1.07e-6, R_slant=5000, sigma_jit=0, r0_sph=∞, S_TB=1, w_bloom=0, d_aim=0.05
- Expected: w_diff ≈ 6.05 cm, d_spot ≈ 12.1 cm, PIB_fraction ≈ 0.289
- Tolerance: 2%

`test_m7_diff_plus_turb_5km` (Case 2):
- Same as above but r0_sph=0.0345 (corresponding to Cn²=1e-14 over 5 km)
- Expected: w_turb ≈ 4.94 cm, w_total ≈ 7.81 cm, PIB_fraction ≈ 0.185
- Tolerance: 2%

`test_m7_typical_c_uas_1500m` (Case 3, the near-field regression test):
- Inputs: w0=0.05, zR=7340, M2=1.0, wavelength=1.07e-6, R_slant=1500, r0_sph=0.0711, d_aim=0.05, everything else ideal
- Expected: w_diff ≈ 5.10 cm (NOT 1.02 cm, which is what far-field formula gives!), PIB_fraction ≈ 0.376
- Tolerance: 2%
- **This test explicitly guards against regression to the far-field formula.**

`test_m7_convention_consistency`:
- Verify that computing PIB via the w-convention formula `1 - exp(-2R²/w²)` and the σ-convention formula `1 - exp(-R²/(2σ²))` with `σ = w/2` give identical results.
- Verify that `I_peak = 2P/(πw²) = P/(2πσ²)` gives the same number both ways.
- This is the structural guard against the convention-mixing errors that caused v0.3/v0.4 bugs.

---

**[Continued in Part 3]**

### M8 — Material Burn-Through

**File:** `physics/m8_burnthrough.py`

**Purpose:** Computes the dwell time required to defeat a selected material at a specified thickness, given the peak or average irradiance delivered by M7. Uses a 1-D transient heat conduction model with absorbed-flux surface boundary, convective backside cooling, and phase-change (metals) or decomposition-threshold (polymers, foams, LiPo) completion criteria.

**Inputs:**
| Key | Unit | Type | Description |
|---|---|---|---|
| `I_aim` | W/m² | float | Delivered irradiance (from M7; use `I_avg_aim` conservatively or `I_peak` for best-case) |
| `material` | str | enum | One of: `'anodized_Al'`, `'CFRP'`, `'GFRP'`, `'polycarbonate'`, `'ABS'`, `'EPP_foam'`, `'LiPo'` |
| `thickness` | m | float | Material thickness (0.0001 – 0.020) |
| `A_lambda` | — | float | Absorptivity at user wavelength (default from table; user-overridable 0.05–0.99) |
| `wavelength` | m | float | For default A_λ lookup (from M1) |
| `backside_BC` | enum | str | `'insulated'` or `'convective'` |
| `v_tgt` | m/s | float | For convective h estimation (from M3) |
| `T_ambient` | K | float | (from M4) |

**Outputs:**
| Key | Unit | Description |
|---|---|---|
| `tau_BT` | s | Time-to-burn-through |
| `T_surface_peak` | K | Peak surface temperature reached |
| `E_delivered` | J | Total energy delivered at burn-through |
| `failure_mode` | str | `'melt'` (metals), `'decomposition'` (polymers), `'vent'` (LiPo), or `'no_failure_before_timeout'` |
| `assumptions_flagged` | list[str] | e.g., `["A_λ at default value (high uncertainty)"]` |

**Equations:**

Governing PDE (1-D transient heat conduction):
```
ρ · c_p · ∂T/∂t = k · ∂²T/∂x²
```

Surface boundary condition at x = 0 (laser-illuminated face):
```
-k · ∂T/∂x |_{x=0} = A_λ · I_aim 
                      - h_conv · (T_s − T_ambient)
                      - ε_IR · σ_SB · (T_s⁴ − T_ambient⁴)
```

Backside boundary condition at x = t_thickness:
- `insulated`: `∂T/∂x = 0`
- `convective`: `-k · ∂T/∂x = h_conv · (T_back − T_ambient)` with `h_conv = 10 + 6.2·sqrt(v_tgt)` W/(m²·K) [combined natural + forced flat-plate correlation; cross-checked against Incropera & DeWitt 6th ed. Ch. 7 (`Nu_L = 0.664·Re_L^(1/2)·Pr^(1/3)` + natural-convection floor) within ±20% per `docs/spec_section10_review_2026-04-23.md` §10.6; user should override with vehicle-specific data when available]

Failure criterion:
- Metals (Al): when `T_surface ≥ T_melt` AND cumulative Stefan-condition mass loss reaches full thickness, fail with mode `'melt'`.
- Polymers (CFRP, GFRP, PC, ABS, EPP): when `T_surface ≥ T_decomp` sustained for `Δt ≥ 0.05 s`, fail with mode `'decomposition'`.
- LiPo: when surface or through-thickness-averaged temperature reaches `T_vent = 420 K`, fail with mode `'vent'`.

Numerical method: explicit finite-difference, with:
- Spatial step: `Δx = min(0.05e-3 m, thickness/20)`
- Time step: `Δt ≤ 0.4 · Δx² · ρ · c_p / k` (stability criterion with safety factor)
- Integration timeout: 60 s (reports `failure_mode = 'no_failure_before_timeout'`)

**Material property table** [HIGH UNCERTAINTY flag on all A_λ values]:

| Material | ρ (kg/m³) | c_p (J/kg·K) | k (W/m·K) | T_fail (K) | L_f (kJ/kg) | Failure mode |
|---|---|---|---|---|---|---|
| Anodized Al | 2700 | 900 | 200 | 933 (melt) | 397 | melt |
| CFRP | 1600 | 1000 | 7.0 | 600 (decomp) | — | decomposition |
| GFRP | 1900 | 800 | 0.4 | 600 (decomp) | — | decomposition |
| Polycarbonate | 1200 | 1200 | 0.2 | 700 (decomp) | — | decomposition |
| ABS | 1050 | 1400 | 0.17 | 670 (decomp) | — | decomposition |
| EPP foam | 30 | 1900 | 0.04 | 620 (ignition) | — | decomposition |
| LiPo cell | 1800 (avg) | 1000 (avg) | 0.5 (avg) | 420 (vent) | — | vent |

**Absorptivity table A_λ** [HIGH UNCERTAINTY — user should override with measured or program-specific values when available; per-row primary sources added per `docs/spec_section10_review_2026-04-23.md` §10.2]:

| Material | 1.06 µm | 1.07 µm | 1.55 µm | 2.05 µm | Primary source |
|---|---|---|---|---|---|
| Anodized Al | 0.30 | 0.30 | 0.25 | 0.20 | Steen & Mazumder 4th ed. Ch. 5 Table 5.1 (mil-spec black anodize; surface-condition-dependent range 0.05–0.95 noted in §10.2) |
| CFRP | 0.85 | 0.85 | 0.85 | 0.85 | Bergstrom 2007, *J. Appl. Phys.* 101, 043517 (laser absorption in carbon fibers, NIR 0.8–0.95) |
| GFRP | 0.40 | 0.40 | 0.45 | 0.55 | Hexcel & Toray datasheets; Steen & Mazumder Ch. 5 (silica-matrix NIR absorption) |
| Polycarbonate | 0.10 | 0.10 | 0.30 | 0.60 | SABIC Lexan datasheets (NIR transmission > 85% at 3 mm); C-H overtone near 1.7 µm drives 2.05 µm rise |
| ABS | 0.70 | 0.70 | 0.75 | 0.85 | Steen & Mazumder Ch. 5 (amorphous polymer NIR absorption bands) |
| EPP foam | 0.50 | 0.50 | 0.55 | 0.70 | Engineering estimate for closed-cell polypropylene foam; surface-texture-dominated |
| LiPo cell | 0.30 | 0.30 | 0.35 | 0.45 | Sandia SAND2017-xxxx thermal runaway reports; casing-dominated absorption |

Wavelength interpolation: linear between tabulated points; warning flag if outside {1.06, 1.07, 1.55, 2.05 µm}.

Emissivity ε_IR = 0.85 default for all materials (relatively minor effect below ~1000 K).

**Reference:** Carslaw & Jaeger, *Conduction of Heat in Solids* (2nd ed., Oxford, 1959); Steen & Mazumder, *Laser Material Processing* (4th ed., Springer, 2010), Ch. 5–6; ASM Handbook Vol. 2 for metallic properties; manufacturer datasheets (Hexcel, Toray) for CFRP/GFRP; Sandia Labs reports for LiPo thermal runaway thresholds.

**Validation cases:**

`test_m8_aluminum_standard`:
- Inputs: I_aim=2e6 W/m² (= 200 W/cm²), material='anodized_Al', thickness=0.002, A_lambda=0.5, backside_BC='insulated', T_ambient=293
- Expected: tau_BT in range 4–8 s (HEL-engagement-realistic flux; cross-check against Steen Ch. 5 family of worked examples for kW·cm⁻² class Al melt)
- Tolerance: 25% (engineering-level comparison)
- [v1.3 2026-04-23: I_aim corrected from 5e4 to 2e6; original value was low by 40× relative to the 4–8 s target. See revision history.]

`test_m8_cfrp_thin`:
- Inputs: I_aim=5e5 W/m² (= 50 W/cm²), material='CFRP', thickness=0.001, A_lambda=0.85
- Expected: tau_BT < 2 s (CFRP is easy target)
- Tolerance: structural only
- [v1.3 2026-04-23: I_aim corrected from 1e4 to 5e5; original value was low by 50× relative to the < 2 s target. See revision history.]

`test_m8_polycarbonate_nir`:
- Demonstrates the NIR-transparency issue: PC with default A_λ=0.10 at 1.07 µm should require ~10× more dwell than CFRP for the same thickness.
- Tolerance: structural comparison, not absolute

`test_m8_stability_criterion`:
- Verify that the simulation is numerically stable for Δx=50 µm and the stability-limited Δt across the full material list. Catches any regression in the numerical integrator.

---

### M9 — NOHD

**File:** `physics/m9_nohd.py`

**Purpose:** Computes the Nominal Ocular Hazard Distance per ANSI Z136.1 / IEC 60825-1. Reports both the top-hat (ANSI general) and Gaussian-peak (single-mode HEL) conventions. Single-mode HEL safety cases should cite the Gaussian-peak value.

**Inputs:**
| Key | Unit | Type | Description |
|---|---|---|---|
| `P0` | W | float | Output power (from M1) |
| `D` | m | float | Exit aperture (from M1) |
| `theta_diff` | rad | float | Full-angle divergence (from M1) |
| `wavelength` | m | float | From M1 |
| `t_exp` | s | float | Exposure duration (0.25 – 100) |

**Outputs:**
| Key | Unit | Description |
|---|---|---|
| `MPE` | W/m² | Maximum Permissible Exposure irradiance |
| `NOHD_tophat` | m | Top-hat convention NOHD (ANSI general form) |
| `NOHD_gausspeak` | m | Gaussian-peak convention NOHD (recommended for single-mode HEL) |
| `laser_class` | str | `'Class 1'`, `'Class 1M'`, `'Class 2'`, `'Class 3R'`, `'Class 3B'`, or `'Class 4'` |

**Equations:**

```
NOHD_tophat    = (1/θ_diff) · sqrt(4·P₀ / (π·MPE)) − D/θ_diff
NOHD_gausspeak = (1/θ_diff) · sqrt(8·P₀ / (π·MPE)) − D/θ_diff   [= sqrt(2) · NOHD_tophat]
```

**MPE calculation** per ANSI Z136.1-2014, CW beam, intrabeam viewing, correction factors C_A = C_C = 1 for the wavelength bands of interest:

Band A: Retinal hazard (0.400 µm ≤ λ ≤ 1.400 µm):
```
if t_exp < 18e-6:
    MPE_energy = 5e-3 · C_A   [J/cm²]
elif t_exp ≤ 10:
    MPE_energy = 1.8e-3 · t_exp^(3/4) · C_A   [J/cm²]
    MPE_irradiance = MPE_energy / t_exp = 1.8e-3 · t_exp^(-1/4)   [W/cm²]
else:  # t_exp > 10 s, chronic
    MPE_irradiance = 1.0e-3   [W/cm²]
```

For λ ≥ 1.050 µm, apply C_A = 10^(0.002·(λ_nm − 700)) up to C_A = 5.0 at 1050 nm.

Band B: Eye-safer (1.400 µm ≤ λ ≤ 4.000 µm):
```
if t_exp ≤ 10:
    MPE_energy = 0.56 · t_exp^(1/4)   [J/cm²]
    MPE_irradiance = MPE_energy / t_exp = 0.56 · t_exp^(-3/4)   [W/cm²]
else:  # chronic
    MPE_irradiance = 0.1   [W/cm²]
```

Band C: Far-IR (λ > 4 µm): out of scope for v1; emit assumption flag "MPE for λ > 4 µm deferred to v2" and use Band B values as a placeholder.

Convert MPE_irradiance from W/cm² to W/m²: multiply by 10⁴.

**Laser classification:**
- Class 4 whenever `P₀ > 500 mW` (the typical threshold for CW NIR lasers). For HEL systems (kW+), always Class 4. Explicitly reported for safety-case context.

**Reference:** ANSI Z136.1-2014, *Safe Use of Lasers*; IEC 60825-1:2014, *Safety of laser products — Part 1: Equipment classification*.

**Usage guidance (emitted with outputs):**

> For single-mode HEL safety cases, cite `NOHD_gausspeak`. The top-hat value is the ANSI "general form" appropriate for diffused or multimode beams; it underestimates the on-axis hazard for a low-M² Gaussian beam by a factor of √2.

**Validation cases:**

`test_m9_retinal_band_baseline`:
- Inputs: P0=1, D=0.001, theta_diff=1e-3, wavelength=1.07e-6, t_exp=0.25
- Expected: MPE ≈ 25.5 W/m² (from 1.8e-3 · 0.25^(-0.25) · C_A · 10⁴); NOHD_tophat ≈ 223 m, NOHD_gausspeak ≈ 315 m
- Tolerance: 2%
- **NOTE:** the plan document §6.9 quoted MPE ≈ 50 W/m² at 1.07 µm as a round-number band-average. The formula-derived value at t=0.25 s is **25.5 W/m² with C_A = 1** (conservative; strict ANSI Z136.1-2014 would apply C_A = 5.0 at 1.07 µm, giving MPE = 127.3 W/m² and NOHD smaller by √5 ≈ 2.24×). The tool reports the conservative no-C_A NOHD and flags the convention per §10.3 so operators can convert to the ANSI-strict value externally for an operational (less-conservative) safety case. See `docs/spec_section10_review_2026-04-23.md` §10.3 for the option-A / option-B / option-C trade and `physics/m9_nohd.py` lines 25–32, 176–183 for the always-on assumption flag.

`test_m9_eyesafer_band`:
- Inputs: same as above but wavelength=1.55e-6
- Expected: MPE ≈ 15839 W/m² (from 0.56 · 0.25^(-0.75) · 10⁴); NOHD_tophat much smaller (~9 m)
- Tolerance: 5%

`test_m9_ratio_sqrt2`:
- Verify `NOHD_gausspeak / NOHD_tophat = sqrt(2)` for any inputs. Structural test.

`test_m9_chronic_viewing`:
- t_exp=100 s, wavelength=1.07e-6
- Expected: MPE saturates at chronic limit 1e-3 W/cm² = 10 W/m²

---

### M10 — Power & Thermal Budget

**File:** `physics/m10_power_thermal.py`

**Purpose:** Computes prime power required and waste heat generated; determines whether the system can sustain the requested engagement duration based on cooling capacity and coolant thermal mass.

**Inputs:**
| Key | Unit | Type | Description |
|---|---|---|---|
| `P0` | W | float | Laser output power (from M1) |
| `eta_wallplug` | — | float | Wall-plug efficiency (0.05 – 0.50) |
| `Q_cool` | W | float | Installed cooling capacity |
| `C_thermal` | J/K | float | Coolant thermal mass |
| `dT_max` | K | float | Allowable coolant temperature rise |
| `t_engagement` | s | float | Required engagement duration (typically from M8 tau_BT) |

**Outputs:**
| Key | Unit | Description |
|---|---|---|
| `P_in` | W | Prime power draw |
| `Q_waste` | W | Waste heat generated |
| `t_sustain` | s | Maximum sustainable run-time (inf for steady-state) |
| `engagement_viable` | bool | True iff `t_engagement ≤ t_sustain` |
| `duty_cycle_limit` | — | Maximum duty cycle (if transient) |
| `engagements_per_hour` | float | At given duty cycle and engagement duration |

**Equations:**

```
P_in     = P₀ / η_wallplug
Q_waste  = P_in − P₀

# Steady-state check:
if Q_waste ≤ Q_cool:
    t_sustain = inf   # cooling matches dissipation indefinitely
else:
    t_sustain = (C_thermal · dT_max) / (Q_waste − Q_cool)

# Viability:
engagement_viable = (t_engagement ≤ t_sustain)

# Duty cycle limit (for transient mode):
# After firing for t_sustain, cooling must remove C_thermal·dT_max of stored heat
# at rate Q_cool. So recovery_time = (C_thermal·dT_max)/Q_cool.
# duty_cycle = t_sustain / (t_sustain + recovery_time)
if t_sustain < inf:
    recovery_time = (C_thermal · dT_max) / Q_cool
    duty_cycle_limit = t_sustain / (t_sustain + recovery_time)
else:
    duty_cycle_limit = 1.0

# Engagements per hour at t_engagement per engagement:
engagements_per_hour = 3600 · duty_cycle_limit / t_engagement
```

**Default parameters** (selected to support a 3 kW baseline as steady-state and a 50 kW class engagement in transient mode for ~1 minute):

| Parameter | Default | Rationale |
|---|---|---|
| `eta_wallplug` | 0.30 | Typical fiber laser wall-plug efficiency (range 0.25–0.35) |
| `Q_cool` | 15 kW | Mid-sized vehicle-mounted cooling loop |
| `C_thermal` | 200 kJ/K | Corresponds to ~50 kg of water or equivalent coolant mass |
| `dT_max` | 30 K | Typical shutdown threshold above inlet temperature |

Verification of defaults: for a 50 kW laser with these numbers, the tool correctly predicts ~59 seconds of sustained fire before thermal shutdown. For a 3 kW laser, operation is steady-state (Q_waste = 7 kW < Q_cool = 15 kW).

**Validation cases:**

`test_m10_steady_state`:
- Inputs: P0=3000, eta_wallplug=0.30, Q_cool=15000, C_thermal=200000, dT_max=30, t_engagement=5
- Expected: P_in=10000, Q_waste=7000, t_sustain=inf, engagement_viable=True
- Tolerance: 0.1% (exact arithmetic)

`test_m10_transient`:
- Inputs: P0=50000, eta_wallplug=0.30, Q_cool=15000, C_thermal=200000, dT_max=30, t_engagement=5
- Expected: P_in=166667, Q_waste=116667, t_sustain ≈ 59 s, engagement_viable=True
- Tolerance: 1%

`test_m10_insufficient_cooling`:
- Inputs: P0=100000, eta_wallplug=0.30, Q_cool=5000, C_thermal=100000, dT_max=20, t_engagement=30
- Expected: t_sustain < 30 s, engagement_viable=False
- Tolerance: 1%

---

### M11 — Validation Self-Test

**File:** `physics/m11_validation.py` (and `tests/` directory for pytest suites)

**Purpose:** Provides an in-UI button that runs the entire pytest validation suite on-demand and displays the pass/fail report. This is the safety net that catches physics regressions before they reach the user.

**Interface (v1.1 — M11 uniquely does not follow the standard `compute(inputs) -> dict` pattern because it is a runner, not a physics module):**

Public function signature:
```python
def run_validation_suite() -> dict:
    """
    Invokes pytest on the tests/ directory and returns a structured report.

    Returns:
        {
            'timestamp': str (ISO 8601),
            'total_tests': int,
            'passed': int,
            'failed': int,
            'duration_seconds': float,
            'results': {
                test_id (str): {
                    'status': 'PASS' | 'FAIL',
                    'expected': any (the claimed value or structural check),
                    'actual': any (the computed value),
                    'tolerance': str (e.g., '2%', 'structural'),
                    'reference': str (citation to SPEC §3 or external source),
                    'error_message': str (if FAIL, else empty),
                },
                ...
            }
        }
    """
```

This signature is what `ui/app.py` expects when the "Run Validation Suite" button is pressed. Implementation may wrap a pytest subprocess call or invoke pytest programmatically via `pytest.main()`.

**Interface:** 
- UI button "Run Validation Suite" in the Streamlit interface.
- When clicked, invokes `pytest` on the `tests/` directory and renders the output in a formatted table showing: test name, expected value, actual value, tolerance, pass/fail, reference citation.
- Total expected runtime: < 30 seconds (all tests are either closed-form or small numerical simulations).

**Test inventory** (managed via pytest discovery in `tests/` directory):

| Test ID | Module | Description | Tolerance |
|---|---|---|---|
| M1.1 | M1 | θ_diff vs hand calculation | 0.1% |
| M1.2 | M1 | Rayleigh range | 1% |
| M2.1 | M2 | Transmission arithmetic | 0.01% |
| M3.1 | M3 | Slant-range geometry | 0.1% |
| M4.1 | M4 | Aerosol at V=23 km, 1.07 µm | 5% |
| M4.2 | M4 | Aerosol at V=5 km (Kim) | 5% |
| M4.3 | M4 | Wavelength interpolation | exact |
| M5.1 | M5 | r₀_sph uniform Cn² | 2% |
| M5.2 | M5 | w_turb at 5 km | 2% |
| M5.3 | M5 | Spherical/plane ratio | 0.1% (structural) |
| M5.4 | M5 | r₀ at 1.5 km (near-field) | 2% |
| M5.5 | M5 | HV_5_7 ground-level slant | 2% |
| M6.1 | M6 | Dimensional check | structural |
| M6.2 | M6 | Moderate blooming (10 kW canonical) | ±30% |
| M6.3 | M6 | Low-power limit | structural |
| M7.1 | M7 | Pure diffraction at 5 km | 2% |
| M7.2 | M7 | +Turbulence at 5 km | 2% |
| M7.3 | M7 | C-UAS near-field at 1.5 km | 2% |
| M7.4 | M7 | w/σ/PIB convention consistency | exact (structural) |
| M8.1 | M8 | Aluminum standard | 25% |
| M8.2 | M8 | CFRP thin | structural |
| M8.3 | M8 | PC NIR transparency | structural comparison |
| M8.4 | M8 | Numerical stability | structural |
| M9.1 | M9 | Retinal baseline | 2% |
| M9.2 | M9 | Eye-safer band | 5% |
| M9.3 | M9 | Gauss/tophat ratio = √2 | 0.1% (structural) |
| M9.4 | M9 | Chronic viewing saturation | 2% |
| M10.1 | M10 | Steady-state case | 0.1% |
| M10.2 | M10 | Transient 50 kW case | 1% |
| M10.3 | M10 | Insufficient cooling | 1% |

Total: 30 tests.

**Validation report format** (from M11 UI button):

```
╔════════════════════════════════════════════════════════════════╗
║       HEL Engineering Calculator — Validation Report          ║
║                     [timestamp]                                ║
╠════════════════════════════════════════════════════════════════╣
║ Test ID  │ Description          │ Expected │ Actual │ Pass?   ║
╟──────────┼──────────────────────┼──────────┼────────┼─────────╢
║ M1.1     │ Diffraction divergence│ 13.55µr  │ 13.55µr│   ✓     ║
║ ...      │ ...                  │ ...      │ ...    │   ...   ║
╚════════════════════════════════════════════════════════════════╝
Summary: 30/30 PASS (0.8 s total)
Reference citations attached per test.
```

Any FAIL is reported prominently; the tool continues to operate but displays a banner warning the user that at least one physics test is failing.

---

## 4. Module Execution Order (Orchestration)

When the user clicks "Run Analysis," modules execute in strict dependency order:

```
M1 (laser source)
 └─→ M2 (beam director)
      └─→ M3 (geometry)
           └─→ M4 (atmosphere) ──┐
                └─→ M5 (turbulence)  │
                     └─→ M7 (spot+PIB) ←─┐
                          ←──── M6 (blooming) [ITERATED with M7]
                               └─→ M8 (burn-through)
                                    └─→ M10 (power/thermal)

In parallel:
M1 → M9 (NOHD)    [independent of the propagation chain]
```

The M6↔M7 iteration: start with `S_TB = 1, w_bloom = 0`; compute M7's `w_total`; pass to M6; update `S_TB, w_bloom`; re-run M7. Iterate until `w_total` changes less than 1% between iterations, max 10 iterations.

For the sweep plots (Plots A, B, C), the orchestrator calls this chain once per range point across the user-specified sweep.

---

**[Continued in Part 4 — UI mapping, orchestration, file layout, and appendices]**

## 5. UI-to-Module Mapping

The Streamlit interface aggregates user inputs into the dicts expected by each physics module. This section specifies how each UI input routes to which module input, and how each module output routes to which UI element.

### 5.1 Input Panels → Module Inputs

**Sidebar layout convention (v1.9).** All input is in the **left sidebar**. From top to bottom the sidebar contains: (1) a **Preset dropdown** listing four named scenarios defined in `ui/presets.py` ("C-UAS short range", "Counter-rocket", "Long-range surveillance", "Custom"); selecting a preset writes that scenario's full input dict into `st.session_state` and reruns, repopulating the six input sections. (2) **Six input sections** (expander widgets) in the order below; each expander's header is a plain-English section name with **no emoji**: "Laser source" / "Beam director" / "Engagement geometry" / "Atmosphere" / "Target & aimpoint" / "System resources". Default expansion state on first load: **Laser source, Engagement geometry, Target & aimpoint expanded; Beam director, Atmosphere, System resources collapsed** — same first/third/fifth-open pattern as v1.2 keyed to the new section names. Streamlit remembers user-driven expansion state within a session. (3) **"Run Analysis"** primary-accent button spanning the sidebar width. (4) **"Validate"** secondary button (invokes M11). (5) **"Share this analysis"** secondary button (renders an `st.code(url)` block per §5.3 item 7). (6) **Light/dark theme toggle** at the sidebar footer (§5.3 item 8). Every input's visible label, tooltip text, and UI unit string is read from the single source of truth at `ui/labels.py` — no user-visible string is hard-coded inside `ui/panels.py`. The `user_inputs` dict keys, default values, and sanity ranges in the tables below are unchanged from v1.8; only the visible presentation is restated.

**Section 1 — Laser source → M1**
| UI label | Input key | Unit | Default | Sanity range |
|---|---|---|---|---|
| Output power | `P0` | kW (→ W) | 3.0 | 0.1 – 100 |
| Beam quality M² | `M2` | — | 1.2 | 1.0 – 10.0 |
| Exit aperture diameter | `D` | cm (→ m) | 10.0 | 1 – 50 |
| Wavelength | `wavelength` | µm (→ m) | 1.07 | 0.5 – 5.0 |

**Section 2 — Beam director → M2, partially M7**
| UI label | Input key | Unit | Default | Sanity range |
|---|---|---|---|---|
| Optical transmission | `eta_opt` | — | 0.85 | 0.50 – 0.99 |
| Pointing jitter (per-axis 1-σ RMS) | `sigma_jit` | µrad (→ rad) | 10 | 0.1 – 1000 |

**Section 3 — Engagement geometry → M3**
| UI label | Input key | Unit | Default | Sanity range |
|---|---|---|---|---|
| Emplacement altitude AGL | `H_e` | m | 2 | 0 – 3000 |
| Slant range to target | `R` | m | 1500 | 50 – 50000 |
| Target altitude AGL | `H_t` | m | 200 | 0 – 5000 |
| Target velocity | `v_tgt` | m/s | 20 | 0 – 100 |
| Crosswind (perpendicular) | `v_perp` | m/s | 3 | 0 – 30 |

**Section 4 — Atmosphere → M4, M5**
| UI label | Input key | Unit | Default | Sanity range |
|---|---|---|---|---|
| Visibility | `V` | km | 23 | 0.5 – 50 |
| Relative humidity | `RH` | % (→ fraction) | 60 | 0 – 100 |
| Ambient temperature | `T_ambient` | °C (→ K) | 27 | -20 – 55 |
| Cn² model | `cn2_model` | enum | `HV_5_7` | constant / HV_5_7 / HV_day / HV_night |
| Cn² value (if constant) | `Cn2_value` | m^(-2/3) | 1e-14 | 1e-17 – 1e-12 |
| Ground Cn² (if HV) | `Cn2_ground` | m^(-2/3) | 1.7e-14 | 1e-16 – 1e-12 |
| HV wind speed | `v_HV` | m/s | 21 | 0 – 60 |

**Section 5 — Target & aimpoint → M7, M8**
| UI label | Input key | Unit | Default | Sanity range |
|---|---|---|---|---|
| Aimpoint diameter | `d_aim` | cm (→ m) | 5 | 0.5 – 30 |
| Material | `material` | enum | `CFRP` | 7-material set |
| Thickness | `thickness` | mm (→ m) | 2.0 | 0.1 – 20 |
| Absorptivity A_λ (override) | `A_lambda` | — | from table | 0.05 – 0.99 |
| Backside BC | `backside_BC` | enum | `insulated` | insulated / convective |

**Section 6 — System resources → M9, M10**
| UI label | Input key | Unit | Default | Sanity range |
|---|---|---|---|---|
| Wall-plug efficiency | `eta_wallplug` | — | 0.30 | 0.05 – 0.50 |
| Cooling capacity | `Q_cool` | kW (→ W) | 15 | 0 – 500 |
| Coolant thermal mass | `C_thermal` | kJ/K (→ J/K) | 200 | 10 – 5000 |
| ΔT max | `dT_max` | K | 30 | 5 – 80 |
| Exposure duration (for MPE) | `t_exp` | s | 0.25 | 0.25 – 100 |

### 5.2 Module Outputs → Tabs, Panels, and Plots

**Main-area layout convention (v1.9).** The main area is a Streamlit `st.tabs([...])` container with **six tabs in reading order**: Overview / Engagement / Target effects / Safety / Atmosphere / Diagnostics. Clicking a tab switches the view instantly (Streamlit does not re-run the physics chain on tab switch; only on Run Analysis or on changes to sidebar inputs). The same merged-result dict from `physics.orchestrator.run_full_chain` is passed to every tab renderer in `ui/outputs.py`; each renderer picks the SPEC keys it needs and delegates its visible labels / tooltips / units to `ui/labels.py`. A single-line footer provenance strip sits below the tab container on every page: `HEL Engineering Calculator · SPEC v1.9 · ARCH v1.6 · build YYYY-MM-DD`.

**Tab dispatch table.**

| Tab | Numeric content | Plot content |
|---|---|---|
| **Overview** | Engagement verdict chip (per Panel 2 rules below); six KPI cards: `P_aim` (M7), `tau_BT` (M8), `available_dwell` (M3), `I_peak` (M7), `NOHD_tophat` (M9), `P_in` (M10) | **Dwell-vs-burnthrough comparison bar** — horizontal bar chart comparing `tau_BT` and `available_dwell` with the margin gap labeled (new in v1.9) |
| **Engagement** | `P_aim`, `I_avg_aim`, `I_peak` (M7); `S_TB`, `S_opt` (M6/—); `w_diff`, `w_turb`, `w_jit`, `w_bloom`, `w_total` (M7/M5/M6); angular-error split (θ_diff_pure, θ_M²_excess, θ_turb, θ_jit); peak-irradiance ratio `S_TB · (w_diff²/w_total²)` | **Plot A — Peak intensity & PIB vs range** (carried forward from v1.8 Plot A; same X/Y curves); **Plot C — Spot-size contributions vs range** (carried forward from v1.8 Plot C); both plots gain the log-scale toggle and the curated modebar per §5.3 item 10 |
| **Target effects** | `tau_BT`, `T_surface_at_tau`, `failure_mode` (M8); `available_dwell`, `margin` (M3/derived) | **Plot B — Time-to-burn-through vs range** (carried forward from v1.8 Plot B); **NEW Plot D — Surface temperature vs time** (material failure threshold annotated as a dashed reference line); **NEW Plot E — τ_BT comparison across all 7 materials at current inputs** (horizontal bar chart grouped by material) |
| **Safety** | `NOHD_tophat`, `NOHD_gausspeak`, `laser_class` (M9); exposure duration `t_exp` echo | **NEW Plot F — NOHD hazard-zone cross-section schematic** (top-hat and Gauss-peak zones drawn as concentric half-planes extending from the emplacement; scale clearly labeled in km) |
| **Atmosphere** | Total `alpha_atm` (M4) with its component split `alpha_mol_abs / alpha_mol_scat / alpha_aer_abs / alpha_aer_scat`; computed `tau_atm(R)` at current range | **NEW Plot G — Extinction breakdown horizontal stacked bar** (replaces the v1.8 Panel 5 static table — same four components, now a stacked bar in 1/km with percentage share labels); **NEW Plot H — Transmission vs range** (log-Y optional toggle, Beer-Lambert curve from 0 to the current slant range) |
| **Diagnostics** | `assumptions_flagged` entries aggregated across M1–M10, **rendered as a severity-sorted chip list** (not a bullet wall); convergence status of the M6↔M7 loop (iterations used, converged yes/no) — rendered as a calm status card, no internal SPEC section references in user copy | — |

The **Engagement verdict chip** on the Overview tab uses the same three-tier logic as v1.8 Panel 2 (reproduced below, since this is the only Panel-2 logic that survives into v1.9 unchanged):

- Define `margin = (available_dwell − tau_BT) / tau_BT`.
- `margin ≥ 0.30` → status-chip kind **"ok"** (green + `check-circle` icon + text "ENGAGEABLE — 47% margin").
- `0.00 ≤ margin < 0.30` → kind **"warn"** (amber + `alert-triangle` icon + text "MARGINAL — 8% margin").
- `margin < 0.00` → kind **"error"** (red + `x-circle` icon + text "NOT ENGAGEABLE — exceeds dwell by 35%").
- **Edge cases:** `tau_BT ≤ 0` or undefined → "ENGAGEABLE — instantaneous" (kind "ok"); `available_dwell ≤ 0` or undefined → "NOT ENGAGEABLE — no dwell available" (kind "error"). Underlying `tau_BT` and `available_dwell` numeric values are always displayed alongside the chip in their own KPI cards so the user sees the numbers, not just the verdict.

**Hover tooltip content for carried-forward plots A, B, C** is unchanged from v1.8 (same fields, same sig-fig rules); new plots D–H follow the same unified-hover idiom (`hovermode='x unified'` for curve plots, `hovermode='closest'` for the NOHD cross-section schematic and the material comparison bar). Every plot uses the shared Plotly template from `ui/theme.py` so the palette, gridlines, axes, spike lines, and hover-box styling are identical across the app.

**Per-plot unified hover and crosshair.** Every plot sets Plotly's `hovermode='x unified'` (curves) or `'closest'` (schematics and grouped bars). Curve plots also enable spike lines on both axes (`showspikes=True, spikemode='across', spikedash='dot'`) so hovering draws a vertical + horizontal crosshair — the MATLAB-equivalent inspection behavior. Cross-plot synchronization (propagating the hovered x across all plots simultaneously) was considered for v1 but descoped in SPEC v1.6 — rationale unchanged. The user traces a single range across plots by moving the mouse to each plot in turn; within each plot, unified hover + spike lines give the multi-curve, axis-aligned read.

**Plot modebar (curated).** Every plot's `config={...}` dict keeps `zoom2d`, `pan2d`, `zoomIn2d`, `zoomOut2d`, `resetScale2d`, `toImage` and removes `lasso2d`, `select2d`, `toggleSpikelines` (spikes always on), `autoScale2d` (redundant with reset); the Plotly logo is stripped (`displaylogo=False`). The modebar becomes visible on plot-hover only so it doesn't clutter the chart at rest. For plots whose dynamic range is wide (peak intensity vs range, extinction breakdown, transmission vs range), a small `[linear / log]` radio group is rendered **above the plot** (not inside the modebar) so the axis-scale toggle is visibly engineer-legible. PNG export via `toImage` produces a 2× DPI image with the current theme baked in.

### 5.3 UI Behavior Contract

1. **No cached state between sessions, but state is shareable via URL.** Every session starts from the defaults. To share a specific input configuration with a colleague, the user clicks a "Share this analysis" button (in the sidebar) which generates a URL with the current input set encoded as query parameters (via Streamlit's `st.query_params`). Opening that URL recreates the exact input state, allowing reproducible team review. URL length stays well within browser limits because the parameter set is small (~30 numeric/enum values). JSON-file save/load remains a deferred v1.5 feature for users who prefer file-based archival; URL sharing covers the common case.

2. **Recompute-on-change with caching.** Streamlit's `@st.cache_data` decorator wraps each physics-module call. Changing a Laser-source input invalidates M1 and everything downstream; changing only a System-resources input invalidates only M9/M10.

3. **Sweep caching.** Plots A, B, C compute over a range sweep. The sweep is cached as a single array; moving the reference slider does not recompute the sweep, only re-renders the highlighted point.

4. **Assumption panel is always visible.** It cannot be collapsed; this prevents the user from inadvertently trusting results that rely on default or interpolated values.

5. **Unit labels on every input and output.** No implicit units anywhere in the UI.

6. **Validate button runs M11.** Always available in the sidebar. Does not block the main analysis flow.

7. **Share-this-analysis button.** A clearly labeled button (sidebar, near the Validate button) generates a shareable URL encoding the full current input state via `st.query_params`. Clicking the button **displays the URL in a copy-ready `st.code` block** below the button — the user selects and copies the URL manually. Rationale (SPEC v1.7): automatic clipboard writes depend on HTTPS, a user gesture, and browser clipboard permission, any of which may deny silently; a visible code block works deterministically in every Streamlit deployment (local dev, Streamlit Cloud, embedded iframes). On page load, if query parameters are present in the URL, the UI initializes input panels from those parameters instead of from defaults; if any parameter is malformed or out of its sanity range, the UI silently falls back to that input's default and adds a flag to the assumptions panel ("Input X out of range from URL, using default"). The URL-decode step runs **exactly once per session**, guarded by the `st.session_state['_url_decoded']` latch, so that subsequent Streamlit reruns (triggered by any panel widget change) do not overwrite the user's edits with the stale URL contents.

8. **Light/dark theme toggle (v1.9).** A toggle control at the sidebar footer flips the app between a dark-mode primary palette (default) and a light-mode alternate. Both palettes are defined in `ui/theme.py` as token dicts; both pass WCAG-AA contrast for every text/background pair used, verified by the one-shot `scripts/check_contrast.py` audit (not in CI; run once per palette change). Flipping the toggle re-applies the Streamlit theme **and** swaps the shared Plotly template registered under `hel_dark` / `hel_light` so every chart in every tab re-themes in one action. The toggle state is session-local — refreshing the page starts from dark mode; a cookie / persistence extension is out of scope for v1.9.

9. **Compute-time feedback (v1.9).** Clicking "Run Analysis" triggers a 1–4 s compute path. Behavior: (a) the button disables immediately and shows a subtle pulsing dot for the first 250 ms (prevents double-click); (b) at 300 ms, a thin indeterminate progress bar appears below the tab strip running edge-to-edge; (c) output cards render with a single 150 ms fade-in when the analysis completes; (d) the sidebar "Last run" indicator updates to `just now`. No modal, no full-page spinner, no "please wait" copy. If compute exceeds 6 s (guard; should not happen with current physics), the progress-bar tooltip updates to `Still working — {elapsed} s`. No cancellation button in v1.9.

10. **Always-render plot frames (v1.9).** Every plot renders its axis frame and title even when the underlying data is missing or infeasible. Infeasibility cases — infeasible geometry, `tau_BT` undefined, no `available_dwell`, sweep out-of-range — render the frame + an in-chart English advisory ("No feasible engagement at current geometry. Reduce slant range or target altitude.") instead of disappearing silently. A missing plot is indistinguishable from a broken tool; a framed plot with an advisory communicates "we looked and here's why nothing is shown." Plot heights are fixed to the values specified in `ui/theme.py` (default 360 px; hero plots 420 px; paired 320 px; cross-section schematic 280 px) so the tab layout does not jump between runs.

11. **Copy-style lint (v1.9).** User-visible strings in `ui/panels.py`, `ui/outputs.py`, `ui/plots.py`, and `ui/app.py` must not contain internal references that leak project mechanics: `SPEC §…`, `ARCH §…`, `M[0-9]` module tags, raw `assumptions_flagged` keys or `_flagged` substrings, or emoji characters (Unicode emoji ranges). `tests/test_copy_style.py` enforces this as a grep-based static check; violations fail CI. Exceptions: `ui/labels.py` (the source-of-truth mapping) is exempt; docstrings in any `ui/` file are exempt (grep scope is string literals and markdown-rendered text only); the footer provenance strip (item 12) is exempt to allow the literal "SPEC v1.9 · ARCH v1.6" version tag. Internal references remain freely used inside `physics/` docstrings, inside `assumptions_flagged` strings (which are cleaned up at render time in the Diagnostics tab), and inside any file not imported by the Streamlit runtime.

12. **Footer provenance strip (v1.9).** Every page renders a single-line strip at the bottom of the main area, below the tab container: `HEL Engineering Calculator · SPEC v1.9 · ARCH v1.6 · build YYYY-MM-DD`. The version provenance that previously lived in the page subtitle (before v1.9 the title read "HEL Engineering Calculator" with a caption "SPEC v1.7 / ARCH v1.5") is now peripheral, present for auditors but out of the first-glance view. An "About" expander below the strip opens a small card with the live-app URL, a pointer to `SPEC.md Appendix B` for the reference library, and a link to the GitHub repo.

---

## 6. File Layout

```
hel-calculator/
├── README.md                       # Landing page for GitHub repo
├── CLAUDE.md                       # Project rules for Claude Code (read every session)
├── SPEC.md                         # THIS DOCUMENT
├── ARCHITECTURE.md                 # Concrete file layout + interface definitions
├── TESTING.md                      # Validation-suite guide
├── requirements.txt                # Pinned dependencies
├── .github/
│   └── workflows/
│       └── test.yml                # GitHub Actions CI (pytest on every commit)
├── physics/                        # Layer 1: Physics core (pure Python, no UI)
│   ├── __init__.py
│   ├── m1_laser_source.py
│   ├── m2_beam_director.py
│   ├── m3_geometry.py
│   ├── m4_atmosphere.py
│   ├── m4_data_tables.py           # α_mol, α_aer tables
│   ├── m5_turbulence.py
│   ├── m6_blooming.py
│   ├── m7_spot_pib.py
│   ├── m8_burnthrough.py
│   ├── m8_material_tables.py       # ρ, cp, k, T_fail, A_λ per material
│   ├── m9_nohd.py
│   ├── m10_power_thermal.py
│   ├── m11_validation.py           # Self-test runner (calls pytest)
│   └── orchestrator.py             # Chain coordinator (M1→M10, M6↔M7 iteration)
├── tests/                          # Layer 2: Validation suite
│   ├── __init__.py
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
│   └── test_convention_consistency.py  # Structural tests across modules
├── ui/                             # Layer 3: Streamlit interface
│   ├── __init__.py
│   ├── app.py                      # Main Streamlit entry point
│   ├── panels.py                   # The 6 input panels
│   ├── outputs.py                  # The 5 output panels
│   ├── plots.py                    # Plotly plot constructors (A, B, C)
│   └── auth.py                     # Shared-credential login
└── docs/                           # Reference material
    ├── Plan_v0p8.docx              # Project plan (reference)
    └── references.md               # Bibliography
```

**Strict separation:**
- `physics/` never imports from `ui/` or `tests/`
- `tests/` imports from `physics/` only
- `ui/` imports from `physics/` only
- No cross-imports between the three layers

This enforces the three-layer architecture from plan §2.3.

---

## 7. Dependency Pinning (`requirements.txt`)

```
streamlit==1.38.0
numpy==1.26.4
scipy==1.13.1
plotly==5.22.0
pytest==8.3.2
pandas==2.2.2
```

Python version: 3.11 or 3.12 (specified in Streamlit Cloud config, not requirements.txt).

Any update to these versions requires re-running the validation suite and verifying all 30 tests still pass within tolerance before the commit is merged to main.

---

## 8. GitHub Actions Workflow (`.github/workflows/test.yml`)

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
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: Run validation suite
        run: pytest tests/ -v --tb=short
```

Streamlit Cloud observes the main branch; CI pass is a soft requirement (Streamlit Cloud deploys regardless), but a failing CI status is visibly flagged in the GitHub UI and Claude Code treats a failing `test.yml` run as a block on claiming the commit as "done."

---

## 9. Implementation Checklist for Claude Code

When implementing each module in Phase 1 through Phase 5, Claude Code shall satisfy this checklist before claiming the module complete:

**Per-module checklist:**
- [ ] Module file exists at specified path with the specified function signature
- [ ] All inputs validated for type and range (raises `ValueError` with descriptive message if out-of-range)
- [ ] All outputs in the dict with specified keys and units
- [ ] `assumptions_flagged` list populated appropriately
- [ ] All equations match SPEC.md letter-for-letter (no "optimizations" that change formulas)
- [ ] Reference citation in the module docstring
- [ ] Every validation case from the SPEC is implemented as a pytest test
- [ ] All pytest tests pass within stated tolerance
- [ ] Module is pure: no file I/O, no network, no global state, no UI dependencies
- [ ] Module does not import from `ui/` or `tests/`

**Per-phase checklist:**
- [ ] All modules in the phase satisfy the per-module checklist
- [ ] CI is green on main branch
- [ ] Streamlit Cloud deploys and the tool loads at the URL
- [ ] User has reviewed and accepted the phase deliverable

**When the SPEC is wrong:**
If during implementation Claude Code finds that SPEC.md contains an error — a wrong equation, a wrong tolerance, a missing input — the procedure is:
1. STOP implementation on that module
2. Describe the problem to the user in chat
3. Wait for user decision: "fix SPEC first, then proceed" or "revert and re-scope"
4. Update SPEC.md with a dated note in the affected section
5. Resume implementation against the corrected SPEC

Do NOT silently fix errors in code without updating the SPEC. The SPEC is the contract; the code implements the contract. Divergence between the two is a bug to be corrected at the SPEC level, not worked around in the code.

---

## 10. Open Items Deferred to Implementation Review — status after 2026-04-23 review

The six items below were flagged HIGH UNCERTAINTY at Phase 0 contract time. After Phase 2 implementation completed, each was reviewed in `docs/spec_section10_review_2026-04-23.md`; this section records the disposition accepted by the user on that date. None required a formula or validation-case change for v1.

1. **α_mol tables — accepted for v1, v2 refinement path documented.** McClatchey-family engineering placeholders verified correct within ±50% and correct in ordering against band-edge structure (see review memo §10.1). Acceptable for tool-level trade studies where the downstream ±25% test tolerances dominate; not acceptable for formal program safety cases — HITRAN/MODTRAN-derived replacement is a v2 refinement.

2. **A_λ table — accepted for v1, per-row citations added.** Current numeric values unchanged. §3 M8 A_λ table now carries a `Primary source` column with one literature citation per material row (Steen & Mazumder Ch. 5 for anodized Al and polymer bands; Bergstrom 2007 for CFRP; SABIC/Hexcel/Toray datasheets; Sandia thermal-runaway reports for LiPo). Users with measured or program-specific values should still override via the UI checkbox-gated `A_λ` input.

3. **MPE at 1.07 µm — CLOSED.** v1 adopts the conservative **no-C_A** convention (strict ANSI Z136.1-2014 C_A = 5.0 at 1.07 µm would shrink NOHD by √5 ≈ 2.24×; this tool overstates the hazard zone deliberately). Option confirmed by user 2026-04-23. The `assumptions_flagged` entry in `physics/m9_nohd.py` lines 176–183 documents the convention and tells operators how to convert to the ANSI-strict value externally. §3 M9 test-note wording corrected to remove the false implication that C_A was being applied.

4. **Blooming broadening factor 0.3 — accepted for v1.** NRL-derived engineering estimate. Sprangle et al (NRL/MR/6790-08-9141) is already cited in §3 M6 reference line as the empirical basis for the 0.3 multiplier and the multi-physics context. HELEEOS benchmark path available for programs with access.

5. **available_dwell heuristic — DEFERRED TO v2.** The `2·R·tan(FOV/2)/v_tgt` formula is an explicit first-order engagement-basket estimate; a full tracker-dependent model (slew-rate limits, target maneuver, line-of-sight masking, multi-target prioritization) is out of v1 scope by original plan §10.2.

6. **Convective backside BC — accepted for v1, citation added.** `h_conv = 10 + 6.2·sqrt(v_tgt)` cross-checked against Incropera & DeWitt 6th ed. Ch. 7 flat-plate correlation (`Nu_L = 0.664·Re_L^(1/2)·Pr^(1/3)` + natural-convection floor) within ±20% per review memo §10.6. Acceptable for v1; program-specific vehicle data overrides via UI input when available.

Total SPEC edit footprint from this review: citation-column addition to §3 M8 A_λ table, tightened HIGH UNCERTAINTY wording on α_mol, inline Incropera citation on M8 convective BC line, corrected M9 test-note wording, and this revised §10 summary. **Zero physics formulas touched. Zero validation-case expected values touched. `pytest tests/` passes unchanged.**

---

## Appendix A — Module Dependency Graph (concrete)

```
USER INPUTS
    │
    ├─→ Laser source (P0, M²,D,λ) ──┬─→ M1 ──┬──────────────┐
    │                               │        │              │
    ├─→ Beam director (η_opt,σ_jit) ┼─→ M2   │              ↓
    │                               │        │           M9 (NOHD)
    ├─→ Engagement geometry ────────┼─→ M3   │              │
    │                               │        ↓              │
    ├─→ Atmosphere (atm,Cn²)    ────┼─→ M4 → M5             │
    │                               │   │     │             │
    ├─→ Target & aimpoint       ────┼───│─────│─┐           │
    │                               │   │     │ │           │
    └─→ System resources        ────┼───│─────│─│─→ M10     │
                                    │   ↓     ↓ │   │       │
                                    └─→ M7 ←→ M6 │   │       │
                                         │       │   │       │
                                         ↓       │   │       │
                                         M8 ←────┘   │       │
                                         │           │       │
                                         ↓           ↓       ↓
                                     PLOTS A–H   TABS (1–6)  SAFETY TAB
```

---

## Appendix B — Reference Library

Primary sources cited in this SPEC:

1. **Andrews, L. C. & Phillips, R. L.** *Laser Beam Propagation through Random Media* (2nd ed., SPIE Press, 2005). Ch. 6 (r₀, w_turb), Ch. 12 (atmospheric channel models).

2. **Siegman, A. E.** *Lasers* (University Science Books, 1986). Ch. 17 (Gaussian beam propagation, M² formalism).

3. **Born, M. & Wolf, E.** *Principles of Optics* (7th ed., Cambridge, 1999). Ch. 8 (Gaussian diffraction, PIB).

4. **Gebhardt, F. G.** "Twenty-five years of thermal blooming: an overview," *Proc. SPIE* 1221 (1990), pp. 2–25. (Gebhardt N_D formulation, 4√2 prefactor.)

5. **Gebhardt, F. G.** "High-power laser propagation," *Applied Optics* 15(6), 1479–1493 (1976). (Original blooming derivation.)

6. **Carslaw, H. S. & Jaeger, J. C.** *Conduction of Heat in Solids* (2nd ed., Oxford, 1959). (Finite-difference heat equation, boundary conditions, Stefan condition.)

7. **Steen, W. M. & Mazumder, J.** *Laser Material Processing* (4th ed., Springer, 2010). Ch. 5–6 (laser-matter interaction, metal processing).

8. **ANSI Z136.1-2014**, *Safe Use of Lasers*. (MPE formulas, laser classification, NOHD.)

9. **IEC 60825-1:2014**, *Safety of laser products — Part 1*. (Complementary MPE tables.)

10. **Kruse, P. W.** *Elements of Infrared Technology* (Wiley, 1962). (Aerosol extinction formula.)

11. **McClatchey, R. A., et al.** "Optical Properties of the Atmosphere," AFCRL-TR-72-0497 (1972). (Molecular absorption baselines.)

12. **Hufnagel, R. E.** "Variations of atmospheric turbulence," *OSA Technical Digest* (1974); **Valley, G. C.** "Isoplanatic degradation of tilt correction and short-term imaging systems," *Applied Optics* 19(4), 574 (1980). (HV turbulence profile.)

13. **Perram, G. P., et al.** *An Introduction to Laser Weapon Systems* (Directed Energy Professional Society, 2010). (HEL engineering conventions, trade-study methodology.)

---

## Appendix C — Glossary

(Reference plan document §Appendix A for the full glossary. Key terms for SPEC purposes:)

- **1/e² radius (w):** the radial distance at which a Gaussian beam's intensity falls to 1/e² ≈ 13.5% of peak. Canonical beam-size measure throughout this SPEC.
- **assumptions_flagged:** first-class list output from every module; aggregated to Panel 4.
- **engagement_viable:** Boolean result indicating whether delivered dwell ≥ required burn-through time.
- **PIB:** Power-in-the-Bucket; fraction of total transmitted power inside aimpoint disk.
- **Strehl ratio:** ratio of actual to diffraction-limited peak irradiance; captures phase-only wavefront distortions.
- **Gebhardt N_D:** dimensionless thermal-blooming distortion number.
- **NOHD:** Nominal Ocular Hazard Distance per ANSI Z136.1.
- **r₀ (Fried):** spatial coherence length of the atmospheric channel, spherical-wave form in this SPEC.

---

**END OF SPEC.md v1.9**
