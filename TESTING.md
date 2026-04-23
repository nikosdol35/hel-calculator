# TESTING.md — Validation Suite Guide

**Version:** 1.1 (Phase 0 draft, post-audit fixes)
**Authority:** This document describes *how* the validation suite works. `SPEC.md §3` defines *what* each test verifies. When in doubt, SPEC is authoritative on test content; this file is authoritative on test structure and discipline.

**Revision history:**
- v1.0 — initial draft
- v1.1 — three post-audit fixes: (1) §6 canonical_inputs fixture now includes `Cn2_value` (was missing — needed for tests that switch to constant-Cn² model) and documents why `A_lambda` and `backside_BC` are intentionally absent (absence signals "use SPEC default"); (2) §7 adds a parametrize guidance paragraph covering when to use `pytest.mark.parametrize` (related tests with same structure, different values) and when not to; (3) §7 test-placement rule sharpened — single-module tests (like M5.3 spherical/plane ratio) go in `test_mX_<module>.py`; `test_convention_consistency.py` is reserved for cross-module / cross-representation checks (like M7.4).

---

## 1. Why This Suite Exists

Every version of the project plan from v0.2 through v0.6 had physics errors that went undetected until a dedicated math-audit pass. The pattern was consistent: each error was invisible to inspection but reproducible with a Python cross-check. Five audit passes, each finding real errors.

The validation suite is the permanent version of those audit passes. Every commit to the physics core runs the full suite automatically via GitHub Actions CI. A regression that would have required a human math-audit to catch is instead caught by pytest in ~30 seconds.

The suite is the safety net that makes the tool trustworthy over time — not at first release, but across every future change. A change that improves the UI cannot silently break the physics; a change that refines a model cannot silently invalidate a validation case elsewhere.

---

## 2. What the Suite Tests

30 tests total, organized into four kinds:

**Closed-form tests (exact arithmetic)** — verify that a module's code reproduces a formula with a hand-derivable answer. Tolerance: 0.01–0.1%. Example: M1.1 (θ_diff from given P, M², D, λ).

**First-principles tests (modest tolerance)** — verify that a module's code gives the right answer against a fully worked-out reference calculation. Tolerance: 1–5%. Example: M5.1 (r₀_sph from path-integrated Cn² with known integral).

**Engineering-model tests (loose tolerance)** — verify that a module lands in the right order-of-magnitude window for an engineering calculation where the model itself has inherent uncertainty. Tolerance: 25–30%. Example: M8.1 (time-to-burn-through for 2 mm aluminum).

**Structural tests (no numerical tolerance)** — verify relationships, dimensions, limit behaviors, or algorithmic properties. Example: M5.3 verifies that `r0_sph / r0_plane = (3/8)^(-3/5) ≈ 1.801` for uniform Cn² — this catches regression to the plane-wave form.

Tolerance assignments are **per-test** and are pinned in SPEC.md §3 and in the M11 test inventory table. They are not a matter of developer judgement; they are part of the contract.

---

## 3. Test Inventory Summary

Full inventory lives in SPEC.md §3 M11 (the 30-row table). Summary here for reference:

| Module | Tests | Coverage |
|---|---|---|
| M1 — Laser source | 2 | divergence, Rayleigh range |
| M2 — Beam director | 1 | transmission arithmetic |
| M3 — Geometry | 1 | slant-range geometry |
| M4 — Atmosphere | 3 | aerosol clear, aerosol hazy, wavelength interpolation |
| M5 — Turbulence | 5 | r₀ uniform Cn², w_turb at 5 km, sph/plane ratio (structural), near-field r₀, HV_5_7 ground-level |
| M6 — Blooming | 3 | dimensional, moderate blooming canonical, low-power limit |
| M7 — Spot & PIB | 4 | pure diffraction, +turbulence, C-UAS near-field, convention consistency (structural) |
| M8 — Burn-through | 4 | aluminum standard, CFRP thin, PC NIR transparency, numerical stability |
| M9 — NOHD | 4 | retinal baseline, eye-safer band, √2 ratio (structural), chronic viewing |
| M10 — Power/thermal | 3 | steady-state, transient 50 kW, insufficient cooling |

