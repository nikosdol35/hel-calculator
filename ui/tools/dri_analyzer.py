"""DRI Analyzer page (multipage refactor + Run-Analysis pattern).

A standalone passive-sensor analyzer that computes Detection /
Recognition / Identification ranges via the Johnson criteria. Lives
on its own page under Streamlit's ``st.navigation`` system; entirely
independent of the HEL Calculator's laser-emitter chain.

Behavioural contract:
    * **Run-Analysis-gated** — first visit shows a welcome card; the
      user adjusts inputs, clicks Run Analysis, and only then does
      the page compute and render results. Once Run has been clicked
      at least once, subsequent edits re-render automatically (the
      cached sweep helpers make that cheap). Mirrors the HEL
      Calculator's "compute on click" workflow.
    * **No HEL physics in the sidebar** — only the DRI sensor / DRI
      atmosphere / DRI target sections, plus a sensor-preset dropdown
      and a theme toggle.
    * **Page-scoped URL decode** — uses its own session-state latch
      (``_url_decoded_dri``) and reads only ``dri_*`` query parameters,
      so a share-URL from this page round-trips without bleeding HEL
      keys across pages.

Dispatched by ``ui/app.py`` via ``st.navigation``; the entry script
handles page config, theme, and auth before this script ever runs.

**Auth defense in depth.** This page calls ``theme.apply()`` and
``require_login()`` at the top, even though ``ui/app.py`` already
does both. The redundancy guards against any flow where a request
reaches this page without going through ``app.py``. Both calls
are idempotent.

References:
    docs/dri_analyzer_design.md — DRI module contract.
    physics/dri_analyzer.py — pure module; ``compute(inputs) -> dict``.
    ui/panels.py — ``collect_dri`` returns the three DRI sections only.
    ui/presets.py — DRI sensor presets.
"""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

import streamlit as st

from physics import dri_analyzer
from ui import outputs, panels, presets, theme
from ui.auth import require_login
from ui.components import progress_bar
from ui.labels import (
    ADVISORY,
    BUTTON_LABELS,
    DRI_PRESET_LABELS,
    DRI_PRESET_PICKER_HELP,
    DRI_PRESET_PICKER_LABEL,
    FOOTER_TEMPLATE,
)


# ---------------------------------------------------------------------------
# Auth defense in depth + theme re-apply.
# Idempotent under normal flow (app.py already did both); guards any
# path that reaches this page without app.py running first.
# ---------------------------------------------------------------------------
_APP_MODE_KEY = "_app_mode"
app_mode = st.session_state.get(_APP_MODE_KEY, "dark")
theme.apply(app_mode)
require_login()


# ---------------------------------------------------------------------------
# Provenance — surfaced in the footer strip only.
# ---------------------------------------------------------------------------
_SPEC_VERSION = "v1.11"
_ARCH_VERSION = "v2.0"
_BUILD_DATE = "2026-04-26"


# ---------------------------------------------------------------------------
# Cache helpers — closed-form sweeps over DRI inputs.
# ---------------------------------------------------------------------------
def _freeze(user_inputs: dict) -> tuple:
    """Convert the DRI-inputs dict to a sorted tuple of (key, value)
    pairs so ``@st.cache_data`` can hash it."""
    return tuple(sorted(user_inputs.items()))


def _resolve_dri_kwargs(base: dict, level: str) -> dict:
    """Pull DRI inputs out of a frozen-tuple-as-dict and resolve them
    into the kwargs ``physics.dri_analyzer`` helpers expect. Shared by
    every DRI sweep helper."""
    target_preset = base["dri_target_preset"]
    if target_preset == "Custom":
        h_target = float(base.get("dri_target_h_m", 1.0))
    else:
        h_target = dri_analyzer.target_critical_dim(target_preset)
    cn2 = dri_analyzer.CN2_PRESETS[base["dri_cn2_preset"]]
    n_cycles_50 = float(base[{
        "Detection": "dri_n_cycles_D",
        "Recognition": "dri_n_cycles_R",
        "Identification": "dri_n_cycles_I",
    }[level]])
    return dict(
        h_target=h_target,
        n_pixels_h=int(base["dri_n_pixels_h"]),
        band=base["dri_band"],
        cn2=cn2,
        V_km=float(base["dri_visibility_km"]),
        f_mm=float(base["dri_focal_length_mm"]),
        f_number=float(base["dri_f_number"]),
        C0=float(base.get("dri_C0", 0.30)),
        probability=float(base.get("dri_probability", 0.50)),
        n_cycles_50=n_cycles_50,
    )


