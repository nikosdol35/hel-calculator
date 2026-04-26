"""Shared visual tokens, CSS, and Plotly template (SPEC v1.9 / ARCH v1.6 §6.8).

Single source of truth for every palette value, typography rule, Plotly
layout default, and CSS selector used in the HEL calculator UI. One edit
in this file re-themes every surface, every chart, and every state.

The module exports four kinds of things:

  1. **Palette dicts** — ``PALETTE_DARK`` and ``PALETTE_LIGHT``, keyed by
     semantic token name (``bg.base``, ``fg.primary``, ``accent.primary``,
     ``plot.gridline``, etc.). Every hex in the app traces back to one
     of these entries; no hue is introduced inline elsewhere.

  2. **Legacy constants** — ``COLOR_PRIMARY``, ``COLOR_REFERENCE``,
     ``COLOR_SUCCESS``, ``COLOR_WARNING``, ``COLOR_CAUTION``, and
     ``PLOT_HEIGHT_PX``. These preserve the pre-v1.6 import surface that
     ``ui/outputs.py`` and ``ui/plots.py`` currently rely on, so PR 1
     lands the theme layer without touching every import site. ``ui/style.py``
     re-exports from here; PR 2 migrates both consumers to import directly
     from ``ui.theme`` and the shim is deleted.

  3. **Plotly template and modebar config** — ``PLOTLY_TEMPLATE_DARK`` /
     ``PLOTLY_TEMPLATE_LIGHT`` (registered with ``plotly.io.templates``)
     and ``PLOTLY_MODEBAR_CONFIG`` (the ``config=`` dict passed to every
     ``st.plotly_chart`` call). These encode gridline, axis, spike,
     hover-box, tabular-nums tick-label, and margin conventions so every
     chart in the app is visually consistent.

  4. **``apply(app_mode)``** — the single bootstrap call ``ui/app.py`` makes
     after ``st.set_page_config``. Injects the CSS for font loading, the
     palette custom properties, card / chip / section-header / focus-ring
     / scrollbar / progress-bar rules, and the ``prefers-reduced-motion``
     overrides; registers the matching Plotly template as the default.

References:
    ARCHITECTURE.md §6.8 — file contract and public API.
    SPEC.md §5.2, §5.3 items 8–12 — visual conventions and behavioral commitments.
    docs/phase3_ui_redesign_plan_2026-04-23.md §3–§5 — palette justification,
        typography scale, plot-specific design tokens, WCAG contrast audit.
"""

from __future__ import annotations

from typing import Literal

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st


# =============================================================================
# Palette tokens — every hex in the app lives here.
# =============================================================================

PALETTE_DARK: dict[str, str] = {
    # --- Surfaces --------------------------------------------------------
    "bg.base":            "#0F1419",   # app canvas
    "bg.surface":         "#1A1F26",   # sidebar, cards, expanders
    "bg.surface-raised":  "#232933",   # hovered cards, active chips, hover box
    # --- Foregrounds -----------------------------------------------------
    "fg.primary":         "#E8EAED",   # body, headings, big numerics
    "fg.secondary":       "#B0B6BD",   # labels, captions
    "fg.tertiary":        "#9AA0A6",   # tick labels, disabled text, hints (≥18px only — see scripts/check_contrast.py scope note)
    # --- Borders ---------------------------------------------------------
    "border.subtle":      "#2C3339",   # card border, input border at rest
    "border.strong":      "#3A424B",   # active input border, divider
    # --- Accent ----------------------------------------------------------
    "accent.primary":     "#4FC3F7",   # active tab, focus ring, primary buttons, links
    "accent.primary-hover": "#81D4FA", # button hover
    # --- Data-series triad (hue + dash + marker shape for color-blind safety) --
    "data.a":             "#F4B942",   # amber   — solid  — circle
    "data.b":             "#4DB6AC",   # teal    — dash   — square
    "data.c":             "#BA68C8",   # purple  — dot    — diamond
    "data.reference":     "#5F6368",   # gray reference / diffraction-limited baseline
    # --- Status (all chips additionally carry Lucide icon + text label) --
    "status.ok":          "#66BB6A",
    "status.warn":        "#FFA726",
    "status.error":       "#EF5350",
    "status.info":        "#4FC3F7",
    # --- Plot-only tokens ------------------------------------------------
    "plot.bg":                 "#1A1F26",
    "plot.bg-plot-area":       "#151A20",
    "plot.gridline":           "#2C3339",
    "plot.gridline-subtle":    "#20262D",
    "plot.axis-line":          "#5F6368",
    "plot.tick-label":         "#9AA0A6",
    "plot.axis-title":         "#E8EAED",
    "plot.spike":              "#9AA0A6",
    "plot.hover-bg":           "#232933",
    "plot.hover-border":       "#4FC3F7",
}

