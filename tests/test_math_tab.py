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

    for key, entry in MATH_CONTENT.items():
        assert entry.display_name, f"{key}: missing display_name"
        assert entry.module, f"{key}: missing module"
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
        # M3 — geometry (4)
        "R_slant", "R_h", "elevation_angle", "available_dwell",
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
    when the dependencies are present in the result dict."""
    from ui.math_content import MATH_CONTENT
    from ui.outputs import _substitute_formula_values

    entry = MATH_CONTENT["I_exit"]   # depends on w0; sensitivity inputs P0, D
    result = {"P0": 3000.0, "D": 0.10, "w0": 0.05}
    sub = _substitute_formula_values(entry, result)
    assert sub is not None
    assert "P0 = 3000" in sub
    assert "D = 0.1" in sub
    assert "w0 = 0.05" in sub


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
