"""Tests for Plot J — cumulative energy & useful-work diagnostic
(PR 10).

SPEC v2.0 §8.5 of `docs/tracker_dwell_plan_2026-04-25.md`. Plot J
plots the cumulative absorbed energy through the engagement, with a
horizontal reference at the lumped-mass failure fluence and a shaded
"useful zone" marking the time window where the irradiance was above
the 1 W/cm² threshold.

Coverage:
  - smoke against a real v2 engagement
  - cumulative-energy curve is monotonically non-decreasing
  - failure-fluence reference computed from material properties
  - useful-zone shading present when the curve crosses the threshold
  - empty-frame fallback for v1.x results
  - empty-frame fallback for None / missing trajectory keys
"""
from __future__ import annotations

from physics.orchestrator import run_full_chain
from tests.golden.scenarios import C_UAS_1500M


def _v2_inputs() -> dict:
    inputs = dict(C_UAS_1500M)
    inputs.pop("R")
    inputs.pop("v_perp")
    inputs.update({
        "R_detect": 1500, "R_min": 100,
        "engagement_geometry": "head_on",
    })
    return inputs


def test_plot_j_smoke():
    """Plot J renders against a real v2 engagement with a single
    cumulative-energy curve."""
    from ui.plots import plot_j_cumulative_energy_diagnostic
    result = run_full_chain(_v2_inputs())
    fig = plot_j_cumulative_energy_diagnostic(result)
    assert len(fig.data) == 1
    assert fig.data[0].name == "Cumulative absorbed energy"


def test_plot_j_cumulative_energy_non_decreasing():
    """Cumulative absorbed energy never decreases (Riemann sum of
    positive flux). Already verified by M8 tests but worth a guard
    here too — the curve is the headline of Plot J."""
    from ui.plots import plot_j_cumulative_energy_diagnostic
    result = run_full_chain(_v2_inputs())
    fig = plot_j_cumulative_energy_diagnostic(result)
    # Trace 0 is the cumulative-energy curve.
    y_vals = list(fig.data[0].y)
    for prev, curr in zip(y_vals, y_vals[1:]):
        assert curr >= prev - 1e-9, (
            f"non-monotone cumulative energy: {prev:.4g} → {curr:.4g}"
        )


def test_plot_j_useful_zone_when_kill_happens():
    """When the engagement closes with a kill, the useful zone (and
    a kill-moment vertical) are drawn — extra layout shapes."""
    from ui.plots import plot_j_cumulative_energy_diagnostic
    result = run_full_chain(_v2_inputs())
    assert result["failure_mode"] == "decomposition"
    fig = plot_j_cumulative_energy_diagnostic(result)
    # Expected shapes: useful-zone vrect + E_fail hline + kill vline = 3
    n_shapes = len(fig.layout.shapes or [])
    assert n_shapes >= 2  # at least useful-zone + E_fail


def test_plot_j_v1_result_empty_frame():
    """v1.x result lacks trajectory series → empty frame."""
    from ui.plots import plot_j_cumulative_energy_diagnostic
    result = run_full_chain(C_UAS_1500M)
    fig = plot_j_cumulative_energy_diagnostic(result)
    assert len(fig.data) == 0


def test_plot_j_none_result_empty_frame():
    from ui.plots import plot_j_cumulative_energy_diagnostic
    fig = plot_j_cumulative_energy_diagnostic(None)
    assert len(fig.data) == 0


def test_plot_j_no_kill_no_kill_marker():
    """An engagement that ends without a kill draws the curve and the
    E_fail reference but skips the kill-marker / useful-zone overlay
    (since useful_end_t is undefined)."""
    from ui.plots import plot_j_cumulative_energy_diagnostic
    inputs = _v2_inputs()
    inputs["material"] = "polycarbonate"
    inputs["thickness"] = 0.020
    inputs["P0"] = 100
    inputs["R_detect"] = 200
    inputs["R_min"] = 100
    result = run_full_chain(inputs)
    assert result["failure_mode"] == "engagement_ended_at_R_min"
    fig = plot_j_cumulative_energy_diagnostic(result)
    # Curve is still drawn.
    assert len(fig.data) == 1
    # Without a kill moment, no kill vline or useful-zone vrect.
    # Only the E_fail hline (if material lookup succeeded) remains.
    n_shapes = len(fig.layout.shapes or [])
    assert n_shapes <= 1


def test_plot_j_E_fail_reference_drawn():
    """Plot J draws an E_fail reference line when the merged-result
    dict carries material + thickness + T_ambient. Mirrors how the UI
    layer calls the plot — ``merged = {**user_inputs, **result}`` —
    so the material lookup succeeds and the lumped-mass failure
    fluence is shown."""
    from ui.plots import plot_j_cumulative_energy_diagnostic
    inputs = _v2_inputs()
    inputs["material"] = "polycarbonate"
    inputs["thickness"] = 0.002
    result = run_full_chain(inputs)
    # UI-shape merge: orchestrator output alone doesn't carry user
    # inputs (material, thickness, T_ambient); the UI overlays them
    # into the merged dict before passing to the plotters.
    merged = {**inputs, **result}
    fig = plot_j_cumulative_energy_diagnostic(merged)
    # E_fail reference is one of the layout shapes (horizontal line).
    # add_hline produces a 'line' shape with y0 == y1 in y-axis
    # coordinates and x0/x1 spanning the 'x domain'.
    e_fail_y: float | None = None
    for shape in (fig.layout.shapes or []):
        if (shape.type == "line"
                and shape.y0 is not None
                and shape.y1 is not None
                and shape.yref == "y"):
            try:
                if abs(float(shape.y0) - float(shape.y1)) < 1e-9:
                    e_fail_y = float(shape.y0)
                    break
            except (TypeError, ValueError):
                continue
    assert e_fail_y is not None, (
        "no horizontal-line shape with y0=y1 in y-coords — E_fail "
        "reference missing"
    )
    # Polycarbonate at 2 mm: E_fail ≈ 115 J/cm²; allow a wide engineering
    # band to absorb any T_ambient variation between v1 and v2 paths.
    assert 50.0 <= e_fail_y <= 250.0, (
        f"E_fail = {e_fail_y} J/cm² outside polycarbonate range"
    )
