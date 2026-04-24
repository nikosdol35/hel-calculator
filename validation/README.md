# Validation tree

This directory holds the documented argument that every number the HEL calculator prints is right to within a stated tolerance, and that every assumption behind it is explicit.

The tree is organised as five layered work packages; this file tracks which are in place. Each layer stands alone and ends at a user-reviewable artefact.

## Layer 1 — Formula and constants audit (Package 1)

- `derivations/m1_source.md` — M1 Gaussian-beam divergence, Rayleigh range, exit-aperture irradiance.
- `derivations/m2_power_link.md` — M2 optical-train transmission.
- `derivations/m3_director.md` — M3 slant/horizontal range, elevation, dwell heuristic.
- `derivations/m4_atmosphere.md` — M4 Kruse aerosol + tabulated molecular extinction + Beer-Lambert.
- `derivations/m5_turbulence.md` — M5 HV-5/7 Cn² profile, Fried r₀_sph, engineering w_turb.
- `derivations/m6_blooming.md` — M6 Gebhardt N_D and Smith Strehl S_TB.
- `derivations/m7_spot.md` — M7 exact-Gaussian w_diff, quadrature-sum spot, PIB.
- `derivations/m8_thermal.md` — M8 1-D transient heat PDE, surface-flux BC, convective backside; includes the 7-material property table and 4-wavelength A_λ matrix with per-value provenance.
- `derivations/m9_safety.md` — M9 ANSI Z136.1-2014 MPE, top-hat vs Gaussian-peak NOHD.
- `derivations/m10_power.md` — M10 power/thermal budget, lumped-mass coolant model, duty cycle.
- `derivations/m11_dwell.md` — dwell heuristic derivation (SPEC §10.5; formula in `m3_geometry.py` line 61–65).
- `constants_audit.md` — master roster of every hard-coded numeric constant in `physics/` (≈ 152 values).
- `input_bounds_audit.md` — every `validate_range(...)` bound cross-checked against SPEC validity.

## Layer 2 — Test-coverage expansion (Package 2)

Goes into `tests/` directly; no files under `validation/` for this layer. See the plan document for the test-file roster.

## Layer 3 — Numerical-methods validation (Package 3)

- `methods/m8_solver.md` — M8 heat PDE: analytic benchmark, grid refinement, CFL, conservation.
- `methods/m6_m7_iteration.md` — M6↔M7 fixed-point: convergence sweep, self-consistency, path-independence.
- `methods/m5_r0_integral.md` — `scipy.integrate.quad` on the r₀ weighting integral.
- `methods/m4_interp.md` — `interp_log_space` validation.

## Layer 4 — HIGH UNCERTAINTY closeout (Package 4)

- `uncertainty_closeout.md` — per-item review of SPEC §10 entries, dispositioning each as close-at-current / revise-with-citation / defer-to-v2 after Packages 1–3. Zero paired SPEC + code edits required in this package; the one physics-level paired edit of the campaign (v1.12 M9 pulsed-regime MPE typo) was applied during Package 3.

## Layer 5 — Independent replication (Package 5)

- `replication/replication_notebook.ipynb` — independent implementations of M1, M5, M7, M8.
- `replication/replication_report.md` — per-scenario comparison table.

## How to audit

Start with `constants_audit.md` and `input_bounds_audit.md` — these surface the specific numbers that must be correct. Then read the per-module derivation files in order: each one traces the module's formulas from first principles to the code line that implements them. Any disagreement between source and code is flagged explicitly in the derivation file's "status" column.

Layer 2 test coverage and Layer 3 numerical-methods reports complement the derivation files: the derivation says "this is the right formula," the test says "the code evaluates that formula correctly at these points," and the methods report says "the solver behind the formula is numerically sound."

## Notation

- **CLAUDE §7.1** refers to the eleven audit-sensitive formulas listed in the top-level `CLAUDE.md`. Every citation to that section is a reminder that the formula has been subject to extra scrutiny.
- **SPEC §N.M** refers to the top-level `SPEC.md` document.
- **HIGH UNCERTAINTY** values are listed in `SPEC.md` §10; each derivation file flags the §10 entries it relies on.

## Revision log

- 2026-04-24 — tree created; Package 1 files written.
- 2026-04-24 — Package 3 Layer 3 numerical-methods files written (`methods/m8_solver.md`, `methods/m6_m7_iteration.md`, `methods/m5_r0_integral.md`, `methods/m4_interp.md`) with companion tests in `tests/test_m8_numerics.py`, `tests/test_m6_m7_convergence.py`, `tests/test_m5_numerics.py`. Layer 3.4 (M4 interp) is doc-only — reuses the Package 2 `tests/test_helpers.py` coverage.
- 2026-04-24 — Package 4 Layer 4 HIGH UNCERTAINTY closeout written (`uncertainty_closeout.md`). All six SPEC §10 items re-reviewed against 2026-04-24 literature and Packages 1–3 outputs. Five confirm prior disposition (close-at-current); one surfaces an ANSI Z136.1-2022 citation-refresh path (v2-scope, tool's current no-C_A 2014 formulas remain conservative under 2022); one remains deferred to v2 (available_dwell tracker-model). Zero paired SPEC + code edits required this package.
