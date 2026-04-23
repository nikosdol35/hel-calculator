# ARCHITECTURE.md — HEL Engineering Calculator

**Version:** 1.3 (Phase 2 UI slice 2a: orchestrator relocation)
**Complements:** `SPEC.md` §6 (file layout) and project plan v0.8 §2.3 (three-layer separation)
**Scope:** Concrete implementation map — file paths, function signatures, import rules, data flow.

**Revision history:**
- v1.0 — initial draft
- v1.1 — post-audit fixes: (a) M9 moved earlier in orchestrator pseudocode to reflect its true independence from the propagation chain; (b) timing estimates in §5.2 explicitly flagged as pre-implementation, to be replaced with Phase 1 benchmark; (c) §6 extended to cover all UI files (added §6.6 orchestrator, §6.7 style, §6.8 __init__); (d) M11 row in §4.2 aligned with SPEC.md v1.1 explicit signature.
- v1.2 — UI alignment with SPEC v1.2: cross-references added so that each of the four UI enhancements added in SPEC v1.2 has a corresponding structural anchor in this document. (a) §6.1 (app.py) now lists URL state encode/decode and the cross-plot hover-sync callback as responsibilities; (b) §6.3 (panels.py) notes default expansion state, emoji iconography, and that initial values come from URL params if present; (c) §6.4 (outputs.py) cross-references the three-tier verdict in SPEC §5.2 Panel 2; (d) §6.5 (plots.py) notes that figures use Plotly `hovermode='x unified'` per SPEC §5.2; (e) §5.1 page-load sequence note added (URL decode happens before panel rendering on first run). No file structure changes, no function-signature changes, no new files. Color constants in §6.7 already aligned (`COLOR_SUCCESS / COLOR_WARNING / COLOR_CAUTION` were defined in v1.0 and are now consumed by SPEC v1.2 verdict logic).
- v1.3 (2026-04-23) — **orchestrator relocated from `ui/` to `physics/`.** The chain coordinator is pure Python (no Streamlit imports) and the M6↔M7 fixed-point loop is physics-critical, so it belongs in Layer 1 where `tests/` can import it directly under the §2 import rules. Updates: (a) §3 repo tree moves `orchestrator.py` under `physics/` and drops it from `ui/`; (b) §5.1 step 2 and §5.3 pseudocode headers updated to the new path; (c) §6.1 (app.py) gains a responsibility to wrap `physics.orchestrator.run_full_chain` in `@st.cache_data` (the caching wrapper lives in `app.py` so `orchestrator.py` stays pure); (d) §6.6 deleted, §6.7 renumbered to §6.6, §6.8 renumbered to §6.7; (e) UI layer file count corrected from 8 to 7 (6 functional + 1 `__init__.py`). No function-signature changes, no physics behavior changes. Resolves the self-contradiction in v1.1–1.2 §6.6 which said the orchestrator was "testable without Streamlit running" while §2 forbade `tests/` from importing from `ui/`.

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
│   └── test_import_rules.py             ← Verifies Layer 1 has no UI imports
│
├── ui/                             ← LAYER 3: Streamlit interface
│   ├── __init__.py
│   ├── app.py                      ← Streamlit entry point (run with `streamlit run`)
│   ├── auth.py                     ← Shared-credential login gate
│   ├── panels.py                   ← The 6 input panels (A–F)
│   ├── outputs.py                  ← The 5 numeric output panels
│   ├── plots.py                    ← Plotly chart constructors (A, B, C)
│   └── style.py                    ← Shared CSS/color constants
│
└── docs/                           ← Reference material
    ├── Plan_v0p8.docx              ← The project plan (read-only reference)
    ├── references.md               ← Bibliography (matches SPEC Appendix B)
    └── CHANGELOG.md                ← Human-readable version history (optional)
