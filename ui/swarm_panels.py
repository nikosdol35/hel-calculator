"""Sidebar + scenario-builder UI for the Swarm Analyzer.

The sidebar reuses the HEL Calculator's six laser/atmosphere
sections (via ``ui.panels.collect_hel``) — the laser-side physics
is identical for swarm engagements. Three new sidebar expanders
cover the swarm-specific inputs:

  * **BD kinematics** — slew rate, accel, settling, reacquire,
    initial bearing
  * **Detection** — max detection range
  * **Engagement** — strategy dropdown + simulation timestep

The main panel (rendered by ``render_scenario_builder``) carries
the **visual scenario builder** (2026-04-29 redesign): a Plotly
map with the BD at center, R_min/R_detect circles, and
click-to-place drone targets. Each placed drone shows as a
colored dot with a velocity arrow; clicking a drone opens an
inline edit panel (speed slider, heading toggle, delete). The
table is preserved in a collapsed expander for power-users who
want raw x/y/vx/vy editing.

Pure UI glue — no physics; relies on ``physics/swarm_scenario.py``
for validation.
"""
from __future__ import annotations

import math

import plotly.graph_objects as go
import streamlit as st

from physics.swarm_drone_types import DRONE_TYPES, get_drone_type
from physics.swarm_kinematics import bearing_to_drone_deg, range_to_bd_m
from physics.swarm_scenario import BDKinematics, Drone, SwarmScenario
from ui import panels
from ui.theme import PLOTLY_MODEBAR_CONFIG


# Session-state keys (scoped with ``_swarm_`` prefix per plan §4.4 to
# avoid stomping HEL Calculator's session-state).
_SWARM_DRONES_KEY = "_swarm_drones"            # list[dict] of drone rows
_SWARM_NEXT_ID_KEY = "_swarm_next_drone_id"    # monotonic id counter
_SWARM_ACTIVE_TYPE_KEY = "_swarm_active_type"  # drone type for next click
_SWARM_SELECTED_KEY = "_swarm_selected_drone"  # drone_id (stable) of selection
_SWARM_R_DETECT_KEY = "_swarm_R_detect_max_m"  # captured for the map extent
_SWARM_LAST_CLICK_KEY = "_swarm_last_click_sig"
# Streamlit's plotly chart preserves the selection state across
# reruns — without this guard we'd re-process the same click on
# every rerun and create infinite drones / infinite loops. The
# signature is a tuple (trace_idx, snapped_x, snapped_y, point_idx)
# that uniquely identifies a click; we only act on a click whose
# signature differs from the one we last processed.


# Plotly trace-index constants (used by the click handler to dispatch
# clicks). Order MUST match the order traces are added to the figure
# in ``_render_scenario_map``.
_TRACE_R_MIN = 0
_TRACE_R_DETECT = 1
_TRACE_GRID_LINES = 2
_TRACE_BD = 3
_TRACE_SNAP_GRID = 4
_TRACE_DRONES = 5


_STRATEGY_LABELS = {
    "earliest_leak_first": "Earliest leak first (recommended)",
    "closest_first": "Closest first",
    "easiest_kill_first": "Easiest kill first",
}

_STRATEGY_HELP = {
    "earliest_leak_first": (
        "Engage the drone whose range is closing fastest relative to "
        "R_min. Tactically correct default — go after whichever target "
        "is about to breach your defended zone next."
    ),
    "closest_first": (
        "Engage the drone with the smallest current range. Simple and "
        "intuitive but can be suboptimal: a slow distant drone might "
        "be easier than a fast close one."
    ),
    "easiest_kill_first": (
        "Engage the drone with the smallest estimated burn-through "
        "time at its current range. Maximizes 'kills per second' but "
        "can let the most threatening target keep closing."
    ),
}


_DT_LABELS = {
    0.05: "0.05 s — default",
    0.02: "0.02 s — high fidelity",
    0.10: "0.10 s — fast",
}


# ---------------------------------------------------------------------------
# Sidebar — swarm-specific section
# ---------------------------------------------------------------------------

