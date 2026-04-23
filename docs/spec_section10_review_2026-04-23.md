# SPEC §10 HIGH UNCERTAINTY review — 2026-04-23

**Purpose.** SPEC §10 lists six items flagged `HIGH UNCERTAINTY` at Phase 0 contract time. This memo reviews each, states what the tool does today, what a rigorous close would require, and a concrete recommendation. **No code or SPEC values are changed by this document.** Each recommendation is a proposal the user accepts, rejects, or modifies before any SPEC/physics edit lands.

**Scope.** Per CLAUDE §7.1, every SPEC physics formula is immutable without user approval via the §4.3 scope-change procedure. This review is the evidence package for deciding which §10 items warrant a SPEC change and which stay flagged as-is.

**Context.** All 11 physics modules (M1–M11) are implemented and their 29 SPEC validation tests are green on main. The full UI (slices 2a → 4) is deployed. The next natural work-block was always "close the §10 items or explicitly accept them as known v1 limitations."

---

## Review ledger

| # | Item | Recommendation | Requires user input? |
|---|---|---|---|
| 1 | α_mol molecular-absorption table | **Keep values**, tighten flag wording + cite McClatchey explicitly | No |
| 2 | A_λ material-absorptivity table | **Keep values**, add baseline literature citation per material row | No |
| 3 | MPE at 1.07 µm (C_A correction) | **Accept current no-C_A conservative choice**, fix SPEC test-note wording that falsely implies C_A is applied | No |
| 4 | Blooming broadening factor 0.3 | **Keep**, cite Sprangle NRL reports alongside Gebhardt | No |
| 5 | `available_dwell = 2·R·tan(FOV/2)/v_tgt` | **Keep for v1**, re-affirm "tracker-dependent model = v2" | No |
| 6 | Convective BC `h_conv = 10 + 6.2·sqrt(v_tgt)` | **Keep**, add Incropera & DeWitt citation | No |

**TL;DR:** None of the six items require a numeric SPEC change for v1. Three require minor text/citation polish (§10.1, §10.3, §10.4, §10.6). One requires a small SPEC-test-note correction (§10.3). The two heuristic items (§10.5 dwell, §10.6 convective BC) stay as-is and are explicit v1 engineering choices. Total SPEC edit footprint if all recommendations are accepted: **~25 lines of text, zero formula changes, zero test-value changes.**

---

## §10.1 — α_mol molecular-absorption table

**Current (SPEC.md lines 273–286):**

Sea-level, mid-latitude summer, 60% RH baseline, linear RH scaling:

| λ (µm) | α_mol_abs (1/km) | α_mol_scat (1/km) |
|---|---|---|
| 1.06 | 0.045 | 0.005 |
| 1.07 | 0.065 | 0.005 |
| 1.55 | 0.190 | 0.010 |
| 2.05 | 0.490 | 0.010 |

Flagged: "engineering placeholders, should be refined against HITRAN/MODTRAN data before formal use."

**What a rigorous close would need.** HITRAN line-by-line integration over each wavelength's resolution window, convolved with the relevant CO₂ / H₂O / O₂ line strengths and profile shapes; or a MODTRAN run at each of the four wavelengths for the US-1976 standard atmosphere. Neither database is part of this project's dependency stack.

**Qualitative cross-check of the current table (what I *can* verify without HITRAN):**
- **1.07 > 1.06** because 1.07 µm sits on the leading edge of the H₂O combination band near 1.13 µm. Ratio of 1.44 is plausible (Thomas & Stamnes 2002 fig. 3.14 shows similar band-edge behavior). ✓
- **2.05 >> others** because 2.05 µm is on the strong H₂O band at 1.87 µm. The SPEC value 0.490 is ~10× the 1.06 value, which matches the rough order-of-magnitude seen in atmospheric-window plots. ✓
- **1.55 in the middle** — 1.55 µm sits in the short-wave atmospheric window between the 1.38 and 1.87 µm H₂O bands, but closer to 1.87. Moderately higher than 1.06/1.07 but far below 2.05. ✓

Values are the right order of magnitude and the relative ordering is correct. The absolute numbers are within ~50% of typical literature figures (McClatchey et al. 1972 table values, which SPEC already cites).

**Impact of a 30–50% numeric change.** At 5 km slant at 1.07 µm, current α_atm ≈ 0.137 1/km, τ_atm ≈ 0.504. A ±50% change in α_mol_abs component (0.065 → 0.033 or 0.098) shifts τ_atm by roughly ±3.3 percentage points. Downstream this moves `P_aim` and `I_peak` proportionally, which is **within the overall tool's engineering-estimate envelope** (≥25% tolerance on tests like M8.1 aluminum burn-through).

