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


__all__ = [
    "plot_a_on_target_performance",
    "plot_b_time_to_burnthrough",
    "plot_c_beam_diameter_breakdown",
    "plot_overview_dwell_vs_burnthrough",
    "plot_target_temperature_envelope",
    "plot_target_material_comparison",
    "plot_safety_nohd_zones",
    "plot_atmosphere_extinction_breakdown",
    "plot_atmosphere_transmission_vs_range",
]
