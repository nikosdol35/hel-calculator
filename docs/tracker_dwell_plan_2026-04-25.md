# Plan: Tracker-supported dwell + threat-trajectory model

**Date:** 2026-04-25
**Status:** Draft, ready for user review. No code work has started.
**File destination:** This plan-file copy is the canonical draft. PR 1 will copy this content to `docs/tracker_dwell_plan_2026-04-25.md` (mirroring how the math-tab plan landed in `docs/`).
**Author:** Claude. Twelve gaps caught in a self-review pass; new plot strategy folded in.

---

## 1 · Context & motivation

The `available_dwell` number this tool computes is wrong for a tracker-equipped director. The current `available_dwell = 2·R·tan(FOV/2) / v_tgt` is the time a target takes to *cross* a 5° FOV at constant lateral velocity, **assuming the director stares**. It was deliberately scoped as an engineering placeholder when we deferred the tracker model to v2 (SPEC §10.5; validation Package 4 closeout in `validation/uncertainty_closeout.md`).

The user has specified that:
1. The director **tracks** the target (PTU + LOS + zoom). FOV-crossing time is no longer the relevant constraint.
2. The threat model is the **target approaching to eliminate the laser site**. The engagement window is bounded by *time-until-target-reaches-its-release-range*, not by any operator-evasion estimate.
3. The two geometries that matter are **head-on closing** and **lateral pass**, both with the trajectory tracked through the engagement.

This change resolves SPEC §10.5. It also requires **time-varying flux** in M8 because the slant range — and therefore the on-target irradiance — changes throughout the engagement.

This is a real physics-scope change (CLAUDE §7.2 explicitly listed tracker-dependent dwell as v2-deferred). It must follow the CLAUDE §4.3 paired-edit procedure: SPEC update first, then code, then tests.

**User-confirmed design decisions (questions answered 2026-04-25):**
- Head-on engagement-end = user-input `R_min` (standoff range)
- Lateral engagement window = from R_detect inbound to closest approach
- M8 model = step the heat PDE forward with time-varying flux
- Stare mode = removed entirely (tracker-only)
- Plot K (operational envelope heatmap) = compute-on-click
- New plot stack-rank = all four (H, I, J, K)

---

## 2 · New input contract

### Inputs to add

| Key | Units | Range | Purpose |
|---|---|---|---|
| `R_detect` | m | [50, 50_000] | Slant range at which target is first detected and engaged |
| `R_min` | m | [10, 5_000] | Engagement-end standoff. Head-on: target's release / danger range. Lateral: closest-approach distance (perpendicular standoff) |
| `engagement_geometry` | str | `"head_on"` \| `"lateral"` | Threat geometry |

### Inputs to remove

- `_FOV_DEG_DEFAULT = 5°` (in `physics/m3_geometry.py`)
- `R` (current "user-input slant range") — replaced by `R_detect` and the dynamic `R(t)`
- `v_perp` — collapsed into `v_tgt` (now interpreted along the threat trajectory)

### Inputs whose semantics change

- `v_tgt` is now the **closing speed** for head-on, or the **lateral speed** for lateral pass. Single quantity meaning "target velocity along the threat trajectory".
- `sigma_jit` becomes "total beam-director jitter (mount + tracker residual)"; tooltip updated. Future v3 may split into `sigma_jit_mount` + `sigma_jit_tracker`.

### Validator constraints

- For both geometries: `R_detect ≥ R_min` (start farther than the engagement-end range; geometrically required for lateral since slant = √(R_min² + axial²)).
- `v_tgt ≥ 0`. Stationary case (`v_tgt < 0.1 m/s`) handled specially — see §3.4.

### Defaults applied if user doesn't override (PR 1 may revise)

- `R_min` default: **100 m** (typical small-drone payload release range).
- `engagement_geometry` default: **"head_on"** (more conservative threat assumption).

---

## 3 · Trajectory model

