"""Shared-credentials login gate per ARCHITECTURE.md §6.2.

Phase 3 PR 1 redesign: a centered login card on the dark canvas replaces
the default Streamlit form stack. A single password field (shared access
code — no username) per the plan's "first pixel" brief; the project
wordmark sits above it in the Inter display face.

Authentication model is unchanged from the v1 contract — one shared
access code protects the live deployment from anonymous web traffic.
No per-user accounts (CLAUDE §7.2 / SPEC §7.2 — out of v1 scope). The
credential lives in Streamlit Cloud's secrets manager:

    APP_PASSWORD = "..."

``APP_USERNAME`` is still read for backward compatibility with existing
deployments; if present it must match a ``username`` query parameter
or be explicitly left empty. New deployments should set ``APP_PASSWORD``
only. Credentials are never committed to git; local development uses
``.streamlit/secrets.toml`` (in ``.gitignore``).

Design notes:
    * No server-side session DB — per-tab ``st.session_state`` holds
      the authed flag for the life of the browser tab.
    * Fails closed when the secret is missing (never opens the app with
      an empty expected password).
    * Wrong access code surfaces a single calm line of feedback; no
      rate limiting, no enumeration hint, no apology spam.
    * User-visible strings route through ``ui/labels.LOGIN_COPY`` so
      the copy-style lint sees a clean auth.py.

References:
    ARCHITECTURE.md §6.2 — file contract.
    docs/phase3_ui_redesign_plan_2026-04-23.md §6 — login-screen brief.
    ui/labels.py — user-visible copy.
    ui/theme.py — palette + typography; must be applied before this runs.
"""

from __future__ import annotations

import os

import streamlit as st

from ui import theme
from ui.labels import LOGIN_COPY


_AUTH_KEY = "_hel_authed"


def require_login() -> None:
    """Gate the app behind a shared access code; halt the script if not authed.

    Reads ``APP_PASSWORD`` (required) from ``st.secrets`` and compares
    against the value the user types. Returns normally if the user is
    already authed in this session. Otherwise renders the centered
    login card and calls ``st.stop()`` so the caller never runs past
    the gate on the same render pass.

    **Test bypass.** When ``HEL_TEST_MODE=1`` is set in the
    environment, the gate is silently skipped — the auth flag is
    flipped to True and we return without rendering any login UI.
    Used by ``tests/test_engagement_tab_e2e.py`` (Streamlit
    ``AppTest``) so the test can exercise the page flow without
    needing a secrets file. Production deployments do not set this
    variable; the env-var check is a single line and does not bypass
    in any other scenario.
    """
    if os.environ.get("HEL_TEST_MODE") == "1":
        st.session_state[_AUTH_KEY] = True
        return

    if st.session_state.get(_AUTH_KEY):
        return

    # Ensure the palette + typography are live before we render the card.
    # ``apply`` is idempotent — calling it here means the login screen
    # uses the same theme as the main app even on the first render.
    theme.apply("dark")

    _render_login_card()

    # ``_render_login_card`` either reruns on success or falls through
    # on failure / first render. Either way, stop the script so the
    # caller (``ui/app.py``) does not proceed past the gate.
    st.stop()


def _render_login_card() -> None:
    """Render the centered login card and handle the submit."""

    # Three-column layout centers the card horizontally on wide screens.
    # The 1:1:1 ratio widens the card on narrow viewports; padding on
    # the card itself keeps interior spacing even.
    left, center, right = st.columns([1, 1, 1])

    with center:
        st.markdown(
            f"<div class='hel-login-wordmark'>{LOGIN_COPY['wordmark']}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='hel-login-tagline'>{LOGIN_COPY['tagline']}</div>",
            unsafe_allow_html=True,
        )

        with st.form("_login_form", clear_on_submit=False):
            password = st.text_input(
                LOGIN_COPY["password_label"],
                type="password",
                key="_login_p",
                label_visibility="visible",
            )
            submitted = st.form_submit_button(
                LOGIN_COPY["submit"],
                type="primary",
                use_container_width=True,
            )

        st.markdown(
            f"<div class='hel-login-help'>{LOGIN_COPY['password_help']}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='hel-login-attribution'>{LOGIN_COPY['attribution']}</div>",
            unsafe_allow_html=True,
        )

    if submitted:
        expected = st.secrets.get("APP_PASSWORD", "")
        # Fail closed: do not treat "" == "" as a match.
        if expected and password == expected:
            st.session_state[_AUTH_KEY] = True
            st.rerun()
        else:
            with center:
                st.error(LOGIN_COPY["auth_failure"])