def render_swarm_sidebar() -> dict:
    """Render the swarm-specific sidebar sections (BD kinematics,
    detection, engagement) plus the HEL sidebar via ``collect_hel``.
    Returns a flat dict of all inputs the orchestrator needs.

    Structure:
      - HEL Calculator's six existing sections (laser, BD, geometry,
        atmosphere, target, system) — reused unchanged
      - New: Beam director kinematics
      - New: Detection
      - New: Engagement strategy + timestep
    """
    # 1. Reuse the HEL sidebar.
    hel_inputs = panels.collect_hel()

    # 2. New: BD kinematics.
    with st.sidebar.expander("Beam director kinematics", expanded=False):
        st.caption(
            "Generic mid-class HEL turret defaults. Override per "
            "system. Operator may also pre-point the BD at a known "
            "threat axis via the initial-bearing field."
        )
        max_slew_rate_dps = st.number_input(
            "Max slew rate (deg/s)",
            min_value=1.0, max_value=360.0, value=60.0, step=5.0,
        )
        max_slew_accel_dps2 = st.number_input(
            "Slew acceleration (deg/s²)",
            min_value=1.0, max_value=720.0, value=120.0, step=10.0,
        )
        settling_time_s = st.number_input(
            "Settling time (s)",
            min_value=0.0, max_value=2.0, value=0.2, step=0.05,
        )
        reacquire_time_s = st.number_input(
            "Reacquire time (s)",
            min_value=0.0, max_value=2.0, value=0.15, step=0.05,
        )
        initial_bearing_deg = st.number_input(
            "BD initial bearing (deg)",
            min_value=-180.0, max_value=180.0, value=0.0, step=5.0,
            help="0° = +x axis. Set to your scenario's threat axis.",
        )

    # 3. New: Detection.
    with st.sidebar.expander("Detection", expanded=False):
        st.caption(
            "Drones outside this range start the simulation as "
            "WAITING and only become DETECTED when their range first "
            "crosses below this threshold."
        )
        R_detect_max_km = st.number_input(
            "Max detection range (km)",
            min_value=0.5, max_value=20.0, value=3.0, step=0.5,
        )

    # 4. New: Engagement strategy + timestep.
    with st.sidebar.expander("Engagement strategy", expanded=True):
        strategy = st.selectbox(
            "Target-selection strategy",
            options=list(_STRATEGY_LABELS.keys()),
            format_func=lambda k: _STRATEGY_LABELS[k],
            index=0,
            help="\n\n".join(
                f"**{label}**: {_STRATEGY_HELP[key]}"
                for key, label in _STRATEGY_LABELS.items()
            ),
        )
        dt_s = st.selectbox(
            "Simulation timestep",
            options=list(_DT_LABELS.keys()),
            format_func=lambda v: _DT_LABELS[v],
            index=0,
        )

    # ── Compose into a single dict the page entry can consume ──
    return {
        "hel_inputs": hel_inputs,
        "bd_kinematics": BDKinematics(
            max_slew_rate_dps=max_slew_rate_dps,
            max_slew_accel_dps2=max_slew_accel_dps2,
            settling_time_s=settling_time_s,
            reacquire_time_s=reacquire_time_s,
            initial_bearing_deg=initial_bearing_deg,
        ),
        "R_min_m": float(hel_inputs.get("R_min", 100.0)),
        "R_detect_max_m": R_detect_max_km * 1000.0,
        "strategy": strategy,
        "dt_s": dt_s,
    }


# ---------------------------------------------------------------------------
# Drone-list session-state helpers
# ---------------------------------------------------------------------------

def _ensure_drone_state() -> None:
    """Initialize the session-state keys on first render."""
    if _SWARM_DRONES_KEY not in st.session_state:
        st.session_state[_SWARM_DRONES_KEY] = []
    if _SWARM_NEXT_ID_KEY not in st.session_state:
        st.session_state[_SWARM_NEXT_ID_KEY] = 0
    if _SWARM_ACTIVE_TYPE_KEY not in st.session_state:
        st.session_state[_SWARM_ACTIVE_TYPE_KEY] = "commercial_quad"
    if _SWARM_SELECTED_KEY not in st.session_state:
        st.session_state[_SWARM_SELECTED_KEY] = None


def _add_drone(
    type_key: str = "commercial_quad",
    position_m: tuple[float, float] = (1500.0, 0.0),
    velocity_mps: tuple[float, float] | None = None,
) -> None:
    """Append a new drone to the session-state list."""
    _ensure_drone_state()
    drone_type = get_drone_type(type_key)
    if velocity_mps is None:
        # Default: head-on toward BD at the preset's default speed.
        x, y = position_m
        r = math.sqrt(x * x + y * y)
        if r > 0:
            speed = drone_type.speed_mps_default
            velocity_mps = (-speed * x / r, -speed * y / r)
        else:
            velocity_mps = (-drone_type.speed_mps_default, 0.0)
    drone_id = st.session_state[_SWARM_NEXT_ID_KEY]
    st.session_state[_SWARM_NEXT_ID_KEY] = drone_id + 1
    st.session_state[_SWARM_DRONES_KEY].append({
        "drone_id": drone_id,
        "drone_type_key": type_key,
        "position_x_m": float(position_m[0]),
        "position_y_m": float(position_m[1]),
        "velocity_x_mps": float(velocity_mps[0]),
        "velocity_y_mps": float(velocity_mps[1]),
    })


def _clear_drones() -> None:
    """Remove every drone in the session-state list and clear the
    current selection (so the edit panel doesn't dangle)."""
    st.session_state[_SWARM_DRONES_KEY] = []
    st.session_state[_SWARM_NEXT_ID_KEY] = 0
    st.session_state[_SWARM_SELECTED_KEY] = None