A new module `physics/m_trajectory.py` (or a function block inside M3 — code review at PR time) provides closed-form trajectory functions. No quadrature needed.

### 3.1 — Head-on geometry

Target approaches the director along the LOS at constant `v_tgt`, from `R_detect` down to `R_min`.

$$R(t) = R_\text{detect} - v_\text{tgt} \cdot t \qquad t \in [0,\; t_\text{dwell}]$$

$$t_\text{dwell} = \dfrac{R_\text{detect} - R_\text{min}}{v_\text{tgt}}$$

### 3.2 — Lateral geometry

Target flies a straight perpendicular line past the director with closest-approach distance `R_min`. From R_detect inbound to the closest-approach moment (per user decision).

Define `x_0 = √(R_detect² − R_min²)` — the axial distance from closest approach at t=0.

$$R(t) = \sqrt{R_\text{min}^{\,2} + (x_0 - v_\text{tgt} \cdot t)^{\,2}}$$

$$t_\text{dwell} = \dfrac{x_0}{v_\text{tgt}} = \dfrac{\sqrt{R_\text{detect}^{\,2} - R_\text{min}^{\,2}}}{v_\text{tgt}}$$

### 3.3 — Boundary cases

- `R_detect = R_min`: degenerate, `t_dwell = 0`. Validator rejects with a descriptive message.
- `v_tgt < 0.1 m/s`: stationary target. Treat as a single-point engagement at `R = R_detect`; `t_dwell = 60 s` (the M8 timeout); integrate the heat PDE at constant range. This is the v1 "single-point" model preserved as the stationary edge case.

### 3.4 — M3 outputs after the change

| Old key | New equivalent | Notes |
|---|---|---|
| `R_slant` | `R_detect` | Initial-detection slant; what M1-M9 use for one-shot evaluation |
| `available_dwell` | Trajectory-derived value (formulas above) | Same key, new semantics |
| `R_h`, `elevation_angle` | Computed at `R_detect` | Kept for safety / NOHD reporting |
| **NEW** `R_at_dwell_end` | `R_min` (both geometries by construction) | Where the engagement window ends |

---

## 4 · M8 with time-varying flux

### What changes

M8 today: takes a scalar `I_aim`, integrates `∂T/∂t = α·∂²T/∂x²` with constant front-face flux.

M8 after: takes a **flux callable** `I_aim(t)`. At each PDE timestep, evaluate the callable to get the current absorbed flux. Stop on `T_surface ≥ T_fail` OR `t ≥ t_dwell` (whichever first).

Backward-compatibility: a scalar `I_aim` continues to work — wraps in `lambda t: I_aim`. Existing v1-style tests stay green.

### What this doesn't change

- CFL safety factor (0.4)
- 50 µm grid spacing
- Failure-mode classification logic
- Tabulated material properties

### New M8 outputs

| New key | Type | Meaning |
|---|---|---|
| `R_at_kill` | float \| None | Slant range at moment of failure (None if no kill) |
| `failure_mode` extension | str | New value: `"engagement_ended_at_R_min"` (target reached engagement-end without burn-through). Existing values still used. |

---

## 5 · Orchestrator restructure with sub-sampling

The orchestrator currently chains M1 → M2 → M3 → M4 → M5 → M6↔M7 (iterated) → M8 → M9 → M10 once per call. New chain:

