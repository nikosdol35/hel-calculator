"""Layer 5 verification — three frozen golden scenarios.

Per the plan §5 Layer 5: each scenario's expected output dict is
locked by hash. Any drift in the orchestrator (refactor, bug, math
change) triggers a clear test failure with a diff.

The three goldens cover the headline tactical regimes:

  * **Golden A — 5-drone arc**: small swarm, all kills expected.
    Sanity check: with light power on a small commercial-quad arc,
    the BD kills everything. Pinned outcome: kills=5, leaks=0.
  * **Golden B — 10-drone saturation**: medium mixed swarm, all
    kills (lightweight-chain optimism). Demonstrates the "happy
    path" mid-difficulty case.
  * **Golden C — 12-drone stress**: large kamikaze swarm — the
    BD CANNOT kill them all, so the test PROVES the tool reports
    leaks correctly when overwhelmed. Pinned outcome: 2 leaks.

Drift in any of these → investigate. If a real physics or
performance fix changes the answer, regenerate the golden values
and re-pin in the same commit (with a dated comment).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from physics.swarm_orchestrator import run_swarm_simulation
from physics.swarm_scenario import SwarmScenario


_GOLDEN_DIR = Path(__file__).parent / "golden"


# Frozen expected outputs — captured 2026-04-29 from the canonical
# Day-3 orchestrator build. Update intentionally if a real physics
# fix changes the answer.
GOLDEN_EXPECTED = {
    "swarm_5drone_arc": {
        "n_killed": 5,
        "n_leaked": 0,
        "n_timeout": 0,
        "summary_hash": "722eaf369aec8ee8",
    },
    "swarm_10drone_sat": {
        "n_killed": 10,
        "n_leaked": 0,
        "n_timeout": 0,
        "summary_hash": "47dc0316b3dc799e",
    },
    "swarm_12drone_stress": {
        "n_killed": 10,
        "n_leaked": 2,
        "n_timeout": 0,
        "summary_hash": "75fd6a3d504f2320",
    },
}


def _load_golden(name: str) -> SwarmScenario:
    path = _GOLDEN_DIR / f"{name}.json"
    with open(path, encoding="utf-8") as fh:
        blob = fh.read()
    return SwarmScenario.from_json(blob)


@pytest.mark.parametrize("name", list(GOLDEN_EXPECTED.keys()))
def test_golden_scenario_pinned_output(name):
    """Each golden scenario must produce its frozen expected output
    dict (counts + hash). Regression test."""
    scenario = _load_golden(name)
    result = run_swarm_simulation(scenario)
    expected = GOLDEN_EXPECTED[name]

    # The headline counts are the most important regression locks.
    assert result.n_killed == expected["n_killed"], (
        f"{name}: expected {expected['n_killed']} kills, got {result.n_killed}"
    )
    assert result.n_leaked == expected["n_leaked"], (
        f"{name}: expected {expected['n_leaked']} leaks, got {result.n_leaked}"
    )
    assert result.n_timeout == expected["n_timeout"], (
        f"{name}: expected {expected['n_timeout']} timeouts, "
        f"got {result.n_timeout}"
    )
    # Summary hash catches subtler drift (a kill at a different time
    # for example).
    assert result.summary_hash == expected["summary_hash"], (
        f"{name}: summary_hash drift\n"
        f"  expected: {expected['summary_hash']}\n"
        f"  got:      {result.summary_hash}\n"
        "If this drift is intentional (a real physics fix), update "
        "GOLDEN_EXPECTED with a dated comment explaining why."
    )


def test_golden_files_exist_and_parse():
    """Each golden JSON file is valid + parses into a SwarmScenario.
    Catches schema-version drift or hand-editing mistakes."""
    for name in GOLDEN_EXPECTED:
        path = _GOLDEN_DIR / f"{name}.json"
        assert path.exists(), f"golden file missing: {path}"
        with open(path, encoding="utf-8") as fh:
            blob = fh.read()
        # Both JSON-parseable AND scenario-valid.
        data = json.loads(blob)
        assert "version" in data
        scenario = SwarmScenario.from_json(blob)
        assert len(scenario.drones) > 0


def test_golden_c_proves_leak_reporting():
    """Golden C (the stress scenario) MUST report leaks.
    This is the test that proves the tool correctly identifies
    "system overwhelmed" — without it, a leak-reporting bug could
    silently turn every scenario into "all kills"."""
    scenario = _load_golden("swarm_12drone_stress")
    result = run_swarm_simulation(scenario)
    assert result.n_leaked >= 1, (
        "Golden C must produce at least one leak — the leak-counting "
        "logic doesn't work otherwise"
    )
    assert result.first_leak_time_s is not None
    assert result.closest_leak_range_m is not None
    assert result.closest_leak_range_m <= 100.0  # R_min default


def test_round_trip_via_json():
    """Save → load → simulate via JSON → identical result. The
    golden tests rely on this; if it broke, every golden test
    becomes meaningless."""
    s_direct = _load_golden("swarm_5drone_arc")
    r_direct = run_swarm_simulation(s_direct)
    blob = s_direct.to_json()
    s_round = SwarmScenario.from_json(blob)
    r_round = run_swarm_simulation(s_round)
    assert r_direct.summary_hash == r_round.summary_hash
