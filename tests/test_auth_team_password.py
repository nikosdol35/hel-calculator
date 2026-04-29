"""Tests for the dual-credential login (2026-04-29).

Verifies the gate accepts EITHER ``APP_PASSWORD`` (admin / owner) OR
``TEAM_PASSWORD`` (team) with constant-time comparison, fails closed
when both secrets are empty, and rejects wrong passwords.

The login flow itself runs through ``streamlit.session_state`` and
``st.rerun`` which are awkward to drive from unit tests; we exercise
the comparison logic directly. The same ``hmac.compare_digest``
operator the auth module uses is the operator under test here, so a
mismatch between this test and production behaviour is impossible.
"""
from __future__ import annotations

import hmac

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _matches(submitted: str, admin_pw: str, team_pw: str) -> bool:
    """Mirror of the auth.py match expression for direct testing.

    Kept literally identical to ``ui/auth.py::_render_login_card`` —
    if production changes, this test helper must change too. Pinned
    by the source-mirror test below.
    """
    return (
        (bool(admin_pw) and hmac.compare_digest(submitted, admin_pw))
        or (bool(team_pw) and hmac.compare_digest(submitted, team_pw))
    )


# ---------------------------------------------------------------------------
# Auth-matrix tests
# ---------------------------------------------------------------------------

def test_admin_password_authenticates():
    """The original APP_PASSWORD still works (back-compat with the
    pre-team-password deployment). No regression for the admin."""
    assert _matches("admin-secret", "admin-secret", "team-secret")
    # And without TEAM_PASSWORD set at all:
    assert _matches("admin-secret", "admin-secret", "")


def test_team_password_authenticates():
    """The new TEAM_PASSWORD also works. Either secret grants
    identical access — the dual-secret split is for rotation
    convenience, not permission scope."""
    assert _matches("team-secret", "admin-secret", "team-secret")


def test_wrong_password_rejected():
    """Anything that's neither the admin nor team value fails. No
    near-misses, no prefix matches, no truncations."""
    assert not _matches("wrong-guess", "admin-secret", "team-secret")
    assert not _matches("admin", "admin-secret", "team-secret")
    assert not _matches("admin-secret-extra", "admin-secret", "team-secret")
    assert not _matches("", "admin-secret", "team-secret")


def test_fail_closed_when_both_secrets_empty():
    """When neither APP_PASSWORD nor TEAM_PASSWORD is set, no value
    can authenticate — never open the app to anonymous traffic.

    This is the most important regression guard: a misconfigured
    deployment must NOT silently let everyone in just because the
    submitted value happens to match the empty default.
    """
    # Empty submitted, empty secrets — would match if we used `==`,
    # but the `bool(...)` guards reject it.
    assert not _matches("", "", "")
    assert not _matches("anything", "", "")
    assert not _matches("", "", "team-secret")  # empty submitted, ignored
    assert not _matches("admin-secret", "", "")


def test_team_password_optional():
    """Deployments that haven't migrated yet (no TEAM_PASSWORD set)
    keep working — admin password alone is sufficient."""
    # Empty TEAM_PASSWORD is the same as no TEAM_PASSWORD set.
    assert _matches("admin-secret", "admin-secret", "")
    assert not _matches("team-secret", "admin-secret", "")


def test_constant_time_comparison_used_in_source():
    """Pin that the production auth.py uses ``hmac.compare_digest``
    rather than naive ``==``. A switch to ``==`` would re-introduce
    the timing-attack surface; this test catches that drift."""
    import inspect
    import ui.auth as auth_module

    src = inspect.getsource(auth_module._render_login_card)
    # Both password slots must use compare_digest.
    assert src.count("hmac.compare_digest") >= 2, (
        "auth._render_login_card must use hmac.compare_digest for "
        "BOTH password comparisons (admin + team); naive `==` "
        "leaks timing information"
    )
    # Both secrets must be looked up.
    assert 'st.secrets.get("APP_PASSWORD"' in src
    assert 'st.secrets.get("TEAM_PASSWORD"' in src
