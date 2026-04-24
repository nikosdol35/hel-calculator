"""Copy-style lint: forbidden tokens in user-facing UI strings.

Phase 3 PR 1 adds this test to codify the voice-and-tone rules from
``docs/phase3_ui_redesign_plan_2026-04-23.md`` §"Voice and tone":

  * No emoji anywhere in user-visible copy.
  * No internal contract citations (``SPEC §``, ``ARCH §``, the
    ``SPEC.md`` / ``ARCHITECTURE.md`` filenames).
  * No pre-v1.6 chrome naming (``Panel A/B/C/D/E/F``, ``Plot A/B/C``).
  * No module tags (``M6↔M7``, ``M1 → M10``) as user-visible module
    references.

The test walks the AST of each scanned file, collects every string
literal, excludes module / function / class docstrings (where SPEC /
ARCH citations are legitimate maintainer references), and checks the
remaining strings for forbidden substrings and emoji codepoints.

Scoped files (PR 1): the four user-visible UI entry points.
    ui/app.py, ui/auth.py, ui/panels.py, ui/outputs.py

Deliberately NOT scanned:
    ui/labels.py  — this IS the source of truth for user copy; lint
                    would be circular.
    ui/theme.py   — CSS strings contain no user copy.
    ui/icons.py   — SVG path data only.
    ui/style.py   — compatibility shim (to be deleted in PR 2).
    ui/plots.py   — will be folded into this lint in PR 4; PR 1 does
                    a minimal title scrub but leaves the full clean-up
                    for the plot-theme PR.
    ui/components.py, ui/presets.py — do not exist yet (PR 2, PR 6).

When PR 4 / PR 6 land, extend ``SCANNED_FILES`` below to cover them.

References:
    docs/phase3_ui_redesign_plan_2026-04-23.md § "Voice and tone".
    SPEC.md §5.3 item 11 — copy-style lint behavioral commitment.
    CLAUDE.md §5.1 — test-authoring conventions.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_UI_DIR = _REPO_ROOT / "ui"


# -----------------------------------------------------------------------------
# Scope: which UI files are audited by this lint.
# -----------------------------------------------------------------------------
SCANNED_FILES: tuple[Path, ...] = (
    _UI_DIR / "app.py",
    _UI_DIR / "auth.py",
    _UI_DIR / "panels.py",
    _UI_DIR / "outputs.py",
)


# -----------------------------------------------------------------------------
# Forbidden substrings (checked case-insensitively — matches "spec §" too).
# -----------------------------------------------------------------------------
FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "SPEC §",
    "ARCH §",
    "ARCHITECTURE §",
    "SPEC.md",
    "ARCHITECTURE.md",
    "Panel A",
    "Panel B",
    "Panel C",
    "Panel D",
    "Panel E",
    "Panel F",
    "Plot A",
    "Plot B",
    "Plot C",
)


# -----------------------------------------------------------------------------
# Module-tag regex (e.g. "M6", "M10", "M1 → M10"). Matches a standalone
# capital M followed by 1-2 digits; requires a word boundary on each side
# so variable names like ``M2`` used as a dict key or Greek-letter strings
# (``M²`` — the ² is not a digit character class member) are not flagged.
# ``M²`` is permitted because ² (U+00B2) is not a [0-9] class member.
# -----------------------------------------------------------------------------
MODULE_TAG_RE = re.compile(r"\bM\d{1,2}\b")


# -----------------------------------------------------------------------------
# Emoji detection. Covers:
#   U+25A0-U+25FF  Geometric Shapes      (▶ ■ ● ◆)
#   U+2600-U+27BF  Misc Symbols + Dingbats (☀ ⚙ ✓ ✗ ✦)
#   U+1F000-U+1FAFF Plane 1 pictograph blocks (🔦 🎯 📐 🌫 🛡 🔗 …)
#
# Deliberately does not include the Basic Multilingual Plane below U+25A0,
# so Greek letters (α β θ σ τ λ), micro sign (µ), degree sign (°), super-
# script digits (¹ ² ³), multiplication sign (×), etc. are all permitted.
# -----------------------------------------------------------------------------
EMOJI_RE = re.compile(
    "["
    "\u25A0-\u25FF"
    "\u2600-\u27BF"
    "\U0001F000-\U0001FAFF"
    "]"
)


# =============================================================================
# Helpers
# =============================================================================

def _collect_docstring_constants(tree: ast.AST) -> set[int]:
    """Return a set of ``id()`` values for every AST Constant node that is
    the module-, class-, or function-level docstring. These are excluded
    from the forbidden-substring check.
    """
    docstring_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node,
            (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstring_ids.add(id(first.value))
    return docstring_ids


def _iter_string_constants(tree: ast.AST, skip_ids: set[int]):
    """Yield every ``ast.Constant`` node whose value is ``str`` and whose
    ``id()`` is not in ``skip_ids``. Covers plain string literals, f-string
    literal parts (as ``ast.Constant`` children of ``ast.JoinedStr``), and
    concatenated string constants folded by the parser."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skip_ids
        ):
            yield node


def _violations_in_file(path: Path) -> list[str]:
    """Return a list of human-readable violation messages for one file."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    docstring_ids = _collect_docstring_constants(tree)

    violations: list[str] = []
    for node in _iter_string_constants(tree, docstring_ids):
        text = node.value
        line = node.lineno

        for needle in FORBIDDEN_SUBSTRINGS:
            if needle.lower() in text.lower():
                violations.append(
                    f"{path.name}:{line}  forbidden substring {needle!r} "
                    f"in string literal"
                )

        m = MODULE_TAG_RE.search(text)
        if m:
            violations.append(
                f"{path.name}:{line}  module tag {m.group()!r} in user "
                f"copy — reference the module by its user-facing name instead"
            )

        e = EMOJI_RE.search(text)
        if e:
            # Report the codepoint so a reviewer can identify the glyph
            # even if their terminal does not render it.
            codepoint = f"U+{ord(e.group()):04X}"
            violations.append(
                f"{path.name}:{line}  emoji {e.group()!r} ({codepoint}) "
                f"in user copy — use a Lucide icon via ui/icons.py instead"
            )

    return violations


# =============================================================================
# Tests
# =============================================================================

@pytest.mark.parametrize(
    "path",
    SCANNED_FILES,
    ids=[p.name for p in SCANNED_FILES],
)
def test_no_forbidden_tokens_in_user_copy(path: Path) -> None:
    """Each scanned file must be free of forbidden tokens in string literals
    (docstrings excluded). One failing file reports all its violations so
    the author fixes them in a single pass rather than whack-a-mole."""
    assert path.exists(), f"SCANNED_FILES lists {path} but it does not exist"
    violations = _violations_in_file(path)
    if violations:
        pytest.fail(
            f"{path.name}: copy-style violations found:\n  "
            + "\n  ".join(violations)
        )


def test_scan_list_covers_phase3_pr1_surface() -> None:
    """Guard: ensure the scan list actually names the four PR 1 entry
    points. If someone deletes an entry accidentally, the per-file test
    disappears silently without this check."""
    expected_names = {"app.py", "auth.py", "panels.py", "outputs.py"}
    actual_names = {p.name for p in SCANNED_FILES}
    assert expected_names == actual_names, (
        f"SCANNED_FILES drift: expected {expected_names}, got {actual_names}. "
        "If you are adding a file (e.g. PR 4 brings plots.py into scope), "
        "update the expected_names set in this guard too."
    )