def _delete_drone(drone_id: int) -> None:
    """Remove the drone with the given drone_id from the list. Clears
    the selection if it pointed to the deleted drone."""
    drones = st.session_state.get(_SWARM_DRONES_KEY, [])
    st.session_state[_SWARM_DRONES_KEY] = [
        d for d in drones if d["drone_id"] != drone_id
    ]
    if st.session_state.get(_SWARM_SELECTED_KEY) == drone_id:
        st.session_state[_SWARM_SELECTED_KEY] = None


def _ensure_selection_valid() -> None:
    """If the current selection points to a drone that no longer
    exists (e.g., deleted via the table editor), clear it."""
    selected = st.session_state.get(_SWARM_SELECTED_KEY)
    if selected is None:
        return
    drones = st.session_state.get(_SWARM_DRONES_KEY, [])
    valid_ids = {d["drone_id"] for d in drones}
    if selected not in valid_ids:
        st.session_state[_SWARM_SELECTED_KEY] = None


def _drone_velocity_toward_bd(
    type_key: str, position_m: tuple[float, float],
) -> tuple[float, float]:
    """Compute the default velocity vector for a drone of the given
    type at the given position — heading directly at the BD (origin)
    at the type's preset speed. Returns (vx, vy) in m/s."""
    drone_type = get_drone_type(type_key)
    x, y = position_m
    r = math.sqrt(x * x + y * y)
    if r > 0:
        speed = drone_type.speed_mps_default
        return (-speed * x / r, -speed * y / r)
    return (-drone_type.speed_mps_default, 0.0)


def _quick_action_arc(
    n: int,
    arc_deg: float,
    range_m: float,
    type_key: str,
) -> None:
    """Place ``n`` drones equally spaced over ``arc_deg`` at ``range_m``,
    each heading directly at the BD."""
    _clear_drones()
    if n < 1:
        return
    half = arc_deg / 2.0
    for i in range(n):
        if n == 1:
            angle_deg = 0.0
        else:
            angle_deg = -half + arc_deg * i / (n - 1)
        angle_rad = math.radians(angle_deg)
        x = range_m * math.cos(angle_rad)
        y = range_m * math.sin(angle_rad)
        _add_drone(type_key, (x, y))


def _quick_action_mixed_speed() -> None:
    """5 fast Group-1 kamikaze + 5 slow commercial quads."""
    _clear_drones()
    for i in range(5):
        angle = -30.0 + 15.0 * i
        rad = math.radians(angle)
        _add_drone("group1_kamikaze", (1500.0 * math.cos(rad), 1500.0 * math.sin(rad)))
    for i in range(5):
        angle = -45.0 + 22.5 * i
        rad = math.radians(angle)
        _add_drone("commercial_quad", (1200.0 * math.cos(rad), 1200.0 * math.sin(rad)))


# ---------------------------------------------------------------------------
# Scenario builder — main panel (visual click-to-place + Advanced table)
# ---------------------------------------------------------------------------