```

**Total files:** roughly 40, most of them small (one module = one file, one test file per module, one UI file per concern). Every file has a single, clearly named purpose.

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

5. Result dict flows to `ui/outputs.py`, which renders the 5 numeric panels, and to `ui/plots.py`, which renders plots A, B, C via Plotly.

**Page-load sequence (first run, before any user click):** before §5.1 step 1 above can apply, `ui/app.py` performs URL-parameter decoding once per session. If `st.query_params` is non-empty, each parameter is parsed, range-checked against the SPEC §5.1 sanity ranges, and either accepted (becoming the panel's initial value) or silently dropped with a flag added to the assumptions panel ("Input X out of range from URL, using default"). If `st.query_params` is empty, all panels initialize from the SPEC §5.1 defaults. Only after this initialization do the panel widgets render in the sidebar.

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

1. Check authentication (`ui/auth.py`)
2. On first page load, decode any `st.query_params` present in the URL into an initial input dict (per SPEC §5.3 item 1); fall back to defaults for missing or malformed parameters and flag any out-of-range values for the assumptions panel
3. Lay out the page: left sidebar = 6 input panels, main area = plots + output panels
4. Wire up the "Run Analysis" button and result rendering; the click handler calls `physics.orchestrator.run_full_chain` via the `@st.cache_data`-wrapped helpers defined in §5.3 — the wrappers live in `app.py` (not in `orchestrator.py`) so the orchestrator stays pure Python and directly testable from `tests/`
5. Wire up the "Share this analysis" sidebar button (per SPEC §5.3 item 7) which encodes the current input dict to `st.query_params` and copies the resulting URL to the clipboard
6. Wire up the cross-plot hover synchronization callback (per SPEC §5.2): when the user hovers on Plot A, B, or C, the hovered x-coordinate is propagated to the other two charts

Total expected length: 80–120 lines (was 60–100 in v1.1; URL handling and hover-sync callback add ~15–20 lines).

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

All six panels are Streamlit `st.expander` widgets in the sidebar. Per SPEC §5.1, each expander's label includes a leading emoji icon (A `🔦`, B `🎯`, C `📐`, D `🌫️`, E `🛡️`, F `⚙️`), and default expansion state on first load is **A, C, E expanded; B, D, F collapsed**. Each input is a `st.number_input` or `st.selectbox` with explicit min/max matching SPEC sanity ranges. Initial values for each input come from the URL-decoded dict produced by `ui/app.py` on page load (per SPEC §5.3 item 1) when present, otherwise from the defaults in SPEC.md §5.1.

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

`render_panel_2_engagement` implements the three-tier verdict (ENGAGEABLE / MARGINAL / NOT ENGAGEABLE) per SPEC §5.2 Panel 2, using the `COLOR_SUCCESS / COLOR_WARNING / COLOR_CAUTION` constants from `ui/style.py` (§6.7) for the traffic-light indicator. Function signatures are unchanged from v1.1; the verdict logic lives inside the function body.

### 6.5 `ui/plots.py` — Plotly constructors

```python
def plot_a_on_target_performance(sweep: list[dict]) -> plotly.graph_objects.Figure:
    """Plot A: I_peak and PIB vs range, with dual y-axis."""

def plot_b_time_to_burnthrough(sweep: list[dict]) -> plotly.graph_objects.Figure: ...
def plot_c_beam_diameter_breakdown(sweep: list[dict]) -> plotly.graph_objects.Figure: ...
```

Each returns a Plotly `Figure` object that `ui/app.py` passes to `st.plotly_chart`. No global state; pure constructors. Per SPEC §5.2, each figure sets `hovermode='x unified'` and populates hover tooltips with the per-plot content specified there (Plot A: range/I_peak/PIB/S_TB/τ_atm; Plot B: range/tau_BT/dwell/margin; Plot C: range/curve diameter/total/curve label). The cross-plot hover synchronization callback that propagates the hovered x-coordinate across all three charts lives in `ui/app.py` (§6.1), not here, to keep `plots.py` constructors pure and stateless.

### 6.6 `ui/style.py` — shared visual constants

```python
# Color palette (color-blind-safe, consistent across plots)
COLOR_PRIMARY   = "#1f4e79"
COLOR_REFERENCE = "#808080"  # diffraction-limited reference curves
COLOR_SUCCESS   = "#2e7d32"
COLOR_WARNING   = "#e65100"
COLOR_CAUTION   = "#bf360c"

# Plot sizing defaults
PLOT_HEIGHT_PX = 420
```

Shared by `plots.py` and `outputs.py`. No logic, only constants.

### 6.7 `ui/__init__.py`

Empty (by convention) — marks `ui/` as a Python package. No exports at the package level; all code is reached via explicit module imports (`from ui import app`, `from ui.panels import collect_all`, etc.). Cross-layer imports follow the same idiom: `from physics.orchestrator import run_full_chain`.

**UI layer total: 7 files** (6 functional + 1 `__init__.py`).

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

**END OF ARCHITECTURE.md v1.1 (Phase 0 draft, post-audit fixes)**
