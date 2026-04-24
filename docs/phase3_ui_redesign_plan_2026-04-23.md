# Phase 3 — UI/UX redesign plan (2026-04-23)

## 1. Context

Phase 2 shipped a feature-complete Streamlit app backed by eleven physics modules, 30 green validation tests, and a working orchestrator. Walking through the live app at `hel-calculator.streamlit.app` with fresh eyes surfaced a consistent problem: **the physics is right, the surface is not.** The tool reads like a developer-facing diagnostic dump, not like a premium engineering instrument.

Six diagnosed failure modes in the current surface:

1. **No typographic hierarchy.** Titles, labels, values, and prose all sit in the same visual weight band.
2. **Cryptic variable names at the display layer.** `θ_diff_pure`, `S_TB`, `τ_BT`, `Q_waste`, etc. — legitimate as physics-contract dict keys, wrong as user-facing labels.
3. **Emojis in chrome.** Page title and panel headers carry `🔦`, `🎯`, `📐` etc., which read as informal.
4. **Internal jargon leaked into user copy.** `SPEC v1.7 / ARCH v1.5` subtitle; `M6↔M7 loop: 2 iterations, converged (SPEC §3 M6 tolerance)`; `HV-5/7 Cn² profile assumed`.
5. **Assumption flags as a 14-item text wall.** Unscannable; violates the "glance-readable" expectation an engineer brings to this class of tool.
6. **Silent failure of the most important visual element.** When the range-sweep is infeasible (e.g., slant range < altitude difference), the plots are silently skipped. A tool without charts reads as broken — even if every number on the page is correct.

This plan replaces the surface end-to-end while holding the physics contract invariant. SPEC §3 dict keys do not change. All 30 validation tests stay green. CLAUDE §7.1 formula immutability is preserved.

## 2. Design principles (user-approved)

Four design decisions are locked from the 2026-04-23 kickoff:

