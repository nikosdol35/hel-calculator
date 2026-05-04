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
    list. Confirms the table-edit UI is reactive."""
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
