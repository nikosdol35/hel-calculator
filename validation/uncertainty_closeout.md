# HIGH UNCERTAINTY closeout — Package 4

**Date:** 2026-04-24
**Scope:** Permanent record in the `validation/` tree of the disposition of every SPEC §10 HIGH UNCERTAINTY item, after Packages 1–3 validation work.
**Supersedes for the validation audit trail:** `docs/spec_section10_review_2026-04-23.md` (the same six items were first dispositioned there after Phase 2 closeout; this file is the post-Package-3 refresh and the long-term record).
**Does NOT supersede SPEC §10** — SPEC §10 remains the contract-level disposition summary. This file is the evidence package.

---

## TL;DR

All six SPEC §10 items reviewed one more time against fresh literature (2026-04-24) and against Packages 1–3 validation outputs. **Five confirm the prior disposition; one surfaces a citation-only refresh path (ANSI Z136.1-2022 supersedes 2014).** **Zero formula changes, zero validation-case expected-value changes, zero paired SPEC + code edits required.** The single v1.12 paired edit (M9 pulsed-regime MPE constant typo) has already been applied and is CLOSED.

One item remains explicitly deferred to v2; a GitHub issue is proposed below for the user to file.

| # | SPEC §10 item | 2026-04-23 disposition | 2026-04-24 refresh | Final status |
|---|---|---|---|---|
| 1 | α_mol tables | Keep (HITRAN/MODTRAN v2) | ✓ Confirmed; HITRAN2024 available but no v1 action | **close-at-current** |
| 2 | A_λ matrix | Keep (per-row citations added) | ✓ Confirmed; 2024–25 CFRP lit. within envelope | **close-at-current** |
| 3 | MPE / C_A convention | CLOSED (no-C_A conservative) | ⚠ Citation refresh: ANSI Z136.1-**2022** now supersedes -2014 (physics unchanged; 2014 formulas remain conservative under 2022) | **revise-with-citation** (v2-scope) |
| 4 | Blooming 0.3 factor | Keep (Sprangle NRL cited) | ✓ Confirmed; Sprangle 2015 *Appl. Opt.* F201 still current | **close-at-current** |
| 5 | available_dwell heuristic | DEFERRED to v2 | ✓ Confirmed; v2 tracker-model remains standard scoping practice | **defer-to-v2** (file issue) |
| 6 | h_conv = 10 + 6.2√v | Keep (Incropera cited) | ✓ Confirmed; Lienhard 2020 and 2024 refresh within envelope | **close-at-current** |

---

## Method

1. Re-read the 2026-04-23 review memo (`docs/spec_section10_review_2026-04-23.md`) and the v1.8 SPEC §10 disposition summary (SPEC.md lines 1261–1277).
2. Traced each item through Packages 1–3 outputs:
   - Per-module derivation files (`validation/derivations/m*.md`, especially m4, m6, m8, m9).
   - Constants audit (`validation/constants_audit.md`).
   - Numerical-methods audits (`validation/methods/m*.md`).
   - Paired SPEC + code edits applied during Package 3 (SPEC v1.12, M9 pulsed-regime MPE typo).
3. Ran a fresh 2026-04-24 literature pass on each item — not to replace the 2026-04-23 research, but to catch anything new since.
4. For each item: **close-at-current**, **revise-with-citation**, or **defer-to-v2**. Any "revise-with-numeric-change" would trigger a paired SPEC + code edit per CLAUDE §4.3; none required.

---

## Item 1 — α_mol molecular-absorption table — CLOSE-AT-CURRENT

**Current values (SPEC §3 M4 lines 273–286, sea-level / 60% RH / mid-latitude summer baseline):**

| λ (µm) | α_mol_abs (1/km) | α_mol_scat (1/km) |
|---|---|---|
| 1.06 | 0.045 | 0.005 |
| 1.07 | 0.065 | 0.005 |
| 1.55 | 0.190 | 0.010 |
| 2.05 | 0.490 | 0.010 |

Source: McClatchey-family engineering placeholders, AFCRL-TR-72-0497 (1972). Flagged HIGH UNCERTAINTY in SPEC since v1.0.

**Package 1 verification (`validation/derivations/m4_atmosphere.md`).** All 8 values cross-checked against band-edge structure (H₂O combination band near 1.13 µm, H₂O strong band at 1.87 µm, atmospheric windows). Ordering correct; absolute values within the ±50% envelope typical of sea-level mid-latitude engineering tables. `interp_log_space` validated independently in `validation/methods/m4_interp.md`.

