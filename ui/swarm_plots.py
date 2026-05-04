"""Visualizations for the Swarm Analyzer.

Three plots consumed by ``ui/tools/swarm_analyzer.py``:

  * ``render_playback_plot`` — animated 2D top-down view of the
    engagement: drones moving as colored dots, BD turret as a
    slewing aim-line, dead drones gray, leaked drones red X.
  * ``render_gantt_chart`` — per-drone Gantt: time horizontal,
    one row per drone, colored bars showing slew / engage / kill /
    leak phases.
  * ``render_sensitivity_panel`` — compute-on-click sensitivity
    sweeps (slew rate, laser power, swarm size, σ_jit). Each sweep
    re-runs the simulation at 5 perturbed values and plots the
    leak-count response.

All three render via Plotly so the look matches HEL Calculator's
existing plots.
"""
from __future__ import annotations

import math
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from physics.swarm_drone_types import DRONE_TYPES, get_drone_type
from physics.swarm_kinematics import position_at
from physics.swarm_orchestrator import (
    SwarmEngagementResult,
    run_swarm_simulation,
)
from physics.swarm_scenario import SwarmScenario
from ui.theme import PLOTLY_MODEBAR_CONFIG


# ---------------------------------------------------------------------------
# 2D animated playback (Plotly Frames)
# ---------------------------------------------------------------------------

def _drone_state_at(
    result: SwarmEngagementResult,
    drone_id: int,
    t: float,
) -> str:
    """Replay the event log up to time t to determine a drone's
    state at that moment. Cheap O(events) lookup; runs once per
    frame per drone in the playback."""
    state = "WAITING"
    for ev in result.event_log:
        if ev.drone_id != drone_id or ev.t_s > t:
            continue
        if ev.kind == "DETECT":
            state = "DETECTED"
        elif ev.kind == "SLEW_START":
            state = "SLEWING"
        elif ev.kind == "ENGAGE_START":
            state = "ENGAGED"
        elif ev.kind == "KILL":
            state = "DESTROYED"
        elif ev.kind == "LEAK":
            state = "LEAKED"
        elif ev.kind == "TIMEOUT":
            state = "TIMEOUT"
    return state


def _bd_aim_at(
    result: SwarmEngagementResult,
    scenario: SwarmScenario,
    t: float,
) -> tuple[float | None, str]:
    """Return (target_drone_id_or_None, bd_state_at_t) by replaying
    the event log up to t. Used to draw the BD's aim-line."""
    target_id: int | None = None
    bd_state = "IDLE"
    for ev in result.event_log:
        if ev.t_s > t:
            break
        if ev.kind == "SLEW_START":
            target_id = ev.drone_id
            bd_state = "SLEWING"
        elif ev.kind == "ENGAGE_START":
            target_id = ev.drone_id
            bd_state = "ENGAGING"
        elif ev.kind in ("KILL", "LEAK") and ev.drone_id == target_id:
            bd_state = "IDLE"
            target_id = None
    return target_id, bd_state