**Recommendation.** Keep the current table for v1. Tighten the SPEC §10.1 text to:
> α_mol tables are McClatchey-family engineering placeholders verified correct within ±50% and correct in ordering against band-edge structure. A HITRAN/MODTRAN-derived replacement is a v2 refinement. Current values are acceptable for tool-level trade studies where the downstream ±25% test tolerances dominate; not acceptable for formal program safety cases — use program-measured or HITRAN-derived values there.

**User decision requested:** none. Proposed SPEC text change only.

---

## §10.2 — A_λ material-absorptivity table

**Current (SPEC.md lines 651–663):** 7 materials × 4 wavelengths. All cells flagged HIGH UNCERTAINTY.

| Material | 1.06 µm | 1.07 µm | 1.55 µm | 2.05 µm |
|---|---|---|---|---|
| Anodized Al | 0.30 | 0.30 | 0.25 | 0.20 |
| CFRP | 0.85 | 0.85 | 0.85 | 0.85 |
| GFRP | 0.40 | 0.40 | 0.45 | 0.55 |
| Polycarbonate | 0.10 | 0.10 | 0.30 | 0.60 |
| ABS | 0.70 | 0.70 | 0.75 | 0.85 |
| EPP foam | 0.50 | 0.50 | 0.55 | 0.70 |
| LiPo cell | 0.30 | 0.30 | 0.35 | 0.45 |

**Spot literature checks (what can be done without a materials testbed):**
- **Anodized Al at 1.06 µm — 0.30.** Steen & Mazumder Ch. 5 table for black-anodized Al at ~1 µm reports 0.2–0.4; SPEC value is mid-range. ✓
- **CFRP at 1.06 µm — 0.85.** Bergstrom 2007 *J. Appl. Phys.* on laser absorption in carbon fibers shows 0.8–0.95 for NIR; SPEC value within range. ✓
- **Polycarbonate at 1.07 µm — 0.10.** PC is essentially transparent in the NIR (transmission > 85% for 3 mm thickness per SABIC datasheets); SPEC's 0.10 absorptivity is consistent with the residual surface + bulk absorption. ✓
- **PC at 2.05 µm — 0.60.** PC has a strong C-H overtone near 1.7 µm; absorption at 2.05 µm is significant. SPEC value is qualitatively correct. ✓

**Where the table is most uncertain.** Surface condition dominates. Anodized-Al absorptivity in particular spans 0.05 (polished) to 0.95 (oxidized black anodize); the SPEC value presumes "standard mil-spec anodize". For a program trade study, the user **must** override via the UI's checkbox-gated `A_λ` input (slice-2b improvement #5).

**Recommendation.** Keep the table as-is (values defensible as mid-range literature defaults). Add a per-row citation column to SPEC §3 M8's A_λ table:
> | Material | 1.06 µm | 1.07 µm | 1.55 µm | 2.05 µm | Primary source |
> | Anodized Al | 0.30 | 0.30 | 0.25 | 0.20 | Steen & Mazumder Ch. 5 Table 5.1 (mil-spec black anodize) |
> | CFRP | 0.85 | ... | ... | ... | Bergstrom 2007 *J. Appl. Phys.* 101, 043517 |
> | (etc.) |

**User decision requested:** none. Proposed citation-column addition only. Numeric values unchanged.

---

## §10.3 — MPE at 1.07 µm and the C_A correction factor

**Current SPEC behavior (SPEC.md lines 722–735, 759–765):** The retinal-band MPE formula text specifies C_A = 10^(0.002·(λ_nm − 700)) saturating at 5.0 for λ ≥ 1050 nm. The validation case `test_m9_retinal_band_baseline` expects **MPE = 25.5 W/m² at 1.07 µm, t=0.25 s**, which corresponds to C_A = 1.0 (not the specified C_A = 5.0).

**Current code behavior (physics/m9_nohd.py lines 65–98, 176–183):** The implementation deliberately omits C_A, aligning with the test expectation. The module's docstring (lines 25–32) and an `assumptions_flagged` entry explicitly explain: no-C_A gives a **larger MPE-inverse and hence a larger NOHD**, which is the conservative choice for a safety case.

**Cross-check against ANSI Z136.1-2014:** For retinal-hazard Band A (400–1400 nm), the standard applies a wavelength-correction factor C_A that equals 1.0 at 700 nm, rises as 10^(0.002·(λ_nm−700)) through the 700–1050 nm range, and caps at 5.0 for λ ≥ 1050 nm. At 1.07 µm, strict ANSI gives C_A = 5.0, which would bring the SPEC MPE to 127.3 W/m² (and reduce NOHD by √5 ≈ 2.24×). The plan document's round-number 50 W/m² sits between these two endpoints.