PALETTE_LIGHT: dict[str, str] = {
    "bg.base":            "#F7F8FA",
    "bg.surface":         "#FFFFFF",
    "bg.surface-raised":  "#FFFFFF",
    "fg.primary":         "#1A1F26",
    "fg.secondary":       "#3C4048",
    "fg.tertiary":        "#5F6368",
    "border.subtle":      "#E0E3E7",
    "border.strong":      "#BDC1C6",
    "accent.primary":     "#0277BD",
    "accent.primary-hover": "#01579B",
    "data.a":             "#E09712",
    "data.b":             "#00897B",
    "data.c":             "#8E24AA",
    "data.reference":     "#9AA0A6",
    "status.ok":          "#2E7D32",
    "status.warn":        "#E65100",
    "status.error":       "#C62828",
    "status.info":        "#0277BD",
    "plot.bg":                 "#FFFFFF",
    "plot.bg-plot-area":       "#FAFBFC",
    "plot.gridline":           "#E0E3E7",
    "plot.gridline-subtle":    "#EEF0F3",
    "plot.axis-line":          "#9AA0A6",
    "plot.tick-label":         "#5F6368",
    "plot.axis-title":         "#1A1F26",
    "plot.spike":              "#5F6368",
    "plot.hover-bg":           "#FFFFFF",
    "plot.hover-border":       "#0277BD",
}


# =============================================================================
# Legacy constants (pre-v1.6 import surface for ui/outputs.py and ui/plots.py)
# =============================================================================
# ``ui/style.py`` re-exports these unchanged. Current consumers continue to
# work without edits; PR 2 migrates them to import from ui.theme directly.

COLOR_PRIMARY   = PALETTE_DARK["accent.primary"]       # "actual" curve color
COLOR_REFERENCE = PALETTE_DARK["data.reference"]        # diffraction-limited reference
COLOR_SUCCESS   = PALETTE_DARK["status.ok"]
COLOR_WARNING   = PALETTE_DARK["status.warn"]
COLOR_CAUTION   = PALETTE_DARK["status.error"]
PLOT_HEIGHT_PX  = 420   # hero-plot default; other sizes live in PLOT_HEIGHTS below


# =============================================================================
# Plot sizing and typography scale
# =============================================================================

PLOT_HEIGHTS: dict[str, int] = {
    "default":     360,   # most per-tab plots
    "hero":        420,   # Overview dwell-vs-burnthrough, Engagement spot contributions
    "paired":      320,   # side-by-side pair
    "cross-section": 280, # Safety tab NOHD schematic
}

TYPOGRAPHY_CSS = """
/* Load Inter + JetBrains Mono (Google Fonts, inline <link>). Programs with
   air-gap constraints can swap this block for a bundled font file. */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
"""


# =============================================================================
# Plotly template
# =============================================================================

