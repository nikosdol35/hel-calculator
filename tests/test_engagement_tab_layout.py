"""Tests for the Engagement-tab layout reorder (2026-04-28).

Two plots were retired and one was promoted:
  - Plot I (outcome map vs R_detect) — hidden
  - Plot E (burn-through time vs dwell window) — hidden
  - Plot B (time-to-burn-through vs detection range) — moved UP into
    Plot I's slot, immediately after Plot H.

Their constructors still live in ``ui/plots.py`` (cheap dead code; a
follow-up cleanup commit will remove them) — only the *render calls*
in ``ui/outputs.py::render_tab_engagement`` are gone.

Static-source tests rather than full-Streamlit render tests because
the existing `tests/test_pages_smoke.py` pattern is static analysis,
and a real Streamlit render brings in heavy session-state machinery
that's irrelevant to "is the call site still there".
"""
from __future__ import annotations

import inspect
import re

from ui import outputs


def _engagement_tab_source() -> str:
    """Return the source text of ``render_tab_engagement`` only."""
    return inspect.getsource(outputs.render_tab_engagement)


def test_plot_i_render_call_removed_from_engagement_tab():
    """Plot I (outcome-map vs R_detect) was hidden 2026-04-28.
    ``render_tab_engagement`` must no longer call its constructor."""
    src = _engagement_tab_source()
    assert "plot_i_outcome_map_vs_R_detect" not in src, (
        "Plot I constructor should no longer be invoked from the "
        "Engagement tab; remove the render call."
    )
    # Likewise the explanation key.
    assert 'EXPLANATIONS["plot_i_intro"]' not in src
    assert "EXPLANATIONS['plot_i_intro']" not in src


def test_plot_e_render_call_removed_from_engagement_tab():
    """Plot E (BT vs dwell window) was hidden 2026-04-28."""
    src = _engagement_tab_source()
    assert "plot_e_engagement_margin_vs_range" not in src, (
        "Plot E constructor should no longer be invoked from the "
        "Engagement tab; remove the render call."
    )
    assert 'EXPLANATIONS["plot_e_intro"]' not in src
    assert "EXPLANATIONS['plot_e_intro']" not in src


def test_plot_b_render_call_present_exactly_once():
    """Plot B was promoted into Plot I's old slot; it must render
    exactly once on the tab (not in two places, not zero)."""
    src = _engagement_tab_source()
    # `plot_b_time_to_burnthrough(` matches the call site only — not
    # comments mentioning the name.
    matches = re.findall(r"plot_b_time_to_burnthrough\(", src)
    assert len(matches) == 1, (
        f"expected exactly 1 Plot B render call; found {len(matches)}"
    )


def test_plot_b_renders_before_plot_j():
    """Plot B sits immediately after Plot H and BEFORE Plot J in the
    new layout — the freed Plot I slot."""
    src = _engagement_tab_source()
    plot_b_pos = src.find("plot_b_time_to_burnthrough(")
    plot_j_pos = src.find("plot_j_cumulative_energy_diagnostic(")
    assert plot_b_pos > 0 and plot_j_pos > 0
    assert plot_b_pos < plot_j_pos, (
        "Plot B must render BEFORE Plot J (it now occupies Plot I's "
        "old slot, which was directly above Plot J)."
    )


def test_plot_h_still_renders_first():
    """Plot H (engagement-profile timeline) remains the first plot in
    the v2 trajectory block — the layout reorder didn't displace it."""
    src = _engagement_tab_source()
    plot_h_pos = src.find("plot_h_engagement_profile(")
    plot_b_pos = src.find("plot_b_time_to_burnthrough(")
    assert plot_h_pos > 0 and plot_b_pos > 0
    assert plot_h_pos < plot_b_pos
