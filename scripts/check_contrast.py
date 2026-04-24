"""One-shot WCAG 2.1 AA contrast verifier for the HEL calculator palette.

Reads ``PALETTE_DARK`` and ``PALETTE_LIGHT`` from ``ui/theme.py`` and
audits every foreground-on-background token pair the UI actually uses.
Prints a human-readable report and exits non-zero if any pair falls
below its documented WCAG threshold.

Scope: audit-only. Not in CI — the palette is stable once the plan is
accepted; running this script after any palette edit is sufficient.

WCAG 2.1 relative-luminance formula (per W3C TR/WCAG21/#dfn-relative-luminance):

    L = 0.2126 R + 0.7152 G + 0.0722 B

where each channel c ∈ {R, G, B} is linearised from the sRGB value
s ∈ [0, 1] via:

    c = s / 12.92                       if s ≤ 0.03928
    c = ((s + 0.055) / 1.055) ** 2.4     otherwise

Contrast ratio between two luminances L1 (lighter) and L2 (darker):

    (L1 + 0.05) / (L2 + 0.05)

WCAG 2.1 AA thresholds:

    Normal body text         ≥ 4.5
    Large text (≥18pt / ≥14pt bold) or UI component ≥ 3.0

AAA thresholds are ≥ 7.0 / ≥ 4.5 respectively — informational only; we
do not gate on AAA per the plan.

Usage:
    python scripts/check_contrast.py

    Exit code is zero when every pair in ``PAIRS`` meets its required
    minimum; non-zero otherwise.

References:
    docs/phase3_ui_redesign_plan_2026-04-23.md §"Palette justification
        and color audit" — the required-minimum table this script
        implements.
    SPEC.md §5.3 item 8 — contrast audit one-shot commitment.
    ARCHITECTURE.md §6.8 — ``ui/theme.py`` palette contract.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal, NamedTuple

# Ensure the repo root is on sys.path so we can import ui.theme when the
# script is invoked directly from inside scripts/.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ui.theme import PALETTE_DARK, PALETTE_LIGHT  # noqa: E402


# =============================================================================
# Low-level colour math
# =============================================================================

def _hex_to_srgb(hex_str: str) -> tuple[float, float, float]:
    """Convert ``"#RRGGBB"`` to a 0-1 sRGB triplet."""
    s = hex_str.lstrip("#")
    if len(s) != 6:
        raise ValueError(f"Expected #RRGGBB, got {hex_str!r}")
    r = int(s[0:2], 16) / 255.0
    g = int(s[2:4], 16) / 255.0
    b = int(s[4:6], 16) / 255.0
    return r, g, b


def _linearise(channel: float) -> float:
    """sRGB → linear-RGB per WCAG 2.1."""
    if channel <= 0.03928:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_str: str) -> float:
    """Relative luminance per WCAG 2.1."""
    r, g, b = _hex_to_srgb(hex_str)
    rl = _linearise(r)
    gl = _linearise(g)
    bl = _linearise(b)
    return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl


def _contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """WCAG 2.1 contrast ratio between two colours, either order."""
    l_fg = _relative_luminance(fg_hex)
    l_bg = _relative_luminance(bg_hex)
    lighter, darker = (l_fg, l_bg) if l_fg > l_bg else (l_bg, l_fg)
    return (lighter + 0.05) / (darker + 0.05)


# =============================================================================
# Audit table
# =============================================================================

_TextScope = Literal["body", "large", "ui"]


class Pair(NamedTuple):
    """One fg-on-bg audit entry."""
    fg_token: str
    bg_token: str
    scope: _TextScope   # body → AA ≥4.5 | large → AA ≥3.0 | ui → AA ≥3.0
    description: str    # where in the UI this pair is used


# Token pairs the UI actually renders. Keep aligned with the §3.1 palette
# justification table; reviewers should be able to trace every row back to
# a concrete place the colour appears on screen.
PAIRS: tuple[Pair, ...] = (
    # Primary body copy
    Pair("fg.primary",     "bg.base",    "body",  "Body, headings, big numerics on app canvas"),
    Pair("fg.primary",     "bg.surface", "body",  "Card body, big numerics inside cards"),
    # Labels, captions
    Pair("fg.secondary",   "bg.base",    "body",  "Section labels, captions on canvas"),
    Pair("fg.secondary",   "bg.surface", "body",  "Labels inside cards"),
    # Tertiary — scope-limited to ≥18 px use only
    Pair("fg.tertiary",    "bg.base",    "large", "Axis ticks, helper hints — ≥18px scope only"),
    Pair("fg.tertiary",    "bg.surface", "large", "Disabled text on cards — ≥18px scope only"),
    # Accent — active tab, focus ring, primary button text on dark bg
    Pair("accent.primary", "bg.base",    "ui",    "Active tab underline, focus ring, links"),
    Pair("accent.primary", "bg.surface", "ui",    "Link text inside cards"),
    # Data series (hue + dash + marker encodes — colour still must meet AA for
    # line-plot rendering)
    Pair("data.a",         "bg.base",    "ui",    "Primary data series (amber) on canvas"),
    Pair("data.b",         "bg.base",    "ui",    "Secondary data series (teal) on canvas"),
    Pair("data.c",         "bg.base",    "ui",    "Tertiary data series (purple) on canvas"),
    # Status chip text (chip background is bg.surface-raised; text colour is
    # the status token — check against the plot-area / card background it
    # sits on)
    Pair("status.ok",      "bg.base",    "ui",    "Status chip text — ok"),
    Pair("status.warn",    "bg.base",    "ui",    "Status chip text — warn"),
    Pair("status.error",   "bg.base",    "ui",    "Status chip text — error"),
    Pair("status.info",    "bg.base",    "ui",    "Status chip text — info"),
)


_THRESHOLDS: dict[_TextScope, float] = {
    "body": 4.5,
    "large": 3.0,
    "ui": 3.0,
}


# =============================================================================
# Reporter
# =============================================================================

def _audit_palette(name: str, palette: dict[str, str]) -> int:
    """Run the audit for one palette dict. Returns the number of failures."""
    print()
    print(f"=== {name} palette ===")
    print(f"{'foreground':<22} {'on':<3} {'background':<20}"
          f" {'ratio':>7}  {'min':>5}  scope    status")
    print("-" * 92)
    failures = 0

    for p in PAIRS:
        fg = palette[p.fg_token]
        bg = palette[p.bg_token]
        ratio = _contrast_ratio(fg, bg)
        threshold = _THRESHOLDS[p.scope]
        passing = ratio >= threshold
        status = "PASS" if passing else "FAIL"
        if not passing:
            failures += 1
        print(
            f"{p.fg_token:<22} on  {p.bg_token:<20}"
            f" {ratio:>6.2f}:1  {threshold:>4.1f}  {p.scope:<8} {status}"
        )
        # Second line: description — indented for readability.
        print(f"{'':<47} ({p.description})")

    return failures


def main() -> int:
    total_failures = 0
    total_failures += _audit_palette("DARK",  PALETTE_DARK)
    total_failures += _audit_palette("LIGHT", PALETTE_LIGHT)

    print()
    if total_failures == 0:
        print("All audited pairs meet WCAG 2.1 AA. OK.")
        return 0

    print(f"{total_failures} pair(s) fall below WCAG 2.1 AA. "
          "Adjust palette tokens in ui/theme.py and re-run.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
