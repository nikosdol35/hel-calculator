"""Smoke tests for Plot N — burn-through time vs jitter.

The physics module ``physics.jitter_sensitivity`` has its own
extensive test suite (`tests/test_jitter_sensitivity.py`); this file
covers only the ``ui.plots.plot_n_jitter_sensitivity`` *plot
constructor* — title, axis types, trace count for a real curve.
"""
from __future__ import annotations

import pytest

from physics.jitter_sensitivity import compute_jitter_sensitivity
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


def test_plot_n_title_calls_out_tracking_accuracy():
    """Plot N's headline must explain that 'jitter' = tracking
    accuracy so non-specialists understand the connection — per the
    user's 2026-04-28 feedback that 'jitter' alone is jargon."""
    from ui.plots import plot_n_jitter_sensitivity
    curve = compute_jitter_sensitivity(_merged_result(), n_points=8)
    fig = plot_n_jitter_sensitivity(curve)
    title = (fig.layout.title.text or "")
    assert "How tracking accuracy" in title, (
        f"plot N title should mention 'tracking accuracy'; got: {title!r}"
    )
    # Original phrase must remain so the connection to the underlying
    # quantity (σ_jit) is preserved.
    assert "Burn-through time vs Jitter" in title


def test_plot_n_renders_with_log_x_axis():
    """Plot N's σ_jit axis spans 1 µrad..500 mrad — a log axis is
    necessary for the curve to be readable."""
    from ui.plots import plot_n_jitter_sensitivity
    curve = compute_jitter_sensitivity(_merged_result(), n_points=8)
    fig = plot_n_jitter_sensitivity(curve)
    assert fig.layout.xaxis.type == "log"


def test_plot_n_handles_none_curve():
    """None input → always-render empty frame, not a crash."""
    from ui.plots import plot_n_jitter_sensitivity
    fig = plot_n_jitter_sensitivity(None)
    assert len(fig.data) == 0