```
   M1, M2 (engagement-invariant scalars: w0, zR, P_exit, etc.)
   M3 (compute t_dwell from R_detect, R_min, geometry)
   M9 (uses M1 only — geometry-independent — unchanged)

   ┌─ TRAJECTORY LOOP (driven by M8 PDE solver) ─────────────────────┐
   │   At each PDE step (~1–10 ms of engagement time):               │
   │     1. R(t) = trajectory_R_of_t(geometry, ...)                  │
   │     2. (sub-sampled every ~50–100 ms; cached + interpolated)    │
   │        M4 at R(t): tau_atm, alpha components                    │
   │        M5 at R(t): r0_sph, w_turb (HV-5/7 path integral)        │
   │        M6↔M7 fixed-point at R(t): N_D, S_TB, w_total, I_avg_aim │
   │           (warm-started from previous sub-sample's converged    │
   │           w_total — typically 1-2 iterations vs 2-4 cold)       │
   │     3. q(t) = A_lambda · I_avg_aim(t) − ε·σ·(T⁴ − T_amb⁴)       │
   │     4. PDE step forward with q(t)                               │
   │     5. If T_surf ≥ T_fail: kill at R(t); break                  │
   │     6. If t ≥ t_dwell: timeout; break                           │
   └─────────────────────────────────────────────────────────────────┘

   M8 result: tau_BT, R_at_kill, T_surface_peak, E_delivered, failure_mode
   M10 (with extended engagement_viable definition — see §6)
```

### Performance considerations

- M6↔M7 Picard fixed-point now runs once per upstream sub-sample (~40–80 sub-samples per engagement). Warm-start from previous converged value drops typical iteration count from 2–4 to 1–2.
- HV-5/7 quad integration cached: re-evaluate when R(t) changes by more than a tunable threshold (default 5 %).
- Realistic per-call wall-time: 0.5–2 s on the canonical scenario. Acceptable interactively.
- The 30-point R_detect sweep on the Engagement tab becomes 30 × ~1 s = ~30 s total. Streamlit cache keeps subsequent renders instant.

### New per-trajectory orchestrator outputs

| New key | Type | Meaning |
|---|---|---|
| `R_at_kill` | float \| None | Already in M8; passes through |
| `I_peak_max` | float | Maximum on-target I_peak across the trajectory |
| `I_avg_aim_max` | float | Same, average-in-bucket version |
| `trajectory_R` | tuple[float] | Sampled R(t) for plotting |
| `trajectory_t` | tuple[float] | Sampled time axis |
| `trajectory_I_peak` | tuple[float] | I_peak vs time |
| `trajectory_I_avg_aim` | tuple[float] | I_avg_aim vs time |
| `trajectory_T_surface` | tuple[float] | Surface temperature vs time |
| `trajectory_E_cumulative` | tuple[float] | Cumulative absorbed energy vs time |
| `trajectory_d_spot` | tuple[float] | Spot diameter vs time (for spot-tightening visual) |
| `trajectory_PIB` | tuple[float] | PIB vs time |

---

## 6 · SPEC changes (paired per CLAUDE §4.3)

**No code lands until SPEC is reviewed and accepted at PR 1.**

### SPEC §3 M3 (geometry)

- Remove FOV-based dwell formula and the 5° constant
- Replace with the two new closed forms (head-on, lateral) — §3 of this plan
- Add new inputs (`R_detect`, `R_min`, `engagement_geometry`); remove `R` and `v_perp`; redefine `v_tgt`
- Add `R_at_dwell_end` output
- Add validator-level rejection of `R_detect < R_min` and stationary-target degenerate handling

### SPEC §3 M8 (burn-through)

- Replace "constant `I_aim`" with "time-dependent `I_aim(t)` driven by trajectory R(t)"
- Add `R_at_kill` output and the new failure_mode value `"engagement_ended_at_R_min"`
- Heat PDE itself unchanged — only the boundary-condition specification

### SPEC §3 M10

- `engagement_viable` definition extends to: `(tau_BT ≤ t_dwell) AND (R_at_kill ≥ R_min) AND thermal_budget_ok`
- The R_at_kill clause is logically redundant with the τ_BT clause but explicit

### SPEC §4 (execution order)

- Document the new trajectory loop with sub-sampling

### SPEC §10.5 (HIGH UNCERTAINTY)

- Disposition changes from "deferred to v2" to **CLOSED** with pointer to the new M3 + M8 trajectory model