def _render_scenario_map(R_detect_max_m: float, R_min_m: float) -> None:
    """Build and render the BD-centered scenario map. Captures
    Plotly click events via ``st.plotly_chart(... on_select="rerun")``
    and dispatches them: snap-grid clicks add a new drone of the
    active type; drone clicks select that drone for the edit panel.

    Trace order (locked, must match the ``_TRACE_*`` constants):
      0. R_min circle (red dashed)
      1. R_detect circle (gray dotted)
      2. Major + minor grid lines (single trace, faint)
      3. BD square at origin
      4. Invisible snap-grid (200 m spacing) — click target
      5. Drones (single trace; ``point_number`` = drones-list index)
    """
    drones = st.session_state[_SWARM_DRONES_KEY]
    selected_id = st.session_state.get(_SWARM_SELECTED_KEY)

    extent_m = R_detect_max_m * 1.1

    fig = go.Figure()

    # Trace 0: R_min circle.
    n_circle = 64
    r_min_x = [R_min_m * math.cos(2 * math.pi * i / n_circle) for i in range(n_circle + 1)]
    r_min_y = [R_min_m * math.sin(2 * math.pi * i / n_circle) for i in range(n_circle + 1)]
    fig.add_trace(go.Scatter(
        x=r_min_x, y=r_min_y, mode="lines",
        line=dict(color="rgba(229, 80, 86, 0.7)", width=1.5, dash="dash"),
        name=f"R_min = {R_min_m:.0f} m",
        hoverinfo="skip",
    ))

    # Trace 1: R_detect circle.
    r_det_x = [R_detect_max_m * math.cos(2 * math.pi * i / n_circle) for i in range(n_circle + 1)]
    r_det_y = [R_detect_max_m * math.sin(2 * math.pi * i / n_circle) for i in range(n_circle + 1)]
    fig.add_trace(go.Scatter(
        x=r_det_x, y=r_det_y, mode="lines",
        line=dict(color="rgba(127, 142, 156, 0.5)", width=1, dash="dot"),
        name=f"R_detect = {R_detect_max_m / 1000.0:.1f} km",
        hoverinfo="skip",
    ))

    # Trace 2: minor grid lines (every 200 m, very faint). Built as
    # a single trace with NaN separators between line segments — one
    # GPU draw, very cheap.
    grid_x: list[float | None] = []
    grid_y: list[float | None] = []
    grid_step_m = 200.0
    n_steps = int(extent_m / grid_step_m)
    for i in range(-n_steps, n_steps + 1):
        v = i * grid_step_m
        # Vertical line at x = v
        grid_x.extend([v, v, None])
        grid_y.extend([-extent_m, extent_m, None])
        # Horizontal line at y = v
        grid_x.extend([-extent_m, extent_m, None])
        grid_y.extend([v, v, None])
    fig.add_trace(go.Scatter(
        x=grid_x, y=grid_y, mode="lines",
        line=dict(color="rgba(127, 142, 156, 0.08)", width=0.5),
        hoverinfo="skip", showlegend=False,
        name="_grid_lines",
    ))

    # Trace 3: BD marker at origin.
    fig.add_trace(go.Scatter(
        x=[0.0], y=[0.0], mode="markers+text",
        marker=dict(symbol="square", size=16, color="white",
                    line=dict(color="black", width=1)),
        text=["BD"],
        textposition="bottom center",
        textfont=dict(size=11, color="white"),
        name="Beam director",
        hoverinfo="skip",
    ))

    # Trace 4: invisible snap-grid (clicks register here when the
    # operator clicks empty space).
    snap_xs: list[float] = []
    snap_ys: list[float] = []
    snap_grid_step_m = 200.0
    snap_n = int(extent_m / snap_grid_step_m)
    for ix in range(-snap_n, snap_n + 1):
        for iy in range(-snap_n, snap_n + 1):
            snap_xs.append(ix * snap_grid_step_m)
            snap_ys.append(iy * snap_grid_step_m)
    # Snap-grid markers: SMALLER than drone markers (10 vs 18) so
    # that clicks at a drone's location resolve to the drone trace,
    # not the snap-grid underneath. (Plotly's click hit-test uses
    # marker pixel size; the larger marker wins for overlapping
    # points regardless of trace z-order. Original v1 used size=20
    # invisible markers which captured drone clicks as snap-grid
    # clicks — bug user reported 2026-04-29.) Faint colour so the
    # user gets a visual cue of where the snap targets are.
    fig.add_trace(go.Scatter(
        x=snap_xs, y=snap_ys, mode="markers",
        marker=dict(size=10, color="rgba(127,142,156,0.15)"),
        hoverinfo="skip",
        showlegend=False,
        name="_snap_grid",
    ))

    # Trace 5: drones (colored dots).
    if drones:
        drone_xs = [d["position_x_m"] for d in drones]
        drone_ys = [d["position_y_m"] for d in drones]
        drone_colors = [
            get_drone_type(d["drone_type_key"]).color_hex for d in drones
        ]
        # Selected drone gets a thick outline ring; others get a
        # thin black border for definition.
        line_widths = [
            3 if d["drone_id"] == selected_id else 1
            for d in drones
        ]
        line_colors = [
            "white" if d["drone_id"] == selected_id else "black"
            for d in drones
        ]
        hover_texts = [
            f"#{d['drone_id']} {get_drone_type(d['drone_type_key']).label}"
            f"<br>({d['position_x_m']:.0f}, {d['position_y_m']:.0f}) m"
            f"<br>v = ({d['velocity_x_mps']:+.1f}, {d['velocity_y_mps']:+.1f}) m/s"
            for d in drones
        ]
        fig.add_trace(go.Scatter(
            x=drone_xs, y=drone_ys, mode="markers",
            marker=dict(
                # 18 px — bigger than snap-grid (10 px) so drone
                # clicks always win the hit-test when a drone sits
                # on a snap-grid point.
                size=18, color=drone_colors,
                line=dict(color=line_colors, width=line_widths),
            ),
            text=hover_texts,
            hovertemplate="%{text}<extra></extra>",
            showlegend=False,
            name="_drones",
        ))
    else:
        # Empty trace placeholder so trace_idx for drones stays
        # at _TRACE_DRONES = 5 even before any drone is placed.
        fig.add_trace(go.Scatter(
            x=[], y=[], mode="markers",
            marker=dict(size=18),
            showlegend=False,
            name="_drones",
        ))

    # Velocity arrows as per-drone annotations.
    arrow_scale = extent_m * 0.06  # ~6% of map extent — readable
    for d in drones:
        vx, vy = d["velocity_x_mps"], d["velocity_y_mps"]
        v_mag = math.sqrt(vx * vx + vy * vy)
        if v_mag <= 0:
            continue
        arrow_dx = vx / v_mag * arrow_scale
        arrow_dy = vy / v_mag * arrow_scale
        fig.add_annotation(
            x=d["position_x_m"] + arrow_dx,
            y=d["position_y_m"] + arrow_dy,
            ax=d["position_x_m"],
            ay=d["position_y_m"],
            xref="x", yref="y",
            axref="x", ayref="y",
            showarrow=True,
            arrowhead=2,
            arrowsize=1.2,
            arrowwidth=2,
            arrowcolor=get_drone_type(d["drone_type_key"]).color_hex,
        )

    fig.update_layout(
        title="Scenario map — click empty space to place drones, click a drone to edit",
        xaxis=dict(
            title="x (m, BD at origin)",
            range=[-extent_m, extent_m],
            scaleanchor="y", scaleratio=1,
            zeroline=True, zerolinecolor="rgba(127,142,156,0.3)",
        ),
        yaxis=dict(
            title="y (m)",
            range=[-extent_m, extent_m],
            zeroline=True, zerolinecolor="rgba(127,142,156,0.3)",
        ),
        height=600,
        margin=dict(l=60, r=20, t=60, b=60),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1.0,
        ),
    )

    # Render with click event capture. Streamlit 1.38 returns a
    # state-like object whose ``.selection.points`` is the list of
    # currently-selected scatter points. Each user click triggers
    # a rerun (``on_select="rerun"``); subsequent clicks at the
    # same coordinates are ignored by the de-duplication guard
    # below.
    selection = st.plotly_chart(
        fig,
        on_select="rerun",
        selection_mode="points",
        key="_swarm_map_chart",
        use_container_width=True,
        config=PLOTLY_MODEBAR_CONFIG,
    )

    # Streamlit 1.38: returns a state object whose .selection.points
    # is a list of {curve_number, point_number, x, y} dicts. Be
    # defensive about the shape (dict-like vs object-like).
    points = []
    if selection is not None:
        sel = (
            selection.get("selection")
            if isinstance(selection, dict)
            else getattr(selection, "selection", None)
        )
        if sel is not None:
            points = (
                sel.get("points", [])
                if isinstance(sel, dict)
                else getattr(sel, "points", []) or []
            )
    if points:
        # Streamlit + Plotly's selection ACCUMULATES every clicked
        # point across reruns rather than replacing on each click.
        # That means after clicking a drone (selects it) and then
        # clicking an empty cell (intended to move the drone), the
        # selection list looks like ``[drone_click, snap_click]``.
        # Reading ``points[0]`` would give us the stale drone-click
        # we already processed last render — and the move would
        # never fire. Always take ``points[-1]``: the MOST RECENT
        # click, which is what the user just did. (User report:
        # "click drone, then click empty space, drone doesn't
        # move" — this was the root cause.)
        clicked = points[-1]
        trace_idx = (
            clicked.get("curve_number")
            if isinstance(clicked, dict)
            else getattr(clicked, "curve_number", None)
        )
        cx = clicked.get("x") if isinstance(clicked, dict) else getattr(clicked, "x", None)
        cy = clicked.get("y") if isinstance(clicked, dict) else getattr(clicked, "y", None)
        pt_idx = (
            clicked.get("point_number")
            if isinstance(clicked, dict)
            else getattr(clicked, "point_number", None)
        )
        # Click-de-duplication: Streamlit preserves the chart's
        # selection state across reruns, so without this guard the
        # same click would be re-processed forever (creating drones
        # endlessly or looping the page in "Running…"). We hash the
        # click into a signature and only act when the signature is
        # NEW relative to the last processed click.
        click_sig = (trace_idx, round(float(cx or 0.0), 1),
                     round(float(cy or 0.0), 1), pt_idx)
        if click_sig == st.session_state.get(_SWARM_LAST_CLICK_KEY):
            # Already-processed click — ignore. Don't rerun.
            pass
        elif trace_idx == _TRACE_SNAP_GRID and cx is not None and cy is not None:
            st.session_state[_SWARM_LAST_CLICK_KEY] = click_sig
            selected_id = st.session_state.get(_SWARM_SELECTED_KEY)
            drones_list = st.session_state[_SWARM_DRONES_KEY]
            if selected_id is not None and any(
                d["drone_id"] == selected_id for d in drones_list
            ):
                # A drone is currently selected and the user clicked
                # empty space → MOVE the selected drone to the
                # snapped coordinates (click-to-grab, click-to-drop;
                # closest UX we get to drag-and-drop without a 3rd-
                # party component). The drone keeps its TYPE; its
                # velocity is recomputed to head toward the BD from
                # the new position at its current speed.
                for d in drones_list:
                    if d["drone_id"] == selected_id:
                        old_speed = math.sqrt(
                            d["velocity_x_mps"] ** 2
                            + d["velocity_y_mps"] ** 2
                        )
                        new_pos = (float(cx), float(cy))
                        d["position_x_m"] = new_pos[0]
                        d["position_y_m"] = new_pos[1]
                        # Re-aim toward BD at the previous speed. If
                        # the drone was stationary, leave it stationary.
                        if old_speed > 0:
                            r = math.sqrt(new_pos[0] ** 2 + new_pos[1] ** 2)
                            if r > 0:
                                d["velocity_x_mps"] = -old_speed * new_pos[0] / r
                                d["velocity_y_mps"] = -old_speed * new_pos[1] / r
                        break
            else:
                # No selection → click adds a new drone of the
                # active dropdown type.
                active_type = st.session_state.get(
                    _SWARM_ACTIVE_TYPE_KEY, "commercial_quad",
                )
                _add_drone(active_type, (float(cx), float(cy)))
            st.rerun()
        elif trace_idx == _TRACE_DRONES and pt_idx is not None:
            st.session_state[_SWARM_LAST_CLICK_KEY] = click_sig
            drones_list = st.session_state[_SWARM_DRONES_KEY]
            if 0 <= pt_idx < len(drones_list):
                st.session_state[_SWARM_SELECTED_KEY] = (
                    drones_list[pt_idx]["drone_id"]
                )
                st.rerun()


