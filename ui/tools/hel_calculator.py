"""HEL Calculator page (multipage refactor + auth-bypass hotfix).

The HEL Engineering Calculator workflow: a six-section sidebar
(laser source, beam director, engagement geometry, atmosphere,
target & aimpoint, system resources), a preset dropdown, Run / Share
/ Validate buttons, the cached orchestrator chain, and the seven-tab
results stack with the "Last run" indicator.

Dispatched by ``ui/app.py`` via Streamlit's ``st.navigation`` /
``st.Page`` API. The entry script handles the four shell concerns
(``sys.path`` shim, ``st.set_page_config``, theme bootstrap, auth
gate) before this script runs.

**Auth defense in depth (2026-04-26 hotfix).** This page calls
``theme.apply()`` and ``require_login()`` at the top, even though
``ui/app.py`` already does both. The redundancy guards against any
flow where a request reaches this page without going through
``app.py``. Both calls are idempotent — ``require_login()`` returns
immediately when the session is already authed; ``theme.apply()``
just re-injects identical CSS.

References:
    ui/app.py — multipage entry script.
    ui/tools/dri_analyzer.py — DRI page (sibling).
    ui/panels.py — ``collect_hel`` returns the six HEL sections only.
    ui/outputs.py — ``render_tab_*`` renderers.
"""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

import streamlit as st

from physics import m11_validation
from physics.orchestrator import run_full_chain
from ui import outputs, panels, presets, theme
from ui.auth import require_login
from ui.components import error_card, progress_bar
from ui.labels import (
    ADVISORY,
    BUTTON_LABELS,
    FOOTER_TEMPLATE,
    PRESET_LABELS,
    PRESET_PICKER_HELP,
    PRESET_PICKER_LABEL,
    TAB_LABELS,
)


# ---------------------------------------------------------------------------
# Auth defense in depth + theme re-apply.
# Both are idempotent under the normal app.py-driven flow; they exist as
# a safety net for any path that reaches this page without app.py.
# ---------------------------------------------------------------------------
_APP_MODE_KEY = "_app_mode"
app_mode = st.session_state.get(_APP_MODE_KEY, "dark")
theme.apply(app_mode)
require_login()


# ---------------------------------------------------------------------------
# Provenance — surfaced in the footer strip only (never in the header).
# Keep in sync with the latest contract-document revisions.
# ---------------------------------------------------------------------------
_SPEC_VERSION = "v1.11"
_ARCH_VERSION = "v2.0"
_BUILD_DATE = "2026-04-26"


# ---------------------------------------------------------------------------
# Caching wrappers.
# ---------------------------------------------------------------------------
def _freeze(user_inputs: dict) -> tuple:
    """Convert the user-inputs dict to a sorted tuple of (key, value) pairs.

    ``@st.cache_data`` requires a hashable key. Dicts are unhashable, so
    we sort by key and tuple-ify. All stored values are primitives
    (float, int, str, bool) — sort order is deterministic.
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

    **Tolerant of per-sample ValueErrors.** A single degenerate sample
    (e.g. ``R_detect == R_min`` when in v2 trajectory mode → t_dwell=0
    → M8 rejects) used to make the whole sweep raise and the engagement
    tab show "No feasible engagement" on every plot. Now the bad sample
    is skipped and the sweep returns the points that did succeed. If
    *none* succeed the function still raises so the caller can fall
    back to the empty-frame advisory.
    """
    base = dict(frozen_inputs)
    samples: list[dict] = []
    # SPEC v2.0: in trajectory mode the sweep varies R_detect; in v1.x
    # mode it varies R. Pick the right key based on what the inputs
    # carry.
    sweep_key = "R_detect" if "engagement_geometry" in base else "R"
    last_exc: ValueError | None = None
    for R in ranges_m:
        inputs_at_R = {**base, sweep_key: R}
        try:
            result = run_full_chain(inputs_at_R)
        except ValueError as exc:
            # Skip degenerate sweep points — see docstring. Other
            # samples may still produce useful curves.
            last_exc = exc
            continue
        samples.append({**result, "range": R})
    if not samples and last_exc is not None:
        raise last_exc
    return samples


