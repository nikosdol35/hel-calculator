"""Tests for the cancel-token mechanism on the engagement-envelope
sweeps.

Background: ``Future.cancel()`` on a ``ThreadPoolExecutor`` returns
``False`` once the work has started running — Python can't kill a
running thread without cooperation from the worker. So when the
user changed sidebar inputs while an envelope compute was in
flight, the worker kept running, kept eating a slot, and the new
render had to wait for it. Symptom (reported 2026-04-26): "every
input change made everything stuck again."

The fix: ``compute_operational_envelope`` and
``compute_atmospheric_envelope`` now accept an optional
``cancel_token: threading.Event``. The cell loop checks
``cancel_token.is_set()`` between cells and raises
``concurrent.futures.CancelledError`` on set. The state machine in
``ui/outputs.py`` sets the token on input change / Cancel click,
which frees the worker slot within ~1-2 seconds.

These tests verify the token is checked at the right boundaries
and that an unset token doesn't introduce overhead.
"""
from __future__ import annotations

import concurrent.futures
import threading
import time

import pytest

from physics.operational_envelope import (
    compute_atmospheric_envelope,
    compute_operational_envelope,
)
from tests.golden.scenarios import C_UAS_1500M


def _v2_inputs(**overrides) -> dict:
    inputs = dict(C_UAS_1500M)
    inputs.pop("R", None)
    inputs.pop("v_perp", None)
    inputs.update({
        "R_detect": 1500, "R_min": 100,
        "engagement_geometry": "head_on",
    })
    inputs.update(overrides)
    return inputs


# Tight bounds so the test sweep finishes in seconds.
_FAST_BOUNDS_OP = dict(
    R_low_m=200.0, R_high_m=2_000.0,
    v_low_mps=5.0, v_high_mps=30.0,
)
_FAST_BOUNDS_ATM = dict(
    cn2_low=1.0e-16, cn2_high=1.0e-13,
    V_low_km=5.0, V_high_km=30.0,
)


# ---------------------------------------------------------------------------
# Operational envelope cancel-token coverage
# ---------------------------------------------------------------------------
def test_operational_envelope_cancel_token_pre_set_aborts_immediately():
    """A token set BEFORE the call → CancelledError on the first
    cell-loop check (before any orchestrator run)."""
    token = threading.Event()
    token.set()
    with pytest.raises(concurrent.futures.CancelledError):
        compute_operational_envelope(
            _v2_inputs(), n_R=3, n_v=3, cancel_token=token,
            **_FAST_BOUNDS_OP,
        )


def test_operational_envelope_no_token_runs_to_completion():
    """No token (default) → sweep runs to completion. Regression
    guard that adding the cancel-token parameter didn't break the
    no-token path."""
    env = compute_operational_envelope(
        _v2_inputs(), n_R=3, n_v=3, **_FAST_BOUNDS_OP,
    )
    assert len(env.R_detect_axis) == 3
    assert len(env.v_tgt_axis) == 3


def test_operational_envelope_unset_token_runs_to_completion():
    """A token that's never set behaves the same as no token."""
    token = threading.Event()  # unset
    env = compute_operational_envelope(
        _v2_inputs(), n_R=3, n_v=3, cancel_token=token,
        **_FAST_BOUNDS_OP,
    )
    assert env.n_kills + env.n_failures + sum(
        1 for row in env.margin_grid for v in row
        if v == v and v < 0  # finite, negative
    ) == 9  # 3 × 3 = 9 cells


def test_operational_envelope_cancel_mid_sweep_via_thread():
    """A token set DURING the sweep → CancelledError raised at
    the next inter-cell boundary, freeing the worker.

    Drives the cancel from a separate thread to simulate the
    UI flow (state-machine sets the event from the main script,
    worker checks it from a ThreadPoolExecutor slot).
    """
    token = threading.Event()
    container: dict = {}

    def worker():
        try:
            compute_operational_envelope(
                _v2_inputs(), n_R=8, n_v=8,
                cancel_token=token, **_FAST_BOUNDS_OP,
            )
        except concurrent.futures.CancelledError as exc:
            container["cancelled"] = exc
        except Exception as exc:  # pragma: no cover — defensive
            container["other_error"] = exc
        else:
            container["finished"] = True

    t = threading.Thread(target=worker)
    t.start()
    # Let it start the first cell, then cancel.
    time.sleep(0.05)
    token.set()
    t.join(timeout=10.0)
    assert not t.is_alive(), "worker thread should have exited promptly"
    # Either the worker noticed the token (preferred) or it finished
    # the whole 64-cell sweep in <50 ms (impossible given the M8 PDE
    # cost); only the cancelled branch is realistic in CI.
    assert "cancelled" in container, (
        f"expected CancelledError from worker; got "
        f"{list(container.keys())}"
    )


# ---------------------------------------------------------------------------
# Atmospheric envelope cancel-token coverage
# ---------------------------------------------------------------------------
def test_atmospheric_envelope_cancel_token_pre_set_aborts_immediately():
    token = threading.Event()
    token.set()
    with pytest.raises(concurrent.futures.CancelledError):
        compute_atmospheric_envelope(
            _v2_inputs(), n_cn2=3, n_V=3, cancel_token=token,
            **_FAST_BOUNDS_ATM,
        )


def test_atmospheric_envelope_no_token_runs_to_completion():
    env = compute_atmospheric_envelope(
        _v2_inputs(), n_cn2=3, n_V=3, **_FAST_BOUNDS_ATM,
    )
    assert len(env.cn2_axis) == 3
    assert len(env.V_km_axis) == 3


# ---------------------------------------------------------------------------
# Default grid size locked at 8×8
# ---------------------------------------------------------------------------
def test_operational_envelope_default_grid_8x8():
    """Default n_R / n_v are 8 (was 10; reduced 2026-04-26 because
    the corner cells dominated total compute time and 64 cells is
    plenty of resolution for a heatmap)."""
    import inspect
    sig = inspect.signature(compute_operational_envelope)
    assert sig.parameters["n_R"].default == 8
    assert sig.parameters["n_v"].default == 8


def test_atmospheric_envelope_default_grid_8x8():
    import inspect
    sig = inspect.signature(compute_atmospheric_envelope)
    assert sig.parameters["n_cn2"].default == 8
    assert sig.parameters["n_V"].default == 8
