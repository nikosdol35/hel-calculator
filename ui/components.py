"""Reusable UI components for the HEL calculator (SPEC v1.9 / ARCH v1.6 §6.9).

This module is the small, deliberate component library that ``ui/outputs.py``,
``ui/panels.py``, ``ui/plots.py``, and ``ui/app.py`` compose their surface from.
Every visible element the user sees — KPI cards, status chips, section
headers, skeleton placeholders, the footer provenance strip — is emitted
by one of the helpers below.

Design intent
-------------
- **One function per element.** ``metric_card``, ``status_chip``,
  ``section_header``, ``skeleton_card``, ``footer_strip``.
- **``format_value`` is the single gate for numbers.** Anywhere a numeric
  result goes on screen, it routes through this helper; the sig-figs rule,
  scientific-notation threshold, thousands-separator rule, and
  non-breaking-space-before-unit rule all live in one place and no caller
  re-implements them.
- **CSS lives in ``ui/theme.py``.** The helpers here emit HTML that targets
  ``.hel-card``, ``.hel-card-label``, ``.hel-card-value``, ``.hel-chip``,
  ``.hel-section-header``, ``.hel-skeleton``, and ``.hel-footer`` — all
  defined in ``theme.py`` so a palette or spacing change re-themes every
  component in one edit.
- **Icons come from ``ui/icons.py``.** Status chips carry a Lucide icon
  next to the text label (hue + icon + text = color-blind triple-encoded
  per docs §3 "Color-blindness dual-encoding" rule).
- **No physics, no labels hard-coded.** Callers pass already-resolved
  label text (from ``ui/labels.py``) and already-computed numeric values
  (from the orchestrator). These helpers format; they don't fetch.

Public API
----------
``format_value(value, unit, *, sig_figs=3) -> str``
    Format a numeric scalar with its unit under the SPEC v1.9 numeric-display
    conventions (3 sig figs, comma thousands-separator, scientific notation
    for |v| < 0.01 or |v| >= 1e5, non-breaking space before unit).

``metric_card(label, value, unit='', *, tooltip=None, flag_est=False, size='lg')``
    Render a labelled KPI card on the current Streamlit surface. Intended
    to be called inside a ``st.columns(...)`` cell so a row of cards
    snaps to the 12-column alignment grid.

``status_chip(text, severity)``
    Render an inline status chip with hue + icon + text. Severity is one
    of ``"ok" | "warn" | "error" | "info"``.

``section_header(title, *, icon=None)``
    Render a section header (h3) with an optional Lucide glyph.

``skeleton_card(*, height_px=88, label='Pending first run')``
    Render a placeholder card the same shape as a real metric card, for
    the pre-first-run state described in SPEC §5.3 item 10.

``footer_strip(spec_version, arch_version, build_date)``
    Render the single-line provenance strip described in SPEC §5.3 item 12.

References:
    ARCHITECTURE.md §6.9 — file contract.
    SPEC.md §5.2, §5.3 items 8–12 — numeric-display, status-chip verdict,
        always-render frames, provenance strip.
    docs/phase3_ui_redesign_plan_2026-04-23.md §"Numerical display
        conventions" and §"Component inventory".
"""

from __future__ import annotations

import math
from typing import Literal

import streamlit as st

from ui.icons import icon as _icon


# =============================================================================
# format_value — the single gate for numbers in the UI
# =============================================================================

# Scientific-notation thresholds (SPEC v1.9 §5.3 item 8, numerical-display
# conventions from the phase-3 plan). Values with magnitude strictly less
# than 0.01 OR at or above 1e5 render as "1.23 × 10^n"; everything between
# renders as a fixed-point number with comma thousands-separators.
_SCI_LOW  = 1e-2
_SCI_HIGH = 1e5

