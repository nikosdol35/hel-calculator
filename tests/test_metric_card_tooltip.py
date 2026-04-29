"""Tests for the Phase C "show formula" disclosure on every metric card.

PR: feature/math-tab-phase-c (2026-04-28).

Phase C extends the per-metric card so that, when a metric has a
MATH_CONTENT entry, an inline `<details>/<summary>` disclosure appears
below the card's existing tooltip. Click to expand → see the metric's
formula plus this run's substituted values, without leaving the tab.

The implementation is conditional: keys WITHOUT a MATH_CONTENT entry
(e.g. raw input labels, DRI-side metrics) keep their existing
tooltip-only behaviour. This test file pins that contract so future
contributors can't accidentally break the conditional path.

Coverage:
  - Builder returns None for keys with no MATH_CONTENT entry
  - Builder returns None for categorical metrics
  - Builder returns None when result is missing
  - Builder returns proper HTML for a real numeric metric
  - HTML includes the formula text
  - HTML includes substituted values with labels
  - HTML uses <details>/<summary> disclosure markup
  - Markdown-emphasis-to-HTML helper handles bold + italic
"""
from __future__ import annotations

import pytest

from physics.orchestrator import run_full_chain
from tests.golden.scenarios import C_UAS_1500M


def _v2_inputs(**overrides) -> dict:
    inputs = dict(C_UAS_1500M)
    inputs.pop("R", None)
    inputs.pop("v_perp", None)
    inputs.update({
        "R_detect": 1500, "R_min": 100,
        "engagement_geometry": "head_on",
    })
    inputs.update(overrides)
    return inputs


def _merged_result(**overrides) -> dict:
    inputs = _v2_inputs(**overrides)
    result = run_full_chain(inputs)
    return {**inputs, **result}


# ---------------------------------------------------------------------------
# _build_formula_details_html — the conditional logic
# ---------------------------------------------------------------------------
def test_returns_none_when_result_is_none():
    """Without a result dict (chain hasn't run), no formula disclosure."""
    from ui.outputs import _build_formula_details_html
    assert _build_formula_details_html("I_peak", None) is None


def test_returns_none_for_unknown_key():
    """Keys without a MATH_CONTENT entry (raw inputs like 'P0',
    DRI-side keys, etc.) get no formula disclosure — preserves
    existing tooltip-only behaviour."""
    from ui.outputs import _build_formula_details_html
    result = _merged_result()
    # P0 is a raw user input; INPUT_LABELS has it but MATH_CONTENT
    # does not (since MATH_CONTENT is for *computed* metrics).
    assert _build_formula_details_html("P0", result) is None
    # Made-up key that doesn't exist anywhere.
    assert _build_formula_details_html("totally_not_a_real_key", result) is None


def test_returns_none_for_categorical_metric():
    """Categorical metrics (failure_mode, laser_class) don't have a
    formula to substitute into — disclosure suppressed."""
    from ui.outputs import _build_formula_details_html
    result = _merged_result()
    assert _build_formula_details_html("failure_mode", result) is None
    assert _build_formula_details_html("laser_class", result) is None


def test_returns_html_for_real_numeric_metric():
    """A numeric metric with a MATH_CONTENT entry produces a
    non-empty HTML <details>/<summary> block."""
    from ui.outputs import _build_formula_details_html
    result = _merged_result()
    html = _build_formula_details_html("I_peak", result)
    assert html is not None
    assert "<details" in html
    assert "<summary>" in html
    assert "Show formula" in html
    assert "</details>" in html


def test_html_contains_formula_text():
    """The disclosure body shows the metric's formula text — for
    I_peak, the formula contains the variable I_peak and at least
    one of its dependencies."""
    from ui.outputs import _build_formula_details_html
    result = _merged_result()
    html = _build_formula_details_html("I_peak", result)
    assert html is not None
    # The ASCII formula_text references P_exit / tau_atm / S_TB / w_total.
    # Don't assume exact spacing; just check the symbols appear.
    assert "I_peak" in html
    assert "P_exit" in html or "P_aim" in html
    assert "w_total" in html or "w_total^2" in html or "w_total**2" in html