**Total: 30 tests.**

Two kinds of tests in the table deserve special attention:

- **Structural regression tests** — M5.3 (spherical/plane r₀ ratio), M7.4 (w/σ/PIB convention consistency), M9.3 (NOHD √2 ratio). These exist specifically to catch the class of regression that caused earlier audit failures. Do not remove or weaken them even if they feel redundant.

- **Near-field regression test** — M7.3 at 1.5 km (where L/z_R ≈ 0.2). This one exists specifically because the v0.5 plan silently used the far-field `w_diff` formula and under-predicted spot size by 5× at this range. If the test fails or is removed, the far-field bug can come back.

---

## 4. Tolerance Philosophy

Tolerance is not "how close does the answer need to be." Tolerance is "how much can the answer differ from the reference before we should be worried the model is wrong." Three principles:

**(a) Tolerance matches the physical uncertainty of the model.** M8 burn-through is fundamentally ±25% because material properties have ±15% uncertainty and absorption coefficients have ±30%. A 2% tolerance there would be overclaiming. M7 spot size is fundamentally 2% because the physics is closed-form and the only uncertainty is numerical roundoff.

**(b) Tolerance tightens toward the input end and loosens toward the output end.** M1 is tighter than M7 is tighter than M8, because each subsequent module stacks additional model-uncertainty contributions. The M11 test inventory reflects this gradient.

**(c) Structural tests have no tolerance.** They verify exact mathematical identities or ratios. `r0_sph / r0_plane = 1.801` to 0.1% — because the formula itself is an identity, not a measurement. A structural test failing at 0.1% means the code has a bug, not a model mismatch.

When adding a new test, **do not guess the tolerance**. Either:
- Derive the answer from closed-form math → use 0.1% or tighter
- Cite a published reference or benchmark → use the tolerance the reference itself claims
- The answer comes from an engineering estimate → use 25% or document why looser is acceptable

---

## 5. File Layout

Per ARCHITECTURE.md §3:

```
tests/
├── __init__.py
├── conftest.py                          ← Shared fixtures (see §6)
├── test_m1_laser_source.py              ← 2 tests: test_m1_divergence, test_m1_rayleigh_range
├── test_m2_beam_director.py             ← 1 test: test_m2_transmission
├── test_m3_geometry.py                  ← 1 test: test_m3_geometry
├── test_m4_atmosphere.py                ← 3 tests
├── test_m5_turbulence.py                ← 5 tests
├── test_m6_blooming.py                  ← 3 tests
├── test_m7_spot_pib.py                  ← 4 tests
├── test_m8_burnthrough.py               ← 4 tests
├── test_m9_nohd.py                      ← 4 tests
├── test_m10_power_thermal.py            ← 3 tests
├── test_convention_consistency.py       ← Cross-module structural tests (M7.4 and related)
└── test_import_rules.py                 ← Verifies physics/ has no ui/ imports
```

One test file per physics module. Test function names match the IDs in SPEC.md §3 (e.g., `test_m7_typical_c_uas_1500m`). Cross-module structural tests go in `test_convention_consistency.py`.

`test_import_rules.py` is not a physics test — it parses each `.py` file under `physics/` with Python's `ast` module and verifies that no import statement references `ui` or `tests`. It runs as part of `pytest tests/` but fails fast with an architectural error rather than a numerical error.

---

## 6. Fixtures (`conftest.py`)

Shared test fixtures live in `tests/conftest.py`. The canonical fixture is `canonical_inputs`, which returns the Panel A–F default parameter set from SPEC.md §5.1. Tests needing variations of the canonical inputs make a local copy and modify; they do not edit the fixture.