def render_playback_plot(
    result: SwarmEngagementResult,
    scenario: SwarmScenario | None,
) -> None:
    """Render the animated 2D playback as a Plotly figure with
    Frames. Dots = drones (color by type, faded gray when dead).
    Red X = leaked drones. BD turret as a small triangle at origin
    with an aim-line drawn to the currently-engaged target.

    Falls back to a static "engagement summary" scatter when
    ``scenario`` is None (shouldn't happen in normal use)."""
    if scenario is None:
        st.info("Animated playback needs the scenario; nothing to draw.")
        return

    # Frame timing — display every Nth simulation timestep so we get
    # ~60–120 frames total (smooth in browser without overwhelming).
    total_t = max(o.outcome_time_s for o in result.drones)
    target_n_frames = 80
    n_steps_total = int(round(total_t / scenario.dt_s)) + 1
    stride = max(1, n_steps_total // target_n_frames)
    frame_times = [scenario.dt_s * i for i in range(0, n_steps_total + 1, stride)]
    if frame_times[-1] < total_t:
        frame_times.append(total_t)

    # Initial frame builds the figure shell.
    fig = go.Figure()

    # Determine plot extent — fit the largest initial range, padded.
    max_range = max(
        (math.sqrt(d.position_m[0] ** 2 + d.position_m[1] ** 2)
         for d in scenario.drones),
        default=2000.0,
    )
    extent_m = max(max_range * 1.2, scenario.R_detect_max_m * 1.05)

    # ── Static layer: BD position + R_min / R_detect circles ──────
    # R_min circle (your defended zone).
    n_circle = 64
    r_min_x = [scenario.R_min_m * math.cos(2 * math.pi * i / n_circle) for i in range(n_circle + 1)]
    r_min_y = [scenario.R_min_m * math.sin(2 * math.pi * i / n_circle) for i in range(n_circle + 1)]
    fig.add_trace(go.Scatter(
        x=r_min_x, y=r_min_y, mode="lines",
        line=dict(color="rgba(229, 80, 86, 0.6)", width=1, dash="dash"),
        name=f"R_min = {scenario.R_min_m:.0f} m",
        hoverinfo="skip",
    ))

    # R_detect circle.
    r_det_x = [scenario.R_detect_max_m * math.cos(2 * math.pi * i / n_circle) for i in range(n_circle + 1)]
    r_det_y = [scenario.R_detect_max_m * math.sin(2 * math.pi * i / n_circle) for i in range(n_circle + 1)]
    fig.add_trace(go.Scatter(
        x=r_det_x, y=r_det_y, mode="lines",
        line=dict(color="rgba(127, 142, 156, 0.4)", width=1, dash="dot"),
        name=f"R_detect = {scenario.R_detect_max_m / 1000.0:.1f} km",
        hoverinfo="skip",
    ))

    # BD marker at origin.
    fig.add_trace(go.Scatter(
        x=[0.0], y=[0.0], mode="markers+text",
        marker=dict(symbol="square", size=14, color="white",
                    line=dict(color="black", width=1)),
        text=["BD"],
        textposition="bottom center",
        textfont=dict(size=10, color="white"),
        name="Beam director",
        hoverinfo="skip",
    ))

    # ── Dynamic layer: drone positions per frame ─────────────────
    # Drone trace order matches scenario.drones; each frame updates
    # marker properties (color, opacity, symbol) to reflect state.
    drone_xs_t0: list[float] = []
    drone_ys_t0: list[float] = []
    drone_colors_t0: list[str] = []
    drone_symbols_t0: list[str] = []
    drone_opacities_t0: list[float] = []
    drone_hover_t0: list[str] = []
    for d in scenario.drones:
        drone_xs_t0.append(d.position_m[0])
        drone_ys_t0.append(d.position_m[1])
        drone_colors_t0.append(get_drone_type(d.drone_type_key).color_hex)
        drone_symbols_t0.append("circle")
        drone_opacities_t0.append(1.0)
        drone_hover_t0.append(
            f"#{d.drone_id} {get_drone_type(d.drone_type_key).label}"
        )

    fig.add_trace(go.Scatter(
        x=drone_xs_t0, y=drone_ys_t0, mode="markers",
        marker=dict(
            size=12, color=drone_colors_t0, symbol=drone_symbols_t0,
            opacity=drone_opacities_t0,
            line=dict(color="black", width=1),
        ),
        text=drone_hover_t0,
        hovertemplate="%{text}<br>(%{x:.0f}, %{y:.0f}) m<extra></extra>",
        name="Drones",
        showlegend=False,
    ))

    # BD aim-line — drawn from origin to current target each frame.
    fig.add_trace(go.Scatter(
        x=[0.0, 0.0], y=[0.0, 0.0], mode="lines",
        line=dict(color="rgba(255, 224, 130, 0.9)", width=2),
        hoverinfo="skip",
        name="BD aim",
        showlegend=False,
    ))

    # ── Build Plotly Frames for the animation ────────────────────
    frames = []
    for t in frame_times:
        xs, ys, colors, symbols, opacities, hovers = [], [], [], [], [], []
        for d in scenario.drones:
            state = _drone_state_at(result, d.drone_id, t)
            outcome = next(
                (o for o in result.drones if o.drone_id == d.drone_id), None
            )
            # Position freezes at outcome time (drone "lands").
            if outcome is not None and t >= outcome.outcome_time_s:
                pos = position_at(d.position_m, d.velocity_mps, outcome.outcome_time_s)
            else:
                pos = position_at(d.position_m, d.velocity_mps, t)
            xs.append(pos[0])
            ys.append(pos[1])
            base_color = get_drone_type(d.drone_type_key).color_hex
            if state in ("DESTROYED",):
                colors.append("#5F6368")
                symbols.append("circle")
                opacities.append(0.4)
                hovers.append(f"#{d.drone_id} KILLED")
            elif state in ("LEAKED",):
                colors.append("#E55056")
                symbols.append("x")
                opacities.append(1.0)
                hovers.append(f"#{d.drone_id} LEAKED")
            elif state == "TIMEOUT":
                colors.append("#9AA0A6")
                symbols.append("circle")
                opacities.append(0.5)
                hovers.append(f"#{d.drone_id} timed out")
            elif state == "ENGAGED":
                colors.append(base_color)
                symbols.append("circle")
                opacities.append(1.0)
                hovers.append(
                    f"#{d.drone_id} {get_drone_type(d.drone_type_key).label} (engaged)"
                )
            elif state == "WAITING":
                colors.append("#3A424B")
                symbols.append("circle-open")
                opacities.append(0.4)
                hovers.append(f"#{d.drone_id} waiting (out of range)")
            else:
                colors.append(base_color)
                symbols.append("circle")
                opacities.append(0.85)
                hovers.append(f"#{d.drone_id} {get_drone_type(d.drone_type_key).label}")

        # Aim-line.
        target_id, bd_state = _bd_aim_at(result, scenario, t)
        if target_id is not None and bd_state in ("SLEWING", "ENGAGING"):
            tgt = next(
                (sd for sd in scenario.drones if sd.drone_id == target_id),
                None,
            )
            if tgt is not None:
                outcome = next(
                    (o for o in result.drones if o.drone_id == target_id), None
                )
                tgt_t = (
                    outcome.outcome_time_s
                    if outcome is not None and t >= outcome.outcome_time_s
                    else t
                )
                tgt_pos = position_at(tgt.position_m, tgt.velocity_mps, tgt_t)
                aim_x = [0.0, tgt_pos[0]]
                aim_y = [0.0, tgt_pos[1]]
            else:
                aim_x, aim_y = [0.0, 0.0], [0.0, 0.0]
        else:
            aim_x, aim_y = [0.0, 0.0], [0.0, 0.0]

        frames.append(go.Frame(
            data=[
                # Static traces 0,1,2 (R_min, R_detect, BD) unchanged.
                go.Scatter(x=r_min_x, y=r_min_y),
                go.Scatter(x=r_det_x, y=r_det_y),
                go.Scatter(x=[0.0], y=[0.0]),
                # Dynamic drones (trace 3).
                go.Scatter(
                    x=xs, y=ys, mode="markers",
                    marker=dict(
                        size=12, color=colors, symbol=symbols,
                        opacity=opacities,
                        line=dict(color="black", width=1),
                    ),
                    text=hovers,
                ),
                # Aim-line (trace 4).
                go.Scatter(
                    x=aim_x, y=aim_y, mode="lines",
                    line=dict(color="rgba(255, 224, 130, 0.9)", width=2),
                ),
            ],
            name=f"t={t:.1f}",
        ))

    fig.frames = frames

    # ── Layout + animation controls ──────────────────────────────
    fig.update_layout(
        title="Swarm engagement playback",
        xaxis=dict(
            title="x (m)",
            range=[-extent_m, extent_m],
            scaleanchor="y", scaleratio=1,
        ),
        yaxis=dict(
            title="y (m)",
            range=[-extent_m, extent_m],
        ),
        height=600,
        hovermode="closest",
        updatemenus=[dict(
            type="buttons",
            x=0.0, y=-0.05, xanchor="left", yanchor="top",
            showactive=False,
            buttons=[
                dict(
                    label="▶ Play",
                    method="animate",
                    args=[None, {
                        "frame": {"duration": 100, "redraw": True},
                        "fromcurrent": True,
                        "transition": {"duration": 0},
                    }],
                ),
                dict(
                    label="⏸ Pause",
                    method="animate",
                    args=[[None], {
                        "frame": {"duration": 0, "redraw": False},
                        "mode": "immediate",
                        "transition": {"duration": 0},
                    }],
                ),
            ],
        )],
        sliders=[dict(
            active=0,
            steps=[
                dict(
                    method="animate",
                    args=[[f.name], {
                        "frame": {"duration": 0, "redraw": True},
                        "mode": "immediate",
                        "transition": {"duration": 0},
                    }],
                    label=f.name,
                )
                for f in frames
            ],
            x=0.1, y=-0.05, xanchor="left", yanchor="top",
            len=0.85,
        )],
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1.0,
        ),
    )

    st.plotly_chart(
        fig, use_container_width=True, config=PLOTLY_MODEBAR_CONFIG,
    )
    st.caption(
        "▶ Play / ⏸ Pause to animate; drag the slider to scrub. "
        "Dots are drones (color = type), gray = killed, red X = "
        "leaked. The yellow line is the BD's aim direction (slewing "
        "or engaging)."
    )


