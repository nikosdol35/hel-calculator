"""Plotly figure constructors per SPEC §5.2 (Phase 3 PR 4 rewrite).

Each function returns a ``plotly.graph_objects.Figure`` object that
``ui/outputs.py`` passes to ``st.plotly_chart``. Pure constructors: no
Streamlit imports, no caching, no global state.

PR 4 changes versus PR 3:

* Every figure now picks up the shared Plotly template registered in
  ``ui/theme.py`` (``hel_dark`` / ``hel_light`` selected via
  ``plotly.io.templates.default``). No figure overrides paper / plot-area
  backgrounds, gridlines, axes, spike lines, hover-box styling, or tick
  fonts — those are the template's job. One edit in ``ui/theme.py``
  re-themes every chart.
* Multi-series lines use a **hue + dash + marker-shape** triad so a
  protanope / deuteranope / tritanope viewer distinguishes series by dash
  and marker shape even if the hues collapse. Series A is amber / solid /
  circle; B is teal / dash / square; C is purple / dot / diamond.
* Every constructor accepts ``sweep=None`` (or an empty list) and renders
  a frame with a centered advisory annotation instead of silently
  failing. The advisory copy comes from ``ui/labels.ADVISORY`` — infeasible
  geometry, no burn-through, etc.
* Hover templates use English labels + display units (Peak irradiance,
  Time to burn-through, Atmospheric transmission, …) rather than SPEC
  dict keys.
* Plot A accepts an optional ``log_y`` flag so callers can offer the
  user a linear / log radio above the chart (the left axis spans several
  decades at realistic engagement ranges).

Unified hover (``hovermode='x unified'``) is preserved on every figure.
Cross-plot synchronization was considered in SPEC v1.6 and descoped —
each plot is self-contained.

The ``sweep`` argument is a ``list[dict]`` where each element is a
merged-result dict (one per range sample along the user-selected range
axis) with at least these keys:

  - ``range`` (m): slant range at this sample
  - ``I_peak`` (W/m²), ``PIB_fraction``, ``S_TB``, ``tau_atm``,
    ``w_diff``, ``w_total``, ``w_turb``, ``w_jit``, ``tau_BT``,
    ``available_dwell``

Missing keys fall back to ``NaN`` so the plot still renders — e.g. if
``M8`` has not been exercised along the full sweep.

References:
    SPEC.md §5.2 — plot contracts and hover-tooltip content.
    SPEC.md §5.3 item 10 — always-render chart frames commitment.
    ARCHITECTURE.md §6.5 — file contract, signatures, template adoption.
    ui/theme.py — palette dicts + registered Plotly templates.
    ui/labels.py — ADVISORY strings and OUTPUT_LABELS for axis / series names.
"""

from __future__ import annotations

import math

import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from ui.labels import ADVISORY
from ui.theme import PALETTE_DARK, PALETTE_LIGHT, PLOT_HEIGHTS


# ---------------------------------------------------------------------------
# Palette lookup — matches whichever template ``ui.theme.apply`` registered.
# ---------------------------------------------------------------------------

def _active_palette() -> dict[str, str]:
    """Return the palette dict matching the current Plotly default template.

    ``ui.theme.apply(app_mode)`` sets ``plotly.io.templates.default`` to
    ``"hel_dark"`` or ``"hel_light"``; plot constructors consult that
    default so every figure picks up the right palette without the caller
    threading ``app_mode`` through.
    """
    return PALETTE_LIGHT if pio.templates.default == "hel_light" else PALETTE_DARK


# ---------------------------------------------------------------------------
# Series styling — hue + dash + marker for color-blind dual-encoding.
# ---------------------------------------------------------------------------
# Three primary data series; each tuple is (palette color token, dash
# pattern, marker symbol). The combination hue + dash + marker means a
# viewer with any single dichromatic color-vision deficiency still
# distinguishes the three series by the remaining two channels.
_SERIES: tuple[tuple[str, str, str], ...] = (
    ("data.a", "solid",  "circle"),
    ("data.b", "dash",   "square"),
    ("data.c", "dot",    "diamond"),
)