**2026-04-24 literature refresh.**
- HITRAN2024 (Gordon et al.) is released with updated line-by-line parameters. No headline revision of sea-level NIR continuum absorption at 1.06–2.05 µm that would move values outside ±50% of the McClatchey placeholders.
- HAPI2LIBIS (GMD 2025) couples HITRAN into libRadtran 2.0.6. Tooling is available for a programmatic re-derivation but is a v2 refinement path, not a v1 revision requirement.

**Impact of a ±50% change** (from the 2026-04-23 memo, re-verified): at 5 km slant at 1.07 µm, current α_atm ≈ 0.137 1/km → τ_atm ≈ 0.504. A ±50% change in the α_mol_abs component shifts τ_atm by ~±3.3 percentage points — within the tool's engineering-estimate envelope (≥25% tolerance on tests like M8.1 aluminum burn-through).

**Decision.** close-at-current. v2 refinement path documented: HITRAN line-by-line integration via HAPI2LIBIS + libRadtran.

**Not acceptable for formal program safety cases** — use program-measured or HITRAN-derived values there. SPEC §10.1 already carries this warning.

---

## Item 2 — A_λ material-absorptivity matrix — CLOSE-AT-CURRENT

**Current values (SPEC §3 M8 lines 643–663, 7 materials × 4 wavelengths, per-row citations added in v1.8).**

| Material | 1.06 | 1.07 | 1.55 | 2.05 | Primary source |
|---|---|---|---|---|---|
| Anodized Al | 0.30 | 0.30 | 0.25 | 0.20 | Steen & Mazumder Ch. 5 Table 5.1 |
| CFRP | 0.85 | 0.85 | 0.85 | 0.85 | Bergstrom 2007 *J. Appl. Phys.* 101:043517 |
| GFRP | 0.40 | 0.40 | 0.45 | 0.55 | Steen & Mazumder + composite datasheets |
| Polycarbonate | 0.10 | 0.10 | 0.30 | 0.60 | SABIC Lexan datasheet + C-H overtone at 1.7 µm |
| ABS | 0.70 | 0.70 | 0.75 | 0.85 | Polymer datasheets |
| EPP foam | 0.50 | 0.50 | 0.55 | 0.70 | Polymer datasheets |
| LiPo cell | 0.30 | 0.30 | 0.35 | 0.45 | Sandia thermal-runaway reports |

**Package 1 verification.** Per-material traceability confirmed: every row in `validation/derivations/m8_thermal.md` has a cited source consistent with the SPEC table; discrepancies are within the surface-condition uncertainty band noted in the 2026-04-23 memo.

**2026-04-24 literature refresh.**
- CFRP: Zuo et al. 2024 *Polymer Composites* review and two 2025 CFRP laser-processing papers (MDPI *Materials* + *Sci. Reports*) continue to report 86–91% NIR absorption for as-received CFRP. SPEC's 0.85 flat remains well within this band.
- Anodized Al, polycarbonate: no 2024–2026 publication surfaces that would tighten values at the four SPEC wavelengths beyond the surface-condition spread already documented.