- **Theme.** Dark-mode primary, light-mode toggle available. Dark is the "premium engineering instrument" anchor (Bloomberg, Jupyter Lab Pro, LabVIEW front panels); light mode is for outdoor / projector use.
- **Navigation.** Sidebar inputs + tabbed results. Inputs stay on the left (today's pattern); main area splits into result-ordered tabs rather than the current single-scroll input-ordered dump.
- **Rollout.** Six iterative PRs, each visibly improving the app. Every PR is a review gate; no long-lived branch.
- **Labels.** I draft the full SPEC-key → UI-label → tooltip mapping as a single table; user redlines in one sitting; result applies across cards, plots, and flags.

## 3. Visual system (design tokens)

A single `ui/theme.py` module defines the tokens. Streamlit's `.streamlit/config.toml` sets the base palette; `ui/theme.py` injects the rest via targeted CSS. No external UI libraries (no `streamlit-elements`, no MUI bridges) — they add deployment risk on Streamlit Cloud for a small aesthetic win.

**Color palette (dark-mode primary).** Graphite family for surfaces, restrained amber + blue-green for data and accents, muted red/orange for status only.

| Token | Dark | Light | Use |
|---|---|---|---|
| `bg.base` | `#0F1419` | `#F7F8FA` | Page background |
| `bg.surface` | `#1A1F26` | `#FFFFFF` | Card / panel background |
| `bg.surface-raised` | `#232933` | `#F0F2F5` | Elevated card (inside a card) |
| `fg.primary` | `#E8EAED` | `#1A1F26` | Headings, big numerics |
| `fg.secondary` | `#9AA0A6` | `#5F6368` | Labels, captions |
| `fg.tertiary` | `#5F6368` | `#9AA0A6` | Helper text, axis ticks |
| `accent.primary` | `#4FC3F7` | `#0277BD` | Interactive / link / active tab |
| `accent.data-a` | `#F4B942` | `#B8860B` | Primary data series (amber) |
| `accent.data-b` | `#4DB6AC` | `#00695C` | Secondary data series (teal) |
| `accent.data-c` | `#BA68C8` | `#6A1B9A` | Tertiary data series (purple) |
| `status.ok` | `#66BB6A` | `#2E7D32` | "Engageable" verdict chip |
| `status.warn` | `#FFA726` | `#E65100` | Caution chip |
| `status.error` | `#EF5350` | `#C62828` | "Not engageable" chip |
| `border.subtle` | `#2C3339` | `#E0E3E7` | Card outlines, dividers |

Palette is restrained on purpose: at most three data colors for multi-series plots, one accent for interactive elements, three status colors. No color carries meaning outside its swim lane.

**Typography.**
- UI: **Inter** (free, excellent readability, shipped via Google Fonts CDN — single `<link>` in the app `<head>` via CSS injection).
- Numeric displays: **JetBrains Mono** at tabular-nums. Numbers always align vertically on the decimal; reading a column of metrics feels like reading a Bloomberg terminal.
- Scale: `h1 32 / h2 24 / h3 18 / body 14 / caption 12` px with `1.4–1.5` line-height.

**Spacing.** 4-px base scale (`4 / 8 / 12 / 16 / 24 / 32 / 48`). Cards pad `24px`. Section gaps `32px`. Metric rows `16px`. Only these values appear anywhere in the app.

**Radii.** Cards `8px`. Chips `999px` (pill). Buttons `6px`. Inputs inherit Streamlit default.

## 4. Information architecture

**Sidebar (inputs, left, ~320 px).**

- No emojis anywhere.
- Top of sidebar: **Preset scenarios dropdown** — "C-UAS short range", "Counter-rocket", "Long-range surveillance deterrence", "Custom (manual)". Selecting a preset pre-fills every input; switching to Custom leaves them where they are.
- Six input sections, same content groupings as today (A–F), but with:
  - Renamed: "Laser source", "Beam director", "Engagement geometry", "Atmosphere", "Target & aimpoint", "System resources". (Current labels strip the "A —", "B —" prefixes.)
  - Each section collapsible (expander), state persisted across reruns via `st.session_state`.
  - Each input shows its unit and valid range inline: `Output power (kW) — 0.5 to 500`.
  - The `A_λ` override is already a checkbox-gated slider (from slice 2b improvement #5). Keep.
- Bottom of sidebar: **Run Analysis** primary button, full-width, prominent.
- Below the button: a tiny "Last run: 2 s ago · inputs changed" indicator so the user can tell when the results on screen match the sidebar.

**Main area (results, right, tabbed).**

Six tabs. The order is the reading order — first tab is the top-level verdict, last tab is where you go when you distrust something.

1. **Overview.** Verdict chip ("Engageable" / "Not engageable, exceeds dwell by 22%") as a quiet colored pill, not a full-width banner. Six big metric cards in a responsive grid: *delivered power at aimpoint*, *peak on-target intensity*, *time to burn through target*, *available engagement window*, *top-hat hazard distance*, *sustainable run time*. Below: a small horizontal bar chart showing how the available dwell compares to the required burn-through time (the single most important visual for an operator).

2. **Engagement.** Interactive plots as the hero content: (a) **spot-size contributions vs range** — stacked area showing how diffraction, turbulence, jitter, and blooming each contribute to the 1/e² radius; (b) **power-in-the-bucket vs range** — with aimpoint-radius overlay; (c) **peak on-target intensity vs range** — with diffraction-limited reference line. Plot A is the one that answers "why is my beam this size at range X". Below the plots: a quiet table of spot-decomposition values at the configured range.

3. **Target effects.** (a) **Material surface temperature vs time** — for the selected material/thickness/A_λ, with failure-threshold horizontal reference line annotated "melts" or "decomposes"; (b) side-by-side comparison mini-chart of τ_BT for all seven materials at the current irradiance (so an operator can see "would CFRP burn faster? yes, 2 s vs 8 s"). Numeric summary below.

4. **Safety.** Both hazard distances (top-hat and Gaussian-peak) as large numeric cards, side by side, with the selection guidance rendered as prose underneath ("Cite the Gaussian-peak value for single-mode HEL safety cases; the top-hat is ANSI's general-form conservative for multimode/diffused sources"). Laser class in its own card. Below: a **hazard-zone cross-section plot** — a quiet schematic of the engagement geometry with the NOHD rendered to scale. Operators love this because it makes the number physical. The strict-ANSI conversion note (`× √5` to recover the C_A = 5.0 number) appears as a small help caption.

5. **Atmosphere.** (a) **Extinction breakdown** as a horizontal stacked bar (molecular absorption / molecular scattering / aerosol absorption / aerosol scattering) — the current table becomes the tooltip; (b) **transmission vs range** curve for the selected wavelength. Both charts hover-interactive.

6. **Diagnostics.** Assumption flags live here in a **severity-sorted list with chips**: `[HIGH UNCERTAINTY] α_mol sea-level tables used on slant path …` renders as a chip + one-line text, not a bullet wall. Convergence status (iteration count, converged/not) appears as a quiet info card. No internal references (`SPEC §3 M6 tolerance`, `CLAUDE §7.1 invariants`) leak here; those live in the help tooltips, not the primary text.

**Empty and edge states.**

- Before first Run Analysis: each tab shows a **skeleton state** (placeholder cards, plot frames with "Run Analysis to populate" text overlaid). Never a blank page.
- Infeasible geometry: the Engagement tab's range-sweep plots still render as chart frames, with an inline banner inside the chart area: "Geometry infeasible at the configured range (R must be ≥ |target altitude − emplacement altitude|). Adjust range or altitudes." No silent skipping.
- Validation error (e.g., negative `P0`): caught at the app boundary and rendered as a calm red card with the specific error, not a Python traceback.

## 5. Component inventory

Pure Streamlit + Plotly + minimal CSS. No new Python dependencies. New files:

- `ui/theme.py` — palette + CSS + Plotly template + font loader + light/dark toggle.
- `ui/components.py` — four helpers:
  - `metric_card(label, value, unit, *, help=None, status=None)` — the big-number card.
  - `status_chip(label, status)` — pill for verdicts and flag severities.
  - `section_header(title, subtitle=None)` — tab-level heading with consistent spacing.
  - `skeleton_card(label)` — empty-state placeholder.
- `ui/labels.py` — single source of truth for SPEC-key → UI-label → tooltip mapping. Every output-facing label in the app reads from this table. This file IS the deliverable of the PR1 user-review step.
- `ui/presets.py` — preset scenario definitions (dicts keyed by preset name, values are complete `user_inputs` dicts).

Edited files:

- `ui/app.py` — wires theme, replaces the current panel-rendering loop with a tabbed layout, routes results through the component helpers.
- `ui/panels.py` — drops emojis, renames sections, adds presets dropdown and "last run" indicator.
- `ui/outputs.py` — rewritten to emit metric cards rather than raw Streamlit metrics; delegates all labels to `ui/labels.py`.
- `ui/plots.py` — rewritten to apply the shared Plotly template and always-render chart frames; gains three new plot functions (temperature vs time, extinction breakdown, NOHD cross-section).
- `ui/auth.py` — unchanged behavior, new theme applied.
- `.streamlit/config.toml` — new theme block (primary color, base color, font).

## 6. Plot strategy

Plotly with a single shared `go.layout.Template` defined in `ui/theme.py`. Axes titles are the same English labels as the metric cards (so "Peak on-target intensity (W/cm²)" — never `I_peak`). Every trace has a `hovertemplate` that spells the quantity out in full and carries the unit.

Plots per tab (summary):

| Tab | Plot | Type | Axes |
|---|---|---|---|
| Overview | Dwell-vs-burnthrough comparison | Horizontal bar | Time (s); two bars |
| Engagement | Spot-size contributions vs range | Stacked area / multi-line | Range (m) × spot radius (m) |
| Engagement | Power-in-the-bucket vs range | Line + aimpoint overlay | Range (m) × PIB fraction |
| Engagement | Peak intensity vs range | Line + diffraction-limit dashed reference | Range (m) × intensity (W/cm²) |
| Target effects | Surface temperature vs time | Line + failure-threshold annotation | Time (s) × temperature (K) |
| Target effects | τ_burn-through across materials | Horizontal bar | Material × time (s) |
| Safety | Hazard zone cross-section | Schematic (shapes + annotation) | Range (m), to scale |
| Atmosphere | Extinction breakdown | Horizontal stacked bar | Component × α (1/km) |
| Atmosphere | Transmission vs range | Line | Range (m) × τ fraction |

Every plot uses the per-plot unified hover from slice 3 (improvement #2). No cross-plot JS callbacks — that decision from slice 3 stays.

## 7. Label / copy system

One mapping table, applied everywhere. Below is my proposed draft — user redlines in place. Every row is `(SPEC key, UI label ≤ 5 words, tooltip 1 sentence, unit)`.

| SPEC key | Proposed UI label | Proposed tooltip | Unit |
|---|---|---|---|
| `P0` | Output power | Laser source output power before the beam director | kW |
| `M2` | Beam quality | Beam-propagation quality factor; 1.0 is diffraction-limited | dimensionless |
| `D` | Exit aperture diameter | Outer diameter of the beam director exit aperture | cm |
| `wavelength` | Wavelength | Laser operating wavelength | µm |
| `sigma_jit` | Pointing jitter (per-axis RMS) | RMS angular jitter on one axis; quadrature-summed into spot size | µrad |
| `R_slant` | Slant range to target | Line-of-sight distance from beam director to target | m |
| `H_e` | Emplacement altitude (AGL) | Beam director height above ground level | m |
| `H_t` | Target altitude (AGL) | Target height above ground level | m |
| `v_tgt` | Target velocity | Target closing speed along the engagement path | m/s |
| `v_perp` | Crosswind, perpendicular to path | Wind speed across the beam path; drives thermal blooming | m/s |
| `V_vis` | Visibility | Meteorological visibility; drives aerosol extinction | km |
| `RH` | Relative humidity | Humidity at the engagement altitude; drives molecular absorption | — |
| `T_ambient` | Ambient temperature | Air temperature along the beam path | K |
| `Cn2_ground` | Ground-level turbulence strength | Refractive-index structure constant at the emplacement altitude | m⁻²ᐟ³ |
| `cn2_model` | Turbulence profile | Which Cn² altitude profile to integrate over the beam path | — |
| `FOV` | Engagement basket field of view | Angular width of the tracker's engagement basket | deg |
| `t_exp` | MPE exposure-duration basis | Reference exposure time for the maximum-permissible-exposure calculation (safety path only) | s |
| `material` | Target material | Outer-surface material selection for burn-through modeling | — |
| `thickness` | Target thickness | Thickness of the target's outer layer | mm |
| `A_lambda_override` | Override absorptivity | User-supplied absorptivity (replaces SPEC default table) | — |
| `backside_BC` | Backside boundary condition | How heat leaves the rear face of the target layer | — |
| `P_prime` | Prime power | DC power draw from the platform electrical bus | kW |
| `eta_wp` | Wall-plug efficiency | Fraction of prime power converted to optical power | — |
| `C_thermal` | Thermal capacity | Coolant thermal capacity before reaching temperature limit | MJ/K |
| `Q_cool_rated` | Rated cooling capacity | Continuous heat-removal rate of the cooling loop | kW |
| **Output key** | **Proposed UI label** | **Proposed tooltip** | **Unit** |
| `P_aim` | Delivered power at aimpoint | Optical power delivered inside the aimpoint radius at the target | kW |
| `I_peak` | Peak on-target intensity | On-axis intensity at the target, after all propagation losses | W/cm² |
| `I_avg_aim` | Average intensity in aimpoint | Power-in-bucket divided by the aimpoint area | W/cm² |
| `I_peak_diff_lim` | Diffraction-limited peak intensity | What the peak would be without turbulence, jitter, blooming, or optics loss | W/cm² |
| `tau_BT` | Time to burn through target | Time from laser-on to failure-criterion reached on the selected material | s |
| `available_dwell` | Available engagement window | Time the target remains inside the tracker field of view | s |
| `theta_diff_pure` | Diffraction divergence | Beam spread from pure diffraction at the exit aperture | µrad |
| `theta_M2_excess` | Beam-quality divergence | Extra spread from a non-ideal M² | µrad |
| `theta_turb` | Turbulence broadening | Spread from atmospheric refractive-index fluctuations | µrad |
| `theta_jit` | Pointing-jitter broadening | Spread from pointing jitter | µrad |
| `S_TB` | Thermal-blooming Strehl ratio | How much blooming reduces on-axis peak irradiance (1.0 is no blooming) | — |
| `S_opt` | Optical-train Strehl ratio | How much the beam director optics reduce peak irradiance (1.0 is perfect optics) | — |
| `w_at_target` | Beam radius at target | 1/e² radius of the beam at the target range | m |
| `P_in` | Prime-power draw | Electrical power drawn from the platform bus during engagement | kW |
| `Q_waste` | Waste heat rejected | Thermal power the cooling loop must remove during engagement | kW |
| `t_sustain` | Sustainable engagement duration | How long the system can run continuously before a thermal or power limit | s |
| `energy_per_hour` | Energy delivered per hour | Total optical energy delivered if run back-to-back for an hour | MJ/h |
| `NOHD_tophat` | Hazard distance (top-hat) | ANSI top-hat Nominal Ocular Hazard Distance; general-form conservative | m |
| `NOHD_gausspeak` | Hazard distance (Gaussian peak) | Gaussian-peak NOHD; cite this for single-mode HEL safety cases | m |
| `laser_class` | Laser classification | ANSI Z136.1 laser hazard class at the stated exposure basis | — |
| `engagement_verdict` | Engagement verdict | Whether the engagement fits inside the available dwell window | — |
| `engagement_margin_pct` | Engagement margin | Percent difference between available dwell and time to burn through | % |
| `m67_converged` | Blooming iteration converged | Whether the blooming-broadening fixed-point loop reached tolerance | — |
| `m67_iteration_count` | Blooming iteration count | How many M6↔M7 iterations were needed | — |

This table becomes `ui/labels.py` and is imported by `ui/outputs.py`, `ui/plots.py`, and the new `ui/components.py`. No label string appears outside this file.

## 8. Contract-doc updates required

Per CLAUDE §3 rule 1: theme tokens, label rewording, emoji removal, copy edits, Plotly styling — all UI-only, no SPEC/ARCH update. **But** the following changes are structural and need `ARCHITECTURE.md` edited first:

- Adding `ui/theme.py`, `ui/components.py`, `ui/labels.py`, `ui/presets.py` to the repo tree (`ARCHITECTURE.md §3`).
- Changing `ui/app.py`'s top-level structure from single-page scroll to tabbed navigation (`ARCHITECTURE.md §5.1`, §6.1).
- Swapping the Plotly call sites in `ui/plots.py` to the shared template (`ARCHITECTURE.md §6.5`).
- Updating the UI-layer file count (§3).
- Revision-history entry (`ARCHITECTURE.md` v1.6).

`SPEC.md §5.1` (input panels) and `§5.2` (output panels and plots) describe the current UI behaviorally; those sections need updating to reflect the new tabbed layout, the new labels, and the three new plots. Revision-history entry `SPEC.md v1.9`.

These SPEC/ARCH edits are text-only, don't touch physics, and ship **inside PR 1** before any code changes — the documents lead, the code follows (CLAUDE §3).

## 9. Rollout — six PRs

Each PR is independently mergeable, independently reviewable, and leaves the app in a working state. Every PR has a single visible theme, so the user can accept or reject it at a glance.

### PR 1 — Foundation: theme, labels, emoji removal, contract-doc updates

**What ships:**
- `ARCHITECTURE.md` + `SPEC.md` edits above (documents lead).
- `.streamlit/config.toml` with theme block.
- `ui/theme.py` (palette + CSS + Plotly template + font loader, no components yet).
- `ui/labels.py` with the user-redlined SPEC-key → UI-label mapping.
- `ui/panels.py` strips all emojis, renames sections, uses `labels.py`.
- `ui/outputs.py` delegates every label string to `labels.py`.
- `ui/app.py` loads theme + removes the page-title emoji and the `SPEC v1.7 / ARCH v1.5` subtitle.
- Internal jargon (`SPEC §3 M6 tolerance`, etc.) scrubbed from user-facing strings.

**User sees:** a dark, professional tool with every label in plain English and no emojis — same structure, but immediately looks like a different app.

### PR 2 — Metric-card component + status chip

**What ships:**
- `ui/components.py` with `metric_card`, `status_chip`, `section_header`, `skeleton_card`.
- `ui/outputs.py` rewritten to render each output value as a metric card grouped into responsive rows.
- Engagement verdict rendered as a status chip, not a full-width banner.
- Assumption flags rendered as severity-chip + short-text list (preview of PR6 polish, but shipped now to kill the text-wall).

**User sees:** dashboard-style KPI cards, calm status chips, and the 14-item assumption wall replaced with a scannable chip list.

### PR 3 — Tabbed navigation

**What ships:**
- `ui/app.py` restructured with `st.tabs([...])`: Overview / Engagement / Target effects / Safety / Atmosphere / Diagnostics.
- `ui/outputs.py` split into tab-specific render functions.
- Sidebar gets its collapsible sections persisted via `st.session_state`.
- "Last run" indicator under the Run Analysis button.

**User sees:** a result-ordered story instead of an input-ordered dump. Overview answers "can I engage?" in one glance; deeper tabs answer "why?" and "how sure are we?"

### PR 4 — Plot theme + always-render chart frames

**What ships:**
- `ui/plots.py` switches to the shared Plotly template from `ui/theme.py`.
- Every plot renders a frame even when data is missing; infeasible-geometry case draws the frame + a calm in-chart banner.
- Axis labels, tick labels, hover templates — all read from `ui/labels.py` (full English, full units).
- Light-mode toggle (live) in the sidebar footer — flips the Plotly template in sync with the app theme.

**User sees:** the plots that were already in the app now look cohesive with the rest of the tool, and never silently disappear.

### PR 5 — New plots (Target effects, Safety, Atmosphere)

**What ships:**
- `ui/plots.py` gains: temperature-vs-time for the selected material; τ_BT comparison bar across all seven materials; NOHD hazard-zone cross-section; atmospheric-extinction stacked bar; transmission-vs-range line.
- Underlying data comes from existing physics-module outputs — no new physics, no SPEC changes.
- Overview tab gets the dwell-vs-burnthrough comparison bar.

**User sees:** every tab now has plots as the centerpiece. An operator can actually *see* the tradeoffs instead of reading numbers.

### PR 6 — Presets, empty / loading / error states, accessibility polish

**What ships:**
- `ui/presets.py` with named scenarios; dropdown at the top of the sidebar.
- Skeleton states before Run Analysis; loading state during compute; friendly error card for validation failures.
- Number formatting normalized (thousands separators, consistent sig-figs, tabular nums).
- Keyboard-tab order through the sidebar verified.
- Final pass: remove any remaining default-Streamlit rough edges (expander iconography, input spacing).

**User sees:** the app is now a tool, not a form. Fresh visit → preset → Run Analysis → reads the result in fifteen seconds.

## 10. Verification — per-PR acceptance

Each PR has a specific acceptance script. The user drives all of them (CLAUDE §5.3).

- **After PR 1:** Log in. Sidebar has no emojis; page title has no emoji. Every output label reads as English words, not `S_TB` / `τ_BT`. No "SPEC §..." strings in user-facing copy. Plots may still be un-themed; that's OK.
- **After PR 2:** Outputs render as cards, not as bare `st.metric`. Verdict is a calm chip, not a red banner. Assumption flags render as a chip list, not 14 bullets.
- **After PR 3:** Main area has six tabs in the specified order. Switching tabs is instant. No tab shows a stack trace or a `None`.
- **After PR 4:** Plots use the dark theme (or light, if toggled). Infeasible-geometry case shows chart frames with an in-chart advisory. Hover on any plot reads in plain English.
- **After PR 5:** Each tab with a plot shows its plot. Target-effects tab has temperature-vs-time visible. Safety tab has a hazard-zone cross-section. Atmosphere tab has the extinction breakdown as a chart.
- **After PR 6:** Fresh browser, logged-out → login → sees skeleton state → picks a preset → Run Analysis → full results in under three seconds perceived. No crash on any preset. Theme toggle works.

Per CLAUDE §4.4 self-audit, every PR closes with: `pytest tests/` green, import-rules test green, no SPEC numeric changed, no new dependencies added.

## 11. Risks and open decisions

- **Plot theme regressions across Plotly versions.** Mitigated by pinning `plotly==5.22.0` (already pinned) and loading the template once in `ui/theme.py`. If Streamlit Cloud's Plotly rebuild ever drifts, PR 4 is where we'd catch it.
- **Custom CSS injection fragility.** Streamlit is not a general web framework; custom CSS targets internal class names that can change across Streamlit versions. Keep the CSS surface minimal (card, chip, section-header only). Pin `streamlit==1.38.0` (already pinned). If Streamlit breaks the selectors in a future upgrade, the fix is isolated to `ui/theme.py`.
- **Label redlining time cost.** Twenty-five rows × ~30 seconds of user attention per row = ~12 minutes of focused review. If that stretches, PR 1 stretches with it. Mitigation: I ship a best-effort draft and hold the redline conversation in parallel so it doesn't block the rest of PR 1's file changes.
- **Dark mode accessibility.** A small minority of users have low-vision contrast needs that dark mode can hurt. Light-mode toggle is the primary mitigation; high-contrast-mode is out of scope for v1.

Open decisions — to resolve during PR 1 review:

- Font loader: inline Google Fonts `<link>` vs bundled font file? Inline is simpler; bundled avoids the third-party fetch for users on air-gapped networks. Recommend inline unless the user has an air-gap requirement.
- Preset scenarios list: which four? Draft is C-UAS short range / Counter-rocket / Long-range surveillance / Custom. User may want different presets.

## 12. Out of scope

- **Any physics change.** Every formula, every validation case, every dict key, every unit stays frozen per CLAUDE §7.1.
- **Adding wavelengths, materials, or input dimensions.** Still the SPEC §7.3 seven materials, SPEC §7.2 four wavelengths.
- **User accounts, session persistence, DB.** SPEC §7.2 explicitly v2.
- **Mobile-specific layout.** Per CLAUDE §7.2. The dark theme will look fine on tablets but this plan does not commit to phones.
- **`assumptions_flagged` stale-entry sweep.** Still a separate phase-close chore; independent of this redesign.
- **Parts D + E of the Phase 2 closeout plan.** Part D (live-app acceptance of the pre-redesign app) is superseded by acceptance of each PR in this plan. Part E (rotate PAT, flip repo private) is independent and still queued.

---

**Ready to execute on approval.** PR 1 begins with `ARCHITECTURE.md` + `SPEC.md` edits, then `.streamlit/config.toml`, then `ui/theme.py` + `ui/labels.py`. I will open a draft PR with the label-mapping table rendered as a Markdown table in the description so the user can redline it inline as part of the review.