### SPEC §3 M9 — explicit no-change note

- M9 outputs (NOHD, MPE, laser_class) depend only on (P0, M², D, λ, t_exp). They are geometry-independent and **do not change** under the new model. SPEC notes this explicitly so reviewers know it was considered, not overlooked.

### Revision history

Bump SPEC to **v2.0** (the major-version-worthy change). Record: "tracker-supported dwell model resolves §10.5; M3/M8/M10 contract revised; v1 stare-mode removed."

(If user prefers v1.x with a major-revision annotation, easy swap at PR 1.)

---

## 7 · UI changes

### Sidebar (Panel C — Engagement geometry)

- **Add** dropdown: `Engagement geometry` → `"Head-on (closing)"` | `"Lateral (perpendicular pass)"`
- **Add** numeric input: `Detection range R_detect` (m, default 1500) — replaces today's `R`
- **Add** numeric input: `Standoff range R_min` (m, default 100)
- **Rename** `v_tgt` tooltip to: "Target velocity along the threat trajectory (closing speed for head-on, lateral speed for pass-by)"
- **Remove** `v_perp` field — collapsed into the trajectory model

### Verdict chip enhancement (Overview tab)

Today's chip: "Engageable" / "Marginal" / "Not viable".

After: carries operational specifics:
- "Kill at t = 2.3 s, range 280 m" (engageable)
- "Marginal — kill near R_min boundary" (marginal)
- "No kill — target reached R_min at t = 4.4 s" (not viable)

Specific numbers make the verdict actionable.

---

## 8 · Plot strategy — existing plots updated + four new

### 8.1 — Existing plots: keep / modify / remove

| Plot | Today | Under new model | Action |
|---|---|---|---|
| **A** — On-target performance | I_peak, PIB, S_TB, τ_atm vs slant range | I_peak_max, mean PIB, S_TB at closest approach vs R_detect | **Modify** — same axes, new semantics |
| **B** — Time to burn-through vs dwell | τ_BT vs available_dwell vs range | τ_BT achieved vs t_dwell vs R_detect | **Keep** — formula updates |
| **C** — Beam diameter breakdown | 5 contributors vs range | At closest approach (constant per scenario!) — degenerate | **REPLACE** with C' (spot tightening through trajectory) |
| **D** — N_D distortion | N_D vs range | N_D at closest approach (most stressing) vs R_detect | **Modify** — semantic update |
| **E** — Engagement margin | (dwell − τ_BT)/τ_BT % vs range | (t_dwell − τ_BT)/τ_BT % vs R_detect | **Keep** — same formula, new dwell |
| **G** — Spot vs bucket | d_spot vs bucket vs range | d_spot at closest approach vs bucket vs R_detect | **Modify** — semantic update |
| Overview hero (dwell vs τ_BT bars) | Single-point bars | Same, but with new t_dwell | **Modify** — labels |
| Target effects, Safety, Atmosphere, Diagnostics | All single-point | Atmosphere "transmission vs range" stays as a static reference; rest update labels only | **Light modify** |

### 8.2 — Plot C' (REPLACES Plot C) — Spot tightening through trajectory

For one engagement at one R_detect: d_spot vs the trajectory's slant range (R_detect → R_min). The curve drops as the target closes (smaller spot, tighter focus). Bucket diameter as horizontal reference line. Shaded "spot exceeds bucket" region.

Answers: "during this engagement, how does the spot evolve vs. the bucket?"

### 8.3 — NEW Plot H — Engagement profile timeline (answers Q1: "what does an engagement actually look like?")

For one engagement, four stacked panels sharing a time x-axis:

- **Panel 1 — R(t):** trajectory itself. Head-on diagonal; lateral hyperbolic. Log y-axis.
- **Panel 2 — I_peak(t), I_avg_aim(t):** irradiance climbing as target closes. Two traces.
- **Panel 3 — T_surface(t):** heat-solver surface temperature with T_fail reference and kill-moment marker.
- **Panel 4 — E(t) cumulative absorbed:** integrated absorbed energy.

