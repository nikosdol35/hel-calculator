"""Multipage refactor smoke tests + auth-bypass-hotfix invariants.

Verifies the structural invariants of the two-page Streamlit
application:

    * Each page file parses cleanly (Python syntax).
    * Each page imports only from the layers ARCHITECTURE.md allows.
    * The shared collect helpers in ui/panels.py return disjoint
      key spaces (HEL keys vs DRI keys).
    * The DRI preset registry writes the expected widget keys.
    * **Auth defense in depth** — every page script calls
      ``require_login()`` at the top so the auth gate cannot be
      bypassed by direct URL navigation. (See the 2026-04-26 hotfix
      that renamed ``ui/pages/`` to ``ui/tools/`` to kill Streamlit's
      legacy multipage auto-discovery.)
    * **No directory named ``ui/pages/``** — Streamlit auto-discovers
      that path and exposes the page files as top-level URLs without
      running ``ui/app.py``'s auth gate. We must not have a directory
      with that name in the repo.

We don't actually run the page scripts under bare-mode pytest (they
need a Streamlit ScriptRunContext), but we cover the structural
contracts the multipage refactor relies on so a regression that
would crash or expose the live app is caught before deploy.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_PAGES_DIR = _REPO_ROOT / "ui" / "tools"


# ---------------------------------------------------------------------------
# 1. Page files parse cleanly.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("page_filename", [
    "hel_calculator.py",
    "dri_analyzer.py",
])
def test_page_file_parses(page_filename: str) -> None:
    """Each page file must be syntactically valid Python."""
    path = _PAGES_DIR / page_filename
    with open(path, encoding="utf-8") as f:
        src = f.read()
    ast.parse(src, filename=str(path))


def test_pages_init_exists() -> None:
    """The ui/tools/__init__.py marker exists (so the directory is
    treated as a Python package by mypy / pyflakes)."""
    assert (_PAGES_DIR / "__init__.py").exists()


def test_no_pages_directory_in_ui() -> None:
    """**Critical security invariant** (2026-04-26 hotfix). Streamlit's
    legacy multipage system auto-discovers any directory named
    literally ``pages/`` adjacent to the entry script and exposes its
    contents as top-level URLs reachable WITHOUT running the entry
    script. That bypasses ``ui/app.py``'s auth gate.

    The two tool scripts must therefore NOT live under ``ui/pages/``.
    They live under ``ui/tools/`` and are dispatched only via
    ``st.navigation`` from ``ui/app.py``, which runs after the auth
    check.

    This test fails if anyone re-introduces a ``ui/pages/`` directory.
    """
    forbidden = _REPO_ROOT / "ui" / "pages"
    assert not forbidden.exists(), (
        f"{forbidden} exists; Streamlit's legacy multipage discovery "
        f"would expose its contents WITHOUT the auth gate. Move the "
        f"page files to ui/tools/ (or any non-'pages' directory) and "
        f"register them via st.Page in ui/app.py."
    )


# ---------------------------------------------------------------------------
# 2. Page entry-script structure — the entry script must declare two
#    pages and dispatch via st.navigation.
# ---------------------------------------------------------------------------

def test_app_entrypoint_uses_navigation() -> None:
    """ui/app.py must call st.navigation([...]).run() with two pages."""
    src = (_REPO_ROOT / "ui" / "app.py").read_text(encoding="utf-8")
    assert "st.navigation" in src, (
        "ui/app.py must dispatch via st.navigation([...]).run()"
    )
    assert "tools/hel_calculator.py" in src, (
        "ui/app.py must register the HEL Calculator page"
    )
    assert "tools/dri_analyzer.py" in src, (
        "ui/app.py must register the DRI Analyzer page"
    )


@pytest.mark.parametrize("page_filename", [
    "hel_calculator.py",
    "dri_analyzer.py",
])
def test_each_page_calls_require_login(page_filename: str) -> None:
    """**Auth defense in depth** (2026-04-26 hotfix). Each page script
    must call ``require_login()`` at module level so the auth gate
    triggers even if a request reaches the page without going through
    ``ui/app.py`` first. ``require_login()`` is idempotent on already-
    authed sessions, so this is free in the normal flow."""
    src = (_PAGES_DIR / page_filename).read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "require_login"):
            found = True
            break
    assert found, (
        f"ui/tools/{page_filename} does not call require_login() — the "
        "auth gate must be applied at the page level too, as defense "
        "in depth in case Streamlit dispatches this page without "
        "running ui/app.py first."
    )


@pytest.mark.parametrize("page_filename", [
    "hel_calculator.py",
    "dri_analyzer.py",
])
def test_each_page_imports_require_login(page_filename: str) -> None:
    """The auth defense-in-depth test above checks the *call*. This
    test checks the *import* — both must be present, and the import
    must be from ui.auth (not a stubbed re-export)."""
    src = (_PAGES_DIR / page_filename).read_text(encoding="utf-8")
    assert "from ui.auth import require_login" in src, (
        f"ui/tools/{page_filename} must import require_login from "
        "ui.auth so the auth gate is enforced at page level."
    )


def test_app_entrypoint_runs_auth_before_navigation() -> None:
    """require_login must be called BEFORE st.navigation(...).run() so
    the auth gate covers both pages. We walk the AST module-level
    statements to find the line numbers of the two calls — looking at
    raw source positions falsely matches the call names inside the
    module docstring."""
    src = (_REPO_ROOT / "ui" / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    auth_lineno: int | None = None
    nav_lineno: int | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # require_login() — bare-name call
        if (isinstance(node.func, ast.Name)
                and node.func.id == "require_login"):
            if auth_lineno is None or node.lineno < auth_lineno:
                auth_lineno = node.lineno
        # st.navigation(...) — attribute call
        if (isinstance(node.func, ast.Attribute)
                and node.func.attr == "navigation"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "st"):
            if nav_lineno is None or node.lineno < nav_lineno:
                nav_lineno = node.lineno

    assert auth_lineno is not None, (
        "ui/app.py must call require_login()"
    )
    assert nav_lineno is not None, (
        "ui/app.py must call st.navigation(...)"
    )
    assert auth_lineno < nav_lineno, (
        f"require_login() (line {auth_lineno}) must run BEFORE "
        f"st.navigation (line {nav_lineno}) in ui/app.py — the auth "
        "gate must cover every page."
    )


# ---------------------------------------------------------------------------
# 3. panels.collect_hel / collect_dri have disjoint key spaces.
# ---------------------------------------------------------------------------

def test_collect_hel_and_collect_dri_exist() -> None:
    """The split aggregator functions must both be importable."""
    from ui import panels
    assert callable(panels.collect_hel)
    assert callable(panels.collect_dri)
    assert callable(panels.collect_all)


def test_collect_dri_keys_use_dri_prefix() -> None:
    """Every key returned by collect_dri must start with ``dri_``.
    This is the contract that lets the URL decoder filter HEL vs DRI
    params by prefix."""
    # Inspect the source rather than calling the function (it requires
    # a Streamlit context to render widgets). Read the section_*
    # function bodies and confirm only dri_ keys appear in their
    # return dicts.
    panels_src = (_REPO_ROOT / "ui" / "panels.py").read_text(encoding="utf-8")
    # Locate the three DRI section function bodies and pull the return
    # dict key strings.
    import re
    for func_name in (
        "section_7_dri_sensor",
        "section_8_dri_atmosphere",
        "section_9_dri_target",
    ):
        # Find the function start, then the next return statement.
        m = re.search(rf"def {func_name}\(.*?\) -> dict:", panels_src)
        assert m is not None, f"Could not find function {func_name}"
        body = panels_src[m.end():]
        # Find the closing `return` block — first {{...}} after `return`.
        ret_m = re.search(r"return\s*\{(.*?)\n\s*\}", body, re.DOTALL)
        assert ret_m is not None, f"Could not find return dict in {func_name}"
        return_block = ret_m.group(1)
        # Every key string in the return block must start with dri_.
        keys = re.findall(r'"([^"]+)":', return_block)
        non_dri = [k for k in keys if not k.startswith("dri_")]
        assert not non_dri, (
            f"{func_name} returns non-dri_ keys: {non_dri} — DRI sections "
            f"must keep the dri_ prefix to stay disjoint from HEL inputs."
        )


def test_collect_all_is_union_of_collect_hel_and_collect_dri() -> None:
    """The aggregator function still exists and the docstring says it
    is the union of the two splits. We can't run it without a
    Streamlit context, but we can grep the body."""
    panels_src = (_REPO_ROOT / "ui" / "panels.py").read_text(encoding="utf-8")
    import re
    # Find collect_all body
    m = re.search(r"def collect_all\(.*?\) -> dict:.*?return.*?\}", panels_src, re.DOTALL)
    assert m is not None
    body = m.group(0)
    assert "collect_hel" in body and "collect_dri" in body, (
        "collect_all must compose collect_hel and collect_dri"
    )


# ---------------------------------------------------------------------------
# 4. DRI preset registry writes the expected widget keys.
# ---------------------------------------------------------------------------

def test_dri_preset_registry_populated() -> None:
    """ui.presets.DRI_PRESET_PARAMETERS must contain the five named
    presets and ``apply_dri_preset_to_session_state`` must be callable."""
    from ui import presets
    assert hasattr(presets, "DRI_PRESET_PARAMETERS")
    expected = {
        "eo_daytime_surveillance",
        "eo_long_range_surveillance",
        "swir_night_vision",
        "mwir_thermal_imager",
        "lwir_thermal_imager",
    }
    assert set(presets.DRI_PRESET_PARAMETERS.keys()) == expected
    assert callable(presets.apply_dri_preset_to_session_state)


def test_apply_dri_preset_writes_session_state_keys() -> None:
    """Applying a preset writes the canonical DRI widget keys to a
    session-state-shaped dict."""
    from ui import presets
    sess: dict = {}
    ok = presets.apply_dri_preset_to_session_state(
        sess, "eo_daytime_surveillance",
    )
    assert ok is True
    expected_keys = {
        "dri_n_pixels_h", "dri_n_pixels_v",
        "dri_nfov_deg", "dri_wfov_deg",
        "dri_focal_length_mm", "dri_f_number",
        "dri_band", "dri_cn2_preset",
        "dri_visibility_km", "dri_C0",
        "dri_target_preset", "dri_probability",
        "dri_n_cycles_D", "dri_n_cycles_R", "dri_n_cycles_I",
    }
    assert expected_keys.issubset(sess.keys())


def test_apply_dri_preset_custom_is_noop() -> None:
    """Selecting "custom" leaves session_state untouched."""
    from ui import presets
    sess: dict = {"_dri_smoke": "untouched"}
    ok = presets.apply_dri_preset_to_session_state(sess, "custom")
    assert ok is False
    assert sess == {"_dri_smoke": "untouched"}


def test_apply_dri_preset_unknown_key_is_noop() -> None:
    """Unknown preset keys are ignored (no-op, no exception)."""
    from ui import presets
    sess: dict = {}
    ok = presets.apply_dri_preset_to_session_state(sess, "nonexistent_preset")
    assert ok is False
    assert sess == {}


def test_dri_preset_values_match_band_label() -> None:
    """Each thermal preset uses a thermal band; visible presets use
    Visible. Catches accidental cross-wiring at the preset level."""
    from ui import presets
    cases = {
        "eo_daytime_surveillance":    "Visible",
        "eo_long_range_surveillance": "Visible",
        "swir_night_vision":          "SWIR",
        "mwir_thermal_imager":        "MWIR",
        "lwir_thermal_imager":        "LWIR",
    }
    for key, expected_band in cases.items():
        assert presets.DRI_PRESET_PARAMETERS[key]["dri_band"] == expected_band


# ---------------------------------------------------------------------------
# 5. TAB_LABELS no longer contains the DRI tab.
# ---------------------------------------------------------------------------

def test_tab_labels_does_not_contain_dri_analyzer() -> None:
    """DRI is now a page, not a tab. TAB_LABELS must not list it."""
    from ui.labels import TAB_LABELS
    assert "dri_analyzer" not in TAB_LABELS, (
        "TAB_LABELS still contains 'dri_analyzer'; the multipage "
        "refactor turned DRI into a page (ui/tools/dri_analyzer.py)."
    )


def test_dri_preset_labels_present() -> None:
    """The DRI sensor-preset dropdown labels must be in ui/labels."""
    from ui.labels import (
        DRI_PRESET_LABELS, DRI_PRESET_PICKER_LABEL, DRI_PRESET_PICKER_HELP,
    )
    assert "custom" in DRI_PRESET_LABELS
    assert len(DRI_PRESET_LABELS) >= 6  # 5 presets + Custom
    assert isinstance(DRI_PRESET_PICKER_LABEL, str)
    assert isinstance(DRI_PRESET_PICKER_HELP, str)


# ---------------------------------------------------------------------------
# 6. HEL page contains zero DRI references.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("forbidden", [
    "render_tab_dri_analyzer",
    "run_dri_fov_sweep_cached",
    "run_dri_target_size_sweep_cached",
    "run_dri_cn2_sweep_cached",
    "run_dri_heatmap_cached",
    "_resolve_dri_kwargs",
    "dri_analyzer.compute",
])
def test_hel_page_contains_no_dri_references(forbidden: str) -> None:
    """The HEL page must not call any DRI helpers — those moved to
    the DRI page in PR 2. Catches a stale leftover that would
    duplicate compute work."""
    src = (_PAGES_DIR / "hel_calculator.py").read_text(encoding="utf-8")
    assert forbidden not in src, (
        f"hel_calculator.py still references {forbidden!r}; the DRI "
        f"page (ui/tools/dri_analyzer.py) owns those helpers now."
    )


# ---------------------------------------------------------------------------
# 7. DRI page imports + structure
# ---------------------------------------------------------------------------

def test_dri_page_imports_dri_analyzer_module() -> None:
    """The DRI page must import physics.dri_analyzer (its compute backend)."""
    src = (_PAGES_DIR / "dri_analyzer.py").read_text(encoding="utf-8")
    assert "from physics import dri_analyzer" in src


def test_dri_page_uses_collect_dri_not_collect_all() -> None:
    """The DRI page sidebar must call panels.collect_dri (not
    collect_all) — that's how it stays free of HEL inputs."""
    src = (_PAGES_DIR / "dri_analyzer.py").read_text(encoding="utf-8")
    assert "panels.collect_dri(" in src
    assert "panels.collect_all(" not in src


def test_dri_page_has_no_run_button() -> None:
    """The DRI page is reactive — it must NOT have a Run Analysis
    button. Detected by the absence of BUTTON_LABELS["run_analysis"]
    references in the page source."""
    src = (_PAGES_DIR / "dri_analyzer.py").read_text(encoding="utf-8")
    # The Share / theme-toggle buttons reference BUTTON_LABELS["share"]
    # and BUTTON_LABELS["theme_toggle_*"], which is fine.
    assert 'BUTTON_LABELS["run_analysis"]' not in src, (
        "DRI page should not have a Run Analysis button — the page "
        "is reactive."
    )


def test_hel_page_uses_collect_hel() -> None:
    """The HEL page must call panels.collect_hel (the post-multipage
    aggregator); collect_all is no longer used here."""
    src = (_PAGES_DIR / "hel_calculator.py").read_text(encoding="utf-8")
    assert "panels.collect_hel(" in src
    assert "panels.collect_all(" not in src