# ---------------------------------------------------------------------------
# URL-parameter handling (session-state latch prevents re-application on
# subsequent reruns).
# ---------------------------------------------------------------------------
_URL_DECODE_LATCH = "_url_decoded_hel"
_URL_PREFILL_KEY = "_url_prefill_hel"
_URL_FLAGS_KEY = "_url_flags_hel"
#: Keys whose values should be carried as strings (enums); everything
#: else is parsed as float.
_URL_STRING_KEYS = frozenset({
    "cn2_model", "material", "backside_BC",
    # SPEC v2.0 §3 M3 — engagement_geometry is a string enum.
    "engagement_geometry",
})


def _decode_url_params_once() -> None:
    """Read HEL ``st.query_params`` into ``session_state[_URL_PREFILL_KEY]``.

    Fires exactly once per session — the ``_URL_DECODE_LATCH`` guard
    prevents subsequent Streamlit reruns (triggered by any widget edit)
    from re-applying stale URL values on top of the user's edits.

    DRI keys (``dri_*``) are skipped — the DRI page has its own
    page-scoped decode (``_url_decoded_dri``) that handles those.
    """
    if st.session_state.get(_URL_DECODE_LATCH):
        return

    prefill: dict[str, Any] = {}
    flags: list[str] = []
    for key, value in st.query_params.items():
        if key.startswith("dri_"):
            continue                          # belongs to the DRI page
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
    """Encode ``user_inputs`` into a shareable URL."""
    params = {k: _stringify(v) for k, v in user_inputs.items()}
    # Streamlit does not expose the host URL; the user copies the
    # path + query string. Document that limitation inline near the
    # code block.
    return "?" + urlencode(params)