```python
# tests/conftest.py
import pytest

@pytest.fixture
def canonical_inputs():
    """
    The Panel A–F default parameter set from SPEC.md §5.1.
    Represents a typical C-UAS engagement at 1.5 km with a 3 kW laser.
    """
    return {
        # Panel A — Laser Source
        'P0': 3000, 'M2': 1.2, 'D': 0.10, 'wavelength': 1.07e-6,
        # Panel B — Beam Director
        'eta_opt': 0.85, 'sigma_jit': 10e-6,
        # Panel C — Engagement Geometry
        'H_e': 2, 'R': 1500, 'H_t': 200, 'v_tgt': 20, 'v_perp': 3,
        # Panel D — Atmosphere
        'V': 23, 'RH': 0.60, 'T_ambient': 300,
        'cn2_model': 'HV_5_7', 'Cn2_value': 1e-14, 'Cn2_ground': 1.7e-14, 'v_HV': 21,
        # Panel E — Aimpoint & Material
        'd_aim': 0.05, 'material': 'CFRP', 'thickness': 0.002,
        # Panel F — System Resources & Safety
        'eta_wallplug': 0.30, 'Q_cool': 15000,
        'C_thermal': 200e3, 'dT_max': 30, 't_exp': 0.25,
    }
```

**Keys intentionally absent from this fixture:**

- **`A_lambda`** — SPEC §3 M8 specifies a per-material, per-wavelength default (from `m8_material_tables.py`). Omitting this key from inputs signals "use the table default." Tests that want to override A_λ explicitly (e.g., to verify how the burn-through time scales with absorptivity) should add it in the local test copy of the fixture.
- **`backside_BC`** — SPEC §3 M8 default is `'insulated'`. Same pattern as A_λ: absence signals default. Tests that verify convective cooling should set `backside_BC='convective'` locally.

**Key included but inactive for default fixture:** `Cn2_value` is included at `1e-14` but is unused when `cn2_model='HV_5_7'` (the HV profile supplies its own Cn² per altitude). Tests that switch to `cn2_model='constant'` use this key directly. Including it in the canonical fixture means switching models in a test requires only a one-key override, not a two-key edit.

Additional fixtures may be added for specific test patterns (e.g., `clear_atmosphere` that overrides `V=50`, `RH=0.20`). Add them to `conftest.py`, not to individual test files.

---

## 7. Test Function Structure

Every test follows this pattern:

```python
def test_m<N>_<short_name>(canonical_inputs):
    """
    <One-sentence description of what this test verifies.>
    Reference: SPEC.md §3 M<N> validation case "<ID>"
    Expected from SPEC: <value> (tolerance <N>%)
    """
    # Arrange: build the module's input dict
    inputs = {
        'key_1': canonical_inputs['key_1'],
        'key_2': <specific_value_for_this_test>,
        # ...
    }
    
    # Act: call the module
    result = m<N>_<module>.compute(inputs)
    
    # Assert: numerical check with pytest.approx
    assert result['output_key'] == pytest.approx(<expected>, rel=<tolerance>)
    
    # For structural tests: verify the identity/relationship
    assert result['ratio_key'] == pytest.approx(<ratio_value>, rel=0.001)
```

**Assertion rules:**

- Use `pytest.approx(expected, rel=tolerance)` for all numerical comparisons. Never `==` on floats.
- `rel=0.02` means "within 2%" — relative tolerance matches SPEC §3 tolerance column.
- `abs=1e-9` is sometimes appropriate for quantities that should be ~zero (e.g., checking a correction term is negligible).
- For boolean/string outputs, use exact `==`.
- For list/dict outputs (like `assumptions_flagged`), check membership (`'warning' in result['assumptions_flagged']`) rather than list equality — the order of flags is not contractually fixed.

**What NOT to do:**

- Do not add a test without a SPEC.md §3 reference. If SPEC doesn't cover the case, update SPEC first (per CLAUDE.md §3 step 1).
- Do not loosen a tolerance because a test is failing. The tolerance is part of the contract. If the test is genuinely wrong, fix the code; if the code is genuinely right and the test is wrong, update both the test and the SPEC.
- Do not use `try/except` to make a test "pass by catching the exception." A failing test is a signal.
- Do not duplicate tests across files. **Test placement rule:** A test belongs in `tests/test_mX_<module>.py` when it verifies a property of a *single module* — even if that property is a ratio or identity internal to the module. Examples: M5.3 (spherical/plane r₀ ratio) verifies an internal M5 identity → goes in `test_m5_turbulence.py`; M9.3 (NOHD √2 ratio) verifies an internal M9 relationship → goes in `test_m9_nohd.py`. A test belongs in `tests/test_convention_consistency.py` only when it verifies a relationship that *spans multiple modules* or *cross-checks different representations of the same quantity* — for example, M7.4 verifies that the w-convention PIB formula and the σ-convention PIB formula give identical results when σ = w/2, which is a cross-representation check that could be violated by a bug anywhere in M7 or M1. When uncertain, default to `test_mX_<module>.py` — cross-cutting tests are the exception, not the rule.