Vertical dashed line at the kill moment crosses all four panels.

**Why it earns a slot:** answers "what happens during my engagement?" in one glance. Single highest-value chart for trade-study deliverables.

**Cost:** ~200 lines (Plotly multi-panel subplot).

### 8.4 — NEW Plot I — Outcome map vs detection range (answers Q2: "at what detection range can I kill?")

Single curve of engagement margin `(t_dwell − τ_BT)/τ_BT × 100 %` vs R_detect (log x-axis). Three coloured bands: green ≥ +30 % engageable, amber 0–30 % marginal, red < 0 % not viable. Annotation calling out the **minimum detection range for a guaranteed kill** where the curve crosses 0 %.

**Why it earns a slot:** answers the operational question "how far away do I need to detect this target?" in one read.

**Cost:** ~150 lines.

### 8.5 — NEW Plot J — Cumulative energy & useful-work diagnostic (answers Q3: "how much window did I waste?")

For one engagement, two stacked traces: cumulative absorbed energy vs time, with a horizontal reference line at `E_fail = ρ·c_p·thickness·(T_fail − T_amb)` (the lumped-mass failure fluence). Shaded "useful zone" from when irradiance first exceeds an absorbed-flux threshold (e.g., 1 W/cm²) until kill — visualizes how much of the engagement window was actually doing meaningful damage.

**Why it earns a slot:** for high-power lasers vs. small targets, the early part of the trajectory often delivers irradiance below the radiation-loss break-even point. This plot makes that visible.

**Cost:** ~120 lines.

### 8.6 — NEW Plot K — Operational envelope heatmap (answers Q4: "what's my engagement region?")

2D heatmap with R_detect on the x-axis (log, ~0.1–30 km), v_tgt on the y-axis (linear, 0–100 m/s), cell colour = engagement margin. Red ← 0 % → green. Cell text/marker (❌ / ⚠ / ✓) for color-blind backup. A reference dot for the user's current scenario ("you are here").

**Compute on click** per user decision. Renders ~100 cached engagements (10 × 10 grid); ~100 s on first click; instant subsequent renders.

**Why it earns a slot:** strategic / mission-planning view. Tells the operator "for this system, against threats slower than 30 m/s, I'm engageable from 1 km onward; faster threats need detection past 5 km."

**Cost:** ~150 lines + a "Compute envelope" button.

### 8.7 — Updated Engagement tab layout

| Position | Plot | Status |
|---|---|---|
| 1 | **Plot H — Engagement profile timeline** | NEW |
| 2 | **Plot I — Outcome map vs R_detect** | NEW |
| 3 | Plot A — On-target performance | modified |
| 4 | Plot B — τ_BT vs t_dwell | modified |
| 5 | Plot E — Engagement margin | modified |
| 6 | **Plot J — Cumulative energy & useful work** | NEW |
| 7 | **Plot C' — Spot tightening through trajectory** | replacement for old C |
| 8 | Plot D — N_D distortion | modified |
| 9 | Plot G — Spot vs bucket | modified |
| 10 | **Plot K — Operational envelope** (compute-on-click) | NEW (opt-in) |

**Net: +5 plots, every position earns its keep.**

---

## 9 · Math tab updates

Per the existing math-tab framework (5-PR campaign closed):

- **M3 row updates:** new `available_dwell` formulas (two cases by `engagement_geometry`), new `R_at_dwell_end` row, retire the FOV formula
- **M8 row updates:** replace constant-flux LaTeX with time-varying-flux PDE statement; add `R_at_kill` row; new `engagement_ended_at_R_min` failure_mode value documented
- **New `MATH_CONTENT` entries:** `R_detect`, `R_min`, `engagement_geometry` (categorical), `R_at_kill`, `I_peak_max`
- **Worked example walkthrough rewrite:** the c_uas-1km example becomes a head-on engagement at `R_detect = 1500 m, R_min = 100 m, v_tgt = 20 m/s`. Walk through trajectory step-through showing R(t), I_peak(t) growing, T_surface(t) climbing, kill moment at some t < t_dwell

