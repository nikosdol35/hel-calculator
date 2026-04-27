"""End-to-end Streamlit ``AppTest`` for the Engagement tab.

Regression guards for the 2026-04-26 user-reported bug pair:

1. **Compute envelope click did nothing** — the button-click handler
   set ``ss[job_key]`` but Streamlit fragments do NOT auto-rerun on
   ``st.session_state`` mutations. The spinner only appeared on the
   next 2-second polling tick (``@st.fragment(run_every="2s")``).
   Fix: explicit ``st.rerun(scope="fragment")`` in the Compute click
   handler. Test guard: ``test_compute_envelope_button_click_triggers_spinner``.

2. **Run Analysis took 30-60 seconds** — sweep ran 30 full
   v2-trajectory chains sequentially. Fix: cut ``N_samples`` 30 → 15.
   Test guard: ``test_run_analysis_completes_under_45s_on_canonical_scenario``
   (loose budget check; catches accidental ``N_samples`` bumps).

These tests use Streamlit's ``AppTest`` framework — synchronous, no
real browser, no WebSocket. ``run_every`` polling does NOT fire under
``AppTest``, so the explicit ``st.rerun`` from Fix A is essential here:
without it, the spinner test fails immediately because the polling
tick that would otherwise rescue the state never fires. This makes
the test a *direct* regression guard for Fix A specifically.

Auth gate is bypassed via ``HEL_TEST_MODE=1`` (see ``ui/auth.py``).
"""
from __future__ import annotations

import os
import time

import pytest


# Mark all tests as e2e so CI can opt in / opt out via -m.
pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _test_mode_env(monkeypatch):
    """Bypass the login gate via the HEL_TEST_MODE env var (see
    ``ui/auth.require_login``)."""
    monkeypatch.setenv("HEL_TEST_MODE", "1")


def _make_apptest():
    """Construct an ``AppTest`` for the HEL Calculator page.

    Targets ``ui/tools/hel_calculator.py`` directly (rather than
    ``ui/app.py``) because the multipage navigation isn't needed for
    a single-page test and adds an extra rerun step. Both entry
    points call ``require_login()`` at the top; the test-mode
    bypass covers both.
    """
    # Late import — Streamlit is heavy to import at test-collection time.
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file("ui/tools/hel_calculator.py", default_timeout=180)


def _click_run_analysis(at) -> None:
    """Find the Run Analysis sidebar button by label and click it.

    The button is created without an explicit ``key`` (see
    ``ui/tools/hel_calculator.py:298``), so we identify it by the
    label string from ``BUTTON_LABELS["run_analysis"]``.
    """
    matched = [b for b in at.sidebar.button if b.label == "Run Analysis"]
    if not matched:
        labels = [b.label for b in at.sidebar.button]
        raise AssertionError(
            f"Run Analysis button not found in sidebar. "
            f"Available sidebar buttons: {labels!r}"
        )
    matched[0].click()


# ---------------------------------------------------------------------------
# Smoke: the page loads without exception under AppTest.
# ---------------------------------------------------------------------------
def test_page_loads_under_test_mode():
    """The page renders without any unhandled exception when the
    test-mode auth bypass is set."""
    at = _make_apptest()
    at.run()
    assert not at.exception, (
        f"page raised under AppTest: {[e.value for e in at.exception]!r}"
    )


def test_run_analysis_button_present_and_clickable():
    """The Run Analysis button renders and is clickable. Catches
    any breakage in the sidebar's pre-Run-Analysis layout."""
    at = _make_apptest()
    at.run()
    matched = [b for b in at.sidebar.button if b.label == "Run Analysis"]
    assert len(matched) == 1, (
        f"expected 1 Run Analysis button; got "
        f"{[b.label for b in at.sidebar.button]!r}"
    )


# ---------------------------------------------------------------------------
# Regression: Compute envelope click must trigger the spinner immediately.
# ---------------------------------------------------------------------------
def test_compute_envelope_button_click_triggers_spinner():
    """Regression guard for the 2026-04-26 'Compute envelope dead' bug.

    Without Fix A's explicit ``st.rerun(scope="fragment")``, the
    Compute click sets state but the spinner only appears on the
    next 2-second polling tick. ``AppTest`` is synchronous and the
    polling tick never fires, so this test would fail without Fix A
    — exactly the regression we want to lock in.

    The first ``at.run()`` does the initial page render. ``Run
    Analysis`` triggers the orchestrator + sweep; ``at.run`` blocks
    until the script completes (the sweep is ~10-20 s on the
    canonical 3 kW scenario at ``N_samples=15``). Then the Compute
    envelope button click triggers the fragment rerun; ``at.run()``
    after the click captures the post-rerun state.
    """
    at = _make_apptest()
    at.run()
    _click_run_analysis(at)
    at.run(timeout=180)   # sweep completes here

    # Find the Compute envelope button (operational kind). The state
    # machine renders this in the engagement tab, inside the
    # operational-envelope fragment.
    compute_buttons = [
        b for b in at.button if b.key == "_envelope_btn_operational"
    ]
    assert len(compute_buttons) == 1, (
        f"expected the operational-envelope Compute button to be "
        f"present in idle state; found "
        f"{[b.key for b in at.button]!r}"
    )
    compute_buttons[0].click()
    at.run()

    # After Fix A, the explicit st.rerun(scope='fragment') triggers
    # an immediate fragment rerun that reads the new ss[job_key]
    # state and renders State C (the spinner / 'Computing in the
    # background' info card).
    info_messages = [info.value for info in at.info]
    assert any(
        "Computing in the background" in msg for msg in info_messages
    ), (
        f"expected 'Computing in the background' info card after "
        f"Compute click; got at.info={info_messages!r}. "
        f"This usually means Fix A's st.rerun(scope='fragment') "
        f"in ui/outputs.py:_envelope_state_machine State D was "
        f"removed or broken."
    )


