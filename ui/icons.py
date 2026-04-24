"""Lucide SVG inline helper (SPEC v1.9 / ARCH v1.6 §6.11).

Returns inline SVG markup for the ~12 Lucide icons actually used in the
HEL calculator UI. No network fetch, no npm dependency, no CDN link —
the icons are bundled as SVG path strings below.

Lucide (https://lucide.dev) is MIT-licensed. Each icon's path is copied
verbatim from the Lucide source so the rendered output matches the
Lucide design language exactly (24×24 viewBox, 2 px default stroke).
We render at 16 px in body UI and 20 px in tab bars per the plan;
stroke width is set to 1.5 px for a slightly lighter, more refined
weight than the Lucide default.

Color is inherited from the surrounding CSS via ``stroke="currentColor"``
so status chips, section headers, tab labels, etc. control the color
from their own styling rules.

Usage
-----
>>> st.markdown(icon("check-circle", size=16), unsafe_allow_html=True)
>>> st.markdown(icon("target", size=20, stroke=1.75), unsafe_allow_html=True)

For icon-only interactive controls, the caller wraps the returned markup
in a ``<button aria-label="...">`` — the SVG itself is marked
``aria-hidden="true"`` so screen readers skip the decorative glyph and
read the button label instead.

References:
    ARCHITECTURE.md §6.11 — file contract.
    docs/phase3_ui_redesign_plan_2026-04-23.md §3 — iconography policy.
"""

from __future__ import annotations


# -----------------------------------------------------------------------------
# Lucide SVG path data.
#
# Each entry is the raw inner-SVG markup (the contents of <svg>...</svg>) for a
# single Lucide icon, copied from https://lucide.dev source. The outer <svg>
# wrapper with size/stroke/aria is assembled by icon() below.
# -----------------------------------------------------------------------------

_LUCIDE_PATHS: dict[str, str] = {
    # ---- Status-chip icons (SPEC §5.2 Overview verdict) --------------------
    "check-circle": (
        '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>'
        '<polyline points="22 4 12 14.01 9 11.01"/>'
    ),
    "alert-triangle": (
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>'
        '<path d="M12 9v4"/>'
        '<path d="M12 17h.01"/>'
    ),
    "x-circle": (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="m15 9-6 6"/>'
        '<path d="m9 9 6 6"/>'
    ),
    "info": (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M12 16v-4"/>'
        '<path d="M12 8h.01"/>'
    ),
    # ---- Tab-label icons (SPEC §5.2 tabs) -----------------------------------
    "layout-dashboard": (
        '<rect width="7" height="9" x="3" y="3" rx="1"/>'
        '<rect width="7" height="5" x="14" y="3" rx="1"/>'
        '<rect width="7" height="9" x="14" y="12" rx="1"/>'
        '<rect width="7" height="5" x="3" y="16" rx="1"/>'
    ),
    "target": (
        '<circle cx="12" cy="12" r="10"/>'
        '<circle cx="12" cy="12" r="6"/>'
        '<circle cx="12" cy="12" r="2"/>'
    ),
    "flame": (
        '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>'
    ),
    "shield": (
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'
    ),
    "cloud": (
        '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>'
    ),
    "activity": (
        '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.5.5 0 0 1-.96 0L8.15 2.18a.5.5 0 0 0-.96 0l-2.35 8.36A2 2 0 0 1 2.92 12H2"/>'
    ),
    # ---- Chrome / controls --------------------------------------------------
    "chevron-down": (
        '<path d="m6 9 6 6 6-6"/>'
    ),
    "sun-moon": (
        '<path d="M12 8a2.83 2.83 0 0 1 4 4 4 4 0 1 1-4-4"/>'
        '<path d="M12 2v2"/>'
        '<path d="M12 20v2"/>'
        '<path d="m4.9 4.9 1.4 1.4"/>'
        '<path d="m17.7 17.7 1.4 1.4"/>'
        '<path d="M2 12h2"/>'
        '<path d="M20 12h2"/>'
        '<path d="m6.3 17.7-1.4 1.4"/>'
        '<path d="m19.1 4.9-1.4 1.4"/>'
    ),
    "download": (
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<polyline points="7 10 12 15 17 10"/>'
        '<line x1="12" x2="12" y1="15" y2="3"/>'
    ),
}


# -----------------------------------------------------------------------------
# Public helper.
# -----------------------------------------------------------------------------
def icon(name: str, *, size: int = 16, stroke: float = 1.5) -> str:
    """Return inline SVG markup for a Lucide icon.

    Args:
        name: One of the keys in ``_LUCIDE_PATHS`` (e.g. ``"check-circle"``).
            Raises ``KeyError`` if the icon is not bundled — add the path
            to the table rather than fetching it at runtime.
        size: Pixel size (applied to both width and height). 16 for inline
            UI, 20 for tab labels, 24 for the login card wordmark.
        stroke: Stroke width in pixels. Default 1.5; Lucide's own default
            is 2.0 but a slightly lighter weight reads as more refined on
            dense engineering layouts.

    Returns:
        An SVG string ready to pass to ``st.markdown(..., unsafe_allow_html=True)``.
        The ``<svg>`` element carries ``aria-hidden="true"`` so assistive
        tech skips the decorative glyph; for icon-only interactive controls
        the caller supplies an ``aria-label`` on the surrounding button.

    Example:
        >>> icon("target", size=20)
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" ...'
    """
    if name not in _LUCIDE_PATHS:
        available = ", ".join(sorted(_LUCIDE_PATHS))
        raise KeyError(f"Icon {name!r} not bundled. Available: {available}")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true" focusable="false" '
        f'style="display:inline-block;vertical-align:middle">'
        f'{_LUCIDE_PATHS[name]}'
        f'</svg>'
    )


def available_icons() -> tuple[str, ...]:
    """Return a tuple of bundled icon names (for help messages and tests)."""
    return tuple(sorted(_LUCIDE_PATHS))


__all__ = ["icon", "available_icons"]
