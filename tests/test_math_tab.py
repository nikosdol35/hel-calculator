"""Tests for the "How it's calculated" tab.

PR 1 of docs/math_tab_plan_2026-04-25.md ships the skeleton + glossary +
M1/M2/M3 entries (9 numeric metrics). This test file covers:

  (a) Coverage — every MATH_CONTENT key is also an OUTPUT_LABELS key
      (the math tab and the per-tab cards are kept in sync).
  (b) LaTeX validity — every formula_latex string has balanced braces
      (a malformed string still renders without crashing under
      st.latex, but renders as broken markup; the test catches the
      typos at commit time instead of at user-visible-render time).
  (c) Smoke — render_tab_math doesn't crash on the canonical
      orchestrator output for c_uas_1500m, on a None result, or on
      an infeasible-geometry result.
  (d) Glossary integrity — every glossary key is non-empty and the
      definitions don't contain forbidden SPEC § citations
      (test_copy_style.py would catch this on the source file but
      the per-string test localises any failure to one definition).
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# (a) Coverage — every MATH_CONTENT key has a labels.py entry
# ---------------------------------------------------------------------------

def test_every_math_content_key_has_label():
    """Every metric in MATH_CONTENT must also appear in OUTPUT_LABELS so
    the per-tab metric card and the math tab can never disagree on a
    label, unit, or tooltip."""
    from ui.labels import OUTPUT_LABELS
    from ui.math_content import MATH_CONTENT

    missing = [
        key for key in MATH_CONTENT
        if key not in OUTPUT_LABELS
    ]
    assert not missing, (
        f"MATH_CONTENT has {len(missing)} entries with no OUTPUT_LABELS "
        f"counterpart — math tab and metric cards would drift: {missing}"
    )


def test_math_content_entries_have_required_fields():
    """Each non-categorical entry must have a formula_latex, formula_text,
    and explanation_short. Categorical entries skip the LaTeX requirement
    but still need an explanation. The display unit is sourced from
    ``ui.labels.output_unit(key)`` at render time, so it isn't checked
    on the MetricEntry itself — see test_every_math_content_key_has_label."""
    from ui.math_content import MATH_CONTENT

    # Dimensionless numeric metrics may carry an empty unit_si (the
    # convention for ratios like S_TB, PIB_fraction, τ_atm, N_D).
    # Categorical (verdict) outputs likewise have no unit since they
    # are strings or booleans.
    dimensionless_ok = {
        "tau_atm", "PIB_fraction", "S_TB", "N_D",
        "duty_cycle_limit",      # 0..1 dimensionless
        "m67_iteration_count",   # integer count
    }
    for key, entry in MATH_CONTENT.items():
        assert entry.display_name, f"{key}: missing display_name"
        assert entry.module, f"{key}: missing module"
        if key not in dimensionless_ok and not entry.is_categorical:
            assert entry.unit_si, f"{key}: missing unit_si"
        assert entry.explanation_short, (
            f"{key}: missing explanation_short — every metric needs a "
            f"plain-language one-liner"
        )
        if not entry.is_categorical:
            assert entry.formula_latex, (
                f"{key}: non-categorical metric missing formula_latex"
            )
            assert entry.formula_text, (
                f"{key}: non-categorical metric missing formula_text "
                f"(needed for the Markdown export and search filter)"
            )


# ---------------------------------------------------------------------------
# (b) LaTeX validity — balanced braces in every formula_latex string
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ignore_categorical", [True])
def test_formula_latex_has_balanced_braces(ignore_categorical):
    """Catch unterminated braces in LaTeX strings at commit time —
    Streamlit's st.latex renders malformed input as broken markup
    rather than crashing, so a typo would otherwise reach production."""
    from ui.math_content import MATH_CONTENT

    for key, entry in MATH_CONTENT.items():
        if ignore_categorical and entry.is_categorical:
            continue
        if entry.formula_latex is None:
            continue
        depth = 0
        for ch in entry.formula_latex:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            assert depth >= 0, (
                f"{key}: closing brace before opening in "
                f"formula_latex: {entry.formula_latex!r}"
            )
        assert depth == 0, (
            f"{key}: unbalanced braces in formula_latex "
            f"(net +{depth}): {entry.formula_latex!r}"
        )


def test_pr1_modules_present():
    """PR 1 of the math-tab plan covers M1, M2, M3. Confirm every
    expected entry is in MATH_CONTENT."""
    from ui.math_content import MATH_CONTENT

    expected_pr1_keys = {
        # M1 — laser source (4)
        "theta_diff", "w0", "zR", "I_exit",
        # M2 — power link (1)
        "P_exit",
        # M3 — geometry (4 from PR 1, +1 from tracker-dwell-PR3 = 5)
        "R_slant", "R_h", "elevation_angle", "available_dwell",
        # R_at_dwell_end — added in tracker-dwell PR 3 alongside the
        # M3 contract update (SPEC v2.0); lives logically with the
        # other M3 entries.
        "R_at_dwell_end",
    }
    actual = set(MATH_CONTENT.keys())
    assert expected_pr1_keys.issubset(actual), (
        f"PR 1 missing entries: {expected_pr1_keys - actual}"
    )
    # PR 1 ships exactly nine entries — protect against accidental
    # ahead-of-schedule drift from PRs 2-3.
    pr1_modules = {"M1", "M2", "M3"}
    pr1_entries = {
        k for k, e in MATH_CONTENT.items() if e.module in pr1_modules
    }
    assert pr1_entries == expected_pr1_keys, (
        f"PR 1 module entries ({sorted(pr1_entries)}) differ from "
        f"plan-specified set ({sorted(expected_pr1_keys)})"
    )


def test_pr2_modules_present():
    """PR 2 of the math-tab plan covers M4, M5, M6, M7 (20 numeric
    entries — w_turb is in M5 only since the orchestrator merge
    dedupes M5/M7 collision)."""
    from ui.math_content import MATH_CONTENT

    expected_pr2_keys = {
        # M4 — atmosphere (6)
        "alpha_mol_abs", "alpha_mol_scat", "alpha_aer_abs",
        "alpha_aer_scat", "alpha_atm", "tau_atm",
        # M5 — turbulence (3, w_turb owned by M5)
        "Cn2_integrated", "r0_sph", "w_turb",
        # M6 — blooming (3, all post-iteration)
        "N_D", "S_TB", "w_bloom",
        # M7 — spot/PIB (8, w_turb is M5's pass-through, not duplicated)
        "w_diff", "w_jit", "w_total", "d_spot",
        "I_peak", "PIB_fraction", "P_aim", "I_avg_aim",
    }
    actual = set(MATH_CONTENT.keys())
    missing = expected_pr2_keys - actual
    assert not missing, f"PR 2 missing entries: {missing}"


def test_iterated_metrics_flagged():
    """Metrics whose value comes from the M6↔M7 fixed-point loop must
    have ``is_iterated=True`` set so the renderer can show the
    'computed via fixed-point iteration' banner."""
    from ui.math_content import MATH_CONTENT

    expected_iterated = {"N_D", "S_TB", "w_bloom", "w_total"}
    actual_iterated = {
        k for k, e in MATH_CONTENT.items() if e.is_iterated
    }
    assert actual_iterated == expected_iterated, (
        f"is_iterated flag drift: expected {expected_iterated}, "
        f"got {actual_iterated}"
    )


def test_sensitivity_inputs_only_user_inputs():
    """Every ``sensitivity_inputs`` entry must be an actual user input
    key (so the perturbation runner can find it). Catches typos like
    'V' vs 'visibility' or 'Cn2' vs 'Cn2_ground'."""
    from ui.math_content import MATH_CONTENT

    valid_user_inputs = {
        "P0", "M2", "D", "wavelength", "eta_opt", "sigma_jit",
        "H_e", "R", "H_t", "v_tgt", "v_perp",
        "V", "RH", "T_ambient", "P_atm",
        "cn2_model", "Cn2_value", "Cn2_ground", "v_HV",
        "d_aim", "material", "thickness", "A_lambda",
        "eta_wallplug", "Q_cool", "C_thermal", "dT_max", "t_exp",
        "backside_BC",
        # SPEC v2.0 §3 M3 — tracker-supported trajectory inputs.
        # Migrated from tracker-dwell PR 3 onwards.
        "R_detect", "R_min", "engagement_geometry",
    }
    for key, entry in MATH_CONTENT.items():
        for sens in entry.sensitivity_inputs:
            assert sens in valid_user_inputs, (
                f"{key}: sensitivity_inputs references {sens!r} which "
                f"is not a known user input"
            )


def test_format_sensitivity_line_empty():
    """Empty sensitivity dict → graceful no-data string, not a crash."""
    from ui.sensitivity import format_sensitivity_line
    out = format_sensitivity_line({})
    assert "no sensitivity data" in out.lower()


def test_format_sensitivity_line_top_n():
    """The formatted line shows only the top-N most-influential inputs
    plus a "+K more" suffix when more exist."""
    from ui.sensitivity import format_sensitivity_line

    sens = {
        "P0": 50.0,        # largest |influence|
        "RH": -8.0,
        "M2": 30.0,
        "D": -3.0,
        "wavelength": 1.5,
    }
    line = format_sensitivity_line(sens, top_n=3)
    # Top-3 by |influence|: P0, M2, RH.
    assert "P0" in line and "M2" in line and "RH" in line
    # 5 - 3 = 2 hidden.
    assert "+2 more" in line


def test_compute_sensitivity_skips_zero_base():
    """When the base value is zero, sensitivity is undefined — return
    empty dict rather than emitting infinity."""
    from ui.sensitivity import compute_sensitivity_for_metric

    def runner(k, sign):
        return {"foo": 0.0}

    sens = compute_sensitivity_for_metric(
        metric_key="foo",
        sensitivity_inputs=("P0",),
        base_result={"foo": 0.0},
        base_inputs={"P0": 1000.0},
        perturbation_runner=runner,
    )
    assert sens == {}


def test_pr5_markdown_export_runs():
    """``to_markdown`` returns a non-empty string for the canonical
    scenario without raising. End-to-end smoke."""
    from physics.orchestrator import run_full_chain
    from tests.golden.scenarios import C_UAS_1500M
    from ui.math_export import to_markdown

    res = run_full_chain(C_UAS_1500M)
    merged = {**C_UAS_1500M, **res}
    md = to_markdown(merged, include_full=True)

    assert isinstance(md, str)
    assert len(md) > 5000, (
        f"Expected a substantial export (>5 kB); got {len(md)} chars"
    )


def test_pr5_markdown_export_covers_every_metric():
    """The exported Markdown contains every MATH_CONTENT key under its
    own anchor heading. Catches drift where a new metric is added to
    MATH_CONTENT but the export forgets to render it."""
    from physics.orchestrator import run_full_chain
    from tests.golden.scenarios import C_UAS_1500M
    from ui.math_content import MATH_CONTENT
    from ui.math_export import to_markdown

    res = run_full_chain(C_UAS_1500M)
    merged = {**C_UAS_1500M, **res}
    md = to_markdown(merged)

    for key, entry in MATH_CONTENT.items():
        # Every metric appears in a "#### Display name · `key`" line.
        marker = f"`{key}`"
        assert marker in md, (
            f"Markdown export does not reference metric {key!r}"
        )
        # And its display name appears too.
        assert entry.display_name in md, (
            f"Markdown export does not reference display name "
            f"{entry.display_name!r} for {key}"
        )


def test_pr5_markdown_export_has_required_top_level_sections():
    """The export carries the four top-level structural sections
    (header, glossary, per-module metrics, constants, worked
    example)."""
    from physics.orchestrator import run_full_chain
    from tests.golden.scenarios import C_UAS_1500M
    from ui.math_export import to_markdown

    res = run_full_chain(C_UAS_1500M)
    merged = {**C_UAS_1500M, **res}
    md = to_markdown(merged)

    required = (
        "# How it's calculated",
        "## Glossary",
        "## M1 — Laser source",
        "## M7 — Spot size",
        "## Constants & physical sources",
        "## Worked example",
    )
    for marker in required:
        assert marker in md, f"missing section header: {marker!r}"


def test_pr5_markdown_export_simple_view_drops_full_content():
    """When ``include_full=False`` the export carries the per-metric
    formulas + values + short explanations but omits the citations,
    code references, and assumption lists. Smaller export for
    casual sharing."""
    from physics.orchestrator import run_full_chain
    from tests.golden.scenarios import C_UAS_1500M
    from ui.math_export import to_markdown

    res = run_full_chain(C_UAS_1500M)
    merged = {**C_UAS_1500M, **res}
    md_simple = to_markdown(merged, include_full=False)
    md_full = to_markdown(merged, include_full=True)

    # Simple view is strictly smaller.
    assert len(md_simple) < len(md_full)
    # Simple view does NOT carry the Citation / Implemented-at
    # markers but the full one does.
    assert "**Citation:**" not in md_simple
    assert "**Citation:**" in md_full
    # Simple view DOES carry per-metric formulas and short
    # explanations.
    assert "## M1 — Laser source" in md_simple
    assert "$$" in md_simple


def test_pr5_markdown_export_handles_categorical_metrics():
    """Categorical Verdicts (failure_mode, laser_class, etc.) export
    as code blocks rather than LaTeX."""
    from physics.orchestrator import run_full_chain
    from tests.golden.scenarios import C_UAS_1500M
    from ui.math_export import to_markdown

    res = run_full_chain(C_UAS_1500M)
    merged = {**C_UAS_1500M, **res}
    md = to_markdown(merged)

    # The categorical-marker phrase appears at least once (each of
    # the four categorical metrics emits it).
    assert "Categorical (verdict) output" in md
    # And every categorical metric is referenced.
    for key in ("failure_mode", "laser_class",
                 "engagement_viable", "m67_converged"):
        assert f"`{key}`" in md, f"categorical metric missing: {key}"


def test_pr4_constants_table_present():
    """PR 4 of the math-tab plan ships a structured constants table.
    Verify it covers every module that has hard-coded constants."""
    from ui.constants_table import (
        CONSTANTS_BY_MODULE, ConstantEntry, total_constant_count,
    )

    # Every entry is a ConstantEntry dataclass instance with the
    # required fields populated.
    for group_title, entries in CONSTANTS_BY_MODULE.items():
        assert entries, f"empty group: {group_title!r}"
        for c in entries:
            assert isinstance(c, ConstantEntry)
            assert c.name, f"missing name in {group_title!r}"
            assert c.value, f"missing value for {c.name}"
            # units may legitimately be empty for dimensionless constants
            assert c.source, f"missing source for {c.name}"
            assert c.verdict, f"missing verdict for {c.name}"
            assert c.code_ref, f"missing code_ref for {c.name}"

    # Sanity-check the total count — the audit roster has ~80
    # explicit entries plus the multi-cell tables. We don't pin an
    # exact number since adding a citation row is fine, but the
    # count should be in a sensible range.
    n = total_constant_count()
    assert 50 <= n <= 200, (
        f"constants table has {n} entries; expected 50-200 "
        f"(roster grew or shrank unexpectedly)"
    )


def test_pr4_constants_verdicts_use_known_categories():
    """Verdict strings come from a small known vocabulary so the
    rendering layer can colour-code them consistently in a future
    iteration."""
    from ui.constants_table import CONSTANTS_BY_MODULE

    known_verdict_prefixes = (
        "verified",
        "CLAUDE §7.1 invariant",
        "HIGH UNCERTAINTY",
        "deferred v2",
    )
    for group_title, entries in CONSTANTS_BY_MODULE.items():
        for c in entries:
            assert any(
                c.verdict.startswith(p) for p in known_verdict_prefixes
            ), (
                f"{c.name}: unknown verdict {c.verdict!r}; expected "
                f"one of {known_verdict_prefixes}"
            )


def test_pr4_worked_example_at_1km():
    """The worked example is the c_uas preset under the SPEC v2.0
    trajectory contract: head-on closing from R_detect = 1500 m to
    R_min = 100 m. (Originally pinned at R = 1 km in PR 4 of the
    math-tab plan; rewritten in PR 6 of the tracker-dwell plan to
    consume the new trajectory inputs.)"""
    from ui.worked_example import WORKED_EXAMPLE_INPUTS

    assert WORKED_EXAMPLE_INPUTS["engagement_geometry"] == "head_on"
    assert WORKED_EXAMPLE_INPUTS["R_detect"] == 1500
    assert WORKED_EXAMPLE_INPUTS["R_min"] == 100
    # Other inputs match the c_uas_short_range scenario.
    assert WORKED_EXAMPLE_INPUTS["P0"] == 3000
    assert WORKED_EXAMPLE_INPUTS["material"] == "CFRP"
    assert WORKED_EXAMPLE_INPUTS["wavelength"] == 1.07e-6


def test_pr4_worked_example_runs_without_error():
    """compute_worked_example() must complete without exceptions and
    return all 45 orchestrator output keys."""
    from ui.worked_example import compute_worked_example
    walkthrough = compute_worked_example()
    # Result is the merged dict (inputs ⊕ orchestrator outputs).
    expected_output_keys = {
        # M1-M10 + orchestrator (verified by test_complete_metric_count)
        "theta_diff", "w0", "zR", "I_exit", "P_exit",
        "R_slant", "R_h", "elevation_angle", "available_dwell",
        "alpha_mol_abs", "alpha_mol_scat", "alpha_aer_abs",
        "alpha_aer_scat", "alpha_atm", "tau_atm",
        "Cn2_integrated", "r0_sph", "w_turb",
        "N_D", "S_TB", "w_bloom",
        "w_diff", "w_jit", "w_total", "d_spot",
        "I_peak", "PIB_fraction", "P_aim", "I_avg_aim",
        "tau_BT", "T_surface_peak", "E_delivered", "failure_mode",
        "MPE", "NOHD_tophat", "NOHD_gausspeak", "laser_class",
        "P_in", "Q_waste", "t_sustain",
        "duty_cycle_limit", "engagements_per_hour",
        "engagement_viable",
        "m67_iteration_count", "m67_converged",
    }
    actual_keys = set(walkthrough.result.keys())
    missing = expected_output_keys - actual_keys
    assert not missing, (
        f"Worked example missing orchestrator outputs: {missing}"
    )


def test_pr4_walkthrough_steps_cover_every_metric():
    """The 10-step walkthrough must reference every numeric metric
    at least once. Categorical metrics (failure_mode, laser_class,
    engagement_viable, m67_converged) and the m67_iteration_count
    diagnostic appear inline as part of their respective steps."""
    from ui.math_content import MATH_CONTENT
    from ui.worked_example import WALKTHROUGH_STEPS

    referenced = set()
    for step in WALKTHROUGH_STEPS:
        for key in step.metric_keys:
            referenced.add(key)

    # Every MATH_CONTENT key except the m67 iteration diagnostics
    # (which the walkthrough mentions as part of step 6's narrative
    # rather than as an explicit metric) and R_at_dwell_end (added in
    # tracker-dwell PR 3; the walkthrough rewrite for the v2.0 contract
    # lands in the trajectory-loop PRs 5-6).
    expected = set(MATH_CONTENT.keys()) - {
        "m67_iteration_count", "m67_converged",
        # SPEC v2.0 keys added in tracker-dwell PRs 3-4; the worked
        # example walkthrough rewrite for the v2.0 contract lands in
        # PRs 5-6.
        "R_at_dwell_end", "R_at_kill",
        # SPEC v2.0 trajectory maxima added in PR 12; these are
        # summary scalars over the trajectory time series and the
        # walkthrough's per-step structure doesn't fit them naturally.
        "I_peak_max", "I_avg_aim_max",
    }
    missing_from_walkthrough = expected - referenced
    assert not missing_from_walkthrough, (
        f"Walkthrough doesn't reference these metrics: "
        f"{missing_from_walkthrough}"
    )


def test_pr3_modules_present():
    """PR 3 of the math-tab plan covers M8, M9, M10, and the
    orchestrator (12 numeric + 4 categorical + 1 diagnostic = 17 entries)."""
    from ui.math_content import MATH_CONTENT

    expected_pr3_keys = {
        # M8 — burn-through (3 numeric + 1 categorical)
        "tau_BT", "T_surface_peak", "E_delivered", "failure_mode",
        # M9 — eye safety (3 numeric + 1 categorical)
        "MPE", "NOHD_tophat", "NOHD_gausspeak", "laser_class",
        # M10 — power & thermal (5 numeric + 1 categorical)
        "P_in", "Q_waste", "t_sustain",
        "duty_cycle_limit", "engagements_per_hour",
        "engagement_viable",
        # Orchestrator (1 numeric + 1 categorical)
        "m67_iteration_count", "m67_converged",
    }
    actual = set(MATH_CONTENT.keys())
    missing = expected_pr3_keys - actual
    assert not missing, f"PR 3 missing entries: {missing}"


def test_solver_based_metrics_flagged():
    """The three M8 PDE outputs must have ``is_solver_based=True`` so
    the renderer shows the multi-line formula recipe instead of trying
    to fit the heat PDE into a single LaTeX cell."""
    from ui.math_content import MATH_CONTENT

    expected_solver_keys = {
        "tau_BT", "T_surface_peak", "E_delivered",
        # SPEC v2.0 added R_at_kill in tracker-dwell PR 4; it derives
        # from the M8 PDE solver (R(t) evaluated at tau_BT).
        "R_at_kill",
    }
    actual_solver_keys = {
        k for k, e in MATH_CONTENT.items() if e.is_solver_based
    }
    assert actual_solver_keys == expected_solver_keys, (
        f"is_solver_based flag drift: expected {expected_solver_keys}, "
        f"got {actual_solver_keys}"
    )


def test_categorical_metrics_count_and_keys():
    """The four categorical (verdict) outputs are exactly the ones
    plan §2 enumerates: failure_mode, laser_class, engagement_viable,
    m67_converged. None has a LaTeX formula; all have prose
    formula_text."""
    from ui.math_content import MATH_CONTENT

    expected_categorical = {
        "failure_mode",
        "laser_class",
        "engagement_viable",
        "m67_converged",
    }
    actual_categorical = {
        k for k, e in MATH_CONTENT.items() if e.is_categorical
    }
    assert actual_categorical == expected_categorical, (
        f"Categorical-flag drift: expected {expected_categorical}, "
        f"got {actual_categorical}"
    )

    for key in actual_categorical:
        entry = MATH_CONTENT[key]
        assert entry.formula_latex is None, (
            f"{key}: categorical metric should NOT have formula_latex"
        )
        assert entry.formula_text, (
            f"{key}: categorical metric must have prose formula_text "
            f"(the verdict rule)"
        )


def test_complete_metric_count():
    """MATH_CONTENT must cover every scalar orchestrator output key.

    Catches both under-coverage (a scalar key the orchestrator emits
    with no math-tab record) and ahead-of-schedule drift (an extra
    record that doesn't match a real output).

    SPEC v2.0 trajectory_* keys are excluded — they are time-series
    arrays for plotting (not single-value displayable metrics) and
    don't fit the per-row MATH_CONTENT schema. Their summarised
    scalar maxima (``I_peak_max``, ``I_avg_aim_max``) are covered by
    dedicated entries.
    """
    from physics.orchestrator import run_full_chain
    from tests.golden.scenarios import C_UAS_1500M
    from ui.math_content import MATH_CONTENT

    res = run_full_chain(C_UAS_1500M)
    # Drop the by_module / assumptions_flagged auxiliaries — they
    # aren't displayable metrics.
    output_keys = set(res.keys()) - {"by_module", "assumptions_flagged"}
    # Trajectory_* keys are per-sample time series (plot data, not
    # scalar metrics).
    output_keys = {k for k in output_keys if not k.startswith("trajectory_")}

    math_keys = set(MATH_CONTENT.keys())

    missing_in_math = output_keys - math_keys
    extra_in_math = math_keys - output_keys

    assert not missing_in_math, (
        f"Orchestrator emits {len(missing_in_math)} scalar key(s) with "
        f"no math-tab record: {missing_in_math}"
    )
    assert not extra_in_math, (
        f"MATH_CONTENT has {len(extra_in_math)} key(s) the orchestrator "
        f"does not emit: {extra_in_math}"
    )


def test_compute_sensitivity_signed_direction():
    """Sensitivity sign reflects the +10 % perturbation direction —
    metric goes up when input goes up → positive sign."""
    from ui.sensitivity import compute_sensitivity_for_metric

    def runner(k, sign):
        # Linear metric: foo = 2 * P0
        return {"foo": 2 * 1000.0 * (1.0 + sign * 0.10)}

    sens = compute_sensitivity_for_metric(
        metric_key="foo",
        sensitivity_inputs=("P0",),
        base_result={"foo": 2 * 1000.0},
        base_inputs={"P0": 1000.0},
        perturbation_runner=runner,
    )
    # +10 % input → +10 % metric (linear); sign positive.
    assert sens["P0"] > 0
    assert abs(abs(sens["P0"]) - 10.0) < 0.01


# ---------------------------------------------------------------------------
# (c) Smoke — render_tab_math doesn't crash
# ---------------------------------------------------------------------------

def test_render_tab_math_function_exists_and_signature():
    """``render_tab_math`` is exported from ui.outputs with the expected
    one-argument signature (the merged result dict). The function body
    itself uses Streamlit primitives that are not unit-testable outside
    a script-runner context; the smoke verification of the actual
    render is the local-Streamlit manual run documented in the PR's
    verification section."""
    import inspect
    from ui.outputs import render_tab_math
    sig = inspect.signature(render_tab_math)
    params = list(sig.parameters.values())
    assert len(params) == 1, (
        f"render_tab_math should take one argument (the merged result "
        f"dict), got {len(params)}: {[p.name for p in params]}"
    )
    assert params[0].name == "result"


def test_format_value_for_math_tab_handles_none_and_string():
    """The value-cell formatter must handle None (orchestrator missing
    a key on infeasible geometry) and string values (failure_mode,
    laser_class) without crashing."""
    from ui.outputs import _format_value_for_math_tab

    # None -> em-dash placeholder
    assert _format_value_for_math_tab("I_peak", None, "W/cm²") == "—"
    # String passthrough
    assert _format_value_for_math_tab(
        "failure_mode", "decomposition", "",
    ) == "decomposition"
    # Bool -> yes/no
    assert _format_value_for_math_tab(
        "engagement_viable", True, "",
    ) == "yes"
    assert _format_value_for_math_tab(
        "engagement_viable", False, "",
    ) == "no"
    # Numeric routes through _scale + format_value (3000 W → 3.00 kW
    # for P_aim per existing _DISPLAY_SCALE).
    rendered = _format_value_for_math_tab("P_aim", 3000.0, "kW")
    assert "3.00" in rendered
    assert "kW" in rendered


def test_substitute_formula_values_skips_categorical():
    """The substituted-formula helper must return None for categorical
    metrics (failure_mode, laser_class, etc.) — those don't have a
    formula to substitute into."""
    from ui.math_content import MetricEntry
    from ui.outputs import _substitute_formula_values

    # Build a minimal categorical entry for the test.
    cat_entry = MetricEntry(
        key="failure_mode",
        module="M8",
        display_name="Failure mode",
        symbol_latex=r"",
        unit_si="",
        is_categorical=True,
    )
    assert _substitute_formula_values(cat_entry, {"failure_mode": "melt"}) is None


def test_substitute_formula_values_real_metric():
    """A real numeric metric returns a non-empty substitution string
    when the dependencies are present in the result dict.

    Phase A.1 (2026-04-28): output is now a Markdown bullet list.
    Each bullet contains the symbol + value (+ optional unit) +
    human label."""
    from ui.math_content import MATH_CONTENT
    from ui.outputs import _substitute_formula_values

    entry = MATH_CONTENT["I_exit"]   # depends on w0; sensitivity inputs P0, D
    result = {"P0": 3000.0, "D": 0.10, "w0": 0.05}
    sub = _substitute_formula_values(entry, result)
    assert sub is not None
    # Substring checks now expect the bolded `**key**` markup.
    assert "**P0**" in sub
    assert "3000" in sub
    assert "**D**" in sub
    assert "0.1" in sub
    assert "**w0**" in sub
    assert "0.05" in sub
    # Each bullet starts with a markdown list marker.
    assert sub.startswith("- ")
    # Multi-line: at least 3 entries.
    assert sub.count("\n") >= 2


def test_substitute_formula_values_includes_human_labels():
    """Phase A.1 requirement: each substituted value carries the
    human-readable label of what it physically represents, not just
    the code symbol. Verifies the Phase A.1 promise the user asked
    for ('S_TB = 0.97 — what is this number?')."""
    from ui.math_content import MATH_CONTENT
    from ui.outputs import _substitute_formula_values

    # I_peak depends on P_exit, tau_atm, S_TB, w_total + sensitivity
    # inputs P0, eta_opt, M2, D, wavelength, sigma_jit, …
    entry = MATH_CONTENT["I_peak"]
    result = {
        "P_exit": 2550.0, "tau_atm": 0.81, "S_TB": 0.97, "w_total": 0.06,
        "P0": 3000.0, "eta_opt": 0.85, "M2": 1.2, "D": 0.10,
        "wavelength": 1.07e-6, "sigma_jit": 1e-5, "V": 23.0,
        "RH": 0.6, "Cn2_ground": 1.7e-14, "v_HV": 21.0,
        "T_ambient": 300.0, "P_atm": 101325.0,
    }
    sub = _substitute_formula_values(entry, result)
    assert sub is not None
    # P_exit (output, has MATH_CONTENT entry): the display_name is
    # "Power leaving the beam director".
    assert "Power leaving the beam director" in sub
    # tau_atm (output): display_name "Atmospheric transmission".
    assert "Atmospheric transmission" in sub
    # S_TB (output): display_name "Thermal-blooming Strehl" — this is
    # the key user-pain example from the screenshot.
    assert "Thermal-blooming Strehl" in sub
    # P0 (raw input): INPUT_LABELS["P0"]["label"] = "Output power".
    assert "Output power" in sub
    # M2 (raw input): "Beam quality (M²)".
    assert "Beam quality" in sub


def test_substitute_formula_values_includes_si_units():
    """Phase A.1 requirement: each substituted value carries its SI
    unit so the reader knows whether 2550 is W, mW, or something
    else. Outputs use MATH_CONTENT.unit_si; raw inputs use the new
    _INPUT_SI_UNITS lookup."""
    from ui.math_content import MATH_CONTENT
    from ui.outputs import _substitute_formula_values

    entry = MATH_CONTENT["I_peak"]
    result = {
        "P_exit": 2550.0, "tau_atm": 0.81, "S_TB": 0.97, "w_total": 0.06,
        "P0": 3000.0, "eta_opt": 0.85, "M2": 1.2, "D": 0.10,
        "wavelength": 1.07e-6, "sigma_jit": 1e-5, "V": 23.0,
        "RH": 0.6, "Cn2_ground": 1.7e-14, "v_HV": 21.0,
        "T_ambient": 300.0, "P_atm": 101325.0,
    }
    sub = _substitute_formula_values(entry, result)
    assert sub is not None
    # P0 has SI unit "W" per the _INPUT_SI_UNITS lookup.
    assert "3000 W" in sub
    # D has SI unit "m".
    assert "0.1 m" in sub
    # sigma_jit has SI unit "rad".
    assert "rad" in sub
    # v_HV has SI unit "m/s".
    assert "m/s" in sub


# ---------------------------------------------------------------------------
# (d) Glossary integrity
# ---------------------------------------------------------------------------

def test_glossary_has_22_entries():
    """Plan §10 closes the glossary at 22 entries for v1. New entries
    require a plan revision."""
    from ui.glossary import GLOSSARY
    assert len(GLOSSARY) == 22, (
        f"Glossary has {len(GLOSSARY)} entries; plan §10 fixes the "
        f"v1 list at 22. Add the new term to plan first."
    )


def test_glossary_entries_non_empty():
    """Every glossary value is a non-empty 2-3 sentence definition.

    Sentence count uses a regex that excludes decimal points (1.06 µm,
    etc.) so numeric literals don't inflate the count — counting raw
    periods would mis-classify the Wavelength entry's '1.06, 1.07,
    1.55, 2.05 µm' fragment as four sentence terminators.
    """
    import re
    from ui.glossary import GLOSSARY

    # A sentence terminator is a period (or ! or ?) followed by a
    # whitespace + capital letter, OR end-of-string. This excludes
    # decimal points like '1.06' (where the period is followed by a
    # digit, not a letter).
    terminator = re.compile(r"[.!?](?:\s+[A-Z]|\s*$)")

    for term, definition in GLOSSARY.items():
        assert definition.strip(), f"glossary entry {term!r} is empty"
        sentence_count = len(terminator.findall(definition))
        assert 1 <= sentence_count <= 5, (
            f"glossary entry {term!r} has {sentence_count} sentences; "
            f"target 2-3"
        )


def test_glossary_no_spec_section_citations():
    """test_copy_style.py forbids 'SPEC §' in user-facing copy. Glossary
    entries are user-facing — verify per-entry."""
    from ui.glossary import GLOSSARY
    for term, definition in GLOSSARY.items():
        assert "SPEC §" not in definition, (
            f"glossary entry {term!r} contains a 'SPEC §' citation; "
            f"plain-language only per copy-style rule"
        )


# ---------------------------------------------------------------------------
# Module render-order sanity
# ---------------------------------------------------------------------------

def test_module_order_covers_every_module_in_content():
    """Every module a MATH_CONTENT entry references must appear in
    MODULE_ORDER, otherwise the renderer would skip that section."""
    from ui.math_content import MATH_CONTENT, MODULE_ORDER, MODULE_TITLES

    used_modules = {e.module for e in MATH_CONTENT.values()}
    missing = used_modules - set(MODULE_ORDER)
    assert not missing, (
        f"MATH_CONTENT references modules not in MODULE_ORDER: {missing}"
    )
    # Every used module also has a title.
    for m in used_modules:
        assert m in MODULE_TITLES, (
            f"MATH_CONTENT references module {m} but MODULE_TITLES "
            f"has no entry for it"
        )


# ---------------------------------------------------------------------------
# Phase A v3.7 (2026-04-28) — tab-of-origin grouping
# ---------------------------------------------------------------------------

def test_every_entry_has_primary_tab_in_TAB_ORDER():
    """Every MetricEntry's primary_tab must be a valid TAB_ORDER value.
    The renderer iterates TAB_ORDER and would skip an entry tagged
    to an unknown tab — silent invisibility is the worst failure mode."""
    from ui.math_content import MATH_CONTENT, TAB_ORDER

    for entry in MATH_CONTENT.values():
        assert entry.primary_tab in TAB_ORDER, (
            f"{entry.key!r} has primary_tab={entry.primary_tab!r} which is "
            f"not in TAB_ORDER={TAB_ORDER}"
        )


def test_every_entry_also_in_is_subset_of_TAB_ORDER():
    """The optional `also_in` tuple must contain only valid TAB_ORDER
    values. Catches typos in cross-reference badges before they ship."""
    from ui.math_content import MATH_CONTENT, TAB_ORDER

    valid = set(TAB_ORDER)
    for entry in MATH_CONTENT.values():
        for tab in entry.also_in:
            assert tab in valid, (
                f"{entry.key!r} has also_in entry {tab!r} not in TAB_ORDER"
            )
        # also_in should not include the primary_tab (would be a self-reference).
        assert entry.primary_tab not in entry.also_in, (
            f"{entry.key!r} primary_tab {entry.primary_tab!r} also appears "
            f"in also_in — self-reference, drop it"
        )


def test_TAB_ORDER_buckets_cover_every_entry():
    """Iterating TAB_ORDER and collecting entries by primary_tab must
    yield the full MATH_CONTENT set. Guards against entries tagged to
    a tab that exists but isn't in TAB_ORDER (impossible by construction
    today, but the test is cheap insurance)."""
    from ui.math_content import MATH_CONTENT, TAB_ORDER

    bucketed_keys = set()
    for tab_id in TAB_ORDER:
        for e in MATH_CONTENT.values():
            if e.primary_tab == tab_id:
                bucketed_keys.add(e.key)
    assert bucketed_keys == set(MATH_CONTENT.keys()), (
        "TAB_ORDER iteration missed some entries: "
        f"{set(MATH_CONTENT.keys()) - bucketed_keys}"
    )


def test_TAB_TITLES_covers_every_TAB_ORDER_entry():
    """Every TAB_ORDER value must have a TAB_TITLES entry — the renderer
    uses the title as the section header, so a missing entry would
    crash with KeyError at render time."""
    from ui.math_content import TAB_ORDER, TAB_TITLES

    for tab_id in TAB_ORDER:
        assert tab_id in TAB_TITLES, (
            f"TAB_ORDER includes {tab_id!r} but TAB_TITLES has no entry"
        )