# ---------------------------------------------------------------------------
# Per-drone Gantt chart
# ---------------------------------------------------------------------------

def render_gantt_chart(result: SwarmEngagementResult) -> None:
    """Per-drone Gantt: one row per drone, time on x-axis, colored
    bars showing detect / slew-to-engage / engage / kill or leak.

    Helps the operator see "where did time go": if the BD spent
    most of total time slewing, more laser power won't help — a
    faster turret will.
    """
    fig = go.Figure()
    drone_ids = [o.drone_id for o in result.drones]

    for o in result.drones:
        # Light-gray "queued / detected" bar from detect_time to
        # first engage start (or outcome if never engaged).
        if o.detect_time_s is not None:
            queue_end = (
                o.engage_starts_s[0]
                if o.engage_starts_s
                else o.outcome_time_s
            )
            fig.add_trace(go.Bar(
                x=[queue_end - o.detect_time_s], y=[f"#{o.drone_id}"],
                base=o.detect_time_s,
                orientation="h",
                marker=dict(color="rgba(180, 188, 196, 0.5)"),
                name="Queued",
                showlegend=(o.drone_id == drone_ids[0]),
                hovertemplate=(
                    f"#{o.drone_id}: queued "
                    f"{o.detect_time_s:.1f} → {queue_end:.1f} s<extra></extra>"
                ),
            ))
        # Engage bars (orange).
        for start, dur in zip(o.engage_starts_s, o.engage_durations_s):
            fig.add_trace(go.Bar(
                x=[dur], y=[f"#{o.drone_id}"],
                base=start,
                orientation="h",
                marker=dict(color="#F5A623"),
                name="Engaged",
                showlegend=(o.drone_id == drone_ids[0] and o.engage_starts_s.index(start) == 0),
                hovertemplate=(
                    f"#{o.drone_id}: engaged "
                    f"{start:.1f} → {start + dur:.1f} s ({dur:.2f} s)"
                    "<extra></extra>"
                ),
            ))
        # Verdict marker at outcome time.
        verdict_color = {
            "KILL": "#3CC988",
            "LEAK": "#E55056",
            "TIMEOUT": "#9AA0A6",
        }.get(o.verdict, "#9AA0A6")
        fig.add_trace(go.Scatter(
            x=[o.outcome_time_s], y=[f"#{o.drone_id}"],
            mode="markers+text",
            marker=dict(
                size=14,
                color=verdict_color,
                symbol="square",
                line=dict(color="black", width=1),
            ),
            text=[o.verdict],
            textposition="middle right",
            textfont=dict(size=10, color="white"),
            name=o.verdict,
            showlegend=False,
            hoverinfo="skip",
        ))

    fig.update_layout(
        title="Per-drone Gantt — where did time go?",
        xaxis_title="Time (s)",
        yaxis_title="Drone ID",
        barmode="stack",
        height=max(300, 60 + 30 * len(result.drones)),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1.0,
        ),
    )
    st.plotly_chart(
        fig, use_container_width=True, config=PLOTLY_MODEBAR_CONFIG,
    )


