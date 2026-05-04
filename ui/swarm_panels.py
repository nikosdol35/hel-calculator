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
the drone-list table-edit UI. Day-4 v1 ships table-only; the
click-on-map builder lands in Day 5 alongside the playback plot.

Pure UI glue — no physics; relies on ``physics/swarm_scenario.py``
for validation.
"""
from __future__ import annotations

import math

import streamlit as st

from physics.swarm_drone_types import DRONE_TYPES, get_drone_type
from physics.swarm_scenario import BDKinematics, Drone, SwarmScenario
from ui import panels


# Session-state keys (scoped with ``_swarm_`` prefix per plan §4.4 to
# avoid stomping HEL Calculator's session-state).
_SWARM_DRONES_KEY = "_swarm_drones"          # list[dict] of drone rows
_SWARM_NEXT_ID_KEY = "_swarm_next_drone_id"  # monotonic id counter


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
    """Remove every drone in the session-state list."""
    st.session_state[_SWARM_DRONES_KEY] = []
    st.session_state[_SWARM_NEXT_ID_KEY] = 0


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
# Scenario builder — main panel
# ---------------------------------------------------------------------------

def render_scenario_builder() -> list[dict]:
    """Render the drone-list table-edit UI in the main panel.

    Returns the current list of drone dicts (session-state). The
    caller composes a ``SwarmScenario`` from this + the sidebar
    output before invoking the orchestrator.

    Day-4 v1: table-only edit. Click-on-map adds in Day 5.
    """
    _ensure_drone_state()

    st.markdown("### Swarm scenario")
    st.caption(
        "Build a multi-drone scenario. The beam director sits at the "
        "origin. Drones are placed in a 2D top-down plane around it; "
        "each row below describes one drone's starting position, "
        "velocity, and class."
    )

    # ── Quick-action buttons ─────────────────────────────────────
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        if st.button("Add quad", help="Add one commercial quad-copter at 1.5 km, head-on"):
            _add_drone("commercial_quad", (1500.0, 0.0))
    with col2:
        if st.button("Add fixed-wing", help="Add one mini fixed-wing UAV at 1.5 km, head-on"):
            _add_drone("mini_fixed_wing", (1500.0, 0.0))
    with col3:
        if st.button("Add kamikaze", help="Add one Group-1 kamikaze at 1.5 km, head-on"):
            _add_drone("group1_kamikaze", (1500.0, 0.0))
    with col4:
        if st.button(
            "Saturation arc",
            help="12 mixed drones evenly spaced over a 90° arc at 1.5 km",
        ):
            _quick_action_arc(12, 90.0, 1500.0, "group1_kamikaze")
    with col5:
        if st.button(
            "Mixed-speed test",
            help="5 fast kamikaze + 5 slow quads at mixed ranges",
        ):
            _quick_action_mixed_speed()
    with col6:
        if st.button("Clear all", help="Remove every drone"):
            _clear_drones()

    drones = st.session_state[_SWARM_DRONES_KEY]
    if not drones:
        st.info(
            "No drones placed yet. Use the buttons above to add a "
            "preset scenario, or 'Add quad/fixed-wing/kamikaze' for a "
            "single test target."
        )
        return drones

    # ── Editable table ───────────────────────────────────────────
    st.markdown(f"**{len(drones)} drone(s) placed**")

    # Build a Pandas DataFrame for st.data_editor.
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
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "type": st.column_config.SelectboxColumn(
                "Type",
                options=list(DRONE_TYPES.keys()),
                required=True,
                width="medium",
            ),
            "x_m": st.column_config.NumberColumn(
                "x (m)", min_value=-50000.0, max_value=50000.0, step=50.0,
                format="%.0f", width="small",
            ),
            "y_m": st.column_config.NumberColumn(
                "y (m)", min_value=-50000.0, max_value=50000.0, step=50.0,
                format="%.0f", width="small",
            ),
            "vx_m/s": st.column_config.NumberColumn(
                "vx (m/s)", min_value=-200.0, max_value=200.0, step=1.0,
                format="%.1f", width="small",
            ),
            "vy_m/s": st.column_config.NumberColumn(
                "vy (m/s)", min_value=-200.0, max_value=200.0, step=1.0,
                format="%.1f", width="small",
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
                "drone_id": int(row["id"]) if not pd.isna(row["id"]) else st.session_state[_SWARM_NEXT_ID_KEY],
                "drone_type_key": type_key,
                "position_x_m": float(row["x_m"]),
                "position_y_m": float(row["y_m"]),
                "velocity_x_mps": float(row["vx_m/s"]),
                "velocity_y_mps": float(row["vy_m/s"]),
            })
        except (ValueError, KeyError, TypeError):
            continue
    # Reassign IDs if any new rows have NaN ids (st.data_editor adds
    # blank rows when num_rows="dynamic").
    next_id = st.session_state[_SWARM_NEXT_ID_KEY]
    for item in new_list:
        if item["drone_id"] >= next_id:
            next_id = item["drone_id"] + 1
    st.session_state[_SWARM_NEXT_ID_KEY] = next_id
    st.session_state[_SWARM_DRONES_KEY] = new_list
    return new_list


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