**Parametrized tests (`pytest.mark.parametrize`):**

Use parametrize when a group of tests share the same *structure* but differ only in *values* — for example, M4's three aerosol tests (clear/hazy/wavelength-interp) all compute `α_aer` from `(V, RH, wavelength)` and check a single output against an expected value. Parametrize collapses this into a single function body with a data table:

```python
@pytest.mark.parametrize("V, RH, wavelength_um, expected_alpha_aer", [
    pytest.param(23, 0.60, 1.07, 0.072, id="m4_clear"),   # SPEC M4.1
    pytest.param( 5, 0.60, 1.07, 0.366, id="m4_hazy"),    # SPEC M4.2
])
def test_m4_aerosol_kruse(V, RH, wavelength_um, expected_alpha_aer, canonical_inputs):
    inputs = {**canonical_inputs, 'V': V, 'RH': RH, 'wavelength': wavelength_um * 1e-6}
    result = m4_atmosphere.compute(inputs)
    assert result['alpha_aer_total_per_km'] == pytest.approx(expected_alpha_aer, rel=0.05)
```

Use parametrize when:
- Three or more tests share identical arrange/act/assert structure with only numeric differences.
- Each parametrize row maps 1-to-1 with a SPEC §3 validation case (put the SPEC test ID in the `id=` field so pytest output remains readable).

Do NOT use parametrize when:
- The tests verify fundamentally different physics (e.g., do not parametrize across M5's `r0_sph` test and M5's `w_turb` test — they test different quantities).
- The expected output shape differs between cases (e.g., one returns a scalar, another returns a dict structure).
- The tolerances differ between cases (forces awkward conditional tolerance logic; write separate tests instead).

When in doubt, write the tests as separate functions first — parametrize is a refactor, not an architectural choice.

---

## 8. Running the Suite

### Locally (for developers / Claude Code)

```bash
# Full suite
pytest tests/ -v

# Single module
pytest tests/test_m7_spot_pib.py -v

# Single test
pytest tests/test_m7_spot_pib.py::test_m7_pure_diffraction_5km -v

# Show print output (useful for debugging)
pytest tests/ -v -s

# Stop on first failure
pytest tests/ -x
```