def _series_style(i: int, palette: dict[str, str]) -> dict[str, dict]:
    """Return ``{"line": ..., "marker": ...}`` kwargs for the i-th series.

    Repeats cyclically beyond three series (rare). Callers spread the
    returned mapping into ``go.Scatter(line=..., marker=...)``.
    """
    color_token, dash, symbol = _SERIES[i % len(_SERIES)]
    color = palette[color_token]
    return {
        "line":   dict(color=color, width=2, dash=dash),
        "marker": dict(color=color, size=5, symbol=symbol),
    }


def _reference_style(palette: dict[str, str]) -> dict:
    """Gray dash-dot styling for reference lines (e.g. diffraction limit)."""
    return dict(color=palette["data.reference"], width=1.5, dash="dashdot")


# ---------------------------------------------------------------------------
# Sweep helpers.
# ---------------------------------------------------------------------------

def _x_km(sweep: list[dict]) -> list[float]:
    """Return the sweep's slant-range axis in km (for readable tick labels)."""
    return [s.get("range", 0.0) / 1000.0 for s in sweep]


def _get(sweep: list[dict], key: str, default: float = math.nan) -> list[float]:
    """Pull one key across the sweep, coercing missing entries to a sentinel."""
    return [float(s.get(key, default)) for s in sweep]


def _log_safe(values: list[float]) -> list[float]:
    """Clip non-positive / non-finite values to NaN so log axes don't explode."""
    return [v if (v is not None and v > 0 and math.isfinite(v)) else math.nan
            for v in values]


def _all_nan(values: list[float]) -> bool:
    """Return True when every element is NaN or None (no plottable data)."""
    return all(
        (v is None) or (isinstance(v, float) and not math.isfinite(v))
        for v in values
    )


# ---------------------------------------------------------------------------
# Always-render frame helper.
# ---------------------------------------------------------------------------

def _empty_frame(
    *,
    title: str,
    xtitle: str,
    ytitle: str,
    advisory: str,
    height: int,
) -> go.Figure:
    """Return a frame-only figure with a centered advisory annotation.

    Called when the sweep is missing, infeasible, or all-NaN. The axes
    are drawn (via the shared Plotly template) so the layout slot
    reserves the same pixel footprint it will when data becomes
    available; the advisory reads inside the plot area rather than
    replacing the figure with a blank.
    """
    palette = _active_palette()
    fig = go.Figure()
    fig.update_layout(
        title=title,
        height=height,
        hovermode=False,
    )
    # Hide tick labels but keep the axis lines and titles so the frame
    # still reads as "a chart that is waiting for data".
    fig.update_xaxes(
        title_text=xtitle,
        range=[0, 1],
        showticklabels=False,
        showspikes=False,
    )
    fig.update_yaxes(
        title_text=ytitle,
        range=[0, 1],
        showticklabels=False,
        showspikes=False,
    )
    fig.add_annotation(
        text=advisory,
        xref="paper", yref="paper",
        x=0.5, y=0.5, xanchor="center", yanchor="middle",
        showarrow=False,
        align="center",
        font=dict(color=palette["fg.secondary"], size=13),
        bgcolor=palette["bg.surface"],
        bordercolor=palette["border.subtle"],
        borderwidth=1,
        borderpad=10,
    )
    return fig


# ---------------------------------------------------------------------------
# Plot A — Peak irradiance + aimpoint throughput vs slant range.
# ---------------------------------------------------------------------------

