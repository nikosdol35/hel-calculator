"""Swarm Analyzer page — multi-drone HEL engagement timing.

Sibling to the HEL Calculator and DRI Analyzer. Operator builds a
2D top-down swarm scenario in the main panel (drone-list editor),
sets the laser/atmosphere via the reused HEL sidebar plus a few
swarm-specific inputs (BD slew kinematics, detection range,
engagement strategy), clicks Run, and sees:

  * KPI bar — verdict (kills vs leaks), first-leak time, total time
  * Per-drone results table
  * Animated 2D playback (Day-5 polish; falls back to a static
    summary on Day-4 build)
  * Per-drone Gantt chart (Day-5)
  * Sensitivity panel (Day-6)
  * Assumptions block

Reuses the HEL physics chain (M1–M8) by import via
``physics/swarm_orchestrator.py`` — zero risk to the HEL Calculator.

Dispatched by ``ui/app.py`` via ``st.navigation``; the entry script
handles page config + theme + auth before this script ever runs.
"""
from __future__ import annotations

import time
from typing import Any

import streamlit as st

from physics.swarm_orchestrator import run_swarm_simulation
from physics.swarm_scenario import SwarmScenario
from ui import swarm_outputs, swarm_panels, theme
from ui.auth import require_login


# Auth defense in depth + theme re-apply (idempotent under normal
# flow; guards any path that reaches this page without app.py).
_APP_MODE_KEY = "_app_mode"
app_mode = st.session_state.get(_APP_MODE_KEY, "dark")
theme.apply(app_mode)
require_login()


# Session-state keys (per plan §4.4) — all prefixed ``_swarm_`` so
# they don't collide with the HEL Calculator or DRI Analyzer.
_SWARM_RESULT_KEY = "_swarm_result"
_SWARM_LAST_SCENARIO_HASH_KEY = "_swarm_last_scenario_hash"


def _scenario_hash(scenario: SwarmScenario) -> str:
    """Stable hash of the scenario for cache invalidation."""
    return scenario.to_json()


# ---------------------------------------------------------------------------
# Header + intro
# ---------------------------------------------------------------------------
st.title("Swarm Analyzer")
st.caption(
    "Simulate how a single beam director defends itself against a "
    "multi-drone swarm. Build a 2D top-down scenario; the simulation "
    "schedules engagements, accounts for slew time, and reports how "
    "many drones leak through to your minimum-engagement range."
)


# ---------------------------------------------------------------------------
# Sidebar — HEL inputs + swarm-specific (BD kinematics, detection, strategy)
# ---------------------------------------------------------------------------
sidebar_inputs = swarm_panels.render_swarm_sidebar()

# Thread R_min and R_detect_max through to the visual map renderer
# via session-state. The map needs them to draw the dashed rings;
# capturing them here keeps render_scenario_builder() agnostic of
# the sidebar's exact return-dict shape.
st.session_state["_swarm_R_min_m"] = sidebar_inputs["R_min_m"]
st.session_state["_swarm_R_detect_max_m"] = sidebar_inputs["R_detect_max_m"]


# ---------------------------------------------------------------------------
# Main panel — scenario builder
# ---------------------------------------------------------------------------
drones_state = swarm_panels.render_scenario_builder()

st.markdown("---")

# Run button — full width, primary action.
run_clicked = st.button(
    "▶ Run simulation",
    type="primary",
    use_container_width=True,
    help="Execute the swarm engagement simulation.",
    disabled=(len(drones_state) == 0),
)
if len(drones_state) == 0:
    st.caption("⚠ Build a scenario above (use the Add buttons or a quick-action) "
               "before running the simulation.")