# ---------------------------------------------------------------------------
# Sensitivity panel (compute-on-click) — Day 6
# ---------------------------------------------------------------------------

_SENSITIVITY_CACHE_KEY = "_swarm_sensitivity_cache"


def _scenario_with_param(
    scenario: SwarmScenario, param: str, value: float
) -> SwarmScenario:
    """Build a perturbed scenario with one input changed."""
    if param == "slew_rate":
        bd = scenario.bd_kinematics
        new_bd = type(bd)(
            max_slew_rate_dps=value,
            max_slew_accel_dps2=bd.max_slew_accel_dps2,
            settling_time_s=bd.settling_time_s,
            reacquire_time_s=bd.reacquire_time_s,
            initial_bearing_deg=bd.initial_bearing_deg,
        )
        return type(scenario)(
            drones=scenario.drones, bd_kinematics=new_bd,
            hel_inputs=scenario.hel_inputs, R_min_m=scenario.R_min_m,
            R_detect_max_m=scenario.R_detect_max_m,
            strategy=scenario.strategy, dt_s=scenario.dt_s,
            t_max_s=scenario.t_max_s,
        )
    if param == "P0":
        new_inputs = dict(scenario.hel_inputs)
        new_inputs["P0"] = value
        return type(scenario)(
            drones=scenario.drones, bd_kinematics=scenario.bd_kinematics,
            hel_inputs=new_inputs, R_min_m=scenario.R_min_m,
            R_detect_max_m=scenario.R_detect_max_m,
            strategy=scenario.strategy, dt_s=scenario.dt_s,
            t_max_s=scenario.t_max_s,
        )
    if param == "sigma_jit":
        new_inputs = dict(scenario.hel_inputs)
        new_inputs["sigma_jit"] = value
        return type(scenario)(
            drones=scenario.drones, bd_kinematics=scenario.bd_kinematics,
            hel_inputs=new_inputs, R_min_m=scenario.R_min_m,
            R_detect_max_m=scenario.R_detect_max_m,
            strategy=scenario.strategy, dt_s=scenario.dt_s,
            t_max_s=scenario.t_max_s,
        )
    raise ValueError(f"unknown sensitivity param {param}")