---

## 10 · Test impact

### SPEC validation cases

All SPEC §3 cases that use `available_dwell` or constant-flux M8 need updates. Estimate: **~8 of the 30 cases** require new expected values; **4–6 brand-new cases** for the trajectory model.

### Golden fixtures — re-seeded (one-time migration)

Three fixtures (c_uas_1500m, counter_rocket_3000m, long_range_8000m) translated:
- `R` → `R_detect`
- `v_perp` → `v_tgt` for `engagement_geometry = "lateral"`
- `R_min` → 100 m default
- Validate new outputs (R_at_kill, I_peak_max, trajectory series) make physical sense and seed the JSON

### New test files

| File | Purpose |
|---|---|
| `tests/test_trajectory.py` | Closed-form R(t) + t_dwell math; edge cases (R_detect = R_min; geometry switch; stationary target) |
| `tests/test_m8_time_varying_flux.py` | Callable flux: constant-flux callable reproduces v1 result; ramping flux integrates correctly; PDE stability under time-varying BC |
| `tests/test_orchestrator_trajectory_loop.py` | Sub-sampling correctness, warm-start convergence, trajectory-series outputs, kill-range bookkeeping |
| `tests/test_plot_h_engagement_profile.py` | New plot smoke tests |
| `tests/test_plot_i_outcome_map.py` | Threshold detection in the curve |
| `tests/test_plot_j_energy_diagnostic.py` | Useful-zone calculation |
| `tests/test_plot_k_operational_envelope.py` | Heatmap data-grid construction (no rendering) |

### Existing test files needing updates

- `tests/test_m3_geometry.py` — full rewrite with new dwell formulas
- `tests/test_m8_burnthrough.py` — extend for time-varying flux; legacy constant-flux tests stay green via constant-callable trick
- `tests/test_orchestrator.py` — sweep R_detect rather than R
- `tests/test_dimensions.py` — dimensional analysis on new dwell formulas
- `tests/test_cross_module.py` — extend for trajectory consistency
- `tests/test_properties.py` — Hypothesis property: `available_dwell ≥ 0` for any valid (R_detect, R_min, v_tgt, geometry)
- `tests/test_ui_numerics.py` — new sidebar inputs, new engagement-tab plots
- `tests/test_math_tab.py` — new MATH_CONTENT entries, updated walkthrough
- `tests/test_golden.py` — re-seeded JSONs

---

## 11 · Implementation as 12 PRs

Each PR independently mergeable; each leaves the app in a working state.