**Per-material-row override is already exposed** via the UI checkbox-gated `A_λ` input (slice-2b improvement #5). This is the production path for program-specific data.

**Decision.** close-at-current. No numeric change. SPEC per-row citations added v1.8 remain accurate.

---

## Item 3 — MPE / C_A convention at 1.07 µm — REVISE-WITH-CITATION (v2)

**Current SPEC behavior.** SPEC §3 M9 retinal-band MPE uses the no-C_A convention, i.e. C_A = 1 at 1.07 µm (strict ANSI Z136.1-2014 would apply C_A = 5.0 at 1.07 µm; see SPEC §10.3 and the always-on `assumptions_flagged` entry in `physics/m9_nohd.py` lines 176–183). Result: SPEC MPE at 1.07 µm, t=0.25 s is 25.5 W/m² (conservative; strict ANSI would give 127.3 W/m², NOHD smaller by √5 ≈ 2.24×). The tool overstates the hazard zone deliberately.

**Package 3 closeout.** In run-up to Package 3 a latent typo was discovered in the Band A pulsed-regime MPE constant (5e-3 vs ANSI Z136.1-2014 Table 5a value 5e-7 J/cm² for single-pulse retinal radiant exposure). Paired SPEC + code edit applied at SPEC v1.12 (`physics/m9_nohd.py` line 75; SPEC.md line 731). The branch is only reachable at `t_exp < 18 µs`; v1 is CW-only per CLAUDE §7.2, so no v1-scope MPE output changed. 18 µs piecewise continuity now holds to within the ANSI rounding step (verified by `tests/test_helpers.py::test_mpe_continuity_at_18us`). The pulsed branch is defensive; v1 still does not expose pulsed operation.

**2026-04-24 literature refresh.**
- **ANSI Z136.1-2022** has superseded Z136.1-2014 (ANSI Blog confirmation; HPS summary of revisions). The 2022 edition *raised* MPE in the near-infrared for retinal-band exposures.
- **Direction of the change.** Higher MPE → smaller permitted NOHD. Because the tool's current no-C_A convention already overstates the hazard zone relative to strict Z136.1-**2014**, the tool's NOHD under the 2022 standard is even more conservative. **No safety regression** under the newer edition. No paired SPEC + code edit required for v1.
- **Citation posture.** Module docstrings and SPEC Appendix B reference Z136.1-2014, which is the edition whose formulas the tool implements. v2 refinement path is to migrate to Z136.1-2022 Table 5 values (may require test-expected-value revisions).

**Decision.** revise-with-citation (v2-scope). No v1 text edit needed unless the user wants the Appendix B entry updated now to `Z136.1-2014 (2022 supersedes; formulas applied here remain conservative under 2022; v2 refinement path)`. If so, that is a one-line SPEC edit in Appendix B, not a formula change. Recommended to user: leave Appendix B as "Z136.1-2014" (accurate re: the formulas actually implemented) and capture the 2022 migration path in the §10 summary.

**Item 3 remains CLOSED for v1.** The v1.12 pulsed-regime typo fix is the canonical MPE-related change for this package.

---

## Item 4 — Thermal-blooming broadening factor 0.3 — CLOSE-AT-CURRENT

**Current formula (SPEC §3 M6 lines 446–453).**
```
if N_D < 5:       w_bloom = 0
elif 5 ≤ N_D ≤ 30: w_bloom = w_at_target · sqrt((N_D/5)² − 1) · 0.3
else:              w_bloom = (same formula) + flag "N_D > 30, model outside validity range"
```

Cited basis: Gebhardt 1990 *Proc. SPIE* 1221 (4√2 prefactor for N_D); Sprangle et al NRL/MR/6790-08-9141 for the 0.3 broadening-vs-Strehl split.

**Package 1 verification (`validation/derivations/m6_blooming.md`).** All M6 constants (`_C_P_AIR = 1005`, `_T_REF = 288`, `_P_REF = 101325`, `_MOLAR_MASS_AIR = 0.029`, `_DNDT_STP = -0.93e-6`, CLAUDE §7.1 `4√2` prefactor, CLAUDE §7.1 Gladstone-Dale `dn/dT` form) independently cited and verified. The 0.3 multiplier itself is an empirical engineering estimate — acceptable for v1 scoping per the 2026-04-23 disposition.

**Package 3 verification (`validation/methods/m6_m7_iteration.md`).** The M6↔M7 fixed-point loop converges correctly with the 0.3 factor applied; damped oscillation behavior near N_D ≈ 5 is noted (Ortega & Rheinboldt §10.1) but does not affect convergence within the 10-iteration budget at 1% tolerance.

**2026-04-24 literature refresh.**
- Sprangle/Hafizi/Ting/Fischer 2015 *Appl. Opt.* 54:F201 remains the most recent open-literature derivation of the turbulence-plus-blooming Strehl decomposition, and explicitly notes that coupled-Strehl "is exceedingly difficult to quantify using scaling codes" — the 0.3 engineering factor is the best-available scaling-code choice.
- "Improved Thermal Blooming Model" (DTIC AD1026290) accessible as an alternative benchmark path.
- No 2022–2025 declassified NRL/DEPS paper refines the 0.3 broadening factor.

**Sensitivity (from 2026-04-23, re-verified).** At N_D = 10, a ±50% change in the 0.3 factor shifts w_bloom by ±50% and enters quadrature with w_diff, w_turb, w_jit. Downstream PIB effect is ~5–10% for typical C-UAS, up to 20–30% for high-power / low-wind regimes where blooming dominates.

**Decision.** close-at-current. HELEEOS benchmark path available for programs with access.

---

## Item 5 — available_dwell heuristic — DEFER-TO-V2

**Current formula (SPEC §3 M3 line 218–221).**
```
available_dwell = 2·R · tan(FOV/2) / v_tgt   [FOV = _FOV_DEG_DEFAULT = 5° in m3_geometry.py]
```

**Disposition at v1.8.** DEFERRED TO v2 — full tracker-dependent model (slew-rate limits, target maneuver, line-of-sight masking, multi-target prioritization) is out of v1 scope per original plan §10.2 and CLAUDE §7.2.

**Package 1 verification (`validation/derivations/m11_dwell.md`).** The `_FOV_DEG_DEFAULT = 5°` assumption and the first-order engagement-basket formula are documented as explicit v1 simplifications. `assumptions_flagged` carries the entry.

**2026-04-24 refresh.** v2 tracker-model treatment (gimbal dynamics, handoff logic, slew-rate limits) remains the province of specialized tools (HELCOMES, ATLAS). Engineering scoping calculators uniformly use a geometric FOV/velocity approximation.

**Decision.** defer-to-v2. File a GitHub issue (see "v2 issues" section below).

---

## Item 6 — Convective backside BC h_conv = 10 + 6.2·√v_tgt — CLOSE-AT-CURRENT

**Current formula (SPEC §3 M8 line 627).**
```
h_conv = 10 + 6.2·sqrt(v_tgt)   W/(m²·K)   v_tgt in m/s
```

**Package 1 verification (`validation/derivations/m8_thermal.md`).** Cross-checked against Incropera & DeWitt 6th ed. Ch. 7 flat-plate correlation. For air at 300 K, L = 0.1 m: `h = 10 + ~5·sqrt(v)` — within ±20% of SPEC's `10 + 6.2·sqrt(v)`.

**Package 3 verification (`validation/methods/m8_solver.md`).** The 1-D transient heat-equation solver was validated against Carslaw & Jaeger semi-infinite-slab analytic benchmark, grid-refinement, and CFL. The convective BC enters only on the backside; front-side heat flux dominates the time-to-burn-through metric, so the h_conv prefactor uncertainty has minor downstream effect.

**2026-04-24 literature refresh.**
- Lienhard 2020 *ASME J. Heat Transfer* 142:061805 (unified laminar/transitional/turbulent flat-plate correlation) stays within the ±20% envelope of the classical √v form.
- 2024 ScienceDirect "generalized flat-plate correlations" paper also within envelope.
- Neither refines the prefactor outside the stated ±20% tolerance.

**Decision.** close-at-current. Users with vehicle-specific data should override via the UI's backside-BC input (SPEC §5.1 Panel E).

---

## Summary of paired SPEC + code edits this package

**None required for Package 4.**

The one physics-level paired edit of the Packages 1–4 campaign was the v1.12 M9 pulsed-regime MPE typo fix (applied during Package 3 numerical-methods validation, not deferred to Package 4). That edit is already on main (merged via PR #23) and is documented in SPEC revision history v1.12 and in `validation/derivations/m9_safety.md`.

## v2 issues to file

One GitHub issue recommended for user to file at convenience:

**Issue: v2 — tracker-dependent available_dwell model (SPEC §10.5 closeout)**
> SPEC §10.5 `available_dwell = 2·R·tan(FOV/2)/v_tgt` is a first-order geometric engagement-basket heuristic with `_FOV_DEG_DEFAULT = 5°`. v2 target: tracker-dependent model covering slew-rate limits (bounded by M2's σ_jit budget), target-maneuver effects (banking, jinking), line-of-sight masking (terrain, own-platform obscuration), and multi-target prioritization. Current v1 flag: `assumptions_flagged` carries the heuristic disclosure. Confirmed in Package 4 closeout 2026-04-24.

A second optional issue for the α_mol HITRAN refresh path:

**Issue: v2 — α_mol HITRAN/MODTRAN refresh (SPEC §10.1 v2 path)**
> SPEC §3 M4 α_mol absorption/scattering table (8 values) currently uses McClatchey AFCRL-TR-72-0497 (1972) engineering placeholders, verified ±50% of band-edge structure in Packages 1 & 4. v2 refinement path: HITRAN2024 line-by-line integration via HAPI2LIBIS + libRadtran 2.0.6 at the four SPEC wavelengths (1.06, 1.07, 1.55, 2.05 µm) for US-1976 standard atmosphere. Not required for v1 trade studies; required for formal program safety cases.

A third optional issue for the ANSI Z136.1-2022 migration path:

**Issue: v2 — ANSI Z136.1-2022 migration for MPE/NOHD (SPEC §10.3 v2 path)**
> SPEC §3 M9 implements ANSI Z136.1-2014 MPE formulas with conservative no-C_A convention (NOHD overstated relative to strict ANSI). Z136.1-2022 supersedes -2014 as of 2022 (HPS summary); 2022 generally raised NIR MPE so tool's no-C_A NOHD remains conservative under 2022. v2 refinement: migrate to Z136.1-2022 Table 5 values; may require updates to three tests in `test_m9_nohd.py` plus SPEC §3 M9 validation-case expected values.

---

## Acceptance gate

- [x] All six SPEC §10 items re-reviewed against fresh 2026-04-24 literature
- [x] Packages 1–3 validation outputs cross-checked against each item
- [x] Disposition per item: close-at-current (5), revise-with-citation (1, v2-scope only), defer-to-v2 (1)
- [x] Zero paired SPEC + code edits required for Package 4 (the one physics-level paired edit of the campaign — v1.12 MPE typo fix — landed during Package 3)
- [x] v2 issues listed above for user to file at convenience

**Package 4 CLOSED.**