def plot_a_on_target_performance(
    sweep: list[dict] | None,
    *,
    log_y: bool = False,
) -> go.Figure:
    """Peak irradiance and aimpoint-throughput curves vs slant range.

    Left y-axis: peak irradiance (solid data-series A) and the
    diffraction-limited baseline (gray dash-dot reference). Right
    y-axis: three dimensionless 0-1 curves — power-in-the-bucket,
    thermal-blooming Strehl, atmospheric transmission. Optional log
    scaling on the primary y-axis via ``log_y`` (useful when the peak
    irradiance spans decades along the sweep).

    When ``sweep`` is ``None`` or empty, renders a frame-only figure
    with the "infeasible geometry" advisory centered inside the plot
    area so the layout slot remains intact.
    """
    height = PLOT_HEIGHTS["hero"]
    xtitle = "Slant range (km)"
    ytitle = "Peak irradiance (W/cm²)"
    title = "Peak irradiance vs slant range"

    if not sweep:
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["infeasible_geometry"], height=height,
        )

    palette = _active_palette()
    x_km = _x_km(sweep)
    I_peak_cm2 = [v / 1e4 for v in _get(sweep, "I_peak")]
    PIB = _get(sweep, "PIB_fraction")
    S_TB = _get(sweep, "S_TB")
    tau_atm = _get(sweep, "tau_atm")

    # Diffraction-limited baseline — reconstruct from the per-sample
    # algebra  I_peak_actual = 2·P·τ·S_TB / (π·w_total²)  and
    # I_peak_diff = 2·P·τ / (π·w_diff²). The ratio collapses to
    # (w_total/w_diff)² / S_TB, algebraically identical when S_TB=1.
    I_peak_diff: list[float] = []
    for s in sweep:
        w_diff = s.get("w_diff")
        w_total = s.get("w_total")
        I_peak_actual = s.get("I_peak")
        S_TB_s = s.get("S_TB", 1.0)
        if (w_diff and w_total and I_peak_actual and S_TB_s > 0
                and w_diff > 0 and w_total > 0):
            ratio = (w_total ** 2) / (w_diff ** 2) / S_TB_s
            I_peak_diff.append((I_peak_actual * ratio) / 1e4)
        else:
            I_peak_diff.append(math.nan)

    # Guard against all-NaN inputs (e.g. a sweep that satisfied the
    # orchestrator but produced NaN peaks everywhere) — still render a frame.
    if _all_nan(I_peak_cm2):
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["infeasible_geometry"], height=height,
        )

    # For log y-axis, clip non-positive peak-irradiance values to NaN so
    # the log transform does not explode on the rare zero sample.
    if log_y:
        I_peak_cm2 = _log_safe(I_peak_cm2)
        I_peak_diff = _log_safe(I_peak_diff)

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Series A (amber / solid / circle) — actual peak irradiance.
    s0 = _series_style(0, palette)
    fig.add_trace(
        go.Scatter(
            x=x_km, y=I_peak_cm2,
            mode="lines+markers",
            name="Peak irradiance",
            line=s0["line"], marker=s0["marker"],
            hovertemplate="%{y:.3g} W/cm²<extra></extra>",
        ),
        secondary_y=False,
    )
    # Reference (gray / dashdot) — diffraction-limited baseline.
    fig.add_trace(
        go.Scatter(
            x=x_km, y=I_peak_diff,
            mode="lines",
            name="Diffraction limit",
            line=_reference_style(palette),
            hovertemplate="%{y:.3g} W/cm²<extra></extra>",
        ),
        secondary_y=False,
    )
    # Series B (teal / dash / square) — power in the bucket.
    s1 = _series_style(1, palette)
    fig.add_trace(
        go.Scatter(
            x=x_km, y=PIB,
            mode="lines+markers",
            name="Power in the bucket",
            line=s1["line"], marker=s1["marker"],
            hovertemplate="%{y:.2f}<extra></extra>",
        ),
        secondary_y=True,
    )
    # Series C (purple / dot / diamond) — thermal-blooming Strehl.
    s2 = _series_style(2, palette)
    fig.add_trace(
        go.Scatter(
            x=x_km, y=S_TB,
            mode="lines+markers",
            name="Strehl (thermal blooming)",
            line=s2["line"], marker=s2["marker"],
            hovertemplate="%{y:.2f}<extra></extra>",
        ),
        secondary_y=True,
    )
    # Fourth supporting curve (gray / long-dash) — atmospheric
    # transmission. Uses the reference hue so it does not compete with
    # the three primary dual-encoded series.
    fig.add_trace(
        go.Scatter(
            x=x_km, y=tau_atm,
            mode="lines",
            name="Atmospheric transmission",
            line=dict(
                color=palette["data.reference"], width=1.5, dash="longdash",
            ),
            hovertemplate="%{y:.2f}<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title=title,
        hovermode="x unified",
        height=height,
    )
    fig.update_xaxes(title_text=xtitle)
    fig.update_yaxes(
        title_text=ytitle,
        type="log" if log_y else "linear",
        secondary_y=False,
    )
    fig.update_yaxes(
        title_text="Dimensionless (0–1)",
        range=[0, 1.05],
        secondary_y=True,
    )
    return fig


# ---------------------------------------------------------------------------
# Plot B — Time-to-burn-through vs slant range.
# ---------------------------------------------------------------------------

def plot_b_time_to_burnthrough(
    sweep: list[dict] | None,
) -> go.Figure:
    """Time-to-burn-through and available-dwell reference vs slant range.

    The region where ``tau_BT < available_dwell`` is shaded faintly with
    the status-ok color to visualize the engageable-range band per
    SPEC §5.2. Y-axis is log-scaled because burn-through time ranges
    over several decades across realistic geometries.

    When ``sweep`` is ``None``/empty, renders a frame-only figure with
    the "infeasible geometry" advisory. When every burn-through time is
    NaN (e.g. every sweep sample fails to reach burn-through), renders
    the "no burn-through" advisory instead.
    """
    height = PLOT_HEIGHTS["hero"]
    xtitle = "Slant range (km)"
    ytitle = "Time (s)"
    title = "Time to burn-through vs slant range"

    if not sweep:
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["infeasible_geometry"], height=height,
        )

    palette = _active_palette()
    x_km = _x_km(sweep)
    tau_BT = _log_safe(_get(sweep, "tau_BT"))
    dwell = _log_safe(_get(sweep, "available_dwell"))

    if _all_nan(tau_BT):
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["no_burnthrough"], height=height,
        )

    fig = go.Figure()
    s0 = _series_style(0, palette)
    fig.add_trace(
        go.Scatter(
            x=x_km, y=tau_BT,
            mode="lines+markers",
            name="Time to burn-through",
            line=s0["line"], marker=s0["marker"],
            hovertemplate="%{y:.3g} s<extra></extra>",
        )
    )
    s1 = _series_style(1, palette)
    fig.add_trace(
        go.Scatter(
            x=x_km, y=dwell,
            mode="lines+markers",
            name="Available dwell",
            line=s1["line"], marker=s1["marker"],
            hovertemplate="%{y:.3g} s<extra></extra>",
        )
    )

    # Engageable band — wherever τ_BT < dwell, shade between the two
    # curves. The fill uses the status-ok hue at low alpha so the band
    # reads as "green = engageable" without competing with the lines.
    engageable_lower: list[float] = []
    engageable_upper: list[float] = []
    for tbt, dw in zip(tau_BT, dwell):
        if (isinstance(tbt, float) and isinstance(dw, float)
                and math.isfinite(tbt) and math.isfinite(dw) and tbt < dw):
            engageable_lower.append(tbt)
            engageable_upper.append(dw)
        else:
            engageable_lower.append(math.nan)
            engageable_upper.append(math.nan)

    # Convert status.ok hex to rgba for the fill.
    ok_rgba = _hex_to_rgba(palette["status.ok"], alpha=0.18)
    fig.add_trace(
        go.Scatter(
            x=x_km + x_km[::-1],
            y=engageable_upper + engageable_lower[::-1],
            fill="toself",
            fillcolor=ok_rgba,
            line=dict(color="rgba(0,0,0,0)"),
            hoverinfo="skip",
            name="Engageable range",
            showlegend=True,
        )
    )

    fig.update_layout(
        title=title,
        hovermode="x unified",
        height=height,
    )
    fig.update_xaxes(title_text=xtitle)
    fig.update_yaxes(title_text=ytitle, type="log")
    return fig