| PR | Scope | Lines (≈ code + tests) |
|---|---|---|
| **1. SPEC v2.0** | Docs only. SPEC.md updates + `docs/tracker_dwell_plan_2026-04-25.md` (this plan). User reviews and approves before any code work. | 200 + 0 |
| **2. Trajectory module** | New `physics/m_trajectory.py`. Closed-form R(t) and t_dwell. Stationary-target edge case. Unit tests. Not yet wired into orchestrator. | 150 + 200 |
| **3. M3 contract update** | Replace M3 inputs/outputs per new SPEC. New validator constraints. Update `tests/test_m3_geometry.py`. App still runs (orchestrator unchanged structurally; just pulls new M3 outputs). | 100 + 250 |
| **4. M8 time-varying flux** | Extend M8 solver to accept a flux callable. Backward compat with scalar `I_aim`. New stop condition. New outputs (R_at_kill). | 100 + 200 |
| **5. Orchestrator trajectory loop** | The big one. Sub-sampled upstream chain re-eval inside the M8 step. Warm-start Picard. Trajectory-series outputs. Performance check. | 400 + 300 |
| **6. UI inputs + Math tab** | Sidebar fields, presets migration, MATH_CONTENT updates, math-tab walkthrough revision, verdict-chip enhancement, UI numeric tests. | 250 + 100 |
| **7. Plot updates** (existing) | Plots A, B, C', D, E, G updated for new contract semantics. | 250 + 80 |
| **8. Plot H — engagement profile** | The headline new plot (multi-panel timeline). | 200 + 50 |
| **9. Plot I — outcome map** | Margin-vs-R_detect with band shading and threshold annotation. | 150 + 50 |
| **10. Plot J — energy diagnostic** | Useful-work cumulative-energy plot. | 120 + 40 |
| **11. Plot K — operational envelope** | 2D heatmap with compute-on-click button; ~100-cell pre-cache pattern. | 150 + 50 |
| **12. Golden fixtures + cross-cutting tests** | Re-seed all goldens. Update test_dimensions, test_cross_module, test_properties. Final cleanup. | 150 + 200 |

**Total revised:** ~2,400 lines code + ~1,800 tests ≈ **4,200 lines**. Comparable in scale to the math-tab campaign.

### Recommended PR priority for staged rollout

1. **PRs 1–6** (SPEC + physics + UI + math tab) — gives the new model without plot fanfare. Engagement tab shows numbers under the new contract; visually unchanged.
2. **PR 8 (Plot H)** — the engagement-profile timeline. Single highest-impact visualization. Promote ahead of plot-update PRs.
3. **PR 9 (Plot I)** — outcome map. Second-most-useful.
4. **PR 7** — bulk update of existing plots.
5. **PRs 10–12** — energy diagnostic, operational envelope, golden re-seed.

After PR 6 you have a working tracker model; after PR 8 you have the headline new plot; rest are enhancements.

---

## 12 · Gap fixes incorporated from review pass

Twelve gaps caught in self-review and folded into the appropriate sections:

| # | Gap | Fix landed in |
|---|---|---|
| 1 | Target altitude `H_t` constant during engagement (not noted) | §13 Out of scope |
| 2 | M5 sub-sampling interpolates the integral, not the integrand | §5 |
| 3 | M6↔M7 fixed-point uses warm-start from previous sub-sample | §5 |
| 4 | New failure_mode value `engagement_ended_at_R_min` | §4, §6 |
| 5 | Stationary-target degenerate case (`v_tgt < 0.1 m/s`) | §3.3 |
| 6 | Cache-key updates with new `frozen_inputs` | §5 (verified by cache-hit test) |
| 7 | Tracker jitter contribution noted in `sigma_jit` semantics | §2 |
| 8 | Math-tab worked example rewrite | §9 |
| 9 | Verdict chip carries operational specifics (kill time, range) | §7 |
| 10 | `engagement_viable` extended definition | §6 |
| 11 | Golden-fixture migration plan | §10 |
| 12 | M9 NOHD invariant — explicitly noted, not overlooked | §6 |

Plus the plot-strategy rebuild (§8) that recognized Plot C becomes degenerate under the new model and replaces it with C' (trajectory-aware spot tightening).

---

## 13 · Out of scope

- **No tracker dynamics.** Slew-rate limits, gimbal acceleration, tracker noise — assumed perfect. Only LOS geometry and trajectory closure rate modelled.
- **No target maneuver.** Trajectory is straight-line at constant `v_tgt`. Banking turns, evasive maneuvers, climb/dive — all v3.
- **No 3D trajectory.** Target altitude `H_t` constant during engagement; only slant range `R(t)` varies.
- **No multi-target scheduling.** One target, one engagement.
- **No line-of-sight masking.** Terrain, clouds, own-platform structure — all v3.
- **Constant target signature.** `material`, `thickness`, `d_aim` are scalars throughout the trajectory. Aspect-angle changes — v3.
- **No real-time tracker simulation.** The model assumes the tracker "just works"; we don't simulate breaklock probability or aimpoint wander.

