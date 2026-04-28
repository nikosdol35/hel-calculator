"""Smoke tests for Plot O — peak irradiance vs Cn² family.

Verifies the plot constructor renders against a real chain result,
returns the expected number of traces, and falls back to the empty
frame for None / empty inputs.
"""
from __future__ import annotations

import pytest

from physics.cn2_family import compute_cn2_family_curves
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


def test_plot_o_smoke_real_chain():
    """Plot O renders against a real v2 chain result with the
    expected number of traces (5 references + 1 current + 1 star)."""
    from ui.plots import plot_o_peak_irradiance_vs_cn2
    curves = compute_cn2_family_curves(_merged_result())
    fig = plot_o_peak_irradiance_vs_cn2(curves)
    # 5 reference traces (canonical Cn² doesn't trigger duplicate
    # suppression) + 1 current curve + 1 star = 7 total.
    assert len(fig.data) == 7


def test_plot_o_log_axes():
    """Plot O has log x and log y axes."""
    from ui.plots import plot_o_peak_irradiance_vs_cn2
    curves = compute_cn2_family_curves(_merged_result())
    fig = plot_o_peak_irradiance_vs_cn2(curves)
    assert fig.layout.xaxis.type == "log"
    assert fig.layout.yaxis.type == "log"


def test_plot_o_handles_none_curves():
    """None input → always-render empty frame, not a crash."""
    from ui.plots import plot_o_peak_irradiance_vs_cn2
    fig = plot_o_peak_irradiance_vs_cn2(None)
    # Empty frame has zero traces.
    assert len(fig.data) == 0


def test_plot_o_duplicate_suppression_renders_one_fewer_curve():
    """When the user's Cn² matches a reference, that reference is
    dropped → 4 references + 1 current + 1 star = 6 traces."""
    from ui.plots import plot_o_peak_irradiance_vs_cn2
    # Cn²_ground = 1.0e-14 = exactly the 'Clear' reference.
    curves = compute_cn2_family_curves(_merged_result(Cn2_ground=1.0e-14))
    fig = plot_o_peak_irradiance_vs_cn2(curves)
    assert len(fig.data) == 6


def test_plot_o_no_star_when_current_I_peak_missing():
    """If the current_I_peak_wpcm2 is None or NaN (e.g. degenerate
    scenario), the star isn't drawn but the rest of the figure
    still renders."""
    from ui.plots import plot_o_peak_irradiance_vs_cn2
    curves = compute_cn2_family_curves(_merged_result())
    # Force current_I_peak to None via dataclass replace.
    import dataclasses
    curves = dataclasses.replace(curves, current_I_peak_wpcm2=None)
    fig = plot_o_peak_irradiance_vs_cn2(curves)
    # 5 references + 1 current curve = 6 traces (no star).
    assert len(fig.data) == 6


# ---------------------------------------------------------------------------
# Phase: book-style Cn² formatting + legend repositioning (2026-04-28)
# ---------------------------------------------------------------------------
def test_plot_o_legend_uses_book_style_unicode():
    """Cn² values must render as e.g. '1×10⁻¹⁵ m⁻²ᐟ³' (Unicode
    superscripts), not the raw '1e-15' code form. This matches how
    Andrews & Phillips / Tatarski write the refractive-index structure
    constant in print."""
    from ui.plots import plot_o_peak_irradiance_vs_cn2
    curves = compute_cn2_family_curves(_merged_result())
    fig = plot_o_peak_irradiance_vs_cn2(curves)
    names = [t.name or "" for t in fig.data]
    # At least one legend entry should contain the new Unicode form.
    assert any("×10" in n for n in names), (
        f"no legend entry uses '×10' Unicode multiplier; names={names}"
    )
    assert any("⁻²ᐟ³" in n for n in names), (
        f"no legend entry uses Unicode 'm⁻²ᐟ³' superscript; names={names}"
    )
    # No legend entry should still use the old 'e-' raw form.
    assert not any("e-1" in n for n in names), (
        f"some legend entry still uses 'e-' raw form; names={names}"
    )


def test_plot_o_legend_positioned_outside_to_right():
    """Plot O's legend must be vertical and anchored OUTSIDE the plot
    area on the right, so it doesn't overlap the (long) plot title.
    Pre-fix, the horizontal legend at y=1.02 collided with the
    headline."""
    from ui.plots import plot_o_peak_irradiance_vs_cn2
    curves = compute_cn2_family_curves(_merged_result())
    fig = plot_o_peak_irradiance_vs_cn2(curves)
    assert fig.layout.legend.orientation == "v"
    # x ≥ 1.0 means the legend is at the right edge of the plotting
    # frame or further right (outside).
    assert (fig.layout.legend.x or 0) >= 1.0


def test_fmt_cn2_book_style_helper():
    """The Cn² formatter handles canonical reference values + edge
    cases (zero, negative, NaN, fractional mantissa)."""
    from ui.plots import _fmt_cn2_book_style
    # Each Cn² reference value → expected book-style string.
    assert _fmt_cn2_book_style(1.0e-15) == "1×10⁻¹⁵ m⁻²ᐟ³"
    assert _fmt_cn2_book_style(1.0e-14) == "1×10⁻¹⁴ m⁻²ᐟ³"
    assert _fmt_cn2_book_style(5.0e-13) == "5×10⁻¹³ m⁻²ᐟ³"
    # Fractional mantissa → 1 decimal place.
    assert _fmt_cn2_book_style(1.7e-14) == "1.7×10⁻¹⁴ m⁻²ᐟ³"
    # Edge cases all return the en-dash placeholder.
    assert _fmt_cn2_book_style(0.0) == "—"
    assert _fmt_cn2_book_style(-1.0) == "—"
    assert _fmt_cn2_book_style(float("nan")) == "—"