def _build_plotly_template(palette: dict[str, str]) -> go.layout.Template:
    """Construct a Plotly template from a palette dict.

    Every token used in the returned template traces back to ``palette``, so
    swapping PALETTE_DARK / PALETTE_LIGHT produces a consistent re-theme of
    every plot in the app.
    """
    return go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=palette["plot.bg"],
            plot_bgcolor=palette["plot.bg-plot-area"],
            colorway=[
                palette["data.a"],
                palette["data.b"],
                palette["data.c"],
                palette["data.reference"],
            ],
            font=dict(
                family="Inter, system-ui, -apple-system, sans-serif",
                color=palette["fg.primary"],
                size=13,
            ),
            margin=dict(l=56, r=32, t=40, b=48),
            xaxis=dict(
                gridcolor=palette["plot.gridline"],
                gridwidth=0.5,
                zeroline=False,
                linecolor=palette["plot.axis-line"],
                ticks="outside",
                tickcolor=palette["plot.axis-line"],
                tickfont=dict(color=palette["plot.tick-label"], size=11),
                title=dict(font=dict(color=palette["plot.axis-title"], size=12)),
                showspikes=True,
                spikecolor=palette["plot.spike"],
                spikesnap="cursor",
                spikemode="across",
                spikedash="dot",
                spikethickness=1,
            ),
            yaxis=dict(
                gridcolor=palette["plot.gridline"],
                gridwidth=0.5,
                zeroline=False,
                linecolor=palette["plot.axis-line"],
                ticks="outside",
                tickcolor=palette["plot.axis-line"],
                tickfont=dict(color=palette["plot.tick-label"], size=11),
                title=dict(font=dict(color=palette["plot.axis-title"], size=12)),
                showspikes=True,
                spikecolor=palette["plot.spike"],
                spikesnap="cursor",
                spikemode="across",
                spikedash="dot",
                spikethickness=1,
            ),
            hoverlabel=dict(
                bgcolor=palette["plot.hover-bg"],
                bordercolor=palette["plot.hover-border"],
                font=dict(
                    family="Inter, system-ui, sans-serif",
                    color=palette["fg.primary"],
                    size=13,
                ),
            ),
            legend=dict(
                bgcolor=palette["plot.bg"],
                bordercolor=palette["border.subtle"],
                borderwidth=1,
                font=dict(color=palette["fg.primary"], size=12),
                orientation="v",
                x=1.0,
                xanchor="right",
                y=1.0,
                yanchor="top",
            ),
        )
    )


#: Registered Plotly templates (switched by ``apply(app_mode)``).
PLOTLY_TEMPLATE_DARK  = _build_plotly_template(PALETTE_DARK)
PLOTLY_TEMPLATE_LIGHT = _build_plotly_template(PALETTE_LIGHT)

pio.templates["hel_dark"]  = PLOTLY_TEMPLATE_DARK
pio.templates["hel_light"] = PLOTLY_TEMPLATE_LIGHT


#: Curated modebar config passed to every ``st.plotly_chart(fig, config=...)``.
#:
#: Keeps zoom / pan / reset-axes / PNG-export; drops lasso / select / spike
#: toggle (spikes always on) / auto-scale (redundant with reset). The Plotly
#: logo is stripped; the modebar itself appears on plot hover only so the
#: chart at rest is uncluttered. PNG exports at 2× DPI with the current
#: theme baked in.
PLOTLY_MODEBAR_CONFIG: dict = {
    "displaylogo": False,
    "displayModeBar": "hover",
    "modeBarButtonsToRemove": [
        "lasso2d",
        "select2d",
        "toggleSpikelines",
        "autoScale2d",
    ],
    "toImageButtonOptions": {
        "format": "png",
        "filename": "hel_calculator_plot",
        "scale": 2,
    },
}


# =============================================================================
# Backward-compatible alias (some callers may import ``PLOTLY_TEMPLATE``).
# =============================================================================
PLOTLY_TEMPLATE = PLOTLY_TEMPLATE_DARK


# =============================================================================
# CSS injection + app-mode bootstrap
# =============================================================================