def test_compute_envelope_pre_click_idle_state_only():
    """Sanity: before the Compute envelope button is clicked, the
    spinner / Cancel button must NOT be present. Catches accidental
    state leakage from a prior session."""
    at = _make_apptest()
    at.run()
    _click_run_analysis(at)
    at.run(timeout=180)

    # No 'Computing in the background' info messages yet.
    info_messages = [info.value for info in at.info]
    assert not any(
        "Computing in the background" in msg for msg in info_messages
    ), (
        f"unexpected spinner before Compute click — state machine may "
        f"be reading stale ss[job_key] from a prior session. "
        f"info={info_messages!r}"
    )

    # No Cancel buttons present in idle state.
    cancel_buttons = [
        b for b in at.button if b.key == "_envelope_cancel_operational"
    ]
    assert len(cancel_buttons) == 0


# ---------------------------------------------------------------------------
# Budget: Run Analysis sweep finishes well under 45 s on CI hardware.
# ---------------------------------------------------------------------------
def test_run_analysis_completes_under_45s_on_canonical_scenario():
    """Regression guard for the sweep-size budget. With
    ``N_samples=15`` on the canonical 3 kW scenario, the sweep
    should finish in well under 45 s on typical CI hardware. Catches
    accidental bumps of ``N_samples`` past 15, or per-cell M8 PDE
    cost regressions that would push the user past their patience
    threshold again.

    Tolerance is intentionally loose (45 s) — real Streamlit Cloud
    is often 1.5-3× slower than a local laptop, but 45 s on local
    leaves comfortable headroom. Tighten to 25 s once we have CI
    timing data.
    """
    at = _make_apptest()
    at.run()
    t0 = time.monotonic()
    _click_run_analysis(at)
    at.run(timeout=120)
    elapsed = time.monotonic() - t0
    assert elapsed < 45.0, (
        f"Run Analysis took {elapsed:.0f}s — sweep budget exceeded. "
        f"Did N_samples increase past 15, or did per-cell M8 PDE "
        f"cost regress? Check ui/tools/hel_calculator.py:472."
    )


# ---------------------------------------------------------------------------
# Auth-bypass safety: HEL_TEST_MODE only applies when the env var is set.
# ---------------------------------------------------------------------------
def test_auth_bypass_only_when_env_var_set(monkeypatch):
    """The HEL_TEST_MODE bypass MUST NOT engage without the explicit
    env var. Production deployments don't set this; if the bypass
    fired unconditionally, anyone could open the app.
    """
    monkeypatch.delenv("HEL_TEST_MODE", raising=False)

    # With no test-mode bypass and no st.secrets configured, the
    # login gate should halt the script (st.stop). Under AppTest,
    # this manifests as the page rendering only the login card —
    # no Run Analysis button visible.
    at = _make_apptest()
    at.run()

    # Without auth: the sidebar should NOT have the Run Analysis
    # button. (The login form lives in the main area, not the
    # sidebar.)
    run_buttons = [b for b in at.sidebar.button if b.label == "Run Analysis"]
    assert len(run_buttons) == 0, (
        "auth bypass should NOT engage without HEL_TEST_MODE=1 env var; "
        "Run Analysis button is visible without auth — security regression"
    )

    # And the main area should have the login form's password input.
    # AppTest exposes text_input under at.text_input.
    password_inputs = [
        ti for ti in at.text_input if ti.key == "_login_p"
    ]
    assert len(password_inputs) == 1, (
        "expected the login password field when auth bypass is off; "
        f"found {[ti.key for ti in at.text_input]!r}"
    )


# ---------------------------------------------------------------------------
# Cleanup: verify HEL_TEST_MODE is restored after the bypass-off test.
# ---------------------------------------------------------------------------
def test_test_mode_env_restored_after_bypass_off_test():
    """After the previous test deleted HEL_TEST_MODE, the autouse
    fixture should re-set it on the next test. Sanity check."""
    assert os.environ.get("HEL_TEST_MODE") == "1"