# Unicode superscript digits and sign (for the "× 10^n" exponent). Using the
# Unicode glyphs keeps the display engine-font-agnostic — no MathJax, no
# CSS vertical-align tricks, works equally in Streamlit, PNG export, and
# a copy-paste into email.
_SUPER_DIGITS = str.maketrans("0123456789-+", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺")

# Non-breaking space between value and unit. Keeps "12,450 m" from wrapping
# across lines when a card is narrow. U+00A0.
_NBSP = "\u00a0"


def _format_superscript(exponent: int) -> str:
    """Return the exponent rendered with Unicode superscript glyphs.

    >>> _format_superscript(-6)
    '⁻⁶'
    >>> _format_superscript(12)
    '¹²'
    """
    return str(exponent).translate(_SUPER_DIGITS)


def _format_scientific(value: float, sig_figs: int) -> str:
    """Format ``value`` in scientific notation as ``"m.mm × 10^n"``.

    The mantissa carries ``sig_figs`` total digits (so ``sig_figs=3`` gives
    one leading digit and two after the decimal), the multiplication sign
    is Unicode U+00D7 (not ``x`` or ``*``), and the exponent uses Unicode
    superscript glyphs.
    """
    if value == 0:
        # Zero in sci notation is conventionally "0"; no exponent needed.
        return "0"
    exponent = int(math.floor(math.log10(abs(value))))
    mantissa = value / (10 ** exponent)
    # sig_figs - 1 digits AFTER the leading digit of the mantissa.
    mantissa_str = f"{mantissa:.{sig_figs - 1}f}"
    return f"{mantissa_str} × 10{_format_superscript(exponent)}"


def _format_fixed(value: float, sig_figs: int) -> str:
    """Format ``value`` in fixed-point with a thousands-separator.

    ``sig_figs`` acts as a **minimum-precision target** rather than a digit
    cap: the integer part of ``value`` is always rendered in full (so
    12,450 stays 12,450, per the design-document example), and the
    fractional part is extended to bring the displayed precision up to
    ``sig_figs`` total digits.

    Examples with ``sig_figs=3``:

        12,450.0  -> "12,450"    (5 sig figs — integer part kept intact)
        1,234.0   -> "1,234"     (4 sig figs — integer part kept intact)
        45.7      -> "45.7"      (3 sig figs — one decimal added)
        0.847     -> "0.847"     (3 sig figs — three decimals added)
        7.0       -> "7.00"      (3 sig figs — two decimals added)

    The comma thousands-separator comes from Python's ``,`` format spec,
    which ``g`` format does not emit — that's why we don't delegate to
    ``g`` here.
    """
    if value == 0:
        return "0"
    # log10(|value|) tells us which decade the value sits in: magnitude >= 0
    # means at least one integer digit; magnitude < 0 means a purely fractional
    # number. For 12,450: magnitude = 4. For 0.0123: magnitude = -2.
    magnitude = int(math.floor(math.log10(abs(value))))
    # Decimal places needed so the TOTAL digit count (integer + fractional)
    # reaches sig_figs. If magnitude + 1 already >= sig_figs (e.g. 12,450 has
    # 5 integer digits against sig_figs=3), we add zero decimals — the
    # integer precision is already enough.
    decimals = max(0, sig_figs - 1 - magnitude)
    # ``,.{decimals}f`` gives commas at thousands and the right number of
    # decimal places. ``{value:,.0f}`` formats 12450 -> "12,450".
    return f"{value:,.{decimals}f}"


def format_value(
    value: float | int | None,
    unit: str = "",
    *,
    sig_figs: int = 3,
) -> str:
    """Return ``value`` formatted with its ``unit`` per SPEC v1.9 §5.3 item 8.

    Rules:
      * ``None``, ``NaN``, ``inf`` → the literal ``"—"`` (U+2014 em-dash);
        a calculation that produced a non-finite value renders as a single
        dash rather than the raw Python ``nan`` / ``inf`` string.
      * ``|value| < 0.01`` or ``|value| >= 1e5`` → scientific notation
        (``"1.23 × 10⁻⁶"``).
      * Otherwise → fixed-point with ``sig_figs`` significant digits and a
        comma at every thousands boundary (``"12,450"``, ``"0.847"``).
      * ``unit`` appends with a leading non-breaking space (U+00A0), so the
        value and unit never wrap apart (``"12,450 m"``). An empty ``unit``
        string yields no trailing space.

    Args:
        value: The numeric value. ``None`` / non-finite → em-dash.
        unit: The unit symbol from ``ui/labels.py`` (e.g., ``"kW"``,
            ``"W/cm²"``, ``""``). Emitted verbatim; callers should already
            hold the Unicode-correct glyph.
        sig_figs: Significant-digit count. Default 3; pass 4 for Strehl
            ratios or any quantity where the fourth digit is meaningful.

    Returns:
        A display-ready string. Never ``None``; never trailing whitespace.

    Examples:
        >>> format_value(12450.0, "m")
        '12,450\\xa0m'
        >>> format_value(0.00000123, "W/cm²")
        '1.23 × 10⁻⁶\\xa0W/cm²'
        >>> format_value(0.847, "")
        '0.847'
        >>> format_value(None, "s")
        '—'
    """
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(v):
        return "—"

    magnitude = abs(v)
    if magnitude != 0 and (magnitude < _SCI_LOW or magnitude >= _SCI_HIGH):
        value_str = _format_scientific(v, sig_figs)
    else:
        value_str = _format_fixed(v, sig_figs)

    if unit:
        return f"{value_str}{_NBSP}{unit}"
    return value_str


# =============================================================================
# metric_card — labelled KPI card
# =============================================================================

# Severity → Lucide icon name. Kept in sync with the triple-encoding rule in
# docs/phase3_ui_redesign_plan_2026-04-23.md §3 "Color-blindness dual-encoding"
# (status chips carry hue + icon + text).
_SEVERITY_ICON: dict[str, str] = {
    "ok":    "check-circle",
    "warn":  "alert-triangle",
    "error": "x-circle",
    "info":  "info",
}

Severity = Literal["ok", "warn", "error", "info"]


def metric_card(
    label: str,
    value: float | int | str | None,
    unit: str = "",
    *,
    tooltip: str | None = None,
    flag_est: bool = False,
    size: Literal["lg", "md"] = "lg",
    sig_figs: int = 3,
) -> None:
    """Render a labelled KPI card on the current Streamlit surface.

    Call this inside a ``st.columns(...)`` cell so a row of cards snaps to
    the 12-column alignment grid. Example — four cards across:

        cols = st.columns(4)
        with cols[0]:
            metric_card("Power in aimpoint", result["P_aim"], "kW")
        with cols[1]:
            metric_card("Peak irradiance", result["I_peak"], "W/cm²")
        ...

    Args:
        label: The card's display label (from ``ui/labels.py``, typically
            ``output_label(key)``). Rendered as 14 px, weight 500, in
            ``fg.secondary``.
        value: The numeric value. Routes through ``format_value`` unless
            it is already a string (e.g., ``"Anodized Al"`` for a material
            card, or a pre-formatted burn-through label). Non-finite
            values render as an em-dash.
        unit: Unit symbol (from ``output_unit(key)``). Empty for
            dimensionless quantities. Ignored if ``value`` is a string.
        tooltip: Optional hover title (from ``output_tooltip(key)``). Set
            as the card's ``title=`` attribute so the browser renders the
            native tooltip after a short hover delay.
        flag_est: If ``True``, append a superscript "est." marker next to
            the value — used for HIGH UNCERTAINTY quantities (SPEC §10).
            The superscript is a link to ``#diagnostics`` so clicking it
            jumps to the Diagnostics tab where the full flag list lives.
        size: ``"lg"`` (default, 28 px value) or ``"md"`` (20 px). ``"md"``
            is for compact rows with 5–6 cards across.
        sig_figs: Passed through to ``format_value``. Default 3; pass 4 for
            Strehl ratios.
    """
    # --- Value formatting -------------------------------------------------
    # A caller can hand us a non-numeric string directly (e.g. a material
    # name for the "Target material" card). In that case we render it as-is
    # and skip format_value. Numeric values (int, float, None) route through
    # the formatter.
    if isinstance(value, str):
        value_html = value
    else:
        value_html = format_value(value, unit="", sig_figs=sig_figs)
        # format_value emits "12,450" — we append the unit in its own span
        # so the label-color styling picks it up independently.

    # --- Unit span --------------------------------------------------------
    unit_html = (
        f'<span class="hel-card-unit">{unit}</span>'
        if unit and not isinstance(value, str)
        else ""
    )

    # --- "est." superscript marker for HIGH UNCERTAINTY values ------------
    est_html = (
        '<a class="hel-card-est" href="#diagnostics" '
        'title="High-uncertainty value — see Diagnostics tab">est.</a>'
        if flag_est
        else ""
    )

    # --- Size modifier class ---------------------------------------------
    value_class = (
        "hel-card-value hel-card-value--md" if size == "md" else "hel-card-value"
    )

    # --- Tooltip via the card's title attribute --------------------------
    # Escaping the tooltip: a user-supplied tooltip comes from ui/labels.py
    # which we control, so full HTML escaping is overkill — but we do
    # replace literal quotes so a stray apostrophe doesn't break the
    # attribute. If a future tooltip needs HTML, that's a labels.py change.
    title_attr = (
        f' title="{tooltip.replace(chr(34), chr(39))}"' if tooltip else ""
    )

    st.markdown(
        f'<div class="hel-card"{title_attr}>'
        f'  <div class="hel-card-label">{label}</div>'
        f'  <div class="hel-card-value-row">'
        f'    <span class="{value_class}">{value_html}</span>'
        f'    {unit_html}'
        f'    {est_html}'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# =============================================================================
# status_chip — hue + icon + text
# =============================================================================

def status_chip(text: str, severity: Severity) -> None:
    """Render an inline status chip with hue + Lucide icon + text label.

    The three-channel encoding (hue + icon + text) means a color-blind
    viewer can still read the chip's severity from the icon and the
    written label, per docs §3 "Color-blindness dual-encoding".

    Args:
        text: The chip's label. Typically already-formatted copy from
            ``VERDICT_TEMPLATES`` in ``ui/labels.py`` (e.g. rendered with
            ``VERDICT_TEMPLATES["ok"].format(margin=42.3)``). Rendered in
            all-caps at 12 px with +0.04 em tracking by the ``.hel-chip``
            CSS rule in ``ui/theme.py``.
        severity: One of ``"ok" | "warn" | "error" | "info"``. Selects
            both the hue token (``.hel-chip--{severity}``) and the Lucide
            icon (check-circle / alert-triangle / x-circle / info).

    Raises:
        KeyError: If ``severity`` is not one of the four allowed values.
            Callers should pass a literal, not a variable from an
            untrusted source.
    """
    if severity not in _SEVERITY_ICON:
        raise KeyError(
            f"status_chip severity must be one of {list(_SEVERITY_ICON)}, "
            f"got {severity!r}"
        )
    icon_svg = _icon(_SEVERITY_ICON[severity], size=14)
    st.markdown(
        f'<span class="hel-chip hel-chip--{severity}">'
        f'{icon_svg}'
        f'<span>{text}</span>'
        f'</span>',
        unsafe_allow_html=True,
    )


# =============================================================================
# section_header — h3 with optional icon
# =============================================================================

def section_header(title: str, *, icon: str | None = None) -> None:
    """Render a section header (h3) with an optional Lucide icon.

    Args:
        title: The header text. Rendered at 18 px, weight 600, in
            ``fg.primary`` per the ``.hel-section-header`` rule in
            ``ui/theme.py``.
        icon: Optional Lucide icon name (from ``ui/icons.py``). Rendered
            16 px, left of the title, coloured in ``accent.primary`` per
            the ``.hel-section-header svg`` rule in theme.py.
    """
    icon_svg = _icon(icon, size=16) if icon else ""
    st.markdown(
        f'<h3 class="hel-section-header">{icon_svg}{title}</h3>',
        unsafe_allow_html=True,
    )


# =============================================================================
# skeleton_card — placeholder for pre-first-run state
# =============================================================================

def skeleton_card(
    *,
    height_px: int = 88,
    label: str = "Pending first run",
) -> None:
    """Render a placeholder card the same silhouette as a real metric card.

    Appears on the tabs before the user clicks Run Analysis (SPEC §5.3
    item 10, always-render frames). A soft pulsing gradient signals
    "waiting for data" without a spinner; ``prefers-reduced-motion``
    shortens the pulse to the 50 ms floor.

    Args:
        height_px: Card height. Default 88 px matches the ``lg``
            ``metric_card`` (label + value + padding). Pass ``56`` for a
            ``md`` card, ``200`` for a plot-frame placeholder.
        label: A very short caption rendered inside the skeleton — tells
            the user *why* the card is empty. Keep under five words.
    """
    st.markdown(
        f'<div class="hel-skeleton" style="height:{height_px}px; '
        f'padding: var(--space-6); display: flex; align-items: center; '
        f'justify-content: center; color: var(--fg-tertiary); '
        f'font-size: 12px; letter-spacing: 0.02em;">'
        f'{label}'
        f'</div>',
        unsafe_allow_html=True,
    )


# =============================================================================
# footer_strip — single-line provenance footer
# =============================================================================

def footer_strip(
    spec_version: str,
    arch_version: str,
    build_date: str,
) -> None:
    """Render the single-line provenance strip at the bottom of the page.

    Mirrors the ``FOOTER_TEMPLATE`` string from ``ui/labels.py`` — this
    helper just wraps it in the ``.hel-footer`` surface so every page in
    the app carries the same provenance line in the same place.

    Args:
        spec_version: SPEC document version (e.g. ``"v1.9"``).
        arch_version: ARCHITECTURE document version (e.g. ``"v1.6"``).
        build_date: ISO-format build date (e.g. ``"2026-04-23"``).
    """
    # Import locally to avoid a module-level circular dependency if
    # ui/labels.py ever starts importing from ui/components.py (it
    # currently does not, but keeping the boundary cheap is inexpensive).
    from ui.labels import FOOTER_TEMPLATE

    line = FOOTER_TEMPLATE.format(
        spec_version=spec_version,
        arch_version=arch_version,
        build_date=build_date,
    )
    st.markdown(
        f'<div class="hel-footer">{line}</div>',
        unsafe_allow_html=True,
    )


__all__ = [
    "format_value",
    "metric_card",
    "status_chip",
    "section_header",
    "skeleton_card",
    "footer_strip",
    "Severity",
]
