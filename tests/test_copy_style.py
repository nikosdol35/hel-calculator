"""Copy-style lint: forbidden tokens in user-facing UI strings.

Phase 3 PR 1 added this test to codify the voice-and-tone rules from
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

Scoped files (PR 2): the five user-visible UI surfaces.
    ui/app.py, ui/auth.py, ui/panels.py, ui/outputs.py, ui/components.py

Deliberately NOT scanned:
    ui/labels.py  — this IS the source of truth for user copy; lint
                    would be circular.
    ui/theme.py   — CSS strings contain no user copy.
    ui/icons.py   — SVG path data only.
    ui/plots.py   — will be folded into this lint in PR 4; PR 1 did
                    a minimal title scrub but the full clean-up lives
                    in the plot-theme PR.
    ui/presets.py — does not exist yet (PR 6).

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
    _UI_DIR / "components.py",
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
# Module-tag regex (e.g. "M6↔M7", "M1 → M10", "per M6 tolerance"). Matches a
# standalone capital M followed by 1-2 digits with word boundaries on each
# side. Two things are deliberately exempt from the match result:
#
#   1. Strings that are EXACTLY the module tag — e.g. ``"M2"`` as a dict key
#      or a function argument to ``input_label("M2")``. These are SPEC-dict
#      identifiers, not user-visible copy. See ``_is_identifier_literal``.
#   2. Greek letters, the micro sign µ, degrees °, superscript ² / ³, ×, etc.
#      ``M²`` is permitted because ² (U+00B2) is not a [0-9] class member.
#
# The rule catches what matters — module tags embedded in prose like
# "M6↔M7 loop converged" — without flagging the bare SPEC keys every UI
# module has to pass around.
# -----------------------------------------------------------------------------
MODULE_TAG_RE = re.compile(r"\bM\d{1,2}\b")


def _is_identifier_literal(text: str, match: re.Match[str]) -> bool:
    """Return True when the match spans the entire (stripped) string.

    A literal like ``"M2"`` appearing as a dict key or a lookup argument is a
    SPEC-dict identifier, not a piece of user-facing copy; the module-tag
    rule should skip it. A literal like ``"M6↔M7 loop converged"`` contains
    the tag inside a longer sentence, so the rule fires as intended.
    """
    return text.strip() == match.group()


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
        if m and not _is_identifier_literal(text, m):
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


def test_scan_list_covers_phase3_pr2_surface() -> None:
    """Guard: ensure the scan list actually names the five PR 2 entry
    points. If someone deletes an entry accidentally, the per-file test
    disappears silently without this check."""
    expected_names = {
        "app.py", "auth.py", "panels.py", "outputs.py", "components.py",
    }
    actual_names = {p.name for p in SCANNED_FILES}
    assert expected_names == actual_names, (
        f"SCANNED_FILES drift: expected {expected_names}, got {actual_names}. "
        "If you are adding a file (e.g. PR 4 brings plots.py into scope), "
        "update the expected_names set in this guard too."
    )


def test_module_tag_rule_discriminates_identifier_vs_prose(tmp_path: Path) -> None:
    """Guard on the ``_is_identifier_literal`` exemption. A bare ``"M2"``
    string (SPEC dict key) must NOT be flagged; a module tag embedded in a
    longer sentence (e.g. ``"M6↔M7 loop converged"``) MUST be flagged.

    If someone widens the exemption — say, by stripping whitespace too
    aggressively or by matching substrings — real violations will silently
    slip through. This test pins the discrimination.
    """
    sample = tmp_path / "sample.py"
    sample.write_text(
        # Lines 1-2: identifier-style literals — all exempt.
        'x = {"M2": 1.0, "M6": 2.0}\n'
        'y = lookup("M10")\n'
        # Lines 3-5: prose-style literals — all flagged.
        'a = "M6↔M7 loop converged"\n'
        'b = "per SPEC §3 M6 tolerance"\n'
        'c = "M1 → M10 pipeline"\n',
        encoding="utf-8",
    )
    violations = _violations_in_file(sample)
    # "SPEC §" also trips the forbidden-substring rule on line 4; strip those
    # out and count only module-tag messages so this test stays focused.
    tag_violations = [v for v in violations if "module tag" in v]
    # Expect exactly three: one per prose literal (lines 3, 4, 5).
    assert len(tag_violations) == 3, (
        f"Expected 3 module-tag violations (one per prose literal), got "
        f"{len(tag_violations)}:\n  " + "\n  ".join(tag_violations)
    )
    # The violation message format is
    #   "{path.name}:{line}  module tag '{tag}' in user copy — …"
    # so the cheapest invariant is that each violation references one of the
    # prose-literal line numbers (3, 4, 5) and none of them references the
    # identifier-literal line numbers (1, 2).
    prose_line_prefixes = {"sample.py:3", "sample.py:4", "sample.py:5"}
    identifier_line_prefixes = {"sample.py:1", "sample.py:2"}
    for v in tag_violations:
        assert any(v.startswith(p) for p in prose_line_prefixes), (
            f"Tag violation should reference a prose line (3/4/5) of the "
            f"sample file, got: {v}"
        )
        assert not any(v.startswith(p) for p in identifier_line_prefixes), (
            f"Tag violation flags an identifier-literal line (exemption may "
            f"be broken): {v}"
        )