def _render_edit_panel() -> None:
    """Show the inline drone-edit panel below the map when a drone
    is selected. Covers per-drone speed, heading mode (toward BD vs
    custom angle), delete, and deselect."""
    selected_id = st.session_state.get(_SWARM_SELECTED_KEY)
    if selected_id is None:
        return
    drones = st.session_state[_SWARM_DRONES_KEY]
    drone = next((d for d in drones if d["drone_id"] == selected_id), None)
    if drone is None:
        # Stale selection (drone deleted via another path) → clear.
        st.session_state[_SWARM_SELECTED_KEY] = None
        return

    drone_type = get_drone_type(drone["drone_type_key"])
    pos = (drone["position_x_m"], drone["position_y_m"])
    vel = (drone["velocity_x_mps"], drone["velocity_y_mps"])
    rng = range_to_bd_m(pos)
    bearing = bearing_to_drone_deg(pos)
    speed_now = math.sqrt(vel[0] ** 2 + vel[1] ** 2)
    # Current heading angle (degrees). atan2(vy, vx) → -180..180.
    heading_now_deg = math.degrees(math.atan2(vel[1], vel[0])) if speed_now > 0 else 0.0
    # Is the current heading approximately "toward BD"? Toward-BD
    # vector from drone position is (-pos)/|pos|. Compare angle.
    if rng > 0 and speed_now > 0:
        toward_bd_deg = math.degrees(math.atan2(-pos[1], -pos[0]))
        # Normalize delta to [-180, 180] and take absolute.
        delta = ((heading_now_deg - toward_bd_deg + 540.0) % 360.0) - 180.0
        is_toward_bd = abs(delta) < 1.0  # within 1° of toward-BD
    else:
        is_toward_bd = True

    st.markdown("---")
    st.markdown(
        f"**Selected: Drone #{selected_id} — {drone_type.label}**  "
        f"  ·  At ({pos[0]:.0f}, {pos[1]:.0f}) m  =  "
        f"{rng / 1000.0:.2f} km @ {bearing:+.1f}°"
    )
    edit_col1, edit_col2 = st.columns([3, 2])
    with edit_col1:
        speed_low, speed_high = drone_type.speed_envelope_mps
        # Allow slider down to 0 for the stationary edge case, up to
        # 1.5× the type envelope so unusual scenarios still fit.
        slider_min = 0.0
        slider_max = max(speed_high * 1.5, speed_now * 1.2, 100.0)
        new_speed = st.slider(
            "Speed (m/s)",
            min_value=slider_min,
            max_value=float(round(slider_max, 0)),
            value=float(speed_now),
            step=1.0,
            key=f"_swarm_speed_slider_{selected_id}",
            help=(
                f"Drone class envelope: {speed_low:.0f}–{speed_high:.0f} m/s. "
                "Slider extends past the envelope for unusual scenarios."
            ),
        )
        heading_mode = st.radio(
            "Heading",
            options=["Toward BD", "Custom angle"],
            index=(0 if is_toward_bd else 1),
            key=f"_swarm_heading_mode_{selected_id}",
            horizontal=True,
        )
        if heading_mode == "Custom angle":
            new_heading_deg = st.slider(
                "Heading angle (deg)",
                min_value=-180.0, max_value=180.0,
                value=float(heading_now_deg),
                step=5.0,
                key=f"_swarm_heading_slider_{selected_id}",
                help=(
                    "0° = +x axis, 90° = +y axis. The BD is at the origin; "
                    "to make the drone head AT the BD, use 'Toward BD' mode."
                ),
            )
        else:
            # Toward BD — derive the angle from the drone's position.
            if rng > 0:
                new_heading_deg = math.degrees(math.atan2(-pos[1], -pos[0]))
            else:
                new_heading_deg = 180.0  # arbitrary; drone at origin

    with edit_col2:
        st.markdown("&nbsp;", unsafe_allow_html=True)  # spacer
        if st.button(
            "🗑 Delete drone",
            key=f"_swarm_delete_btn_{selected_id}",
            use_container_width=True,
            type="secondary",
        ):
            _delete_drone(selected_id)
            st.rerun()
        if st.button(
            "Deselect",
            key=f"_swarm_deselect_btn_{selected_id}",
            use_container_width=True,
        ):
            st.session_state[_SWARM_SELECTED_KEY] = None
            st.rerun()

    # Apply slider edits to the drone's velocity. The tolerance
    # has to absorb cos/sin/radians round-trip drift (~1e-15) AND
    # the inherent re-derivation of "Toward BD" heading from
    # position (which depends on the current floats). A 0.05 m/s
    # threshold safely catches every meaningful slider step (slider
    # min step is 1.0 m/s for speed, 5° for heading) while ignoring
    # noise. Without this guard the panel would loop `st.rerun`
    # indefinitely on every page render (the user reported this
    # 2026-04-29).
    new_heading_rad = math.radians(new_heading_deg)
    new_vx = new_speed * math.cos(new_heading_rad)
    new_vy = new_speed * math.sin(new_heading_rad)
    if (
        abs(new_vx - vel[0]) > 0.05
        or abs(new_vy - vel[1]) > 0.05
    ):
        # Mutate the dict in-place (it's the actual session-state list element).
        drone["velocity_x_mps"] = float(new_vx)
        drone["velocity_y_mps"] = float(new_vy)
        st.rerun()