def _build_css(palette: dict[str, str]) -> str:
    """Return the CSS string injected by ``apply()`` for the given palette."""
    return f"""
{TYPOGRAPHY_CSS}

:root {{
  --bg-base:            {palette['bg.base']};
  --bg-surface:         {palette['bg.surface']};
  --bg-surface-raised:  {palette['bg.surface-raised']};
  --fg-primary:         {palette['fg.primary']};
  --fg-secondary:       {palette['fg.secondary']};
  --fg-tertiary:        {palette['fg.tertiary']};
  --border-subtle:      {palette['border.subtle']};
  --border-strong:      {palette['border.strong']};
  --accent-primary:     {palette['accent.primary']};
  --accent-primary-hover: {palette['accent.primary-hover']};
  --status-ok:          {palette['status.ok']};
  --status-warn:        {palette['status.warn']};
  --status-error:       {palette['status.error']};
  --status-info:        {palette['status.info']};

  --radius-card:   8px;
  --radius-chip:   999px;
  --radius-button: 6px;

  --shadow-1: 0 1px 2px rgba(0,0,0,0.40);
  --shadow-2: 0 4px 8px rgba(0,0,0,0.50);

  --space-1:  4px;
  --space-2:  8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;
}}

/* ---- Typography --------------------------------------------------------- */
html, body, [class*="css"] {{
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  color: var(--fg-primary);
  font-feature-settings: 'ss01', 'cv11';
}}
h1, h2, h3 {{ letter-spacing: -0.01em; font-weight: 600; }}
h1 {{ font-size: 32px; line-height: 1.15; letter-spacing: -0.02em; }}
h2 {{ font-size: 24px; line-height: 1.25; }}
h3 {{ font-size: 18px; line-height: 1.35; }}
.stMarkdown p, .stMarkdown li {{ font-size: 14px; line-height: 1.5; }}
.stCaption, .caption, [data-testid="stCaptionContainer"] {{
  font-size: 12px; color: var(--fg-secondary); letter-spacing: 0.01em;
}}

/* Numeric / metric values render in JetBrains Mono with tabular-nums so
   cards in a row align on the decimal point. */
[data-testid="stMetricValue"],
.hel-metric-value,
.hel-mono {{
  font-family: 'JetBrains Mono', 'Menlo', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  letter-spacing: -0.01em;
}}
[data-testid="stMetricValue"] {{ font-size: 28px; line-height: 1.1; }}
[data-testid="stMetricLabel"] {{ color: var(--fg-secondary); font-weight: 500; font-size: 14px; }}

/* ---- Cards and section headers ----------------------------------------- */
.hel-card {{
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  padding: var(--space-6);
  box-shadow: var(--shadow-1);
  transition: box-shadow 150ms ease-out, transform 150ms ease-out;
  /* Bottom margin gives stacked rows of cards a 16 px vertical rhythm.
     Because every card carries the same margin, two sequential
     ``st.columns(...)`` calls render with clear separation between
     rows without any per-row spacer in the Python layer. */
  margin-bottom: var(--space-4);
}}
.hel-card:hover {{ box-shadow: var(--shadow-2); }}

.hel-section-header {{
  font-size: 18px; font-weight: 600; color: var(--fg-primary);
  margin: var(--space-8) 0 var(--space-4) 0;
  display: flex; align-items: center; gap: var(--space-2);
}}
.hel-section-header svg {{ color: var(--accent-primary); }}

/* ---- Inline explanation prose (caption-sized, calm) -------------------- */
/* Short plain-language sentences sitting under a section header or a plot
   to explain what the viewer is looking at. Readable-first paragraph-width,
   fg.secondary color so the prose reads as guidance rather than data. */
.hel-explanation {{
  color: var(--fg-secondary);
  font-size: 13px;
  line-height: 1.55;
  max-width: 820px;
  margin: var(--space-2) 0 var(--space-6) 0;
}}
.hel-explanation--plot {{
  /* Plot captions sit between the chart and the next header — the top
     margin ties them visually to the chart above. */
  margin-top: var(--space-3);
  margin-bottom: var(--space-8);
}}

/* ---- Column gutters ---------------------------------------------------- */
/* Streamlit's default ``st.columns`` gap packs cards tightly against each
   other at narrow viewports. The design tokens call for 16 px horizontal
   gutters on card rows so the border/shadow of each card has breathing
   room from its neighbours. Rule targets the flex container Streamlit
   emits for every ``st.columns(...)`` call. */
[data-testid="stHorizontalBlock"] {{
  gap: var(--space-4) !important;
}}

/* ---- Status chips (hue + icon + text — color-blind dual-encoded) ------- */
.hel-chip {{
  display: inline-flex; align-items: center; gap: var(--space-2);
  padding: 6px 12px; border-radius: var(--radius-chip);
  font-size: 12px; font-weight: 500; letter-spacing: 0.04em;
  text-transform: uppercase;
  background: var(--bg-surface-raised);
  border: 1px solid transparent;
  transition: transform 150ms ease-out;
}}
.hel-chip:hover {{ transform: scale(1.02); }}
.hel-chip--ok    {{ color: var(--status-ok);    border-color: var(--status-ok); }}
.hel-chip--warn  {{ color: var(--status-warn);  border-color: var(--status-warn); }}
.hel-chip--error {{ color: var(--status-error); border-color: var(--status-error); }}
.hel-chip--info  {{ color: var(--status-info);  border-color: var(--status-info); }}

/* ---- Inputs / focus rings ---------------------------------------------- */
input, textarea, select, button {{ font-family: inherit; }}

/* Keyboard-focus only; mouse clicks don't draw the ring. */
button:focus-visible,
input:focus-visible,
select:focus-visible,
[role="tab"]:focus-visible,
[role="button"]:focus-visible {{
  outline: 2px solid var(--accent-primary) !important;
  outline-offset: 2px;
}}

/* ---- Tabs -------------------------------------------------------------- */
.stTabs [data-baseweb="tab-list"] {{ gap: var(--space-1); border-bottom: 1px solid var(--border-subtle); }}
.stTabs [data-baseweb="tab"] {{
  color: var(--fg-secondary); font-weight: 500; font-size: 14px;
  padding: 10px 14px;
}}
.stTabs [aria-selected="true"] {{
  color: var(--fg-primary) !important;
  border-bottom: 2px solid var(--accent-primary) !important;
}}
.stTabs [data-baseweb="tab"]:hover {{ color: var(--fg-primary); }}

/* ---- Primary buttons (Run Analysis) ------------------------------------ */
.stButton > button[kind="primary"] {{
  background: var(--accent-primary); color: var(--bg-base);
  border: none; border-radius: var(--radius-button);
  font-weight: 500; letter-spacing: 0.01em;
  transition: background 100ms ease-out;
}}
.stButton > button[kind="primary"]:hover {{ background: var(--accent-primary-hover); }}
.stButton > button[kind="primary"]:active {{ transform: translateY(1px); }}

/* ---- Metric card sub-elements (emitted by ui/components.py) ------------ */
/* The card surface itself is .hel-card above; these classes style what
   lives inside it — label line, value + unit row, HIGH UNCERTAINTY "est."
   superscript, and the size-md variant for compact cards. All values are
   set in JetBrains Mono with tabular-nums so a row of cards aligns on the
   decimal point without any per-card tweaking. */
.hel-card-label {{
  font-size: 14px;
  font-weight: 500;
  color: var(--fg-secondary);
  line-height: 1.5;
  margin: 0 0 var(--space-2) 0;
  letter-spacing: 0;
}}
.hel-card-value-row {{
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  line-height: 1.1;
}}
.hel-card-value {{
  font-family: 'JetBrains Mono', 'Menlo', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
  font-size: 28px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--fg-primary);
}}
.hel-card-value--md {{
  font-size: 20px;
  line-height: 1.2;
}}
.hel-card-unit {{
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  font-size: 14px;
  font-weight: 400;
  color: var(--fg-secondary);
  white-space: nowrap;
}}
.hel-card-est {{
  font-size: 10px;
  font-style: italic;
  color: var(--fg-tertiary);
  vertical-align: super;
  margin-left: 2px;
  text-decoration: none;
  letter-spacing: 0.02em;
}}
.hel-card-est:hover {{
  color: var(--accent-primary);
  text-decoration: underline;
}}

/* ---- Skeleton placeholder (pre-first-run) ------------------------------ */
/* Same silhouette as a real card; a soft pulsing gradient signals "waiting
   for data" without a spinner. The @keyframes is outside @media
   (prefers-reduced-motion) so the reduced-motion override above slows
   the pulse to the 50 ms floor. */
.hel-skeleton {{
  background: linear-gradient(
    90deg,
    var(--bg-surface) 0%,
    var(--bg-surface-raised) 50%,
    var(--bg-surface) 100%
  );
  background-size: 200% 100%;
  animation: hel-skeleton-pulse 1.6s ease-in-out infinite;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
}}
@keyframes hel-skeleton-pulse {{
  0%   {{ background-position: 200% 0; }}
  100% {{ background-position: -200% 0; }}
}}

/* ---- Chip list (severity-sorted Diagnostics-tab flag list) ------------- */
.hel-chip-list {{
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: var(--space-2) 0;
}}

/* ---- Progress bar (compute-time feedback) ------------------------------ */
/* Thin 2 px bar with a sliding ::after pseudo-element. The parent track is
   a muted border color; the child "glow" slides edge-to-edge on an infinite
   loop via @keyframes hel-progress-indeterminate. Appears below the tab
   strip while the orchestrator is running (1–4 s typical) and disappears
   when the rerun that produced the result repaints the page. */
.hel-progress-bar {{
  position: relative;
  width: 100%;
  height: 2px;
  overflow: hidden;
  background: var(--border-subtle);
  margin: var(--space-2) 0 var(--space-4) 0;
  border-radius: 1px;
}}
.hel-progress-bar::after {{
  content: "";
  position: absolute;
  top: 0; left: 0;
  height: 100%;
  width: 40%;
  background: var(--accent-primary);
  border-radius: 1px;
  animation: hel-progress-indeterminate 1.2s ease-in-out infinite;
}}
.hel-progress-bar--placeholder {{
  background: transparent;
}}
.hel-progress-bar--placeholder::after {{
  display: none;
}}
@keyframes hel-progress-indeterminate {{
  0%   {{ transform: translateX(-100%); }}
  50%  {{ transform: translateX(100%); }}
  100% {{ transform: translateX(250%); }}
}}

/* Fade-in for the tab container once the compute completes. A 150 ms ease-out
   fade matches the plan's "output cards render with a single fade-in
   transition". The animation runs once on each rerun; prefers-reduced-motion
   users get the 50 ms floor from the @media rule below. */
.stTabs {{
  animation: hel-fade-in 150ms ease-out;
}}
@keyframes hel-fade-in {{
  from {{ opacity: 0; transform: translateY(2px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}

/* ---- Welcome card (pre-first-run state) -------------------------------- */
/* A calm centered card that replaces the default Streamlit st.info banner
   when the user has not yet clicked Run Analysis. Explains the first two
   steps — pick a scenario, then run — without shouting. */
.hel-welcome-card {{
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: var(--space-12) var(--space-12);
  margin: var(--space-8) 0;
  text-align: center;
  box-shadow: 0 1px 2px rgba(0,0,0,0.4);
}}
.hel-welcome-card__title {{
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  font-size: 18px; font-weight: 600; letter-spacing: 0;
  color: var(--fg-primary);
  margin-bottom: var(--space-3);
}}
.hel-welcome-card__body {{
  font-size: 14px; font-weight: 400; line-height: 1.5;
  color: var(--fg-secondary);
  max-width: 520px; margin: 0 auto;
}}

/* ---- Error card (physics validator rejects the input set) -------------- */
/* Calm, single-surface error card that replaces Streamlit's default st.error
   banner. Uses the status-error token for the icon + title, but the card
   body is the standard surface color — "here is what went wrong, here is
   what to change" reads more calmly than a full-width red stripe. */
.hel-error-card {{
  background: var(--bg-surface);
  border: 1px solid var(--status-error);
  border-left: 4px solid var(--status-error);
  border-radius: 8px;
  padding: var(--space-6);
  margin: var(--space-4) 0;
  box-shadow: 0 1px 2px rgba(0,0,0,0.4);
}}
.hel-error-card__header {{
  display: flex; align-items: center; gap: var(--space-3);
  color: var(--status-error);
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  font-size: 14px; font-weight: 600; letter-spacing: 0;
  margin-bottom: var(--space-3);
}}
.hel-error-card__header svg {{ flex: 0 0 auto; }}
.hel-error-card__body {{
  color: var(--fg-primary);
  font-size: 14px; font-weight: 400; line-height: 1.5;
}}
.hel-error-card__suggestion {{
  margin-top: var(--space-3);
  color: var(--fg-secondary);
  font-size: 13px; line-height: 1.5;
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-subtle);
}}

/* ---- "Last run" indicator (sidebar) ------------------------------------ */
.hel-last-run {{
  font-size: 12px;
  color: var(--fg-tertiary);
  letter-spacing: 0.01em;
  margin: var(--space-2) 0 0 0;
  text-align: right;
}}
.hel-last-run--fresh {{
  color: var(--fg-secondary);
}}

/* ---- Footer provenance strip ------------------------------------------- */
.hel-footer {{
  margin-top: var(--space-12); padding: var(--space-4) 0;
  border-top: 1px solid var(--border-subtle);
  color: var(--fg-tertiary); font-size: 12px;
  text-align: center; letter-spacing: 0.01em;
}}

/* ---- Streamlit chrome suppression -------------------------------------- */
/* Hide the built-in hamburger / "Made with Streamlit" / "Manage app"
   floating button. The .streamlit/config.toml toolbarMode=minimal
   handles most of this at the framework level; these CSS rules are
   the belt-and-braces backup that catches any chrome the config flag
   misses (Deploy menu, status indicator, viewer-mode footer badge).
   The owner toolbar across the top of the page (Share / Star / Edit /
   GitHub / Deploy) is a Streamlit Cloud platform feature visible only
   to authenticated owners of the app — it cannot be hidden via app
   CSS, but it is not visible to the team members the link is shared
   with anyway. */
[data-testid="stDeployButton"],
[data-testid="stStatusWidget"],
[data-testid="stToolbar"] [data-testid="manage-app-button"],
[data-testid="stMainMenu"],
.viewerBadge_link__1S137,
.viewerBadge_container__1QSob,
footer[class*="viewerBadge"],
#MainMenu,
header [data-testid="stToolbarActions"] {{
  display: none !important;
  visibility: hidden !important;
}}
/* Some Streamlit builds render a translucent header bar around the
   toolbar; collapse that to zero so the page content sits flush. */
header[data-testid="stHeader"] {{
  background: transparent !important;
  height: 0 !important;
}}

/* ---- Login card (full-viewport centered, dark canvas) ------------------ */
/* The card itself is a centered Streamlit column — styling here tightens
   the wordmark + help-line without wrapping the whole column in custom
   HTML, which would break Streamlit's widget accessibility tree. */
.hel-login-wordmark {{
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  font-size: 26px; font-weight: 600; letter-spacing: -0.01em;
  color: var(--fg-primary);
  text-align: center;
  margin: var(--space-12) 0 var(--space-2) 0;
}}
.hel-login-tagline {{
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  font-size: 13px; color: var(--fg-secondary);
  text-align: center;
  margin: 0 0 var(--space-6) 0;
  letter-spacing: 0.01em;
}}
.hel-login-help {{
  font-size: 12px; color: var(--fg-secondary);
  text-align: center;
  margin-top: var(--space-3);
  letter-spacing: 0.01em;
}}
.hel-login-attribution {{
  font-size: 14px; color: var(--fg-secondary);
  text-align: center;
  margin-top: var(--space-8);
  padding-top: var(--space-4);
  border-top: 1px solid var(--border-subtle);
  letter-spacing: 0.01em;
  font-style: italic;
}}

/* ---- Custom scrollbar (WebKit only; Firefox falls back to system) ------ */
::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-track {{ background: var(--bg-base); }}
::-webkit-scrollbar-thumb {{ background: var(--border-subtle); border-radius: 4px; }}
::-webkit-scrollbar-thumb:hover {{ background: var(--fg-tertiary); }}

/* ---- Respect prefers-reduced-motion ------------------------------------ */
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 50ms !important;
  }}
}}
"""