# Save / load scenario — OPTIONAL, hidden inside an expander so it
# doesn't confuse first-time users. Only opens when you actually
# want to share or re-load a scenario.
with st.expander(
    "💾 Save / load scenario (optional — for sharing scenarios with teammates)",
    expanded=False,
):
    st.caption(
        "Most of the time you don't need this. The scenario you build "
        "above is automatically remembered while the page is open. Use "
        "this section if you want to **save** a scenario as a `.json` "
        "file (to email a teammate, archive, or pin as a benchmark) — "
        "or **load** one a teammate sent you."
    )
    col_save, col_load = st.columns(2)
    with col_save:
        st.markdown("**Save current scenario**")
        scenario_for_export = swarm_panels.build_scenario_from_state(
            sidebar_inputs, drones_state
        )
        if scenario_for_export is not None:
            st.download_button(
                label="📥 Download as JSON",
                data=scenario_for_export.to_json(),
                file_name="swarm_scenario.json",
                mime="application/json",
                use_container_width=True,
                help="Saves drones + sidebar inputs.",
            )
        else:
            st.caption("Add drones to the scenario before saving.")
    with col_load:
        st.markdown("**Load a saved scenario**")
        uploaded = st.file_uploader(
            "Drop a swarm_scenario.json file here",
            type=["json"],
            key="_swarm_upload",
            label_visibility="collapsed",
            help="Loads a previously-downloaded swarm scenario JSON file.",
        )
        if uploaded is not None:
            try:
                json_blob = uploaded.read().decode("utf-8")
                scenario_loaded = SwarmScenario.from_json(json_blob)
                # Replay the loaded scenario into session-state so the
                # table editor shows it.
                st.session_state["_swarm_drones"] = [
                    {
                        "drone_id": d.drone_id,
                        "drone_type_key": d.drone_type_key,
                        "position_x_m": d.position_m[0],
                        "position_y_m": d.position_m[1],
                        "velocity_x_mps": d.velocity_mps[0],
                        "velocity_y_mps": d.velocity_mps[1],
                    }
                    for d in scenario_loaded.drones
                ]
                st.session_state["_swarm_next_drone_id"] = (
                    max((d.drone_id for d in scenario_loaded.drones), default=-1) + 1
                )
                st.success(
                    f"Loaded {len(scenario_loaded.drones)} drone(s). "
                    f"Click **Run simulation** above to engage."
                )
                time.sleep(0.05)
                st.rerun()
            except (ValueError, KeyError) as exc:
                st.error(f"Invalid scenario JSON: {exc}")


# ---------------------------------------------------------------------------
# Run + render results
# ---------------------------------------------------------------------------
scenario = swarm_panels.build_scenario_from_state(sidebar_inputs, drones_state)

if run_clicked and scenario is not None:
    with st.spinner(f"Simulating engagement of {len(scenario.drones)} drone(s)..."):
        t0 = time.time()
        result = run_swarm_simulation(scenario)
        elapsed = time.time() - t0
    st.session_state[_SWARM_RESULT_KEY] = result
    st.session_state[_SWARM_LAST_SCENARIO_HASH_KEY] = _scenario_hash(scenario)
    st.caption(f"Simulation finished in {elapsed:.2f} s.")

# Render whatever result is in session-state — survives reruns.
result = st.session_state.get(_SWARM_RESULT_KEY)
if result is not None:
    last_hash = st.session_state.get(_SWARM_LAST_SCENARIO_HASH_KEY)
    if scenario is not None and last_hash != _scenario_hash(scenario):
        st.warning(
            "The scenario has been edited since the last run. Click "
            "**Run simulation** again to refresh the results below."
        )
    st.markdown("---")
    swarm_outputs.render_kpi_bar(result)
    swarm_outputs.render_timing_breakdown(result)

    # Plots imported lazily so the page still renders if any
    # plotting helper is missing (defense in depth).
    try:
        from ui import swarm_plots
        st.markdown("---")
        swarm_plots.render_playback_plot(result, scenario)
        st.markdown("---")
        swarm_plots.render_gantt_chart(result)
    except (ImportError, AttributeError):
        pass

    st.markdown("---")
    swarm_outputs.render_per_drone_table(result)

    # Sensitivity analysis (compute-on-click) — only when the
    # scenario hasn't drifted from the last run.
    if scenario is not None:
        try:
            from ui import swarm_plots as _sp
            st.markdown("---")
            _sp.render_sensitivity_panel(scenario, result)
        except (ImportError, AttributeError):
            pass

    st.markdown("---")
    swarm_outputs.render_assumptions_block(result)
elif scenario is None:
    st.info("Build a scenario above, then click **Run simulation**.")