@st.cache_data(max_entries=10, show_spinner=False)
def run_dri_fov_sweep_cached(
    frozen_inputs: tuple, level: str, n_points: int = 30,
) -> list[dict]:
    """Cache wrapper: DRI FOV-sweep evaluation NFOV → WFOV.

    ~30 closed-form evaluations + 3-step path-length fixed-point
    iterations; <50 ms typical.
    """
    base = dict(frozen_inputs)
    nfov = float(base["dri_nfov_deg"])
    wfov = float(base["dri_wfov_deg"])
    if wfov <= nfov:
        return []
    return dri_analyzer.fov_sweep(
        level=level,
        fov_low_deg=nfov,
        fov_high_deg=wfov,
        n_points=n_points,
        **_resolve_dri_kwargs(base, level),
    )


@st.cache_data(max_entries=10, show_spinner=False)
def run_dri_target_size_sweep_cached(
    frozen_inputs: tuple, level: str, sizes_m: tuple,
) -> list[dict]:
    """Cache wrapper: DRI range vs target critical dimension at NFOV."""
    base = dict(frozen_inputs)
    kwargs = _resolve_dri_kwargs(base, level)
    kwargs.pop("h_target")
    return dri_analyzer.target_size_sweep(
        level=level,
        sizes_m=tuple(float(s) for s in sizes_m),
        fov_h_deg=float(base["dri_nfov_deg"]),
        **kwargs,
    )


@st.cache_data(max_entries=10, show_spinner=False)
def run_dri_cn2_sweep_cached(
    frozen_inputs: tuple, level: str,
) -> list[dict]:
    """Cache wrapper: DRI range across the seven preset Cn² levels at NFOV."""
    base = dict(frozen_inputs)
    kwargs = _resolve_dri_kwargs(base, level)
    kwargs.pop("cn2")
    return dri_analyzer.cn2_sweep(
        level=level,
        cn2_values=list(dri_analyzer.CN2_PRESETS.values()),
        fov_h_deg=float(base["dri_nfov_deg"]),
        **kwargs,
    )