---

## 14 · Risks & open decisions

### Risks

- **Performance.** Trajectory loop multiplies orchestrator calls by ~50–200×. If sub-sampling and caching don't cut it, the 30-point R_detect sweep becomes ~30 s instead of today's ~6 s. May need a "compute on click" UX for the sweep too if it ends up sluggish.
- **Validation-case coverage.** Some SPEC §3 v1 cases will be impossible to translate (e.g., the dwell tolerance test). PR 1 must enumerate which translate, which retire, and which need new expected values.
- **CLAUDE §7.2 scope guard.** Plan formally relaxes a v1 scope-guard. SPEC PR 1 makes this traceable; user approval is in this plan but the SPEC commit makes it formal.
- **M6↔M7 convergence under fast trajectory changes.** Edge case: very-fast targets with rapid range change may push the warm-start past its convergence basin. Worth a per-engagement convergence-failure flag.

### Open decisions for PR 1 (defaults applied, user may override)

| Decision | Default | Override mechanism |
|---|---|---|
| `R_min` default | 100 m | Single-line edit in `ui/labels.py` defaults |
| Default `engagement_geometry` for new sessions | "head_on" (more conservative) | Same |
| SPEC version bump | v2.0 | Trivial swap to v1.x at PR 1 |

---

## 15 · Verification

### Per-PR

- `pytest tests/` green at the new count
- `pyflakes` + `mypy` permissive clean
- Streamlit local-run smoke against the canonical scenario (head-on c_uas at R_detect = 1500, R_min = 100)

### Campaign-level

- The user's specific case scenario (DJI drone, 500 m, 3 kW, M²=1.4, 10 µrad jitter, both head-on and lateral) produces sensible numbers under both geometries
- Cross-check against the existing c_uas_1500m golden — pure-stare equivalents (R_detect ≈ R_min so t_dwell → 0) reproduce v1 single-point result for irradiance / spot / etc. within tolerance
- Energy-balance sanity: `∫ A_λ · I_avg_aim(t) dt` over the trajectory ≈ E_delivered from M8. Match within ~5 % (the difference being radiation/convection losses the PDE includes but the integral ignores)
- Plot K compute-on-click pre-cache completes in < 120 s on the canonical scenario

---

## 16 · End-of-plan checklist (review verification)

Self-check that nothing was missed:

- [x] User-confirmed answers to the four design questions are reflected (head-on R_min, lateral inbound-only, time-varying flux, tracker-only)
- [x] User-confirmed answers on plots: K compute-on-click, all four (H, I, J, K) included
- [x] All twelve gap-review items folded into the plan
- [x] CLAUDE §4.3 paired-edit procedure enforced (SPEC PR before any code PR)
- [x] CLAUDE §7.2 scope-relaxation explicitly flagged
- [x] Validation-campaign artifact pointers (uncertainty_closeout.md §10.5; math-tab worked example)
- [x] All 45 orchestrator output keys still emitted; 5+ new keys catalogued (R_at_dwell_end, R_at_kill, I_peak_max, I_avg_aim_max, trajectory_*)
- [x] Math tab content roadmap (new MATH_CONTENT entries, walkthrough rewrite, glossary update if needed)
- [x] All four "what does the engineer want to know" questions (Q1–Q4) answered by exactly one plot each (H–K)
- [x] Per-PR test coverage planned for every new module / plot / contract change
- [x] Golden-fixture migration explicit (one-time re-seed at PR 12)
- [x] Out-of-scope items called out (3D trajectories, tracker dynamics, target maneuver, LOS masking, multi-target, aspect-angle)
- [x] Performance risk acknowledged with mitigation (sub-sampling + warm-start + 5 % R-change threshold)

**No outstanding gaps. Plan ready for user approval.**