def render_sensitivity_panel(
    scenario: SwarmScenario,
    result: SwarmEngagementResult,
) -> None:
    """Compute-on-click sensitivity sweeps. Each sweep re-runs the
    simulation at 5 perturbed values of one parameter and plots the
    leak count / kill count response. Cached in session-state so
    re-renders are instant until the scenario changes.

    Three sweeps for v1 (each 5 levels):
      * Slew rate ±50%
      * Laser power ±50%
      * σ_jit ±50%
    """
    st.markdown("#### Sensitivity analysis")
    st.caption(
        "Re-run the simulation at perturbed parameter values to see "
        "which lever matters most for THIS scenario. Compute-on-click "
        "(takes ~10–20 s); results cached until you change the "
        "scenario."
    )

    if _SENSITIVITY_CACHE_KEY not in st.session_state:
        st.session_state[_SENSITIVITY_CACHE_KEY] = {}
    cache_key = scenario.to_json()
    cache = st.session_state[_SENSITIVITY_CACHE_KEY]

    if st.button("Run sensitivity analysis", type="secondary"):
        with st.spinner("Running 15 perturbed simulations..."):
            sweeps: dict[str, list[tuple[float, int, int]]] = {
                "slew_rate": [],
                "P0": [],
                "sigma_jit": [],
            }
            base_slew = scenario.bd_kinematics.max_slew_rate_dps
            base_P0 = scenario.hel_inputs["P0"]
            base_jit = scenario.hel_inputs["sigma_jit"]
            multipliers = [0.5, 0.75, 1.0, 1.25, 1.5]
            for m in multipliers:
                s_slew = _scenario_with_param(scenario, "slew_rate", base_slew * m)
                r_slew = run_swarm_simulation(s_slew)
                sweeps["slew_rate"].append((m, r_slew.n_killed, r_slew.n_leaked))

                s_P0 = _scenario_with_param(scenario, "P0", base_P0 * m)
                r_P0 = run_swarm_simulation(s_P0)
                sweeps["P0"].append((m, r_P0.n_killed, r_P0.n_leaked))

                s_jit = _scenario_with_param(scenario, "sigma_jit", base_jit * m)
                r_jit = run_swarm_simulation(s_jit)
                sweeps["sigma_jit"].append((m, r_jit.n_killed, r_jit.n_leaked))
            cache[cache_key] = sweeps

    sweeps = cache.get(cache_key)
    if sweeps is None:
        return  # nothing to render yet

    cols = st.columns(3)
    titles = {
        "slew_rate": "Slew rate (×)",
        "P0": "Laser power (×)",
        "sigma_jit": "σ_jit (×)",
    }
    for col, (param, title) in zip(cols, titles.items()):
        rows = sweeps[param]
        xs = [m for m, _, _ in rows]
        leaks = [n_leak for _, _, n_leak in rows]
        kills = [n_kill for _, n_kill, _ in rows]
        sub = go.Figure()
        sub.add_trace(go.Bar(
            x=xs, y=leaks, name="Leaks",
            marker_color="#E55056",
        ))
        sub.add_trace(go.Bar(
            x=xs, y=kills, name="Kills",
            marker_color="#3CC988",
        ))
        sub.update_layout(
            title=title,
            xaxis_title="Multiplier",
            yaxis_title="Count",
            height=280,
            barmode="group",
            showlegend=(param == "slew_rate"),
            margin=dict(l=40, r=20, t=40, b=40),
        )
        col.plotly_chart(sub, use_container_width=True, config=PLOTLY_MODEBAR_CONFIG)


__all__ = [
    "render_playback_plot",
    "render_gantt_chart",
    "render_sensitivity_panel",
]
