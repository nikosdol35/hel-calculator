"""Shared-credentials login gate per ARCHITECTURE.md §6.2.

The v1 HEL calculator does not support per-user accounts (CLAUDE §7.2);
a single shared username/password protects the live deployment from
anonymous web traffic. Credentials live in Streamlit Cloud's secrets
manager (Settings → Secrets in the web UI) under:

    APP_USERNAME = "..."
    APP_PASSWORD = "..."

They are never committed to git. Local development can set them via
``.streamlit/secrets.toml`` (which is in ``.gitignore``).

Design:
    * No server-side session DB — Streamlit's per-session
      ``st.session_state`` holds the "authed" flag for the life of
      the browser tab.
    * Wrong credentials surface a generic "Invalid credentials"
      message (no enumeration hint).
    * If the deployment is missing secrets entirely, login fails
      closed (never opens the app with empty expected values).
    * ``require_login`` halts the script via ``st.stop()`` when the
      user is not authed — the caller (``ui/app.py``) should invoke
      it at the top of every page render.

References:
    ARCHITECTURE.md §6.2 — file contract, ~30 lines.
    CLAUDE §7.2 — "User accounts" is out of v1 scope; shared creds only.
"""

from __future__ import annotations

import streamlit as st


_AUTH_KEY = "_hel_authed"


def require_login() -> None:
    """Gate the app behind shared credentials; halt the script if not authed.

    Reads ``APP_USERNAME`` and ``APP_PASSWORD`` from ``st.secrets``.
    Returns normally if the user is already authed in this session.
    Otherwise renders a login form, and on successful submit sets the
    session-state flag and reruns; on failure or first render (before
    submit), calls ``st.stop()`` so the calling module never runs past
    the gate.
    """
    if st.session_state.get(_AUTH_KEY):
        return

    st.title("HEL Engineering Calculator")
    st.caption("Sign in to continue.")

    with st.form("_login_form", clear_on_submit=False):
        username = st.text_input("Username", key="_login_u")
        password = st.text_input("Password", type="password", key="_login_p")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        expected_u = st.secrets.get("APP_USERNAME", "")
        expected_p = st.secrets.get("APP_PASSWORD", "")
        # Fail closed if secrets are missing: do not treat "" == "" as valid.
        if expected_u and expected_p and username == expected_u and password == expected_p:
            st.session_state[_AUTH_KEY] = True
            st.rerun()
        else:
            st.error("Invalid credentials.")

    st.stop()