def test_html_contains_substituted_values_with_labels():
    """The disclosure body lists each variable's substituted value
    AND its human-readable label (Phase A.1 reuse). Verifies the
    Phase C end-to-end story: see a metric in any tab → click
    'Show formula' → read both the math and the labelled values
    without leaving the tab."""
    from ui.outputs import _build_formula_details_html
    result = _merged_result()
    html = _build_formula_details_html("I_peak", result)
    assert html is not None
    # Look for one of the human labels emitted by Phase A.1.
    assert (
        "Power leaving the beam director" in html
        or "Atmospheric transmission" in html
        or "Thermal-blooming Strehl" in html
    )
    # Substituted-value bullets render as <li> elements.
    assert "<li>" in html
    # SI unit annotations (W for power, m for length, etc.) appear
    # somewhere in the bullets — they're sandwiched between the
    # bolded symbol (`<strong>`) and the italicised label (`<em>`).
    assert " W " in html or " m " in html or " W —" in html or " m —" in html


def test_html_uses_details_summary_disclosure_markup():
    """Disclosure uses native HTML5 <details>/<summary> for
    progressive enhancement (works without JavaScript). No <button>
    or <input type='checkbox'> hacks."""
    from ui.outputs import _build_formula_details_html
    result = _merged_result()
    html = _build_formula_details_html("I_peak", result)
    assert html is not None
    # Must use native HTML5 disclosure semantics.
    assert html.lstrip().startswith("<details")
    assert "<summary>" in html
    # Don't accidentally use button or input hacks.
    assert "<button" not in html
    assert "type=\"checkbox\"" not in html


# ---------------------------------------------------------------------------
# Phase: native st.expander disclosure with KaTeX-rendered LaTeX (2026-04-29)
#
# The previous attempt embedded `$$...$$` math inside the HTML <details>
# widget, but Streamlit's KaTeX post-processor doesn't traverse into
# HTML disclosure widgets — the math rendered as literal text. We
# switched to a native ``st.expander`` + ``st.latex`` combo (R1.fallback
# in the plan), which renders KaTeX reliably in every browser.
# ---------------------------------------------------------------------------
def _capture_disclosure_calls(monkeypatch):
    """Patch the Streamlit functions used by ``_render_formula_disclosure``
    so tests can inspect what would have been rendered. Returns a dict
    of capture buckets: ``expanders``, ``latex``, ``code``, ``markdown``.
    """
    captured = {
        "expanders": [],
        "latex": [],
        "code": [],
        "markdown": [],
    }
    import contextlib

    def _exp(label, *_, **__):
        captured["expanders"].append(label)
        return contextlib.nullcontext()

    monkeypatch.setattr("streamlit.expander", _exp)
    monkeypatch.setattr(
        "streamlit.latex", lambda s, **_: captured["latex"].append(str(s))
    )
    monkeypatch.setattr(
        "streamlit.code",
        lambda s, **_: captured["code"].append(str(s)),
    )
    monkeypatch.setattr(
        "streamlit.markdown",
        lambda s, **_: captured["markdown"].append(str(s)),
    )
    return captured


def test_disclosure_renders_latex_via_st_latex(monkeypatch):
    """The expander now calls ``st.latex(formula_latex)`` so KaTeX
    actually renders the Greek-letter formula (the HTML-disclosure
    approach didn't, which the user reported 2026-04-29)."""
    from ui.outputs import _render_formula_disclosure
    from ui.math_content import MATH_CONTENT
    captured = _capture_disclosure_calls(monkeypatch)

    _render_formula_disclosure("I_peak", _merged_result())

    expected_latex = MATH_CONTENT["I_peak"].formula_latex
    assert expected_latex is not None
    assert expected_latex in captured["latex"], (
        f"expected st.latex({expected_latex!r}); "
        f"got latex calls: {captured['latex']}"
    )


