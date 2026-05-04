"""Render functions for the Swarm Analyzer's results panel.

Three blocks consumed by the page entry:

  * ``render_kpi_bar`` — large headline metrics across the top
    (verdict, drones killed/leaked, first-leak time, total time,
    slew fraction)
  * ``render_per_drone_table`` — Pandas-style results table with
    one row per drone (ID, type, verdict, engage time, etc.)
  * ``render_assumptions_block`` — collapsed expander listing the
    ten standing assumptions baked into the lightweight chain

Day-4 v1; the playback animation, Gantt chart, and sensitivity panel
land in Day 5/6 alongside ``ui/swarm_plots.py``.
"""
from __future__ import annotations

import streamlit as st

from physics.swarm_drone_types import get_drone_type
from physics.swarm_orchestrator import SwarmEngagementResult


def _verdict_color_emoji(n_leaked: int) -> tuple[str, str]:
    """Pick a status emoji + verdict tagline based on leak count."""
    if n_leaked == 0:
        return "🟢", "ALL THREATS DEFEATED"
    if n_leaked <= 2:
        return "🟡", f"{n_leaked} LEAK{'S' if n_leaked > 1 else ''}"
    return "🔴", f"{n_leaked} LEAKS"


def render_kpi_bar(result: SwarmEngagementResult) -> None:
    """Hero KPI bar at the top of the results panel.

    Six metrics across:
      Verdict — Drones killed — First leak — Total time —
      Slew fraction — Closest leak
    """
    emoji, tagline = _verdict_color_emoji(result.n_leaked)
    st.markdown(f"### {emoji} {tagline}")

    cols = st.columns(5)
    cols[0].metric(
        "Drones killed",
        f"{result.n_killed} / "
        f"{result.n_killed + result.n_leaked + result.n_timeout}",
    )
    first_leak = (
        f"{result.first_leak_time_s:.1f} s"
        if result.first_leak_time_s is not None
        else "—"
    )
    cols[1].metric("First leak at", first_leak)
    cols[2].metric(
        "Total engagement",
        f"{result.total_engagement_time_s:.1f} s",
    )
    slew_pct = result.slew_fraction * 100.0
    cols[3].metric(
        "Slew-time fraction",
        f"{slew_pct:.0f}%",
        help=(
            "Share of total engagement time spent re-aiming the BD "
            "between targets. > 40% means you're slew-limited — a "
            "faster turret would help more than more laser power."
        ),
    )
    closest_leak = (
        f"{result.closest_leak_range_m:.0f} m"
        if result.closest_leak_range_m is not None
        else "—"
    )
    cols[4].metric("Closest leak", closest_leak)


def render_per_drone_table(result: SwarmEngagementResult) -> None:
    """Per-drone results table — one row per drone, sortable in
    the browser."""
    import pandas as pd

    rows = []
    for d in result.drones:
        drone_type = get_drone_type(d.drone_type_key)
        sum_engage = sum(d.engage_durations_s) if d.engage_durations_s else 0.0
        n_engagements = len(d.engage_starts_s)
        absorbed_pct = (
            100.0 * d.cumulative_absorbed_J_per_cm2 / d.E_fail_J_per_cm2
            if d.E_fail_J_per_cm2 > 0 else 0.0
        )
        rows.append({
            "ID": d.drone_id,
            "Type": drone_type.label,
            "Verdict": d.verdict,
            "Detect (s)": f"{d.detect_time_s:.1f}" if d.detect_time_s is not None else "—",
            "Slew→engage (s)": f"{d.slew_time_to_first_engage_s:.2f}",
            "Engage time (s)": f"{sum_engage:.2f}",
            "# engagements": n_engagements,
            "Range at outcome (m)": f"{d.range_at_outcome_m:.0f}",
            "% of E_fail absorbed": f"{absorbed_pct:.0f}%",
            "Outcome at t (s)": f"{d.outcome_time_s:.1f}",
        })

    df = pd.DataFrame(rows)

    st.markdown("#### Per-drone results")
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_timing_breakdown(result: SwarmEngagementResult) -> None:
    """Small horizontal bar showing how the total engagement time
    splits between slew, engage, and idle phases. Helps the operator
    see if the system is slew-limited or engage-limited."""
    breakdown = result.timing_breakdown
    total = (
        breakdown.slew_total_s
        + breakdown.engage_total_s
        + breakdown.idle_total_s
    )
    if total <= 0:
        return
    st.markdown("#### Time breakdown")
    cols = st.columns(3)
    cols[0].metric(
        "Slewing", f"{breakdown.slew_total_s:.1f} s",
        f"{breakdown.slew_total_s / total * 100.0:.0f}%",
    )
    cols[1].metric(
        "Engaging", f"{breakdown.engage_total_s:.1f} s",
        f"{breakdown.engage_total_s / total * 100.0:.0f}%",
    )
    cols[2].metric(
        "Idle", f"{breakdown.idle_total_s:.1f} s",
        f"{breakdown.idle_total_s / total * 100.0:.0f}%",
    )


def render_assumptions_block(result: SwarmEngagementResult) -> None:
    """Collapsed expander listing the ten standing assumptions that
    apply to every Swarm Analyzer simulation. Per CLAUDE.md §4.5 —
    every output flags its assumptions."""
    with st.expander(
        f"Assumptions baked into this simulation ({len(result.assumptions_flagged)})",
        expanded=False,
    ):
        st.markdown(
            "Each item below is a deliberate simplification baked "
            "into the lightweight chain the Swarm Analyzer uses. "
            "These keep the simulation interactive (~1 s per scenario) "
            "while preserving the tactical question. For the absolute "
            "truth on a single drone's burn-through, run the HEL "
            "Calculator (PDE-accurate full chain)."
        )
        for assumption in result.assumptions_flagged:
            st.markdown(f"- {assumption}")


__all__ = [
    "render_kpi_bar",
    "render_per_drone_table",
    "render_timing_breakdown",
    "render_assumptions_block",
]
