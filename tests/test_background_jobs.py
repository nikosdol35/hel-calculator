"""Tests for ui/background_jobs.py — the ThreadPoolExecutor singleton
backing the engagement-envelope background-compute pattern.

Coverage:
  - get_bg_executor returns the same instance across calls (singleton)
  - submit_compute returns a Future that resolves to the function's
    return value
  - submit_compute survives concurrent submits (the executor handles
    its own queue)
  - shutdown_bg_executor releases the singleton; the next get_bg_executor
    constructs a fresh one (lifecycle hook for tests)
  - Fragment + worker race: submitting a job, polling Future.done(),
    and reading Future.result() when done — the rendering state machine
    relies on this contract working without raising.
"""
from __future__ import annotations

import time
import concurrent.futures

import pytest

from ui.background_jobs import (
    get_bg_executor,
    submit_compute,
    shutdown_bg_executor,
)


@pytest.fixture(autouse=True)
def _reset_executor():
    """Reset the singleton between tests so they're independent."""
    shutdown_bg_executor()
    yield
    shutdown_bg_executor()


def test_get_bg_executor_singleton():
    """Two calls return the same executor instance."""
    e1 = get_bg_executor()
    e2 = get_bg_executor()
    assert e1 is e2


def test_get_bg_executor_returns_thread_pool():
    e = get_bg_executor()
    assert isinstance(e, concurrent.futures.ThreadPoolExecutor)


def test_submit_compute_returns_future():
    fut = submit_compute(lambda: 42)
    assert isinstance(fut, concurrent.futures.Future)
    assert fut.result(timeout=5) == 42


def test_submit_compute_passes_args():
    fut = submit_compute(lambda a, b: a + b, 2, 3)
    assert fut.result(timeout=5) == 5


def test_submit_compute_passes_kwargs():
    fut = submit_compute(lambda a, b: a * b, a=4, b=5)
    assert fut.result(timeout=5) == 20


def test_submit_compute_runs_in_background():
    """The submit returns immediately (before the function finishes).
    Without a background executor, this would block for 0.5 s.
    """
    def slow():
        time.sleep(0.5)
        return "done"

    t0 = time.monotonic()
    fut = submit_compute(slow)
    submit_dt = time.monotonic() - t0
    assert submit_dt < 0.1, (
        f"submit should return in <100 ms, got {submit_dt*1000:.0f} ms"
    )
    assert fut.result(timeout=2) == "done"


def test_submit_compute_two_jobs_run_concurrently():
    """The executor has 2 workers — two slow jobs should overlap, so
    total wall-clock time is roughly max(job_a, job_b), not sum.
    """
    def slow():
        time.sleep(0.5)
        return "ok"

    t0 = time.monotonic()
    f1 = submit_compute(slow)
    f2 = submit_compute(slow)
    f1.result(timeout=2)
    f2.result(timeout=2)
    elapsed = time.monotonic() - t0
    # Both finish in ~0.5 s, not 1.0 s — proving they ran in parallel.
    # Generous tolerance for CI noise.
    assert elapsed < 0.9, (
        f"two parallel 0.5 s jobs took {elapsed:.2f} s — should be <0.9"
    )


def test_submit_compute_propagates_exceptions():
    fut = submit_compute(lambda: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        fut.result(timeout=5)


def test_future_done_state_progresses():
    """Future.done() is False before completion, True after — this is
    the contract the fragment state machine polls on."""
    def slow():
        time.sleep(0.3)
        return 99

    fut = submit_compute(slow)
    assert not fut.done()
    fut.result(timeout=2)
    assert fut.done()


def test_shutdown_releases_singleton():
    e1 = get_bg_executor()
    shutdown_bg_executor()
    e2 = get_bg_executor()
    assert e1 is not e2