def apply(app_mode: Literal["dark", "light"] = "dark") -> None:
    """Apply the HEL calculator theme.

    Called once by ``ui/app.py`` immediately after ``st.set_page_config``.
    Injects the palette CSS + typography + card / chip / focus-ring rules
    and sets the matching Plotly template as the renderer default.

    Args:
        app_mode: ``"dark"`` (default, boot-time) or ``"light"`` (user
            toggle). Flips both the injected CSS and the Plotly template
            in one action.
    """
    palette = PALETTE_DARK if app_mode == "dark" else PALETTE_LIGHT
    st.markdown(f"<style>{_build_css(palette)}</style>", unsafe_allow_html=True)
    pio.templates.default = "hel_dark" if app_mode == "dark" else "hel_light"


__all__ = [
    "PALETTE_DARK",
    "PALETTE_LIGHT",
    "PLOTLY_TEMPLATE",
    "PLOTLY_TEMPLATE_DARK",
    "PLOTLY_TEMPLATE_LIGHT",
    "PLOTLY_MODEBAR_CONFIG",
    "PLOT_HEIGHTS",
    "PLOT_HEIGHT_PX",
    "COLOR_PRIMARY",
    "COLOR_REFERENCE",
    "COLOR_SUCCESS",
    "COLOR_WARNING",
    "COLOR_CAUTION",
    "apply",
]