def render_scenario_builder() -> list[dict]:
    """Render the visual scenario builder.

    Layout (top → bottom):
      1. Header + caption
      2. Active drone-type picker + quick-action buttons
      3. Visual map (click empty space to place; click drone to edit)
      4. Edit panel (only visible when a drone is selected)
      5. Advanced table (collapsed expander) for raw x/y/vx/vy editing

    Returns the current list of drone dicts (session-state). The
    caller composes a ``SwarmScenario`` from this + the sidebar
    output before invoking the orchestrator.
    """
    _ensure_drone_state()
    _ensure_selection_valid()

    st.markdown("### Swarm scenario")
    st.caption(
        "**Click an empty cell** to place a drone of the type selected "
        "in the dropdown (snapped to a 200 m grid; velocity defaults to "
        "head-on at the BD). **Click an existing drone** to select it "
        "(it gets a white outline) → its edit panel opens below with "
        "speed / heading / delete controls. **While a drone is selected, "
        "clicking an empty cell MOVES that drone** (click-to-grab + "
        "click-to-drop) — the closest thing to drag-and-drop without "
        "external dependencies."
    )

    # ── Active type picker + quick-action buttons ────────────────
    type_col, q1, q2, q3, q4, q5 = st.columns([2, 1, 1, 1, 1, 1])
    with type_col:
        st.session_state[_SWARM_ACTIVE_TYPE_KEY] = st.selectbox(
            "Click on the map to place:",
            options=list(DRONE_TYPES.keys()),
            format_func=lambda k: get_drone_type(k).label,
            index=list(DRONE_TYPES.keys()).index(
                st.session_state.get(_SWARM_ACTIVE_TYPE_KEY, "commercial_quad")
            ),
            key="_swarm_active_type_selector",
        )
    with q1:
        st.markdown("&nbsp;")  # vertical alignment hack
        if st.button(
            "Add quad",
            help=(
                "Add 1 commercial quad-copter at 1.5 km, head-on. "
                "Bypasses the dropdown — always adds a quad."
            ),
        ):
            _add_drone("commercial_quad", (1500.0, 0.0))
    with q2:
        st.markdown("&nbsp;")
        if st.button(
            "Add fixed-wing",
            help=(
                "Add 1 mini fixed-wing UAV at 1.5 km, head-on. "
                "Bypasses the dropdown — always adds a fixed-wing."
            ),
        ):
            _add_drone("mini_fixed_wing", (1500.0, 0.0))
    with q3:
        st.markdown("&nbsp;")
        if st.button(
            "Add kamikaze",
            help=(
                "Add 1 Group-1 kamikaze at 1.5 km, head-on. "
                "Bypasses the dropdown — always adds a kamikaze."
            ),
        ):
            _add_drone("group1_kamikaze", (1500.0, 0.0))
    with q4:
        st.markdown("&nbsp;")
        if st.button(
            "Saturation arc",
            help="12 mixed drones evenly spaced over a 90° arc at 1.5 km",
        ):
            _quick_action_arc(12, 90.0, 1500.0, "group1_kamikaze")
    with q5:
        st.markdown("&nbsp;")
        if st.button("Mixed-speed", help="5 fast kamikaze + 5 slow quads"):
            _quick_action_mixed_speed()

    # ── Map ──────────────────────────────────────────────────────
    R_detect_max_m = float(
        st.session_state.get(_SWARM_R_DETECT_KEY, 3000.0)
    )
    R_min_m = 100.0  # Caller threads this in via session-state on render
    if "_swarm_R_min_m" in st.session_state:
        R_min_m = float(st.session_state["_swarm_R_min_m"])
    _render_scenario_map(R_detect_max_m, R_min_m)

    # ── Edit panel (only renders when a drone is selected) ───────
    _render_edit_panel()

    # ── Counter + Clear All ──────────────────────────────────────
    drones = st.session_state[_SWARM_DRONES_KEY]
    counter_col, clear_col = st.columns([4, 1])
    with counter_col:
        if drones:
            st.markdown(f"**{len(drones)} drone(s) placed**")
        else:
            st.caption(
                "ℹ️ Click on the map to place your first drone, or use a "
                "preset above (Saturation arc / Mixed-speed)."
            )
    with clear_col:
        if drones and st.button(
            "Clear all", help="Remove every drone from the scenario",
        ):
            _clear_drones()
            st.rerun()

    # ── Advanced table (collapsed expander) ──────────────────────
    if drones:
        with st.expander(
            "Advanced — fine-tune drone vectors (raw x/y/vx/vy)",
            expanded=False,
        ):
            st.caption(
                "Power-user view. Edit positions and velocity components "
                "directly. Changes here sync back to the visual map."
            )
            import pandas as pd
            df = pd.DataFrame([
                {
                    "id": d["drone_id"],
                    "type": d["drone_type_key"],
                    "x_m": d["position_x_m"],
                    "y_m": d["position_y_m"],
                    "vx_m/s": d["velocity_x_mps"],
                    "vy_m/s": d["velocity_y_mps"],
                }
                for d in drones
            ])
            edited = st.data_editor(
                df,
                column_config={
                    "id": st.column_config.NumberColumn(
                        "ID", disabled=True, width="small",
                    ),
                    "type": st.column_config.SelectboxColumn(
                        "Type",
                        options=list(DRONE_TYPES.keys()),
                        required=True,
                        width="medium",
                    ),
                    "x_m": st.column_config.NumberColumn(
                        "x (m)", min_value=-50000.0, max_value=50000.0,
                        step=50.0, format="%.0f", width="small",
                    ),
                    "y_m": st.column_config.NumberColumn(
                        "y (m)", min_value=-50000.0, max_value=50000.0,
                        step=50.0, format="%.0f", width="small",
                    ),
                    "vx_m/s": st.column_config.NumberColumn(
                        "vx (m/s)", min_value=-200.0, max_value=200.0,
                        step=1.0, format="%.1f", width="small",
                    ),
                    "vy_m/s": st.column_config.NumberColumn(
                        "vy (m/s)", min_value=-200.0, max_value=200.0,
                        step=1.0, format="%.1f", width="small",
                    ),
                },
                num_rows="dynamic",
                use_container_width=True,
                key="_swarm_drone_editor",
            )
            # Sync edited DataFrame back to session-state.
            new_list: list[dict] = []
            for _, row in edited.iterrows():
                try:
                    type_key = str(row["type"])
                    if type_key not in DRONE_TYPES:
                        type_key = "commercial_quad"
                    new_list.append({
                        "drone_id": (
                            int(row["id"]) if not pd.isna(row["id"])
                            else st.session_state[_SWARM_NEXT_ID_KEY]
                        ),
                        "drone_type_key": type_key,
                        "position_x_m": float(row["x_m"]),
                        "position_y_m": float(row["y_m"]),
                        "velocity_x_mps": float(row["vx_m/s"]),
                        "velocity_y_mps": float(row["vy_m/s"]),
                    })
                except (ValueError, KeyError, TypeError):
                    continue
            next_id = st.session_state[_SWARM_NEXT_ID_KEY]
            for item in new_list:
                if item["drone_id"] >= next_id:
                    next_id = item["drone_id"] + 1
            st.session_state[_SWARM_NEXT_ID_KEY] = next_id
            st.session_state[_SWARM_DRONES_KEY] = new_list
            return new_list

    return drones


def build_scenario_from_state(
    sidebar: dict,
    drones_state: list[dict],
) -> SwarmScenario | None:
    """Combine sidebar inputs + drone-list state into a SwarmScenario.

    Returns None when the drone list is empty (caller renders an
    info banner and skips the simulation).
    """
    if not drones_state:
        return None
    drones = tuple(
        Drone(
            drone_id=int(d["drone_id"]),
            drone_type_key=d["drone_type_key"],
            position_m=(d["position_x_m"], d["position_y_m"]),
            velocity_mps=(d["velocity_x_mps"], d["velocity_y_mps"]),
        )
        for d in drones_state
    )
    return SwarmScenario(
        drones=drones,
        bd_kinematics=sidebar["bd_kinematics"],
        hel_inputs=sidebar["hel_inputs"],
        R_min_m=sidebar["R_min_m"],
        R_detect_max_m=sidebar["R_detect_max_m"],
        strategy=sidebar["strategy"],
        dt_s=sidebar["dt_s"],
    )


__all__ = [
    "render_swarm_sidebar",
    "render_scenario_builder",
    "build_scenario_from_state",
]