Expected runtime: approximately 30 seconds for the full suite (SPEC.md §3 M11 states "< 30 seconds total" for the physics tests; pytest's startup and teardown add a few seconds of overhead on top, so a total wall-clock around 30–40 s in CI is normal). If the suite takes much longer than a minute, investigate — something is probably running an unneeded sweep or a heavy M8 simulation with too-fine discretization.

### In CI (GitHub Actions)

The suite runs automatically on every commit to `main` and every pull request (see `.github/workflows/test.yml`). CI output is visible in the GitHub UI under the "Actions" tab. A failing test appears as a red X next to the commit; a passing run appears as a green check.

### From the UI (for the end user)

The tool exposes a "Run Validation Suite" button in the sidebar. When clicked, it invokes the M11 `run_validation_suite()` function (per SPEC.md §3 M11) which executes pytest programmatically and renders a formatted pass/fail report in the Streamlit interface. This lets the user verify the tool's correctness without leaving the browser.

---

## 9. Failure Handling

### When a test fails during normal development

Per CLAUDE.md §4.1, `pytest tests/` runs before every commit. If a test fails:

1. **Read the error carefully.** `pytest.approx` shows both the expected and actual values — the first clue is usually the ratio.
2. **Is the code wrong, or is the test wrong?**
   - If the code changed and the test was working before, the code is probably wrong. Revert to the last working commit and re-check.
   - If the test is new and the code was working before, the test might be wrong. Verify the expected value against SPEC.md §3 and against a hand calculation.
   - If both are new, verify the math against first principles before trusting either.
3. **Do not loosen the tolerance to make it pass.** If the current tolerance is wrong for the physics, that's a SPEC update, not a test edit.
4. **After two failed fix attempts, escalate** (per CLAUDE.md §9). Report the exact pytest output to the user; do not silently keep trying.

### When a test fails in CI but passes locally

Usually a dependency-version difference. Check `requirements.txt`: are the pins correct? Did the local environment drift from the pinned versions? The fix is to match the local environment to the pins, not vice versa.

### When a new module's test doesn't exist yet

This is Phase 1 before Phase 2, or Phase 2 before Phase 3, etc. — it's the expected interim state while a module is being developed. The rule: **a module is not considered "done" until its tests exist and pass.** A pull request that adds a module without tests does not merge.

---

## 10. Adding New Tests

Three common scenarios:

### (A) New material added to M8

1. Add the material properties and A_λ row to `physics/m8_material_tables.py`.
2. Add a SPEC.md §3 M8 validation case for this material (must include expected burn-through time and tolerance).
3. Add a test function in `tests/test_m8_burnthrough.py` following the naming pattern `test_m8_<material>_<scenario>`.
4. Verify the test passes.
5. Update the M11 test inventory row count in SPEC.md §3.

### (B) New model refinement

If a refined blooming model, turbulence model, or similar replaces an existing calculation:

1. **First**, cite the new reference in CLAUDE.md §4.6 format — papers, tolerances, and validity ranges.
2. Update SPEC.md §3 for the affected module — equations and validation cases.
3. Verify the existing structural regression tests (e.g., M7.3 near-field, M5.3 spherical/plane ratio) still pass. If they don't, the refinement has side effects that must be reported.
4. Add a new test for the refinement's specific regime if SPEC.md is updated to cover it.

### (C) New regression test after an audit finding

Exactly the pattern that gave us M5.3, M7.3, and M7.4. When a bug is found in an already-shipped module:

1. Write the test that catches the bug (this test should FAIL with the buggy code).
2. Fix the code.
3. Verify the test passes.
4. Add the test to SPEC.md §3 with a clear description of what regression it guards against.

This is the discipline that keeps the safety net growing. The test inventory is not fixed at 30 — every real bug found should add a test.

---

## 11. What the Suite Does NOT Do (v1 Scope)

These are deliberately out of scope for v1; do not add them unless SPEC is updated first:

- **Property-based testing (Hypothesis).** Current tests are example-based (specific inputs → specific outputs). Property-based testing is a valuable addition but requires defining invariants — deferred to v2.
- **Performance benchmarks.** The ARCHITECTURE.md §5.2 timing estimates are not validated by tests. A benchmark suite could be added later.
- **End-to-end UI tests (Selenium/Playwright).** Plot rendering and panel interactions are verified by manual user testing against the live URL. Automating this is a v2 concern.
- **Mutation testing.** Tools like `mutmut` verify that tests actually catch bugs. Useful but not essential for v1.
- **Sweep-across-range integration tests.** The single-point orchestrator chain (M1 → M2 → ... → M10 with M6↔M7 iteration) is exercised directly by `tests/test_orchestrator.py` (added once `physics/orchestrator.py` landed — the file was moved out of `ui/` into `physics/` in ARCHITECTURE v1.3 / SPEC v1.4 precisely to make this test possible under the §2 import rules). What is still out of scope for v1 is a range-sweep integration test that runs the chain at every point of a sweep array and asserts continuity/monotonicity properties — the per-plot sweeps (A, B, C) are validated by manual review against the live Streamlit app rather than by pytest.

---

## 12. Summary

**Rules of thumb:**
- 30 tests, SPEC-pinned, no exceptions
- Tolerance matches physical uncertainty, not wishful thinking
- Structural tests prevent regressions (keep them, don't weaken them)
- `pytest.approx` always; raw `==` on floats never
- Every new test traces to SPEC §3
- Every audit finding adds a test
- "Done" means tests exist and pass, not "code compiles"

The suite is the first thing to consult when something feels wrong, the first thing to run before every commit, and the first thing to extend when scope grows. It is the reason the tool can be trusted over time.

---

**END OF TESTING.md v1.1 (Phase 0 draft, post-audit fixes)**
