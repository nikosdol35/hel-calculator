"""Tests for Plot H — engagement-profile timeline (PR 8).

SPEC v2.0 §8.3 of `docs/tracker_dwell_plan_2026-04-25.md`. Plot H is
the headline new visualisation for the trajectory model: a 4-panel
multi-subplot figure showing R(t), I_peak(t)+I_avg_aim(t),
T_surface(t), and E_cumulative(t) with a kill-moment marker on
every panel.

Coverage:
  - Plot H smokes against a real v2 head-on engagement
  - 4-row subplot structure with the expected number of traces
  - kill-moment vertical line is present when failure_mode is a
    kill verdict; absent otherwise
  - empty-frame fallback for v1.x results (no trajectory series)
  - empty-frame fallback for None / missing keys
  - M8 record_trajectory adds the new trajectory series to the
    output dict only when explicitly requested
"""
from __future__ import annotations

from physics import m8_burnthrough
from physics.orchestrator import run_full_chain
from tests.golden.scenarios import C_UAS_1500M


def _v2_head_on_inputs() -> dict:
    inputs = dict(C_UAS_1500M)
    inputs.pop("R")
    inputs.pop("v_perp")
    inputs.update({
        "R_detect": 1500, "R_min": 100,
        "engagement_geometry": "head_on",
    })
    return inputs


def test_m8_record_trajectory_adds_series():
    """The M8 record_trajectory flag adds three new trajectory keys
    (t_pde, T_surface, E_cumulative) to the result; default False
    leaves the v1.x output unchanged."""
    inputs_no_record = {
        "I_aim": 5.0e5,
        "material": "CFRP",
        "thickness": 0.002,
        "wavelength": 1.07e-6,
        "backside_BC": "insulated",
        "v_tgt": 20.0,
        "T_ambient": 293.0,
        "A_lambda": 0.85,
    }
    res_no_record = m8_burnthrough.compute(inputs_no_record)
    assert "trajectory_t_pde" not in res_no_record
    assert "trajectory_T_surface" not in res_no_record
    assert "trajectory_E_cumulative" not in res_no_record

    inputs_record = {**inputs_no_record, "record_trajectory": True}
    res_record = m8_burnthrough.compute(inputs_record)
    assert "trajectory_t_pde" in res_record
    assert "trajectory_T_surface" in res_record
    assert "trajectory_E_cumulative" in res_record
    # Same length across the three series.
    n = len(res_record["trajectory_t_pde"])
    assert n == len(res_record["trajectory_T_surface"])
    assert n == len(res_record["trajectory_E_cumulative"])
    # First sample at t=0.
    assert res_record["trajectory_t_pde"][0] == 0.0
    # Bounded — sub-sampled at ~50 ms across a few-second engagement.
    assert 5 <= n <= 5000


def test_m8_record_trajectory_E_cumulative_monotone():
    """Cumulative absorbed energy never decreases — Riemann sum of a
    positive flux."""
    inputs = {
        "I_aim": 5.0e5,
        "material": "CFRP",
        "thickness": 0.002,
        "wavelength": 1.07e-6,
        "backside_BC": "insulated",
        "v_tgt": 20.0,
        "T_ambient": 293.0,
        "A_lambda": 0.85,
        "record_trajectory": True,
    }
    res = m8_burnthrough.compute(inputs)
    E = res["trajectory_E_cumulative"]
    for prev, curr in zip(E, E[1:]):
        assert curr >= prev - 1e-9, (
            f"non-monotone cumulative energy at "
            f"{prev:.4g} → {curr:.4g}"
        )


def test_orchestrator_v2_emits_pde_trajectory_keys():
    """In v2 trajectory mode, the orchestrator's M8 call requests
    trajectory recording and merges the results into the output."""
    result = run_full_chain(_v2_head_on_inputs())
    assert "trajectory_t_pde" in result
    assert "trajectory_T_surface" in result
    assert "trajectory_E_cumulative" in result
    assert len(result["trajectory_t_pde"]) >= 1