def test_disclosure_uses_native_st_expander(monkeypatch):
    """The disclosure uses ``st.expander`` (native), NOT the HTML
    ``<details>`` widget any more — the previous HTML approach
    suppressed KaTeX rendering."""
    from ui.outputs import _render_formula_disclosure
    captured = _capture_disclosure_calls(monkeypatch)

    _render_formula_disclosure("I_peak", _merged_result())
    assert captured["expanders"] == ["Show formula"]


def test_disclosure_still_includes_ascii_formula_and_variables(monkeypatch):
    """Regression guard: the ASCII formula and the substituted variable
    list still render. The native-widget refactor didn't drop them."""
    from ui.outputs import _render_formula_disclosure
    captured = _capture_disclosure_calls(monkeypatch)

    _render_formula_disclosure("I_peak", _merged_result())

    # ASCII formula text appears in the captured st.code calls.
    code_blob = "\n".join(captured["code"])
    assert "I_peak" in code_blob
    assert "P_exit" in code_blob or "tau_atm" in code_blob
    # Variable list appears in the captured st.markdown calls.
    md_blob = "\n".join(captured["markdown"])
    assert "**" in md_blob, "expected bolded variable names in the bullet list"


def test_disclosure_skips_categorical_entries(monkeypatch):
    """Categorical (verdict) entries have no formula — render
    nothing, exactly like the old HTML disclosure path."""
    from ui.outputs import _render_formula_disclosure
    captured = _capture_disclosure_calls(monkeypatch)

    for cat_key in ("failure_mode", "laser_class"):
        _render_formula_disclosure(cat_key, _merged_result())

    assert captured["expanders"] == [], (
        "categorical entries must not open an expander"
    )
    assert captured["latex"] == []
    assert captured["code"] == []


def test_disclosure_skips_when_result_is_none(monkeypatch):
    """No chain → no disclosure (back-compat with pre-result page
    state, e.g. before the user clicks Run Analysis)."""
    from ui.outputs import _render_formula_disclosure
    captured = _capture_disclosure_calls(monkeypatch)

    _render_formula_disclosure("I_peak", None)

    assert captured["expanders"] == []
    assert captured["latex"] == []


def test_disclosure_renders_w_total_special_glyphs(monkeypatch):
    """Spot-check on a metric whose LaTeX has Greek letters, subscripts,
    sqrt, and superscripts — the visible payoff of switching to
    KaTeX rendering."""
    from ui.outputs import _render_formula_disclosure
    captured = _capture_disclosure_calls(monkeypatch)

    _render_formula_disclosure("w_total", _merged_result())

    latex_blob = "\n".join(captured["latex"])
    assert "\\sqrt" in latex_blob
    assert "w_\\text{diff}" in latex_blob or "w_\\text{turb}" in latex_blob


# ---------------------------------------------------------------------------
# _md_emphasis_to_html — small markdown subset converter
# ---------------------------------------------------------------------------
def test_md_emphasis_bold_to_strong():
    from ui.outputs import _md_emphasis_to_html
    assert _md_emphasis_to_html("**bold text**") == "<strong>bold text</strong>"


def test_md_emphasis_italic_to_em():
    from ui.outputs import _md_emphasis_to_html
    assert _md_emphasis_to_html("*italic text*") == "<em>italic text</em>"


def test_md_emphasis_combined():
    """Mixed bold + italic in a single line — both convert."""
    from ui.outputs import _md_emphasis_to_html
    out = _md_emphasis_to_html("**P_exit** = 2550 W — *Beam-director exit power*")
    assert "<strong>P_exit</strong>" in out
    assert "<em>Beam-director exit power</em>" in out


def test_md_emphasis_passes_through_plain_text():
    """Lines with no markdown markers come back unchanged."""
    from ui.outputs import _md_emphasis_to_html
    plain = "no markdown here, just plain text"
    assert _md_emphasis_to_html(plain) == plain
