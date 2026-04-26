"""Background-job helpers for long-running compute on the HEL tab.

The two engagement-envelope sweeps (operational + atmospheric) each
run ~100 orchestrator calls per click, totalling several minutes in
the worst case. Synchronously calling them from the Streamlit script
locks the UI for the duration: the entire app — every tab, every
plot, every widget — becomes unresponsive until the cache call
returns.

The fix: run the compute in a ``ThreadPoolExecutor`` worker, store
the resulting ``Future`` in ``st.session_state``, and let an
``@st.fragment(run_every=...)`` poller swap the placeholder for the
plots when the future completes. The rest of the page renders
normally on every script run; only the envelope section re-renders
on the polling cadence.

Pure helper module — has no Streamlit imports beyond the public
``streamlit`` package; the renderer in ``ui.outputs`` does the
fragment + state-machine work and only calls into here for the
process-level executor singleton.
"""
from __future__ import annotations

import concurrent.futures
import threading

# Module-level singleton executor. ThreadPoolExecutor is correct
# (not ProcessPool) because:
#   - Each compute call is a single thread of work; no GIL contention.
#   - Threads share memory with the main script — no pickling cost
#     for the (large) base_inputs dict on submit, no return-value
#     pickling on completion.
#   - Streamlit Cloud handles threads natively; processes would need
#     a multiprocessing.Manager for state visibility.
_BG_EXECUTOR_LOCK = threading.Lock()
_BG_EXECUTOR: concurrent.futures.ThreadPoolExecutor | None = None

# Two workers covers the two envelope sweeps running in parallel
# (operational + atmospheric). A user could theoretically hit Compute
# on both at the same time; both jobs run concurrently against
# different worker threads.
_MAX_WORKERS = 2


def get_bg_executor() -> concurrent.futures.ThreadPoolExecutor:
    """Process-level singleton ``ThreadPoolExecutor`` for background
    envelope computes. Lazily constructed on first access; the lock
    guards against the two-thread race when fragment polling and the
    main script run interleave on cold start."""
    global _BG_EXECUTOR
    with _BG_EXECUTOR_LOCK:
        if _BG_EXECUTOR is None:
            _BG_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
                max_workers=_MAX_WORKERS,
                thread_name_prefix="hel-envelope-bg",
            )
    return _BG_EXECUTOR


def submit_compute(callable_, *args, **kwargs) -> concurrent.futures.Future:
    """Submit a compute job to the background executor.

    The returned ``Future`` is what the renderer stores in
    ``st.session_state``. ``Future.done()`` is checked on every
    fragment-poll tick; ``Future.result()`` is read once it's done.
    """
    return get_bg_executor().submit(callable_, *args, **kwargs)


def shutdown_bg_executor() -> None:
    """Test-helper / lifecycle hook to release the executor.

    Streamlit Cloud will tear down the process on idle; this is for
    test isolation only. Production code never calls this.
    """
    global _BG_EXECUTOR
    with _BG_EXECUTOR_LOCK:
        if _BG_EXECUTOR is not None:
            _BG_EXECUTOR.shutdown(wait=False, cancel_futures=True)
            _BG_EXECUTOR = None


__all__ = [
    "get_bg_executor",
    "submit_compute",
    "shutdown_bg_executor",
]