@st.cache_data(max_entries=4, show_spinner="Computing DRI heatmap…")
def run_dri_heatmap_cached(
    frozen_inputs: tuple,
    fov_grid_deg: tuple,
    target_grid_m: tuple,
    level: str = "Detection",
) -> list[list[float]]:
    """Cache wrapper: 2D heatmap over (FOV × target size).
    20×20 = 400 evaluations; <500 ms typical."""
    base = dict(frozen_inputs)
    kwargs = _resolve_dri_kwargs(base, level)
    kwargs.pop("h_target")
    return dri_analyzer.heatmap(
        fov_grid_deg=list(fov_grid_deg),
        target_grid_m=list(target_grid_m),
        level=level,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# URL-parameter handling (page-scoped latch + dri_* prefix filter).
# ---------------------------------------------------------------------------
_URL_DECODE_LATCH = "_url_decoded_dri"
_URL_PREFILL_KEY = "_url_prefill_dri"

#: Keys whose values should be carried as strings (enums); others are
#: parsed as float. DRI-page decoder reads only ``dri_*`` keys.
_DRI_URL_STRING_KEYS = frozenset({
    "dri_band", "dri_cn2_preset", "dri_target_preset",
})


def _decode_url_params_once() -> None:
    """Read ``dri_*`` query parameters into ``session_state`` once per
    session. The single-fire latch prevents Streamlit's rerun-on-change
    loop from re-applying stale URL values over the user's edits."""
    if st.session_state.get(_URL_DECODE_LATCH):
        return
    prefill: dict[str, Any] = {}
    for key, value in st.query_params.items():
        if not key.startswith("dri_"):
            continue
        if key in _DRI_URL_STRING_KEYS:
            prefill[key] = value
            continue
        try:
            prefill[key] = float(value)
        except (TypeError, ValueError):
            continue
    st.session_state[_URL_PREFILL_KEY] = prefill
    st.session_state[_URL_DECODE_LATCH] = True


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _build_share_url(user_inputs: dict) -> str:
    """Encode the DRI sub-set of ``user_inputs`` into a share URL."""
    dri_only = {k: v for k, v in user_inputs.items() if k.startswith("dri_")}
    return "?" + urlencode({k: _stringify(v) for k, v in dri_only.items()})


def _render_footer() -> None:
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
# "Last run" indicator + Run-Analysis latch.
# Mirrors the HEL Calculator's pattern so both pages feel identical:
# user clicks Run Analysis once, the latch flips on, and subsequent
# sidebar edits re-render automatically (the cached sweep helpers
# keep that cheap).
# ---------------------------------------------------------------------------
_DRI_RUN_LATCH = "_dri_run_requested"
_DRI_LAST_RUN_AT = "_dri_last_run_at"


def _format_last_run(ts: float | None) -> str:
    """Short human-readable "time since" label for the last DRI run."""
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
    """Render the "Last run …" caption in the DRI sidebar footer."""
    ts = st.session_state.get(_DRI_LAST_RUN_AT)
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

st.title("DRI Analyzer")
st.caption(
    "Detection · Recognition · Identification ranges for a passive "
    "electro-optical sensor. Independent of the HEL Calculator — "
    "click Run Analysis to compute the page."
)

# ---------------------------------------------------------------------------
# Sidebar — sensor preset, three DRI sections, share button, theme toggle.
# ---------------------------------------------------------------------------
_PRESET_KEY = "_dri_preset_choice"
_PRESET_OPTIONS = tuple(DRI_PRESET_LABELS.keys())


def _on_preset_change() -> None:
    """Apply the selected DRI preset's values to session_state.

    The selectbox's ``on_change`` callback fires before the three DRI
    section widgets render on this rerun, so the writes land in time
    to be picked up by each widget's ``key=`` binding.
    """
    choice = st.session_state.get(_PRESET_KEY, "custom")
    presets.apply_dri_preset_to_session_state(st.session_state, choice)


with st.sidebar:
    st.selectbox(
        DRI_PRESET_PICKER_LABEL,
        options=_PRESET_OPTIONS,
        format_func=lambda k: DRI_PRESET_LABELS[k],
        key=_PRESET_KEY,
        on_change=_on_preset_change,
        help=DRI_PRESET_PICKER_HELP,
    )

# Three DRI expanders (sensor, atmosphere, target & criteria).
user_inputs = panels.collect_dri(initial=prefill or None)

with st.sidebar:
    st.markdown("---")
    run_clicked = st.button(
        BUTTON_LABELS["run_analysis"], type="primary",
        use_container_width=True,
        key="_dri_run_btn",
    )
    share_clicked = st.button(
        BUTTON_LABELS["share"],
        use_container_width=True,
        key="_dri_share_btn",
    )

    # --- Sidebar footer: dark / light theme toggle ----------------------
    st.markdown("---")
    toggle_label = (
        BUTTON_LABELS["theme_toggle_dark"]
        if app_mode == "dark"
        else BUTTON_LABELS["theme_toggle_light"]
    )
    if st.button(toggle_label, key="_dri_theme_toggle_btn",
                 use_container_width=True):
        st.session_state[_APP_MODE_KEY] = (
            "light" if app_mode == "dark" else "dark"
        )
        st.rerun()

# ---------------------------------------------------------------------------
# Run-Analysis latch + welcome card.
# Once the user has clicked Run Analysis even once, subsequent reruns
# (preset switch, sidebar edit) re-render the outputs automatically —
# ``@st.cache_data`` on the sweep helpers makes that cheap when inputs
# haven't changed. Track the "ever-run" latch in session state.
# ---------------------------------------------------------------------------
if run_clicked:
    st.session_state[_DRI_RUN_LATCH] = True

_render_last_run_indicator()

if not st.session_state.get(_DRI_RUN_LATCH):
    st.markdown(
        '<div class="hel-welcome-card">'
        f'<div class="hel-welcome-card__title">{ADVISORY["dri_welcome_title"]}</div>'
        f'<div class="hel-welcome-card__body">{ADVISORY["dri_welcome_body"]}</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    _render_footer()
    st.stop()

# ---------------------------------------------------------------------------
# Share URL block (DRI-only — encodes only dri_* keys).
# ---------------------------------------------------------------------------
if share_clicked:
    share_url = _build_share_url(user_inputs)
    st.sidebar.success("Shareable URL ready — select and copy:")
    st.sidebar.code(share_url, language="text")
    st.sidebar.caption(
        "Paste this as the query string of the DRI Analyzer URL to "
        "restore the exact sensor configuration. The link encodes "
        "only DRI inputs; HEL Calculator settings are unaffected."
    )

# ---------------------------------------------------------------------------
# Compute-time feedback: thin progress bar above the results.
# Cached helpers make subsequent re-renders near-instant; on a cold run
# the bar's sliding animation is briefly visible.
# ---------------------------------------------------------------------------
progress_slot = st.empty()
with progress_slot.container():
    progress_bar(visible=True)

# ---------------------------------------------------------------------------
# DRI compute.
# ---------------------------------------------------------------------------
try:
    dri_result = dri_analyzer.compute(user_inputs)
except (KeyError, ValueError) as exc:
    progress_slot.empty()
    st.error(
        f"DRI inputs rejected: {exc}. Adjust the sidebar values and "
        "click Run Analysis again."
    )
    _render_footer()
    st.stop()

# Pre-compute the three required FOV sweeps + the two cheap optional
# sweeps (target-size, Cn²). Each is <100 ms; the heatmap stays
# behind a Compute button (~500 ms on first click).
dri_frozen = _freeze(user_inputs)

dri_sweeps: dict[str, list[dict]] = {}
dri_target_size_sweeps: dict[str, list[dict]] = {}
dri_cn2_sweeps: dict[str, list[dict]] = {}
_target_sizes = tuple(
    0.10 * (10.0 ** (i / 9.0)) for i in range(19)
)  # 19 points covering 0.10 → 10 m
for _level in ("Detection", "Recognition", "Identification"):
    try:
        dri_sweeps[_level] = run_dri_fov_sweep_cached(dri_frozen, _level)
    except (KeyError, ValueError):
        dri_sweeps[_level] = []
    try:
        dri_target_size_sweeps[_level] = run_dri_target_size_sweep_cached(
            dri_frozen, _level, _target_sizes,
        )
    except (KeyError, ValueError):
        dri_target_size_sweeps[_level] = []
    try:
        dri_cn2_sweeps[_level] = run_dri_cn2_sweep_cached(dri_frozen, _level)
    except (KeyError, ValueError):
        dri_cn2_sweeps[_level] = []

# Merge user_inputs into the result so the renderer can read both the
# input echoes (dri_nfov_deg, etc.) and the compute outputs.
merged = {**user_inputs, **dri_result}

# Clear the progress bar — the results below are about to render.
progress_slot.empty()

# Stamp the "Last run" indicator so the next rerun picks up a fresh age.
st.session_state[_DRI_LAST_RUN_AT] = time.time()

# ---------------------------------------------------------------------------
# Render the DRI page content.
# ---------------------------------------------------------------------------
outputs.render_tab_dri_analyzer(
    merged,
    dri_sweeps=dri_sweeps,
    dri_target_size_sweeps=dri_target_size_sweeps,
    dri_cn2_sweeps=dri_cn2_sweeps,
    dri_frozen=dri_frozen,
    dri_heatmap_runner=run_dri_heatmap_cached,
)

_render_footer()