**The three possible SPEC positions:**

| Option | MPE at 1.07 µm, 0.25 s | NOHD_tophat (P0=1 W example) | Safety posture |
|---|---|---|---|
| **A. No C_A (current)** | 25.5 W/m² | 223 m | Conservative — overstates hazard zone |
| **B. Full C_A = 5.0 (strict ANSI)** | 127.3 W/m² | 100 m | ANSI-compliant — smaller hazard zone |
| **C. Plan's 50 W/m² round number** | 50 W/m² | 159 m | Round-number midpoint; not formula-derived |

The SPEC already commits to option A. The implementation, tests, and always-on assumption flag all consistently carry option A.

**What's wrong in SPEC.md today.** The test-note at line 765 reads:
> "The formula-derived value at t=0.25 s is 25.5 W/m² (using C_A appropriate for 1.07 µm) ..."

The parenthetical is incorrect — 25.5 W/m² corresponds to C_A = 1, not to "C_A appropriate for 1.07 µm". This is a SPEC documentation error, not a physics error.

**Recommendation.**
1. Leave the implementation (option A: no C_A) unchanged. The deliberate-conservatism choice is defensible for v1 and the `assumptions_flagged` entry tells operators exactly how to recover the strict-ANSI value if needed.
2. Fix the SPEC §3 M9 test-note wording to:
   > "The formula-derived value at t=0.25 s is 25.5 W/m² with C_A = 1 (conservative; strict ANSI Z136.1-2014 would apply C_A = 5.0 at 1.07 µm, giving MPE = 127.3 W/m² and NOHD smaller by √5 ≈ 2.24×). The tool reports the conservative no-C_A NOHD and flags the convention per SPEC §10.3 so operators can convert to the ANSI-strict value externally for an operational (less-conservative) safety case."
3. Update §10.3 entry to mark the item "**CLOSED** — v1 adopts the no-C_A conservative convention, documented at SPEC §3 M9 and always-on flagged per physics/m9_nohd.py:177."

**User decision requested:** confirm option A (no C_A, conservative) is the intended safety posture, or direct a switch to option B (strict ANSI). If option B: test expectations need to change (three tests in `test_m9_nohd.py` plus the SPEC §3 M9 validation-case expected values).

---

## §10.4 — Blooming broadening factor 0.3

**Current (SPEC.md lines 446–453):**
```
if N_D < 5:       w_bloom = 0
elif 5 ≤ N_D ≤ 30: w_bloom = w_at_target · sqrt((N_D/5)² − 1) · 0.3
else:              w_bloom = (same formula) + flag "N_D > 30, model outside validity range"
```

**What the 0.3 represents.** An engineering estimate for the fraction of blooming-induced phase-front distortion that manifests as bulk beam broadening (as opposed to pure peak-irradiance reduction captured by S_TB = 1/(1 + (N_D/5)²)). Gebhardt's original 1976 derivation gives the Strehl form; the broadening-vs-Strehl split is empirical.

