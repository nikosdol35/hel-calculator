"""Streamlit entry point for the HEL Engineering Calculator.

This is the single file Streamlit Cloud launches via ``streamlit run
ui/app.py`` per ARCHITECTURE.md §6.1. Responsibilities (post-slice-4):

1. Auth gate (``ui/auth.py`` — shared-credentials login).
2. URL-parameter decode, **exactly once per session**, guarded by
   ``st.session_state['_url_decoded']`` (SPEC §5.3 item 7 / improvement
   #1). Prevents Streamlit's rerun-on-widget-change loop from
   re-applying stale URL values on top of the user's edits.
3. Render 6 input panels in the sidebar (``ui/panels.collect_all``).
4. "Run Analysis" click → ``run_chain_cached`` (``@st.cache_data``
   wrapper around ``physics.orchestrator.run_full_chain``) → merged
   result → ``ui/outputs.render_all`` + ``ui/plots.plot_a/b/c``.
5. "Share this analysis" click → encode ``user_inputs`` into
   ``st.query_params`` and render the URL in a copy-ready ``st.code``
   block per SPEC §5.3 item 7 v1.7 / improvement #3.

Three caching wrappers live here (not in ``physics/orchestrator.py``)
so the orchestrator stays pure-Python and directly unit-testable from
``tests/`` under ARCH §2 import rules. The ``_freeze`` helper
(improvement #6) converts the dict ``user_inputs`` to a tuple so
``@st.cache_data`` can hash it.

References:
    ARCHITECTURE.md §5.1 (data flow), §5.3 (caching strategy),
    §6.1 (this file's contract — 70-110 lines target).
    SPEC.md §5 (panel + plot contracts), §5.3 (UI behavior).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# sys.path shim — MUST run before any ``physics`` or ``ui`` import.
#
# ``streamlit run ui/app.py`` (Streamlit Cloud's invocation per ARCH §6.1)
# sets ``sys.path[0]`` to this file's directory, i.e. ``<repo>/ui/`` — NOT
# the repo root. From that vantage ``from physics import ...`` resolves to
# ``<repo>/ui/physics/`` and raises ``ModuleNotFoundError``.
#
# Prepending the repo root here makes every sibling package (``physics``,
# ``ui``) importable without touching Cloud's "Main file path" setting or
# requiring a top-level shim file. Local pytest is unaffected because
# pytest already discovers the repo root from ``tests/conftest.py``.
# ---------------------------------------------------------------------------
import sys as _sys
from pathlib import Path as _Path

_REPO_ROOT = str(_Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in _sys.path:
    _sys.path.insert(0, _REPO_ROOT)

from typing import Any
from urllib.parse import urlencode

import streamlit as st

from physics import m11_validation
from physics.orchestrator import run_full_chain
from ui import outputs, panels, plots
from ui.auth import require_login

# ---------------------------------------------------------------------------
# Page config + auth gate (must run before any other widget).
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="HEL Engineering Calculator",
    page_icon="🔦",
    layout="wide",
)
require_login()


# ---------------------------------------------------------------------------
# Caching wrappers (improvement #6: _freeze → hashable key).
# ---------------------------------------------------------------------------
def _freeze(user_inputs: dict) -> tuple:
    """Convert the user-inputs dict to a sorted tuple of (key, value) pairs.

    ``@st.cache_data`` requires a hashable key. Dicts are unhashable, so
    we sort by key and tuple-ify. All stored values are primitives (float,
    int, str, bool) — sort order is deterministic.
    """
    return tuple(sorted(user_inputs.items()))


@st.cache_data(max_entries=50, show_spinner=False)
def run_chain_cached(frozen_inputs: tuple) -> dict:
    """Cache wrapper: single orchestrator evaluation per frozen input set."""
    return run_full_chain(dict(frozen_inputs))


@st.cache_data(max_entries=10, show_spinner=False)
def run_sweep_cached(frozen_inputs: tuple, ranges_m: tuple) -> list[dict]:
    """Cache wrapper: orchestrator evaluation at N slant-range samples.

    Each sweep element is the merged-result dict with an extra
    ``"range"`` key so ``ui/plots`` can access the x-axis value directly.
    """
    base = dict(frozen_inputs)
    samples: list[dict] = []
    for R in ranges_m:
        inputs_at_R = {**base, "R": R}
        result = run_full_chain(inputs_at_R)
        samples.append({**result, "range": R})
    return samples


# ---------------------------------------------------------------------------
# URL-parameter handling (improvement #1: session-state decode latch).
# ---------------------------------------------------------------------------
_URL_DECODE_LATCH = "_url_decoded"
_URL_PREFILL_KEY = "_url_prefill"
_URL_FLAGS_KEY = "_url_flags"
#: Keys whose values should be carried as strings (enums); everything
#: else is parsed as float.
_URL_STRING_KEYS = frozenset({"cn2_model", "material", "backside_BC"})


def _decode_url_params_once() -> None:
    """Read ``st.query_params`` into ``session_state[_URL_PREFILL_KEY]``.

    Fires exactly once per session — the ``_URL_DECODE_LATCH`` guard
    prevents subsequent Streamlit reruns (triggered by any widget edit)
    from re-applying stale URL values on top of the user's edits.
    """
    if st.session_state.get(_URL_DECODE_LATCH):
        return

    prefill: dict[str, Any] = {}
    flags: list[str] = []
    for key, value in st.query_params.items():
        if key in _URL_STRING_KEYS:
            prefill[key] = value
            continue
        try:
            prefill[key] = float(value)
        except (TypeError, ValueError):
            flags.append(f"Input '{key}' malformed in URL, using default.")

    st.session_state[_URL_PREFILL_KEY] = prefill
    st.session_state[_URL_FLAGS_KEY] = flags
    st.session_state[_URL_DECODE_LATCH] = True


def _build_share_url(user_inputs: dict) -> str:
    """Encode ``user_inputs`` into a shareable URL (SPEC §5.3 item 7)."""
    params = {k: _stringify(v) for k, v in user_inputs.items()}
    # Streamlit does not expose the host URL; the user copies the path
    # + query-string. Document that limitation inline near the code block.
    return "?" + urlencode(params)


def _stringify(value: Any) -> str:
    """Compact numeric string: drop trailing zeros on floats, keep enums."""
    if isinstance(value, bool):  # bool is a float subclass — check first.
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


# ---------------------------------------------------------------------------
# Main body.
# ---------------------------------------------------------------------------
_decode_url_params_once()
prefill = st.session_state.get(_URL_PREFILL_KEY, {})
url_flags = list(st.session_state.get(_URL_FLAGS_KEY, []))

st.title("🔦 HEL Engineering Calculator")
st.caption(
    "Engagement-chain simulator for continuous-wave high-energy laser "
    "systems (SPEC v1.7 / ARCH v1.5)."
)

# ---------------------------------------------------------------------------
# Sidebar — input panels + action buttons.
# ---------------------------------------------------------------------------
user_inputs = panels.collect_all(initial=prefill or None)

with st.sidebar:
    st.markdown("---")
    run_clicked = st.button("▶ Run Analysis", type="primary",
                            use_container_width=True)
    share_clicked = st.button("🔗 Share this analysis",
                              use_container_width=True)
    validate_clicked = st.button("✓ Run Validation Suite",
                                 use_container_width=True,
                                 help="Invoke M11 (pytest) over SPEC §3 "
                                      "validation cases; does not affect "
                                      "the main analysis.")
    # Reference-range slider — drives Panel 1's "at reference range"
    # display and highlights the same range on Plots A, B, C.
    R_ref_km = st.slider(
        "Reference range (km)",
        min_value=0.1,
        max_value=float(user_inputs.get("R", 1500.0)) / 1000.0 * 2.0 + 0.1,
        value=float(user_inputs.get("R", 1500.0)) / 1000.0,
        step=0.1,
        key="R_ref_km",
    )

# ---------------------------------------------------------------------------
# Validation suite (M11) — always available, does not block analysis.
# ---------------------------------------------------------------------------
if validate_clicked:
    with st.sidebar:
        with st.spinner("Running validation suite (M11)…"):
            # Ignore M11's own tests to prevent infinite pytest recursion
            # (per SPEC §3 M11 note and the function's docstring).
            report = m11_validation.run_validation_suite(
                extra_pytest_args=["--ignore=tests/test_m11_validation.py"],
            )
        passed = report.get("passed", 0)
        failed = report.get("failed", 0)
        total = report.get("total_tests", 0)
        duration = report.get("duration_seconds", 0.0)
        if failed == 0 and total > 0:
            st.success(f"M11: {passed}/{total} pass ({duration:.1f} s)")
        elif total == 0:
            st.warning("M11: no tests collected")
        else:
            st.error(f"M11: {failed}/{total} failed ({duration:.1f} s)")

# ---------------------------------------------------------------------------
# Share URL block (improvement #3: st.code, not clipboard).
# ---------------------------------------------------------------------------
if share_clicked:
    share_url = _build_share_url(user_inputs)
    st.sidebar.success("Shareable URL ready — select and copy:")
    st.sidebar.code(share_url, language="text")
    st.sidebar.caption(
        "Paste this as the query string of the calculator URL to "
        "restore the exact input state. (Automatic clipboard writes "
        "require HTTPS + permission; the code block above works in "
        "every deployment.)"
    )

# ---------------------------------------------------------------------------
# Main area — only renders when the user clicks Run Analysis.
# ---------------------------------------------------------------------------
# Once the user has clicked Run Analysis even once, subsequent reruns
# (reference-slider move, panel edit) should re-render the outputs
# automatically — ``@st.cache_data`` on the orchestrator makes that cheap
# when inputs haven't changed. Track the "ever-run" latch in session state.
_RUN_LATCH = "_run_requested"
if run_clicked:
    st.session_state[_RUN_LATCH] = True
if not st.session_state.get(_RUN_LATCH):
    st.info(
        "Adjust the 6 input panels in the sidebar, then click "
        "**▶ Run Analysis** to compute the engagement chain "
        "(M1 → M10 per SPEC §4)."
    )
    st.stop()

# Run the chain (cached). Surface ValueError from any module's
# ``_validate_inputs`` next to the user's panels rather than a
# traceback — per CLAUDE §6.5 "When something is broken".
try:
    frozen = _freeze(user_inputs)
    result = run_chain_cached(frozen)
except ValueError as exc:
    st.error(f"Input validation failed: {exc}")
    st.stop()

# Merge user_inputs into the result so ``outputs.render_panel_1_spot_strehl``
# can read ``result['M2']`` and ``result['sigma_jit']`` without changing
# the ARCH §6.4 signature. User-input keys are disjoint from module-output
# keys (spot checked: P0/M2/D/eta_opt/... vs w0/zR/I_peak/PIB/...) except
# for ``wavelength`` which is idempotent.
merged = {**user_inputs, **result}

# Surface any URL-decode flags onto Panel 4.
if url_flags:
    merged["assumptions_flagged"] = list(url_flags) + list(
        merged.get("assumptions_flagged", [])
    )

# ---------------------------------------------------------------------------
# Numeric output panels.
# ---------------------------------------------------------------------------
outputs.render_all(merged, reference_range=R_ref_km * 1000.0)

# ---------------------------------------------------------------------------
# Range-sweep for Plots A/B/C.
# ---------------------------------------------------------------------------
R_selected = float(user_inputs.get("R", 1500.0))
R_min = max(100.0, R_selected * 0.1)
R_max = min(50_000.0, R_selected * 2.0)
N_samples = 30
step = (R_max - R_min) / (N_samples - 1)
ranges = tuple(R_min + i * step for i in range(N_samples))

try:
    sweep = run_sweep_cached(frozen, ranges)
    st.subheader("Range sweep plots")
    st.plotly_chart(plots.plot_a_on_target_performance(sweep),
                    use_container_width=True)
    st.plotly_chart(plots.plot_b_time_to_burnthrough(sweep),
                    use_container_width=True)
    st.plotly_chart(plots.plot_c_beam_diameter_breakdown(sweep),
                    use_container_width=True)
except ValueError as exc:
    # A sweep point may violate an M3 slant-range validator even if the
    # single-point run did not — report and continue rendering the rest.
    st.warning(f"Range-sweep skipped ({exc}); numeric panels above are valid.")

# ---------------------------------------------------------------------------
# Convergence diagnostic footer (visible but unobtrusive).
# ---------------------------------------------------------------------------
conv_note = (
    f"M6↔M7 loop: {merged['m67_iteration_count']} iterations, "
    f"{'converged' if merged['m67_converged'] else 'did NOT converge'} "
    f"(SPEC §3 M6 tolerance)."
)
st.caption(conv_note)
