"""Streamlit entry point — multipage shell.

Streamlit Cloud launches this file via ``streamlit run ui/app.py``. As
of the multipage refactor (PR 1 of the multipage campaign) this file
is a thin shell that handles four cross-cutting concerns shared by
every tool:

1. ``sys.path`` shim so ``from physics import ...`` resolves when
   Streamlit Cloud sets ``sys.path[0]`` to ``<repo>/ui/``.
2. ``st.set_page_config(...)`` — must be the first Streamlit call.
3. Theme bootstrap (palette + Plotly template + CSS) via
   ``ui.theme.apply``. Honours the ``_app_mode`` session-state key so
   the per-page sidebar toggle can flip dark / light at runtime.
4. Auth gate (``ui/auth.require_login``) — one shared sign-in covers
   every tool exposed by ``st.navigation``.

After those four concerns are handled, this file declares the two
pages (HEL Calculator and DRI Analyzer) and dispatches via Streamlit's
native ``st.navigation`` API. Each page is a self-contained script
under ``ui/pages/`` with its own sidebar, its own state, its own
content area. Switching between them preserves ``st.session_state``,
so the user can move between tools without losing their input edits.

In multipage PR 1 only the HEL Calculator page is registered; the
DRI Analyzer still ships as a tab on the HEL page. PR 2 adds the
sibling DRI page and removes the DRI tab.

References:
    ui/pages/hel_calculator.py — HEL Calculator page (sidebar, tabs,
        Run Analysis, share-URL, the seven HEL tabs).
    ui/auth.py — shared-credentials login.
    ui/theme.py — palette + CSS + Plotly template.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# sys.path shim — MUST run before any ``physics`` or ``ui`` import.
#
# ``streamlit run ui/app.py`` (Streamlit Cloud's invocation per ARCH §6.1)
# sets ``sys.path[0]`` to this file's directory, i.e. ``<repo>/ui/`` —
# NOT the repo root. From that vantage ``from physics import ...``
# resolves to ``<repo>/ui/physics/`` and raises ``ModuleNotFoundError``.
#
# Prepending the repo root here makes every sibling package (``physics``,
# ``ui``) importable without touching Cloud's "Main file path" setting
# or requiring a top-level shim file. Local pytest is unaffected
# because pytest discovers the repo root from ``tests/conftest.py``.
# ---------------------------------------------------------------------------
import sys as _sys
from pathlib import Path as _Path

_REPO_ROOT = str(_Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in _sys.path:
    _sys.path.insert(0, _REPO_ROOT)

from typing import Literal

import streamlit as st

from ui import theme
from ui.auth import require_login


# ---------------------------------------------------------------------------
# Page config + theme bootstrap + auth gate.
# These must run before any widget; they are the cross-cutting concerns
# every page inherits.
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="HEL Engineering Calculator",
    layout="wide",
)

_APP_MODE_KEY = "_app_mode"
_mode_raw = st.session_state.get(_APP_MODE_KEY, "dark")
app_mode: Literal["dark", "light"] = (
    "light" if _mode_raw == "light" else "dark"
)
theme.apply(app_mode)
require_login()


# ---------------------------------------------------------------------------
# Page registration + dispatch.
# ---------------------------------------------------------------------------
# Streamlit's ``st.navigation`` looks up each page script by relative
# path (relative to the working directory, which Streamlit sets to the
# repo root when launched as ``streamlit run ui/app.py``). The default
# page renders when the user lands on the bare URL.
hel_page = st.Page(
    "pages/hel_calculator.py",
    title="HEL Calculator",
    icon=":material/cell_tower:",
    default=True,
)

# DRI page is added in PR 2 of the multipage campaign. Until then the
# DRI Analyzer ships as a tab inside the HEL page so the user-visible
# behaviour is unchanged from the pre-refactor app.
pages = [hel_page]

pg = st.navigation(pages)
pg.run()
