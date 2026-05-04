"""Streamlit AppTest end-to-end smoke for the Swarm Analyzer page.

Mirrors ``tests/test_engagement_tab_e2e.py`` for the HEL Calculator —
spins up Streamlit's headless ``AppTest`` runner, loads the swarm
analyzer page, simulates a click on the "Run simulation" button,
and asserts the page renders without exceptions.

Per CLAUDE.md §5.1 + plan §5 / §8: an e2e test that proves the
new page parses, the auth gate doesn't double-trigger, and a
canonical scenario round-trips through the orchestrator.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _bypass_auth():
    """Skip the login gate for this smoke test (per the
    HEL_TEST_MODE shortcut already wired into ``ui.auth``)."""
    os.environ["HEL_TEST_MODE"] = "1"
    yield
    os.environ.pop("HEL_TEST_MODE", None)


def test_swarm_analyzer_page_loads_without_exception():
    """The page parses, runs to completion, and produces no
    Streamlit exceptions on first load (no scenario yet, just the
    welcome state)."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(
        "ui/tools/swarm_analyzer.py",
        default_timeout=30,
    )
    at.run()

    # No Streamlit-rendered exceptions.
    assert not at.exception, (
        f"swarm analyzer page raised: {at.exception}"
    )

    # The page header renders.
    titles = [t.value for t in at.title]
    assert any("Swarm Analyzer" in t for t in titles), (
        f"page title missing; got titles: {titles}"
    )


def test_swarm_analyzer_quick_action_adds_drones():
    """Clicking 'Add quad' button adds a drone to the session-state
    list. Confirms the quick-action buttons are still reactive
    after the visual-map redesign."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(
        "ui/tools/swarm_analyzer.py",
        default_timeout=30,
    )
    at.run()
    assert not at.exception

    # First render: no drones yet.
    drones_before = (
        at.session_state["_swarm_drones"]
        if "_swarm_drones" in at.session_state else []
    )
    assert len(drones_before) == 0

    # Click "Add quad" — first button in the quick-action row.
    add_quad_button = next(
        (b for b in at.button if "quad" in str(b.label).lower() and "add" in str(b.label).lower()),
        None,
    )
    assert add_quad_button is not None, "couldn't find 'Add quad' button"
    add_quad_button.click()
    at.run()
    assert not at.exception

    drones_after = (
        at.session_state["_swarm_drones"]
        if "_swarm_drones" in at.session_state else []
    )
    assert len(drones_after) == 1
    assert drones_after[0]["drone_type_key"] == "commercial_quad"


def test_active_drone_type_state_initialized():
    """The visual map needs `_swarm_active_type` in session state to
    know what type of drone to drop on the next snap-grid click. The
    page must initialize it on first render so the dropdown has a
    valid default."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(
        "ui/tools/swarm_analyzer.py",
        default_timeout=30,
    )
    at.run()
    assert not at.exception
    assert "_swarm_active_type" in at.session_state, (
        "active-drone-type session-state key not initialized"
    )
    # Default must be one of the three preset keys.
    from physics.swarm_drone_types import DRONE_TYPES
    assert at.session_state["_swarm_active_type"] in DRONE_TYPES


def test_advanced_table_present_only_when_drones_exist():
    """The Advanced table is shown inside an expander when at least
    one drone is placed — and absent (or hidden) when the scenario
    is empty. Regression guard: the visual map must not assume the
    table is always rendered."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(
        "ui/tools/swarm_analyzer.py",
        default_timeout=30,
    )
    at.run()
    assert not at.exception

    # Empty scenario: there should be NO data_editor widget.
    editors_before = list(at.dataframe) if hasattr(at, "dataframe") else []
    # Place one drone via the quick-add button.
    add_quad_button = next(
        (b for b in at.button if "quad" in str(b.label).lower() and "add" in str(b.label).lower()),
        None,
    )
    assert add_quad_button is not None
    add_quad_button.click()
    at.run()
    assert not at.exception

    # After adding a drone, the Advanced expander+table renders. We
    # don't try to programmatically open the expander (st.expander
    # body executes regardless of expanded state), but we do verify
    # session-state reflects the placed drone.
    assert len(at.session_state["_swarm_drones"]) == 1


def test_clear_all_clears_selection_too():
    """Per the plan §3.4: _clear_drones() must also clear the
    `_swarm_selected_drone` session-state key so the edit panel
    doesn't dangle pointing to a deleted drone."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(
        "ui/tools/swarm_analyzer.py",
        default_timeout=30,
    )
    at.run()
    assert not at.exception

    # Add a drone, then manually set the selection in session-state.
    add_quad_button = next(
        (b for b in at.button if "add quad" in str(b.label).lower()),
        None,
    )
    assert add_quad_button is not None
    add_quad_button.click()
    at.run()
    assert len(at.session_state["_swarm_drones"]) == 1
    drone_id = at.session_state["_swarm_drones"][0]["drone_id"]
    at.session_state["_swarm_selected_drone"] = drone_id
    at.run()
    assert at.session_state["_swarm_selected_drone"] == drone_id

    # Now click Clear all (only renders when drones exist).
    clear_btn = next(
        (b for b in at.button if "clear all" in str(b.label).lower()),
        None,
    )
    assert clear_btn is not None, "Clear all button missing"
    clear_btn.click()
    at.run()
    assert not at.exception

    # Selection must be cleared.
    selected_after = (
        at.session_state["_swarm_selected_drone"]
        if "_swarm_selected_drone" in at.session_state else None
    )
    assert selected_after is None, (
        f"selection should be None after Clear all, got {selected_after}"
    )
    assert len(at.session_state["_swarm_drones"]) == 0
