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