def _stringify(value: Any) -> str:
    """Compact numeric string: drop trailing zeros on floats, keep enums."""
    if isinstance(value, bool):  # bool is a float subclass — check first.
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _render_footer() -> None:
    """Render the provenance strip at the bottom of the main area.

    Styled via the ``hel-footer`` class defined in ``ui/theme.py``. The
    caller places this at the end of the main-area render so it's the
    last thing in the document flow.
    """
    text = FOOTER_TEMPLATE.format(
        spec_version=_SPEC_VERSION,
        arch_version=_ARCH_VERSION,
        build_date=_BUILD_DATE,
    )
    st.markdown(
        f"<div class='hel-footer'>{text}</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# "Last run" indicator — relative timestamp ("just now" / "12 s ago" / …)
# ---------------------------------------------------------------------------

_LAST_RUN_AT = "_last_run_at"


def _format_last_run(ts: float | None) -> str:
    """Return a short human-readable "time since" label for the last run.

    Buckets: <5 s → "just now", <60 s → "{n} s ago", <60 min → "{n} min ago",
    otherwise → "{n} h ago". Deliberately coarse: the indicator is a
    staleness hint, not a stopwatch.
    """
    if ts is None:
        return "not yet run"
    elapsed = max(0.0, time.time() - ts)
    if elapsed < 5:
        return "just now"
    if elapsed < 60:
        return f"{int(elapsed)} s ago"
    if elapsed < 3600:
        return f"{int(elapsed // 60)} min ago"
    return f"{int(elapsed // 3600)} h ago"


def _render_last_run_indicator() -> None:
    """Render the "Last run …" caption in the sidebar footer."""
    ts = st.session_state.get(_LAST_RUN_AT)
    # ``fresh`` modifier brightens the text for the first ~5 s after a run
    # so the user sees the tool confirm the compute finished.
    fresh = ts is not None and (time.time() - ts) < 5
    cls = "hel-last-run hel-last-run--fresh" if fresh else "hel-last-run"
    st.sidebar.markdown(
        f"<div class='{cls}'>Last run: {_format_last_run(ts)}</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Main body.
# ---------------------------------------------------------------------------
_decode_url_params_once()
prefill = st.session_state.get(_URL_PREFILL_KEY, {})
url_flags = list(st.session_state.get(_URL_FLAGS_KEY, []))

st.title("HEL Engineering Calculator")

# ---------------------------------------------------------------------------
# Sidebar — preset picker, then input sections, then action buttons.
# ---------------------------------------------------------------------------
# Preset dropdown: rendered BEFORE the six input sections so its
# ``on_change`` callback can write through to the underlying widget
# session-state keys before those widgets render this run. The "Custom"
# default preserves backwards-compatible behavior — a fresh visitor
# with no preset selection still sees the canonical SPEC §5.1 defaults
# via each panel's fallback.
_PRESET_KEY = "_preset_choice"
_PRESET_OPTIONS = tuple(PRESET_LABELS.keys())


def _on_preset_change() -> None:
    """Write the selected preset's values into session-state.

    Runs as the ``on_change`` callback for the preset selectbox, which
    fires before the six input sections render on this rerun — so the
    session-state writes land in time to be picked up by each widget's
    ``key=`` binding.
    """
    choice = st.session_state.get(_PRESET_KEY, "custom")
    presets.apply_to_session_state(st.session_state, choice)


with st.sidebar:
    st.selectbox(
        PRESET_PICKER_LABEL,
        options=_PRESET_OPTIONS,
        format_func=lambda k: PRESET_LABELS[k],
        key=_PRESET_KEY,
        on_change=_on_preset_change,
        help=PRESET_PICKER_HELP,
    )

user_inputs = panels.collect_hel(initial=prefill or None)

with st.sidebar:
    st.markdown("---")
    run_clicked = st.button(
        BUTTON_LABELS["run_analysis"], type="primary",
        use_container_width=True,
    )
    share_clicked = st.button(
        BUTTON_LABELS["share"],
        use_container_width=True,
    )
    validate_clicked = st.button(
        BUTTON_LABELS["validate"],
        use_container_width=True,
        help="Runs the full validation test suite against the physics "
             "modules; does not affect the main analysis.",
    )
    # Reference-range slider — drives the spot-and-Strehl section's
    # "at reference range" display and highlights the same range on
    # the performance, burn-through, and beam-breakdown plots.
    # SPEC v2.0: in trajectory mode the reference range corresponds to
    # R_detect (the sweep varies detection range). Falls back to v1's
    # R when the user is on the legacy contract.
    _R_ref_default = float(
        user_inputs.get("R_detect", user_inputs.get("R", 1500.0))
    )
    R_ref_km = st.slider(
        "Reference range (km)",
        min_value=0.1,
        max_value=_R_ref_default / 1000.0 * 2.0 + 0.1,
        value=_R_ref_default / 1000.0,
        step=0.1,
        key="R_ref_km",
    )

    # --- Sidebar footer: dark / light theme toggle -----------------------
    # Flips the session-state app-mode and triggers a rerun; the entry
    # script (ui/app.py) picks up the new mode on the next run via
    # theme.apply(app_mode), swapping both the CSS palette and the
    # registered Plotly template.
    st.markdown("---")
    toggle_label = (
        BUTTON_LABELS["theme_toggle_dark"]
        if app_mode == "dark"
        else BUTTON_LABELS["theme_toggle_light"]
    )
    if st.button(toggle_label, key="_theme_toggle_btn",
                 use_container_width=True):
        st.session_state[_APP_MODE_KEY] = (
            "light" if app_mode == "dark" else "dark"
        )
        st.rerun()

# ---------------------------------------------------------------------------
# Validation suite — always available, does not block analysis.
# ---------------------------------------------------------------------------
if validate_clicked:
    with st.sidebar:
        with st.spinner("Running validation suite…"):
            # Ignore the validation-harness's own tests to prevent
            # infinite pytest recursion.
            report = m11_validation.run_validation_suite(
                extra_pytest_args=["--ignore=tests/test_m11_validation.py"],
            )
        passed = report.get("passed", 0)
        failed = report.get("failed", 0)
        total = report.get("total_tests", 0)
        duration = report.get("duration_seconds", 0.0)
        if failed == 0 and total > 0:
            st.success(f"Validation: {passed}/{total} pass ({duration:.1f} s)")
        elif total == 0:
            st.warning("Validation: no tests collected")
        else:
            st.error(f"Validation: {failed}/{total} failed ({duration:.1f} s)")

# ---------------------------------------------------------------------------
# Share URL block.
# ---------------------------------------------------------------------------
if share_clicked:
    share_url = _build_share_url(user_inputs)
    st.sidebar.success("Shareable URL ready — select and copy:")
    st.sidebar.code(share_url, language="text")
    st.sidebar.caption(
        "Paste this as the query string of the calculator URL to "
        "restore the exact input state. (Automatic clipboard writes "
        "require HTTPS and user permission; the code block above "
        "works in every deployment.)"
    )

# ---------------------------------------------------------------------------
# Main area — only renders after the user has clicked Run Analysis.
# ---------------------------------------------------------------------------
# Once the user has clicked Run Analysis even once, subsequent reruns
# (reference-slider move, section edit) should re-render the outputs
# automatically — ``@st.cache_data`` on the orchestrator makes that
# cheap when inputs haven't changed. Track the "ever-run" latch in
# session state.
_RUN_LATCH = "_run_requested"
if run_clicked:
    st.session_state[_RUN_LATCH] = True

_render_last_run_indicator()

if not st.session_state.get(_RUN_LATCH):
    st.markdown(
        '<div class="hel-welcome-card">'
        f'<div class="hel-welcome-card__title">{ADVISORY["welcome_title"]}</div>'
        f'<div class="hel-welcome-card__body">{ADVISORY["welcome_body"]}</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    _render_footer()
    st.stop()

# --- Compute-time feedback: thin progress bar above the tabs ---------------
# The bar is rendered into an ``st.empty()`` placeholder so we can clear it
# once the compute finishes. On cold runs the compute takes ~1–4 s and the
# bar's sliding animation is visible; on cached reruns the placeholder is
# cleared within a few tens of ms and the bar is essentially invisible.
progress_slot = st.empty()
with progress_slot.container():
    progress_bar(visible=True)

# Run the chain (cached). Surface ValueError from any module's input
# validator — and NotImplementedError from any unimplemented physics
# branch the UI has accidentally exposed — next to the user's panels
# rather than a traceback. The UI should not expose options that route
# to NotImplementedError; the panel selectboxes are filtered to the
# implemented enum values, but this catch is defense-in-depth so a
# future contract drift never lands as a stack trace on the user.
try:
    frozen = _freeze(user_inputs)
    result = run_chain_cached(frozen)
except ValueError as exc:
    progress_slot.empty()
    error_card(
        "Input out of range",
        f"The solver rejected the current input set: {exc}",
        suggestion=(
            "Adjust the sidebar values until every input sits inside its "
            "sanity range, then click Run Analysis again."
        ),
    )
    _render_footer()
    st.stop()
except NotImplementedError as exc:
    progress_slot.empty()
    error_card(
        "Model branch not available",
        f"That combination of inputs routes to a physics branch that is "
        f"not yet implemented: {exc}",
        suggestion=(
            "Pick a different turbulence profile or reset the sidebar via "
            "the Engagement scenario dropdown, then click Run Analysis."
        ),
    )
    _render_footer()
    st.stop()

# --- Range-sweep samples for the Engagement tab ---------------------------
R_selected = float(
    user_inputs.get("R_detect", user_inputs.get("R", 1500.0))
)
# SPEC v2.0: in trajectory mode the sweep MUST start strictly above
# the user's standoff R_min — a sweep point at R_detect == R_min
# yields t_dwell = 0 and M8 rejects the input ("t_dwell must be > 0").
# Add a 1 m epsilon above R_min(input) so the sweep never touches the
# degenerate boundary; cosmetic on the plot but prevents the whole
# tab from collapsing to "No feasible engagement" when the lower
# bound happens to coincide with R_min.
_R_min_input = float(user_inputs.get("R_min", 0.0))
R_low = max(100.0, R_selected * 0.1, _R_min_input + 1.0)
R_high = min(50_000.0, R_selected * 2.0)
# Guard: when R_selected is very close to R_min the upper bound can
# fall below the lower bound. Clamp.
if R_high <= R_low:
    R_high = R_low + 100.0
# Sweep size — reduced 2026-04-26 from 30 to 15. The sweep runs
# the full v2 trajectory chain at every sample point and blocks the
# main script during compute (~1-2 s per sample); 30 samples gave a
# 30-60 s Run Analysis wait that the user reported as "stuck." 15
# samples cuts that roughly in half while keeping range-sweep plots
# (A, B, C, D, E, G) visually smooth — Plotly interpolates between
# them.
N_samples = 15
step = (R_high - R_low) / (N_samples - 1)
ranges = tuple(R_low + i * step for i in range(N_samples))

sweep: list[dict] | None
try:
    sweep = run_sweep_cached(frozen, ranges)
except ValueError:
    # A sweep point may violate a slant-range validator even if the
    # single-point run did not — the Engagement tab renders the rest of
    # its content and shows an inline advisory where the plots would go.
    sweep = None

# Merge user_inputs into the result so the output sections can read
# ``result['M2']`` and ``result['sigma_jit']`` without changing the
# ARCH §6.4 signature. User-input keys are disjoint from module-output
# keys (spot checked: P0 / M2 / D / eta_opt / ... vs w0 / zR / I_peak /
# PIB / ...) except for ``wavelength`` which is idempotent.
merged = {**user_inputs, **result}

# Surface any URL-decode flags onto the assumptions roll-up.
if url_flags:
    merged["assumptions_flagged"] = list(url_flags) + list(
        merged.get("assumptions_flagged", [])
    )

# Clear the progress bar — the tabs below are about to fade in.
progress_slot.empty()

# Stamp the "Last run" indicator so the next rerun picks up a fresh age.
st.session_state[_LAST_RUN_AT] = time.time()

# ---------------------------------------------------------------------------
# Tabbed results — seven panes in reading order. Each tab's content lives
# in a dedicated ``render_tab_<name>`` function in ``ui/outputs.py``. The
# tab container fades in via a CSS animation on ``.stTabs`` from
# ``ui/theme.py`` (150 ms ease-out; clamped to 50 ms under
# prefers-reduced-motion).
#
# Build a {key: tab_widget} dict instead of positional destructuring —
# adding a tab to TAB_LABELS no longer requires editing this block, and
# a partially-deployed ui/labels.py (e.g. Streamlit Cloud build cache
# missing the latest math-tab key) degrades gracefully rather than
# crashing the whole app at the unpacking line.
# ---------------------------------------------------------------------------
tab_widgets = st.tabs(list(TAB_LABELS.values()))
tabs = dict(zip(TAB_LABELS.keys(), tab_widgets))

# Each render block is keyed by TAB_LABELS key. The .get() with a
# falsy fallback means a missing key no-ops cleanly; the tab simply
# doesn't render. This is the line that breaks the otherwise hard
# dependency between TAB_LABELS and the render dispatch — important
# because the two files can drift in deploy environments where the
# build cache is partial.
if "overview" in tabs:
    with tabs["overview"]:
        outputs.render_tab_overview(merged)

if "engagement" in tabs:
    with tabs["engagement"]:
        outputs.render_tab_engagement(
            merged,
            reference_range=R_ref_km * 1000.0,
            sweep=sweep,
        )

if "target_effects" in tabs:
    with tabs["target_effects"]:
        outputs.render_tab_target_effects(merged)

if "safety" in tabs:
    with tabs["safety"]:
        outputs.render_tab_safety(merged)

if "atmosphere" in tabs:
    with tabs["atmosphere"]:
        outputs.render_tab_atmosphere(merged, sweep=sweep)

if "diagnostics" in tabs:
    with tabs["diagnostics"]:
        outputs.render_tab_diagnostics(merged)

if "math" in tabs:
    with tabs["math"]:
        outputs.render_tab_math(merged)

_render_footer()