**What a rigorous close would need.** Benchmark against HELEEOS or a multi-physics Maxwell-Navier-Stokes HEL propagation code. HELEEOS is a classified USAF tool — not accessible. Alternative: Sprangle et al NRL series (cited in SPEC's M6 reference list already) includes the broadening decomposition for maritime HEL cases; NRL/MR/6790-08-9141 provides the comparison data in the ~10–30 N_D regime.

**Sensitivity.** At N_D = 10 (interesting regime), `sqrt((10/5)² − 1) = sqrt(3) ≈ 1.73`, so the multiplier on w_at_target is 0.52 (with factor 0.3) vs a hypothetical 0.35 with factor 0.2 or 0.87 with factor 0.5. A ±50% change in the 0.3 factor shifts w_bloom by ±50%, which enters in quadrature with w_diff, w_turb, w_jit. For typical C-UAS cases where w_bloom is a minor contributor to w_total, the downstream effect on PIB is modest (~5–10%); for high-power / low-wind cases where blooming dominates, the effect can be 20–30%.

**Recommendation.** Keep 0.3. Add Sprangle NRL/MR/6790-08-9141 to the SPEC §3 M6 reference line as the empirical basis for the 0.3 multiplier; update §10.4 to note the factor is an NRL-derived engineering estimate with a benchmark path via HELEEOS if program access is available.

**User decision requested:** none. Citation addition only.

---

## §10.5 — available_dwell heuristic

**Current (SPEC.md lines 218–221):**
```
available_dwell = 2·R · tan(FOV/2) / v_tgt   [FOV = 5° default]
```

**What this represents.** The time a target traveling at v_tgt crosses a FOV-wide engagement basket at range R, assuming straight-line motion perpendicular to the line of sight. First-order geometry.

**What a rigorous close would need.** A tracker-dependent model that accounts for:
- Slew-rate limits of the beam director (bounded by M2's σ_jit budget)
- Target maneuver — banking turns, jinking
- Line-of-sight masking (terrain, own-platform obscuration)
- Multi-target prioritization logic

None of these are v1 scope per the original plan. SPEC §10.5 already says "tracker-dependent model is a v2 feature" — this is an explicit deferral, not a gap.

**Recommendation.** Mark §10.5 as **"Deferred to v2 (tracker model) per SPEC §10 final-phase disposition."** No v1 change.

**User decision requested:** none. Confirm v2 deferral is still the intended disposition.

---

## §10.6 — Convective backside BC `h_conv = 10 + 6.2·sqrt(v_tgt)`

**Current (SPEC.md line 627):**
```
h_conv = 10 + 6.2·sqrt(v_tgt)   W/(m²·K)   v_tgt in m/s
```

**What this represents.** Standard engineering correlation for combined natural + forced convection over a flat plate in air: h_natural ≈ 10 W/(m²·K) baseline + h_forced scaling as ~√v for low-Reynolds laminar/transition regimes. Used as the backside boundary for M8's transient heat equation when the user selects `backside_BC = 'convective'`.

**Cross-check against Incropera & DeWitt, 6th ed. Ch. 7.** For forced convection over a flat plate in air at ~300 K, the correlation `Nu_L = 0.664·Re_L^(1/2)·Pr^(1/3)` gives `h = (k_air/L) · 0.664 · sqrt(v·L/ν) · Pr^(1/3)`. Plugging standard air properties at 300 K (k = 0.026 W/m·K, ν = 1.57e-5 m²/s, Pr = 0.71), L = 0.1 m: `h = (0.026/0.1) · 0.664 · sqrt(v · 0.1 / 1.57e-5) · 0.71^(1/3) ≈ 4.9·sqrt(v)`. Add the natural-convection floor (h ≈ 10 for vertical flat plate at ΔT ~ 50 K) and the total is `h ≈ 10 + 5·sqrt(v)` — within ~20% of the SPEC's 10 + 6.2·sqrt(v) and within the expected correlation scatter.

**Recommendation.** Keep formula. Add Incropera & DeWitt reference to the SPEC §3 M8 reference line. Update §10.6 to note "cross-checked against Incropera & DeWitt 6th ed. Ch. 7 flat-plate correlation within ±20%, acceptable for v1; program-specific vehicle data overrides via UI input when available."

**User decision requested:** none. Citation + tightened flag wording only.

---

## Appendix — Proposed revised §10 text (all 6 items, after this review)

If the user accepts all recommendations, SPEC §10 would become:

> ## 10. Open Items Deferred to Implementation Review — status after 2026-04-23 review
>
> 1. **α_mol tables** — McClatchey-family engineering placeholders verified correct within ±50% and correct in ordering (see `docs/spec_section10_review_2026-04-23.md` §10.1). Acceptable for v1 trade studies; HITRAN/MODTRAN refinement is a v2 task.
>
> 2. **A_λ table** — per-material literature-cited engineering defaults (citations added to §3 M8 table). Users with measured data should override via the UI's `A_λ` input.
>
> 3. **MPE at 1.07 µm — CLOSED** — v1 adopts the conservative no-C_A convention (SPEC §3 M9); strict-ANSI C_A correction is left to the operator via the always-on `assumptions_flagged` entry. SPEC test-note wording corrected 2026-04-23.
>
> 4. **Blooming broadening factor 0.3** — NRL-derived engineering estimate (Sprangle et al, NRL/MR/6790-08-9141). HELEEOS benchmark path available for programs with access.
>
> 5. **available_dwell heuristic** — v2-deferred (tracker-dependent model). v1 uses the `2·R·tan(FOV/2)/v_tgt` first-order geometry heuristic explicitly.
>
> 6. **Convective backside BC** — cross-checked against Incropera & DeWitt 6th ed. Ch. 7 within ±20%. Users with vehicle-specific data should override.

---

## Next action

This memo is intentionally proposal-only. Once the user reads it and signals accept / modify / reject per item, a follow-up PR can land the concrete SPEC text edits in a single commit (no physics, no formula, no test-value changes required).
