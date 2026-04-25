"""Plotly figure constructors per SPEC §5.2 (Phase 3 PR 5 rewrite).

Each function returns a ``plotly.graph_objects.Figure`` object that
``ui/outputs.py`` passes to ``st.plotly_chart``. Pure constructors: no
Streamlit imports, no caching, no global state.

PR 5 additions versus PR 4:

* Six new constructors wire Target effects, Safety, Atmosphere, and
  Overview to real plots (plan item: "every plot-owning tab renders its
  plot"). The new entry points are:

    - ``plot_overview_dwell_vs_burnthrough``   — Overview hero bar.
    - ``plot_target_temperature_envelope``      — Target effects T envelope.
    - ``plot_target_material_comparison``       — Target effects bar.
    - ``plot_safety_nohd_zones``                — Safety range-axis zones.
    - ``plot_atmosphere_extinction_breakdown``  — Atmosphere stacked bar.
    - ``plot_atmosphere_transmission_vs_range`` — Atmosphere line chart.

  Each one honours the PR 4 contract: shared template, always-render
  frame + advisory when the underlying data is missing, dual-encoded
  series palette, English-prose hover labels.

* No physics changes. The material-comparison constructor receives a
  pre-computed ``{material_name: tau_BT}`` dict; the caller in
  ``ui/outputs.py`` does the seven-times ``m8_burnthrough.compute`` call
  through a ``@st.cache_data`` wrapper so the render path stays fast on
  subsequent reruns.

* The temperature-vs-time view is a simplified two-point envelope
  (ambient → peak, linear interpolation) because the M8 solver only
  returns scalar endpoints in v1. The plot caption and the shared
  ADVISORY["temperature_schematic"] string make the simplification
  explicit to the reader.

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

    Six curves (all 1/e² diameters in cm):

      * Total spot diameter — solid data-series A.
      * Diffraction-limited diameter (pure Gaussian, M²=1) — gray
        dash-dot reference.
      * Beam-quality excess (diffraction − diffraction-pure) — data-
        series B (teal / dash / square).
      * Turbulence contribution — data-series C (purple / dot /
        diamond).
      * Blooming contribution — status-warn hue (amber-orange) /
        dash-dot / triangle-up marker. The contribution is non-zero
        only when N_D ≥ 5 (M6 sets w_bloom = 0 below the Smith cutoff
        per SPEC §3 M6); on samples in the negligible regime the trace
        sits at zero. Without this trace the gap between summed
        components and the total in this plot is unexplained whenever
        blooming engages.
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
    d_bloom = _d_cm("w_bloom")

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
    # Blooming contribution. Uses the status-warn hue because w_bloom > 0
    # is itself the SPEC §10.4 HIGH-UNCERTAINTY regime; the dual-encoded
    # data.a/b/c slots are reserved for the diffraction / M² / turbulence
    # diagnostic triad. dashdot + triangle-up keeps it visually separable
    # from the three primary series and the gray reference traces.
    fig.add_trace(
        go.Scatter(
            x=x_km, y=d_bloom,
            mode="lines+markers",
            name="Blooming contribution",
            line=dict(color=palette["status.warn"], width=1.8, dash="dashdot"),
            marker=dict(symbol="triangle-up", size=6,
                        color=palette["status.warn"]),
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


# ---------------------------------------------------------------------------
# Overview hero — dwell vs burn-through comparison (PR 5).
# ---------------------------------------------------------------------------

def plot_overview_dwell_vs_burnthrough(
    dwell: float | None,
    tau_bt: float | None,
) -> go.Figure:
    """Grouped vertical bars comparing available dwell and time-to-burn-through.

    The Overview tab's single hero chart. Reads "can I hold the beam on
    target long enough to kill it?" in one glance — the dwell bar must
    sit at or above the burn-through bar for the engagement to be
    viable. The y-axis is log-scaled because both quantities span
    several decades across realistic inputs.

    Degenerate cases:

    * ``dwell`` is ``None`` or ≤ 0 → advisory "no dwell available".
    * ``tau_bt`` is ``None`` or NaN → advisory "no burn-through".
    * ``tau_bt`` ≤ 0 (instantaneous) → renders a single dwell bar with
      an informative caption rather than a malformed log-scale value.

    Args:
        dwell: available-dwell seconds from ``m3`` — None or ≤ 0 triggers
            the no-dwell advisory frame.
        tau_bt: time-to-burn-through seconds from ``m8`` — None / NaN
            triggers the no-burn-through advisory frame.
    """
    height = PLOT_HEIGHTS["default"]
    xtitle = ""
    ytitle = "Time (s)"
    title = "Available dwell vs time to burn-through"

    if dwell is None or (isinstance(dwell, float) and not math.isfinite(dwell)):
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["no_dwell_available"], height=height,
        )
    if dwell <= 0.0:
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["no_dwell_available"], height=height,
        )
    if tau_bt is None or (isinstance(tau_bt, float) and not math.isfinite(tau_bt)):
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["no_burnthrough"], height=height,
        )

    palette = _active_palette()
    s_ok = palette["status.ok"]
    s_err = palette["status.error"]
    # Dwell always uses the data-A hue; burn-through tint follows feasibility
    # so the reader's eye lands on the failure case directly.
    tau_color = s_ok if tau_bt <= dwell else s_err

    categories = ["Available dwell", "Time to burn-through"]
    values = [dwell, max(tau_bt, 1e-6)]  # log-axis guard for tau_bt ≤ 0

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=categories,
            y=values,
            marker_color=[palette["data.a"], tau_color],
            hovertemplate="%{x}: %{y:.3g} s<extra></extra>",
            showlegend=False,
        )
    )

    # Margin annotation — the headline number above the bars.
    margin_frac = (dwell - tau_bt) / tau_bt if tau_bt > 0 else float("inf")
    if math.isfinite(margin_frac):
        annotation_text = f"Engagement margin: {margin_frac * 100:+.0f}%"
    else:
        annotation_text = "Engagement margin: instantaneous"
    fig.add_annotation(
        text=annotation_text,
        xref="paper", yref="paper",
        x=0.5, y=1.0, xanchor="center", yanchor="bottom",
        showarrow=False,
        font=dict(color=palette["fg.secondary"], size=12),
    )

    fig.update_layout(
        title=title,
        height=height,
        hovermode="x",
        showlegend=False,
    )
    fig.update_xaxes(title_text=xtitle, showgrid=False)
    fig.update_yaxes(title_text=ytitle, type="log")
    return fig


# ---------------------------------------------------------------------------
# Target effects — temperature envelope (simplified two-point view).
# ---------------------------------------------------------------------------

def plot_target_temperature_envelope(
    *,
    t_amb_c: float | None,
    t_peak_c: float | None,
    t_fail_c: float | None,
    tau_bt: float | None,
    dwell: float | None,
) -> go.Figure:
    """Two-point temperature envelope with failure-threshold annotation.

    Simplified view because ``m8`` exposes only scalar endpoints in v1 —
    the ambient baseline at ``t = 0`` and the peak surface temperature
    at ``t = tau_bt``. The constructor draws a line between the two
    scalars, plus a horizontal failure-threshold reference (``t_fail``)
    and a vertical dwell reference (``dwell``) so the reader can see at
    a glance how close the peak ran to failure and whether the
    kinematics allowed reaching that peak in the first place.

    All inputs are Celsius; the caller in ``ui/outputs.py`` converts
    from Kelvin before calling. This keeps the constructor unit-neutral
    (Celsius shows nicer axis numbers for the realistic range).

    Renders a frame + advisory when any endpoint is missing.
    """
    height = PLOT_HEIGHTS["default"]
    xtitle = "Time (s)"
    ytitle = "Surface temperature (°C)"
    title = "Surface temperature envelope"

    if (
        t_amb_c is None or t_peak_c is None
        or tau_bt is None or (isinstance(tau_bt, float) and not math.isfinite(tau_bt))
        or tau_bt <= 0.0
    ):
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["no_burnthrough"], height=height,
        )

    palette = _active_palette()

    # X-axis: 0 → max(tau_bt, dwell) * 1.1 so the dwell marker stays in
    # frame even when dwell > tau_bt (the "margin" case).
    x_max = max(tau_bt, dwell or 0.0) * 1.1
    # Y-axis: anchor to ambient and expand to include fail threshold plus
    # a small headroom so annotations don't hit the frame edge.
    y_max_candidates = [t_peak_c]
    if t_fail_c is not None:
        y_max_candidates.append(t_fail_c)
    y_max = max(y_max_candidates) * 1.05 if max(y_max_candidates) > 0 else 1.0
    y_min = min(t_amb_c, 0.0) - 10.0

    fig = go.Figure()
    # Rise segment (series A, amber solid, circles at the two endpoints).
    s0 = _series_style(0, palette)
    fig.add_trace(
        go.Scatter(
            x=[0.0, tau_bt],
            y=[t_amb_c, t_peak_c],
            mode="lines+markers",
            name="Surface temperature",
            line=s0["line"], marker=s0["marker"],
            hovertemplate="t = %{x:.2g} s, T = %{y:.1f} °C<extra></extra>",
        )
    )

    # Failure-threshold horizontal line + annotation.
    if t_fail_c is not None and math.isfinite(t_fail_c):
        fig.add_hline(
            y=t_fail_c,
            line=dict(color=palette["status.error"], width=1.5, dash="dash"),
            annotation_text=f"Failure threshold: {t_fail_c:.0f} °C",
            annotation_position="top right",
            annotation_font=dict(color=palette["status.error"], size=11),
        )

    # Burn-through vertical marker.
    fig.add_vline(
        x=tau_bt,
        line=dict(color=palette["data.a"], width=1.5, dash="dot"),
        annotation_text=f"Burn-through: {tau_bt:.2g} s",
        annotation_position="top",
        annotation_font=dict(color=palette["data.a"], size=11),
    )

    # Available-dwell vertical marker (only when it's inside the frame).
    if dwell is not None and math.isfinite(dwell) and dwell > 0.0:
        fig.add_vline(
            x=dwell,
            line=dict(color=palette["status.ok"], width=1.5, dash="dashdot"),
            annotation_text=f"Available dwell: {dwell:.2g} s",
            annotation_position="bottom",
            annotation_font=dict(color=palette["status.ok"], size=11),
        )

    fig.update_layout(
        title=title,
        hovermode="x",
        height=height,
    )
    fig.update_xaxes(title_text=xtitle, range=[0.0, x_max])
    fig.update_yaxes(title_text=ytitle, range=[y_min, y_max])
    return fig


# ---------------------------------------------------------------------------
# Target effects — tau_BT comparison across v1 materials.
# ---------------------------------------------------------------------------

def plot_target_material_comparison(
    *,
    material_tau_bt: dict[str, float] | None,
    material_labels: dict[str, str],
    current_material: str | None,
    dwell: float | None,
) -> go.Figure:
    """Horizontal bar chart of time-to-burn-through across v1 materials.

    One row per material. The currently-selected material highlights in
    the primary data hue; the other six read in the reference gray so
    the eye lands on the current selection first. A vertical reference
    line marks the available dwell — any bar to the left of the line is
    engageable at the reference-range flux.

    Args:
        material_tau_bt: {material_name: tau_BT_seconds}. NaN or
            non-finite entries are shown as "timeout" bars at the right
            edge of the axis (so the layout stays stable).
        material_labels: {material_name: display_label} — English-prose
            labels from the caller (drawn from ``ui/labels.py`` or a
            simple title-case fallback).
        current_material: which material is selected in the input
            panel; that bar highlights in the primary hue.
        dwell: available-dwell seconds — draws a vertical reference
            line when finite and positive.
    """
    height = PLOT_HEIGHTS["hero"]
    xtitle = "Time to burn-through (s)"
    ytitle = ""
    title = "Burn-through comparison across v1 materials"

    if not material_tau_bt:
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["material_comparison_unavailable"],
            height=height,
        )

    palette = _active_palette()

    # Stable sort: ascending by tau_bt so the fastest-failing material
    # sits at the top of the bar chart (easier to compare visually).
    # Non-finite values sink to the bottom.
    def _key(entry: tuple[str, float]) -> tuple[int, float]:
        _, v = entry
        if not math.isfinite(v):
            return (1, 0.0)
        return (0, v)

    sorted_items = sorted(material_tau_bt.items(), key=_key)

    labels: list[str] = []
    values: list[float] = []
    colors: list[str] = []
    hover_texts: list[str] = []
    for name, v in sorted_items:
        display = material_labels.get(name, name)
        labels.append(display)
        is_current = (name == current_material)
        colors.append(palette["data.a"] if is_current else palette["data.reference"])
        if math.isfinite(v) and v > 0:
            values.append(v)
            hover_texts.append(f"{display}: {v:.3g} s")
        else:
            # Display timeout materials at the right edge using the
            # largest finite value ×1.2 so they remain visually
            # distinguishable from feasible ones.
            finite_vals = [w for _, w in sorted_items
                           if math.isfinite(w) and w > 0]
            fill_val = (max(finite_vals) * 1.2) if finite_vals else 60.0
            values.append(fill_val)
            hover_texts.append(f"{display}: no burn-through before timeout")

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=colors,
            text=hover_texts,
            hovertemplate="%{text}<extra></extra>",
            showlegend=False,
        )
    )

    # Available-dwell vertical marker.
    if dwell is not None and math.isfinite(dwell) and dwell > 0.0:
        fig.add_vline(
            x=dwell,
            line=dict(color=palette["status.ok"], width=1.5, dash="dashdot"),
            annotation_text=f"Available dwell: {dwell:.2g} s",
            annotation_position="top right",
            annotation_font=dict(color=palette["status.ok"], size=11),
        )

    fig.update_layout(
        title=title,
        height=height,
        hovermode="y",
        showlegend=False,
    )
    fig.update_xaxes(title_text=xtitle, type="log")
    fig.update_yaxes(title_text=ytitle, automargin=True)
    return fig


# ---------------------------------------------------------------------------
# Safety — NOHD hazard zones along range axis.
# ---------------------------------------------------------------------------

def plot_safety_nohd_zones(
    *,
    nohd_tophat: float | None,
    nohd_gausspeak: float | None,
) -> go.Figure:
    """Range-axis schematic with three colored hazard zones.

    A compact horizontal schematic of the hazard envelope: three bands
    along a slant-range axis, colored from error-red (eye-hazardous
    under both conventions) through warn-amber (hazardous under the
    more-conservative Gaussian-peak convention only) to ok-green (safe
    under both conventions). Vertical markers pin each NOHD value so
    the reader can read the thresholds directly off the chart.

    The axis extends to 1.5× the larger of the two NOHD values so both
    transitions are clearly visible.
    """
    height = PLOT_HEIGHTS["cross-section"]
    xtitle = "Slant range (km)"
    ytitle = ""
    title = "Hazard zones along slant range"

    if (
        nohd_tophat is None or nohd_gausspeak is None
        or not math.isfinite(nohd_tophat) or not math.isfinite(nohd_gausspeak)
        or (nohd_tophat <= 0.0 and nohd_gausspeak <= 0.0)
    ):
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["no_hazard_data"], height=height,
        )

    palette = _active_palette()

    nohd_th_km = max(nohd_tophat, 0.0) / 1000.0
    nohd_gp_km = max(nohd_gausspeak, 0.0) / 1000.0
    # Gaussian-peak NOHD is the more conservative (larger) of the two —
    # pin a consistent ordering so the zone logic below stays right even
    # if the values arrive in an unexpected order.
    inner = min(nohd_th_km, nohd_gp_km)
    outer = max(nohd_th_km, nohd_gp_km)
    axis_max = max(outer * 1.5, outer + 0.1)

    fig = go.Figure()

    # Three shaded zones. The shape layer sits behind the vertical
    # markers; the 0.22 alpha stays legible on both dark and light
    # templates without overwhelming the axis grid.
    def _zone(x0: float, x1: float, hex_color: str) -> None:
        fig.add_shape(
            type="rect",
            xref="x", yref="paper",
            x0=x0, x1=x1, y0=0.0, y1=1.0,
            fillcolor=_hex_to_rgba(hex_color, alpha=0.22),
            line=dict(width=0),
            layer="below",
        )

    _zone(0.0,   inner,     palette["status.error"])
    _zone(inner, outer,     palette["status.warn"])
    _zone(outer, axis_max,  palette["status.ok"])

    # Zone labels as paper-anchored annotations above the axis.
    for x0, x1, text, color in (
        (0.0,   inner,    "Hazard zone",             palette["status.error"]),
        (inner, outer,    "Transition zone",         palette["status.warn"]),
        (outer, axis_max, "Safe under both conventions", palette["status.ok"]),
    ):
        if x1 > x0:
            fig.add_annotation(
                x=(x0 + x1) / 2.0, y=0.88,
                xref="x", yref="paper",
                text=text,
                showarrow=False,
                font=dict(color=color, size=11),
            )

    # Vertical markers for the two NOHD conventions.
    for x_km, label_text, color in (
        (nohd_gp_km, f"NOHD (Gaussian-peak): {nohd_gp_km:.2f} km", palette["data.a"]),
        (nohd_th_km, f"NOHD (top-hat): {nohd_th_km:.2f} km",       palette["data.b"]),
    ):
        fig.add_vline(
            x=x_km,
            line=dict(color=color, width=1.8, dash="solid"),
            annotation_text=label_text,
            annotation_position="top",
            annotation_font=dict(color=color, size=11),
        )

    # Invisible scatter along the axis so hover works across the range.
    fig.add_trace(
        go.Scatter(
            x=[0.0, axis_max],
            y=[0.5, 0.5],
            mode="lines",
            line=dict(color="rgba(0,0,0,0)"),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    fig.update_layout(
        title=title,
        height=height,
        hovermode=False,
        showlegend=False,
    )
    fig.update_xaxes(title_text=xtitle, range=[0.0, axis_max])
    fig.update_yaxes(
        title_text=ytitle,
        range=[0.0, 1.0],
        showticklabels=False,
        showgrid=False,
        zeroline=False,
    )
    return fig


# ---------------------------------------------------------------------------
# Atmosphere — extinction breakdown (horizontal stacked bar).
# ---------------------------------------------------------------------------

def plot_atmosphere_extinction_breakdown(
    *,
    alpha_mol_abs_si: float,
    alpha_mol_scat_si: float,
    alpha_aer_abs_si: float,
    alpha_aer_scat_si: float,
) -> go.Figure:
    """Horizontal stacked bar split into the four extinction components.

    All four inputs are in SI 1/m; the plot converts to display 1/km.
    When the total is effectively zero (vacuum-like path), renders the
    frame + "vacuum_path" advisory so the tab still reads as
    "a chart that is waiting for atmosphere".
    """
    height = PLOT_HEIGHTS["paired"]
    xtitle = "Extinction coefficient (1/km)"
    ytitle = ""
    title = "Atmospheric extinction breakdown"

    total_si = (alpha_mol_abs_si + alpha_mol_scat_si
                + alpha_aer_abs_si + alpha_aer_scat_si)
    if total_si <= 1e-12:
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["vacuum_path"], height=height,
        )

    palette = _active_palette()

    # Component list (label, value in 1/km, color token). Order reads
    # left-to-right: molecular first (always present), then aerosol.
    components = (
        ("Molecular absorption",  alpha_mol_abs_si  * 1e3, "data.a"),
        ("Molecular scattering",  alpha_mol_scat_si * 1e3, "data.b"),
        ("Aerosol absorption",    alpha_aer_abs_si  * 1e3, "data.c"),
        ("Aerosol scattering",    alpha_aer_scat_si * 1e3, "data.reference"),
    )
    total_km = total_si * 1e3

    fig = go.Figure()
    for label, value_km, token in components:
        share_pct = (value_km / total_km * 100.0) if total_km > 0 else 0.0
        fig.add_trace(
            go.Bar(
                x=[value_km],
                y=["Total extinction"],
                orientation="h",
                name=label,
                marker_color=palette[token],
                hovertemplate=(
                    f"{label}: %{{x:.3g}} 1/km ({share_pct:.1f}%)"
                    "<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title=title,
        height=height,
        barmode="stack",
        hovermode="closest",
        showlegend=True,
        legend=dict(orientation="h", x=0.0, y=-0.35, yanchor="top"),
    )
    fig.update_xaxes(title_text=xtitle)
    fig.update_yaxes(title_text=ytitle, showticklabels=False)
    return fig


# ---------------------------------------------------------------------------
# Atmosphere — transmission vs slant range.
# ---------------------------------------------------------------------------

def plot_atmosphere_transmission_vs_range(
    sweep: list[dict] | None,
) -> go.Figure:
    """Atmospheric transmission curve over the sweep's range axis.

    Line chart of τ_atm(L) from the orchestrator's range sweep, with a
    horizontal reference at τ = 1/e ≈ 0.368 (the characteristic
    attenuation length). When the sweep is missing or every
    transmission value is NaN, renders a frame + advisory.
    """
    height = PLOT_HEIGHTS["default"]
    xtitle = "Slant range (km)"
    ytitle = "Atmospheric transmission"
    title = "Transmission vs slant range"

    if not sweep:
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["infeasible_geometry"], height=height,
        )

    palette = _active_palette()
    x_km = _x_km(sweep)
    tau_atm = _get(sweep, "tau_atm")

    if _all_nan(tau_atm):
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["vacuum_path"], height=height,
        )

    fig = go.Figure()
    s0 = _series_style(0, palette)
    fig.add_trace(
        go.Scatter(
            x=x_km, y=tau_atm,
            mode="lines+markers",
            name="Atmospheric transmission",
            line=s0["line"], marker=s0["marker"],
            hovertemplate="%{y:.3f}<extra></extra>",
        )
    )

    # 1/e reference line.
    one_over_e = 1.0 / math.e
    fig.add_hline(
        y=one_over_e,
        line=dict(color=palette["data.reference"], width=1.2, dash="dashdot"),
        annotation_text="1/e attenuation",
        annotation_position="top right",
        annotation_font=dict(color=palette["fg.secondary"], size=11),
    )

    fig.update_layout(
        title=title,
        hovermode="x unified",
        height=height,
    )
    fig.update_xaxes(title_text=xtitle)
    fig.update_yaxes(title_text=ytitle, range=[0.0, 1.05])
    return fig


# ---------------------------------------------------------------------------
# Plot G — Spot diameter vs aimpoint bucket diameter (go/no-go visual).
# ---------------------------------------------------------------------------

def plot_g_spot_vs_bucket(
    sweep: list[dict] | None,
    *,
    d_aim: float | None,
) -> go.Figure:
    """At-a-glance: is the 1/e² spot still inside the aimpoint bucket?

    A single ``d_total = 2·w_total`` curve (cm) is plotted against slant
    range (km) with a horizontal reference at the bucket diameter
    ``d_aim`` (also cm). The region where ``d_total > d_aim`` is shaded
    in the status-warn hue to flag substantial spillover (≤ 86 % of
    energy is inside the bucket once the 1/e² diameter exceeds the
    bucket diameter, so the warn band coincides with the regime where
    PIB drops below the Gaussian-on-its-1/e² fraction).

    This plot answers the cognitive question Plot C does NOT — Plot C
    is a diagnostic ("which broadening term dominates?") while this
    plot is a verdict ("does the energy land in the bucket?"). They
    deliberately overlap on `w_total` but answer different things.

    Renders a frame with the "infeasible geometry" advisory when
    ``sweep`` is None/empty or ``d_aim`` is missing/non-positive.
    """
    height = PLOT_HEIGHTS["default"]
    xtitle = "Slant range (km)"
    ytitle = "1/e² spot diameter (cm)"
    title = "Spot vs bucket vs slant range"

    if not sweep or d_aim is None or not (d_aim > 0):
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["infeasible_geometry"], height=height,
        )

    palette = _active_palette()
    x_km = _x_km(sweep)
    d_total_cm = [
        2.0 * float(s.get("w_total", math.nan)) * 100.0 for s in sweep
    ]
    d_aim_cm = d_aim * 100.0

    if _all_nan(d_total_cm):
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["infeasible_geometry"], height=height,
        )

    # PIB at each sample feeds the hover line. Missing / non-finite
    # entries fall back to NaN so the unified hover still draws.
    pib = [float(s.get("PIB_fraction", math.nan)) for s in sweep]

    fig = go.Figure()

    # Spillover shading — closed polygon between d_aim_cm (lower) and
    # d_total_cm (upper) wherever d_total > d_aim. The fill is laid
    # before the data trace so the curve and bucket reference draw on
    # top of the band.
    upper: list[float] = []
    lower: list[float] = []
    for d in d_total_cm:
        if isinstance(d, float) and math.isfinite(d) and d > d_aim_cm:
            upper.append(d)
            lower.append(d_aim_cm)
        else:
            upper.append(math.nan)
            lower.append(math.nan)
    warn_rgba = _hex_to_rgba(palette["status.warn"], alpha=0.18)
    fig.add_trace(
        go.Scatter(
            x=x_km + x_km[::-1],
            y=upper + lower[::-1],
            fill="toself",
            fillcolor=warn_rgba,
            line=dict(color="rgba(0,0,0,0)"),
            hoverinfo="skip",
            name="Spillover (spot > bucket)",
            showlegend=True,
        )
    )

    # Bucket-diameter reference — horizontal dashed line.
    fig.add_hline(
        y=d_aim_cm,
        line=dict(color=palette["data.reference"], width=1.5, dash="dash"),
        annotation_text=f"Bucket diameter ({d_aim_cm:.1f} cm)",
        annotation_position="top right",
        annotation_font=dict(color=palette["fg.secondary"], size=11),
    )

    # Spot-diameter curve.
    s0 = _series_style(0, palette)
    fig.add_trace(
        go.Scatter(
            x=x_km, y=d_total_cm,
            mode="lines+markers",
            name="Total spot diameter",
            line=s0["line"], marker=s0["marker"],
            customdata=pib,
            hovertemplate=(
                "Range %{x:.2f} km · spot %{y:.1f} cm · "
                "PIB %{customdata:.1%}<extra></extra>"
            ),
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
# Plot D — Thermal-blooming distortion number N_D vs slant range.
# ---------------------------------------------------------------------------

def plot_d_blooming_distortion_number(
    sweep: list[dict] | None,
    *,
    reference_range: float | None = None,
) -> go.Figure:
    """Visualize ``N_D`` vs slant range with SPEC §10.4 validity bands.

    The Gebhardt distortion number ``N_D`` drives ``w_bloom`` but is
    invisible elsewhere in the UI. Here it is plotted on a log y-axis
    with three color-coded bands:

      * ``N_D < 5`` (status-ok) — blooming negligible; M6 sets w_bloom=0
        per SPEC §3 M6 Smith Strehl cutoff.
      * ``5 ≤ N_D ≤ 30`` (no shade) — valid scaling regime; the engineering
        broadening multiplier (0.3 per SPEC §10.4) applies.
      * ``N_D > 30`` (status-error) — outside the M6 model validity range
        per SPEC §10.4 HIGH UNCERTAINTY; the value still computes but
        any downstream w_bloom should be read as "model has failed".

    A vertical dashed reference line marks the user's reference range
    (where the engagement-tab metric cards are computed).

    Renders a frame with the "infeasible geometry" advisory when
    ``sweep`` is None/empty.
    """
    height = PLOT_HEIGHTS["default"]
    xtitle = "Slant range (km)"
    ytitle = "Thermal-blooming N_D (—)"
    title = "Blooming distortion number vs slant range"

    if not sweep:
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["infeasible_geometry"], height=height,
        )

    palette = _active_palette()
    x_km = _x_km(sweep)
    n_d = _log_safe(_get(sweep, "N_D"))

    if _all_nan(n_d):
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["infeasible_geometry"], height=height,
        )

    # Determine the y-axis floor / ceiling so the validity bands always
    # render even when the data sits in just one band. The 0.1 floor is
    # well below the Smith cutoff (5); the 100 ceiling is above the model
    # validity boundary (30) — both extend by ~half a decade past the
    # SPEC §3 M6 thresholds for visual breathing room.
    finite = [v for v in n_d if math.isfinite(v)]
    y_min = max(0.1, min(finite) * 0.5) if finite else 0.1
    y_max = max(100.0, max(finite) * 1.5) if finite else 100.0

    fig = go.Figure()

    # Validity bands — drawn as horizontal rectangles spanning the full
    # x-axis. Plotly's add_hrect places them behind the data traces.
    ok_rgba = _hex_to_rgba(palette["status.ok"], alpha=0.10)
    err_rgba = _hex_to_rgba(palette["status.error"], alpha=0.10)
    fig.add_hrect(
        y0=y_min, y1=5.0,
        fillcolor=ok_rgba, line_width=0,
        annotation_text="Negligible (N_D < 5)",
        annotation_position="bottom left",
        annotation_font=dict(color=palette["fg.secondary"], size=10),
    )
    fig.add_hrect(
        y0=30.0, y1=y_max,
        fillcolor=err_rgba, line_width=0,
        annotation_text="Outside model validity",
        annotation_position="top left",
        annotation_font=dict(color=palette["fg.secondary"], size=10),
    )

    # Reference range — vertical dashed line.
    if reference_range is not None and reference_range > 0:
        fig.add_vline(
            x=reference_range / 1000.0,
            line=dict(color=palette["data.reference"], width=1.2, dash="dash"),
            annotation_text="Reference range",
            annotation_position="top right",
            annotation_font=dict(color=palette["fg.secondary"], size=11),
        )

    # The N_D curve itself.
    s0 = _series_style(0, palette)
    fig.add_trace(
        go.Scatter(
            x=x_km, y=n_d,
            mode="lines+markers",
            name="N_D",
            line=s0["line"], marker=s0["marker"],
            hovertemplate="Range %{x:.2f} km · N_D %{y:.3g}<extra></extra>",
        )
    )

    fig.update_layout(
        title=title,
        hovermode="x unified",
        height=height,
    )
    fig.update_xaxes(title_text=xtitle)
    fig.update_yaxes(title_text=ytitle, type="log",
                     range=[math.log10(y_min), math.log10(y_max)])
    return fig


# ---------------------------------------------------------------------------
# Plot E — Engagement-viability margin vs slant range.
# ---------------------------------------------------------------------------

def plot_e_engagement_margin_vs_range(
    sweep: list[dict] | None,
    *,
    reference_range: float | None = None,
) -> go.Figure:
    """Engagement-viability margin curve with verdict bands.

    Margin is ``(available_dwell − tau_BT) / tau_BT × 100`` (percent),
    the same quantity the Overview-tab verdict chip displays. Three
    color-coded bands:

      * ``margin ≥ +30 %`` (status-ok) — engageable
      * ``0 % ≤ margin < +30 %`` (status-warn) — marginal
      * ``margin < 0 %`` (status-error) — not viable (dwell too short)

    Plotted on a linear y-axis clamped to ``[-100 %, +200 %]`` so a
    single very-engageable sample does not flatten the rest of the
    curve; values outside the clamp are pinned at the limit so the
    curve still terminates inside the plot.

    Renders the "no burn-through" advisory when every ``tau_BT`` sample
    is non-finite (no finite margin can be computed). When the entire
    sweep is in the ``status.error`` band, the curve stays in red — no
    special-case rewrite is needed since the band shading already
    reads the verdict.
    """
    height = PLOT_HEIGHTS["default"]
    xtitle = "Slant range (km)"
    ytitle = "Engagement margin (%)"
    title = "Engagement margin vs slant range"
    Y_FLOOR, Y_CEIL = -100.0, 200.0

    if not sweep:
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["infeasible_geometry"], height=height,
        )

    palette = _active_palette()
    x_km = _x_km(sweep)
    tau_bt = _get(sweep, "tau_BT")
    dwell = _get(sweep, "available_dwell")

    margin: list[float] = []
    verdict: list[str] = []
    for tbt, dw in zip(tau_bt, dwell):
        if (math.isfinite(tbt) and tbt > 0 and math.isfinite(dw)):
            m = 100.0 * (dw - tbt) / tbt
            margin.append(max(Y_FLOOR, min(Y_CEIL, m)))
            if m >= 30.0:
                verdict.append("engageable")
            elif m >= 0.0:
                verdict.append("marginal")
            else:
                verdict.append("not viable")
        else:
            margin.append(math.nan)
            verdict.append("—")

    if _all_nan(margin):
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["no_burnthrough"], height=height,
        )

    fig = go.Figure()

    # Verdict bands.
    ok_rgba = _hex_to_rgba(palette["status.ok"], alpha=0.12)
    warn_rgba = _hex_to_rgba(palette["status.warn"], alpha=0.12)
    err_rgba = _hex_to_rgba(palette["status.error"], alpha=0.12)
    fig.add_hrect(y0=30.0, y1=Y_CEIL,
                  fillcolor=ok_rgba, line_width=0,
                  annotation_text="Engageable (≥ 30 %)",
                  annotation_position="top left",
                  annotation_font=dict(color=palette["fg.secondary"], size=10))
    fig.add_hrect(y0=0.0, y1=30.0,
                  fillcolor=warn_rgba, line_width=0,
                  annotation_text="Marginal (0–30 %)",
                  annotation_position="top left",
                  annotation_font=dict(color=palette["fg.secondary"], size=10))
    fig.add_hrect(y0=Y_FLOOR, y1=0.0,
                  fillcolor=err_rgba, line_width=0,
                  annotation_text="Not viable (< 0 %)",
                  annotation_position="bottom left",
                  annotation_font=dict(color=palette["fg.secondary"], size=10))

    # Zero-line and reference-range markers.
    fig.add_hline(
        y=0.0,
        line=dict(color=palette["data.reference"], width=1.2, dash="dash"),
    )
    if reference_range is not None and reference_range > 0:
        fig.add_vline(
            x=reference_range / 1000.0,
            line=dict(color=palette["data.reference"], width=1.2, dash="dash"),
            annotation_text="Reference range",
            annotation_position="top right",
            annotation_font=dict(color=palette["fg.secondary"], size=11),
        )

    # Margin curve. Use series-B styling (teal / dash / square) so this
    # plot reads as a Plot-B sibling.
    s1 = _series_style(1, palette)
    fig.add_trace(
        go.Scatter(
            x=x_km, y=margin,
            mode="lines+markers",
            name="Engagement margin",
            line=s1["line"], marker=s1["marker"],
            customdata=verdict,
            hovertemplate=(
                "Range %{x:.2f} km · margin %{y:+.0f}% · "
                "%{customdata}<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title=title,
        hovermode="x unified",
        height=height,
    )
    fig.update_xaxes(title_text=xtitle)
    fig.update_yaxes(title_text=ytitle, range=[Y_FLOOR, Y_CEIL])
    return fig


# ---------------------------------------------------------------------------
# Plot C' — Spot tightening through trajectory (SPEC v2.0).
# Replaces Plot C's "spot diameter components vs slant range" view, which
# becomes degenerate under the v2.0 trajectory contract: closest-approach
# values are constant per R_detect sweep so the components don't vary.
# This plot looks at ONE engagement and shows how the spot tightens as
# the target closes from R_detect down to R_min.
# ---------------------------------------------------------------------------

def plot_c_spot_tightening_through_trajectory(
    result: dict | None,
    *,
    d_aim: float | None,
) -> go.Figure:
    """Spot diameter through the engagement trajectory.

    For one engagement, plots the 1/e² spot diameter d_spot at each
    sub-sample of the trajectory R(t), with a horizontal reference at
    the bucket diameter ``d_aim``. The curve drops left-to-right as
    the target closes (R_detect → R_min). Range where the spot still
    exceeds the bucket is shaded in status.warn so the operator sees
    at a glance how much of the trajectory was spent with the spot
    bigger than the aimpoint.

    Falls back to a frame-only figure when called with a v1.x result
    (no trajectory series), with a centered advisory pointing the
    user at the v2.0 contract.
    """
    height = PLOT_HEIGHTS["default"]
    xtitle = "Trajectory slant range (km)"
    ytitle = "1/e² spot diameter (cm)"
    title = "Spot tightening through trajectory"

    if (result is None
            or "trajectory_R" not in result
            or "trajectory_d_spot" not in result):
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["infeasible_geometry"], height=height,
        )

    traj_R = result["trajectory_R"]
    traj_d = result["trajectory_d_spot"]
    if not traj_R or not traj_d:
        return _empty_frame(
            title=title, xtitle=xtitle, ytitle=ytitle,
            advisory=ADVISORY["infeasible_geometry"], height=height,
        )

    palette = _active_palette()
    x_km = [r / 1000.0 for r in traj_R]
    d_cm = [d * 100.0 for d in traj_d]
    d_aim_cm = (d_aim * 100.0) if (d_aim is not None and d_aim > 0) else None

    fig = go.Figure()

    # Spillover band — where d_cm > d_aim_cm.
    if d_aim_cm is not None:
        upper: list[float] = []
        lower: list[float] = []
        for d in d_cm:
            if d > d_aim_cm:
                upper.append(d)
                lower.append(d_aim_cm)
            else:
                upper.append(math.nan)
                lower.append(math.nan)
        warn_rgba = _hex_to_rgba(palette["status.warn"], alpha=0.18)
        fig.add_trace(
            go.Scatter(
                x=x_km + x_km[::-1],
                y=upper + lower[::-1],
                fill="toself",
                fillcolor=warn_rgba,
                line=dict(color="rgba(0,0,0,0)"),
                hoverinfo="skip",
                name="Spillover (spot > bucket)",
                showlegend=True,
            )
        )
        fig.add_hline(
            y=d_aim_cm,
            line=dict(color=palette["data.reference"],
                      width=1.5, dash="dash"),
            annotation_text=f"Bucket diameter ({d_aim_cm:.1f} cm)",
            annotation_position="top right",
            annotation_font=dict(color=palette["fg.secondary"], size=11),
        )

    # The d_spot trajectory itself.
    s0 = _series_style(0, palette)
    fig.add_trace(
        go.Scatter(
            x=x_km, y=d_cm,
            mode="lines+markers",
            name="Total spot diameter",
            line=s0["line"], marker=s0["marker"],
            hovertemplate=(
                "Range %{x:.2f} km · spot %{y:.1f} cm<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title=title,
        hovermode="x unified",
        height=height,
    )
    # The trajectory closes left-to-right (R_detect on the left,
    # R_min on the right), but the natural reading direction for a
    # "target closing on us" story is left-to-right with R decreasing.
    # Reverse the x-axis so larger ranges sit on the left.
    if x_km and x_km[0] > x_km[-1]:
        fig.update_xaxes(title_text=xtitle, autorange="reversed")
    else:
        fig.update_xaxes(title_text=xtitle)
    fig.update_yaxes(title_text=ytitle)
    return fig


# ---------------------------------------------------------------------------
# Plot H — Engagement profile timeline (SPEC v2.0 §8.3).
# Headline new visualization for the trajectory model: shows the
# anatomy of one engagement second by second. Four stacked panels
# share a single time x-axis: trajectory R(t), on-target irradiance,
# surface temperature with T_fail reference, and cumulative absorbed
# energy. A vertical dashed line at the kill moment crosses every
# panel so the eye instantly locates where the engagement closed.
# ---------------------------------------------------------------------------

def plot_h_engagement_profile(result: dict | None) -> go.Figure:
    """Engagement profile vs time — 4-panel multi-subplot figure.

    Panel 1 — R(t): trajectory slant range, log y-axis.
    Panel 2 — I_peak(t) and I_avg_aim(t): irradiance climbing as the
             target closes (W/cm² for display).
    Panel 3 — T_surface(t): heat-solver surface temperature vs time
             (°C), with horizontal T_fail reference and a vertical
             kill-moment marker.
    Panel 4 — E(t) cumulative absorbed: integrated absorbed flux
             (J/cm² for display), showing how much energy was
             actually deposited by each instant.

    All four panels share a single x-axis (engagement time, s) and
    a vertical dashed line at the kill moment when one occurred.

    Renders the always-render frame with the "infeasible geometry"
    advisory when called with a v1.x result (no trajectory series)
    or when the trajectory data is missing.
    """
    import plotly.graph_objects as go  # local re-import for symbol clarity
    from plotly.subplots import make_subplots

    height = 700  # taller than PLOT_HEIGHTS["hero"]; multi-panel
    title = "Engagement profile — what happens during the engagement"

    if (result is None
            or "trajectory_t" not in result
            or "trajectory_R" not in result
            or "trajectory_I_peak" not in result
            or "trajectory_t_pde" not in result
            or "trajectory_T_surface" not in result
            or "trajectory_E_cumulative" not in result):
        return _empty_frame(
            title=title,
            xtitle="Engagement time (s)",
            ytitle="(empty)",
            advisory=ADVISORY["infeasible_geometry"],
            height=height,
        )

    palette = _active_palette()
    t_traj = list(result["trajectory_t"])
    R_traj = list(result["trajectory_R"])
    I_peak_traj = list(result["trajectory_I_peak"])
    I_avg_traj = list(result.get("trajectory_I_avg_aim", I_peak_traj))
    t_pde = list(result["trajectory_t_pde"])
    T_surface = list(result["trajectory_T_surface"])
    E_cum = list(result["trajectory_E_cumulative"])

    if not t_traj or not t_pde:
        return _empty_frame(
            title=title,
            xtitle="Engagement time (s)",
            ytitle="(empty)",
            advisory=ADVISORY["infeasible_geometry"],
            height=height,
        )

    # Convert SI to display units.
    R_m = R_traj  # already metres; plot in m to keep log scale clean
    I_peak_wpcm2 = [v * 1e-4 for v in I_peak_traj]
    I_avg_wpcm2 = [v * 1e-4 for v in I_avg_traj]
    T_surface_C = [v - 273.15 for v in T_surface]
    E_cum_jpcm2 = [v * 1e-4 for v in E_cum]

    # T_fail reference (°C) — drawn as a horizontal line on Panel 3.
    # Look up from the M8 material table via the merged result. The
    # orchestrator includes failure_mode but not T_fail directly; we
    # peek at by_module's M8 outputs which carry the surface_peak
    # and use it as a rough proxy. For the cleanest reference, the
    # plot consumes T_surface_peak which equals T_fail at the kill
    # moment by construction. None when there's no kill.
    T_fail_C: float | None
    if result.get("failure_mode") in ("melt", "decomposition", "vent"):
        T_fail_C = float(result.get("T_surface_peak", 0.0)) - 273.15
    else:
        T_fail_C = None

    # Kill marker — vertical dashed line on every panel.
    tau_BT = result.get("tau_BT")
    R_at_kill = result.get("R_at_kill")
    kill_t: float | None = (
        float(tau_BT) if (
            tau_BT is not None
            and result.get("failure_mode") in ("melt", "decomposition", "vent")
        ) else None
    )

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=(
            "Trajectory — slant range (m)",
            "On-target irradiance (W/cm²)",
            "Front-face temperature (°C)",
            "Cumulative absorbed energy (J/cm²)",
        ),
    )

    # Panel 1 — R(t)
    s0 = _series_style(0, palette)
    fig.add_trace(
        go.Scatter(
            x=t_traj, y=R_m,
            mode="lines+markers",
            name="Slant range",
            line=s0["line"], marker=s0["marker"],
            hovertemplate="t %{x:.2f} s · R %{y:.0f} m<extra></extra>",
            showlegend=False,
        ),
        row=1, col=1,
    )

    # Panel 2 — I_peak and I_avg_aim
    s1 = _series_style(1, palette)
    fig.add_trace(
        go.Scatter(
            x=t_traj, y=I_peak_wpcm2,
            mode="lines+markers",
            name="I_peak",
            line=s0["line"], marker=s0["marker"],
            hovertemplate="t %{x:.2f} s · I_peak %{y:.2g} W/cm²<extra></extra>",
        ),
        row=2, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=t_traj, y=I_avg_wpcm2,
            mode="lines+markers",
            name="I_avg_aim",
            line=s1["line"], marker=s1["marker"],
            hovertemplate="t %{x:.2f} s · I_avg %{y:.2g} W/cm²<extra></extra>",
        ),
        row=2, col=1,
    )

    # Panel 3 — T_surface(t)
    s2 = _series_style(2, palette)
    fig.add_trace(
        go.Scatter(
            x=t_pde, y=T_surface_C,
            mode="lines",
            name="Surface T",
            line=s2["line"],
            hovertemplate="t %{x:.2f} s · T %{y:.0f} °C<extra></extra>",
            showlegend=False,
        ),
        row=3, col=1,
    )
    if T_fail_C is not None:
        fig.add_hline(
            y=T_fail_C, line=dict(
                color=palette["status.error"], width=1.5, dash="dash",
            ),
            annotation_text=f"T_fail ({T_fail_C:.0f} °C)",
            annotation_position="top right",
            annotation_font=dict(color=palette["fg.secondary"], size=11),
            row=3, col=1,
        )

    # Panel 4 — E_cumulative(t)
    fig.add_trace(
        go.Scatter(
            x=t_pde, y=E_cum_jpcm2,
            mode="lines",
            name="E cumulative",
            line=s0["line"],
            hovertemplate=(
                "t %{x:.2f} s · E %{y:.2g} J/cm²<extra></extra>"
            ),
            showlegend=False,
        ),
        row=4, col=1,
    )

    # Kill-moment vertical dashed line on every panel.
    if kill_t is not None:
        kill_label = (
            f"Kill at t = {kill_t:.2f} s"
            + (f", R = {R_at_kill:.0f} m" if R_at_kill is not None else "")
        )
        for row_idx in (1, 2, 3, 4):
            fig.add_vline(
                x=kill_t,
                line=dict(color=palette["status.ok"], width=1.5, dash="dash"),
                annotation_text=kill_label if row_idx == 1 else None,
                annotation_position="top right" if row_idx == 1 else None,
                annotation_font=dict(
                    color=palette["fg.secondary"], size=11,
                ) if row_idx == 1 else None,
                row=row_idx, col=1,
            )

    fig.update_layout(
        title=title,
        height=height,
        hovermode="x unified",
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1.0,
        ),
    )
    # Panel 1 log y so 100 m and 5 km both read cleanly.
    fig.update_yaxes(type="log", row=1, col=1)
    fig.update_xaxes(title_text="Engagement time (s)", row=4, col=1)
    return fig


__all__ = [
    "plot_a_on_target_performance",
    "plot_b_time_to_burnthrough",
    "plot_c_beam_diameter_breakdown",
    "plot_c_spot_tightening_through_trajectory",
    "plot_d_blooming_distortion_number",
    "plot_e_engagement_margin_vs_range",
    "plot_g_spot_vs_bucket",
    "plot_h_engagement_profile",
    "plot_overview_dwell_vs_burnthrough",
    "plot_target_temperature_envelope",
    "plot_target_material_comparison",
    "plot_safety_nohd_zones",
    "plot_atmosphere_extinction_breakdown",
    "plot_atmosphere_transmission_vs_range",
]