# ---------------------------------------------------------------------------
# Plot C — Spot-diameter breakdown vs slant range.
# ---------------------------------------------------------------------------

def plot_c_beam_diameter_breakdown(
    sweep: list[dict] | None,
) -> go.Figure:
    """Spot-diameter contributions vs slant range.

    Five curves (all 1/e² diameters in cm):

      * Total spot diameter — solid data-series A.
      * Diffraction-limited diameter (pure Gaussian, M²=1) — gray
        dash-dot reference.
      * Beam-quality excess (diffraction − diffraction-pure) — data-
        series B (teal / dash / square).
      * Turbulence contribution — data-series C (purple / dot /
        diamond).
      * Jitter contribution — a supporting reference trace in the
        reference hue so it does not compete with the three primary
        dual-encoded series.

    Renders a frame with "infeasible geometry" advisory when ``sweep``
    is ``None``/empty.
    """
    height = PLOT_HEIGHTS["hero"]
    xtitle = "Slant range (km)"
    ytitle = "1/e² diameter (cm)"
    title = "Spot diameter vs slant range"

    if not sweep:
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["infeasible_geometry"], height=height,
        )

    palette = _active_palette()
    x_km = _x_km(sweep)

    def _d_cm(key: str) -> list[float]:
        """Return 2·<key> in centimeters (key is a 1/e² radius in m)."""
        return [2.0 * float(s.get(key, math.nan)) * 100.0 for s in sweep]

    d_total = _d_cm("w_total")
    d_diff = _d_cm("w_diff")
    d_turb = _d_cm("w_turb")
    d_jit = _d_cm("w_jit")

    # Diffraction-pure diameter: 2·w0·sqrt(1 + (L/z_R)²). When w0 or z_R
    # is missing on a sample, the diameter falls back to NaN and that
    # sample's marker is skipped.
    d_diff_pure: list[float] = []
    for s in sweep:
        w0 = s.get("w0")
        zR = s.get("zR")
        L = s.get("range")
        if w0 and zR and L and zR > 0:
            w = w0 * math.sqrt(1.0 + (L / zR) ** 2)
            d_diff_pure.append(2.0 * w * 100.0)
        else:
            d_diff_pure.append(math.nan)

    # Beam-quality excess = d_diff − d_diff_pure (what M² adds on top of
    # the pure-Gaussian diffraction limit).
    d_m2_excess = [
        (d - dp) if (isinstance(d, float) and isinstance(dp, float)
                    and math.isfinite(d) and math.isfinite(dp)) else math.nan
        for d, dp in zip(d_diff, d_diff_pure)
    ]

    if _all_nan(d_total):
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["infeasible_geometry"], height=height,
        )

    fig = go.Figure()
    s0 = _series_style(0, palette)
    fig.add_trace(
        go.Scatter(
            x=x_km, y=d_total,
            mode="lines+markers",
            name="Total spot diameter",
            line=dict(**{**s0["line"], "width": 2.5}),
            marker=s0["marker"],
            hovertemplate="%{y:.3g} cm<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_km, y=d_diff_pure,
            mode="lines",
            name="Diffraction-limited diameter",
            line=_reference_style(palette),
            hovertemplate="%{y:.3g} cm<extra></extra>",
        )
    )
    s1 = _series_style(1, palette)
    fig.add_trace(
        go.Scatter(
            x=x_km, y=d_m2_excess,
            mode="lines+markers",
            name="Beam-quality excess",
            line=s1["line"], marker=s1["marker"],
            hovertemplate="%{y:.3g} cm<extra></extra>",
        )
    )
    s2 = _series_style(2, palette)
    fig.add_trace(
        go.Scatter(
            x=x_km, y=d_turb,
            mode="lines+markers",
            name="Turbulence contribution",
            line=s2["line"], marker=s2["marker"],
            hovertemplate="%{y:.3g} cm<extra></extra>",
        )
    )
    # Jitter uses the reference hue (gray) with a short-dash line — a
    # fourth series would force us outside the three-way dual-encoding
    # rule; jitter is usually the smallest contribution and reads fine
    # as a supporting gray reference.
    fig.add_trace(
        go.Scatter(
            x=x_km, y=d_jit,
            mode="lines",
            name="Jitter contribution",
            line=dict(
                color=palette["data.reference"], width=1.5, dash="dot",
            ),
            hovertemplate="%{y:.3g} cm<extra></extra>",
        )
    )

    fig.update_layout(
        title=title,
        hovermode="x unified",
        height=height,
    )
    fig.update_xaxes(title_text=xtitle)
    fig.update_yaxes(title_text=ytitle)
    return fig


# ---------------------------------------------------------------------------
# Color helpers.
# ---------------------------------------------------------------------------

def _hex_to_rgba(hex_color: str, *, alpha: float) -> str:
    """Convert a ``#rrggbb`` hex string to an ``rgba(r,g,b,a)`` CSS string.

    Used by Plot B to shade the engageable-range band at 18% alpha over
    the status-ok hue.
    """
    h = hex_color.lstrip("#")
    if len(h) != 6:
        # Fallback to the input; caller supplies a palette value so this
        # branch should never fire in practice.
        return hex_color
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


__all__ = [
    "plot_a_on_target_performance",
    "plot_b_time_to_burnthrough",
    "plot_c_beam_diameter_breakdown",
]