def test_orchestrator_v1_does_not_emit_pde_trajectory_keys():
    """v1.x mode skips trajectory recording — the new keys are
    absent."""
    result = run_full_chain(C_UAS_1500M)
    assert "trajectory_t_pde" not in result
    assert "trajectory_T_surface" not in result
    assert "trajectory_E_cumulative" not in result


def test_plot_h_smoke():
    """Plot H renders against a real v2 head-on engagement with the
    expected panel structure."""
    from ui.plots import plot_h_engagement_profile

    result = run_full_chain(_v2_head_on_inputs())
    fig = plot_h_engagement_profile(result)
    # Four panels = four traces minimum (R, I_peak, T_surface,
    # E_cumulative); panel 2 also adds I_avg_aim, so total is 5.
    assert len(fig.data) == 5
    # The figure has multiple subplots — yaxis, yaxis2, yaxis3, yaxis4
    # appear in the layout. Confirm via subplot count.
    assert fig.layout.height is not None
    assert fig.layout.height >= 600  # multi-panel figure


def test_plot_h_kill_marker_present_when_kill():
    """When the engagement closes with a kill verdict, Plot H draws
    a vertical kill-moment dashed line on every panel."""
    from ui.plots import plot_h_engagement_profile

    result = run_full_chain(_v2_head_on_inputs())
    assert result["failure_mode"] == "decomposition"
    fig = plot_h_engagement_profile(result)
    # add_vline appends to fig.layout.shapes. T_fail also adds a
    # shape (Panel 3). Total: 4 kill-vlines + 1 T_fail-hline = 5.
    n_shapes = len(fig.layout.shapes or [])
    assert n_shapes >= 4, (
        f"expected at least 4 shapes (kill vlines per panel); got {n_shapes}"
    )


def test_plot_h_v1_result_renders_empty_frame():
    """v1.x result lacks trajectory series — Plot H falls back to the
    always-render frame with the infeasible-geometry advisory."""
    from ui.plots import plot_h_engagement_profile

    result = run_full_chain(C_UAS_1500M)  # v1 mode
    fig = plot_h_engagement_profile(result)
    assert len(fig.data) == 0  # empty-frame fallback


def test_plot_h_none_result_renders_empty_frame():
    """A None result renders the always-render frame, matching the
    other plot constructors."""
    from ui.plots import plot_h_engagement_profile

    fig = plot_h_engagement_profile(None)
    assert len(fig.data) == 0


def test_plot_h_no_kill_omits_kill_marker():
    """When the engagement ends without a kill (R_min reached or
    timeout), Plot H still renders but does NOT draw the kill-moment
    vertical line. Only the T_fail reference (if any) remains."""
    from ui.plots import plot_h_engagement_profile

    inputs = _v2_head_on_inputs()
    inputs["material"] = "polycarbonate"
    inputs["thickness"] = 0.020
    inputs["P0"] = 100  # effectively no flux
    inputs["R_detect"] = 200
    inputs["R_min"] = 100
    result = run_full_chain(inputs)
    assert result["failure_mode"] == "engagement_ended_at_R_min"
    fig = plot_h_engagement_profile(result)
    # No kill marker → fewer vertical lines than the kill case.
    # The exact count depends on whether T_fail reference also
    # vanishes (it does — failure_mode != kill verdict). Bound
    # loosely: at most 1 shape.
    n_shapes = len(fig.layout.shapes or [])
    assert n_shapes <= 1


def test_plot_h_panel_count_matches_design():
    """Plot H is a 4-panel subplot. Verify the subplot grid via the
    number of unique y-axes."""
    from ui.plots import plot_h_engagement_profile

    result = run_full_chain(_v2_head_on_inputs())
    fig = plot_h_engagement_profile(result)
    # Plotly multi-subplot figures expose yaxis, yaxis2, yaxis3,
    # yaxis4 in the layout for a 4-row grid.
    layout_keys = set(fig.layout)
    yaxes = [k for k in layout_keys if k.startswith("yaxis")]
    assert len(yaxes) == 4, f"expected 4 y-axes, got {len(yaxes)}: {yaxes}"
