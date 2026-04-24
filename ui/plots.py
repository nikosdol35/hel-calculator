"""Three Plotly figure constructors per SPEC §5.2.

Each function returns a ``plotly.graph_objects.Figure`` object that
``ui/app.py`` passes to ``st.plotly_chart``. Pure constructors: no
Streamlit imports, no caching, no global state.

Per-plot unified hover (``hovermode='x unified'``) is set on every
figure per SPEC v1.6 / ARCH v1.4. Cross-plot synchronization was
considered for v1 but descoped — each plot is self-contained.

The ``sweep`` argument is a ``list[dict]`` where each element is a
merged-result dict (one per range sample along the user-selected range
axis) with at least these keys:

  - ``range`` (m): slant range at this sample
  - ``I_peak`` (W/m²), ``PIB_fraction``, ``S_TB``, ``tau_atm``,
    ``w_diff``, ``w_total``, ``w_turb``, ``w_jit``, ``tau_BT``,
    ``available_dwell``

Missing keys fall back to ``NaN`` or ``0`` so the plot still renders
— e.g. if ``M8`` has not been exercised along the full sweep.

References:
    SPEC.md §5.2 (Plot A/B/C contracts, hover-tooltip content).
    ARCHITECTURE.md §6.5 (file contract, signatures, unified hover note).
"""

from __future__ import annotations

import math

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ui.theme import COLOR_CAUTION, COLOR_PRIMARY, COLOR_REFERENCE, PLOT_HEIGHT_PX


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------
def _x_km(sweep: list[dict]) -> list[float]:
    """Return the sweep's slant-range axis in km (for readable tick labels)."""
    return [s.get("range", 0.0) / 1000.0 for s in sweep]


def _get(sweep: list[dict], key: str, default: float = math.nan) -> list[float]:
    """Pull one key across the sweep, coercing missing entries to a sentinel."""
    return [float(s.get(key, default)) for s in sweep]


def _log_safe(values: list[float]) -> list[float]:
    """Clip non-positive values to ``NaN`` so log axes do not explode."""
    return [v if (v is not None and v > 0 and math.isfinite(v)) else math.nan
            for v in values]


# ---------------------------------------------------------------------------
# Plot A — On-Target Performance vs Slant Range.
# ---------------------------------------------------------------------------
def plot_a_on_target_performance(sweep: list[dict]) -> go.Figure:
    """Plot A: I_peak (W/cm²) and PIB fraction vs range, dual y-axis.

    Left y-axis: I_peak (actual, solid) and diff-limited I_peak (dashed
    reference). Right y-axis: PIB fraction, S_TB, τ_atm (all dimensionless
    0–1 curves). Unified hover shows all five values at the hovered range.
    """
    x_km = _x_km(sweep)
    I_peak_w_cm2 = [v / 1e4 for v in _get(sweep, "I_peak")]
    PIB = _get(sweep, "PIB_fraction")
    S_TB = _get(sweep, "S_TB")
    tau_atm = _get(sweep, "tau_atm")

    # Diff-limited reference: use w_diff to compute peak, using P_exit
    # and tau_atm from the sweep. Falls back to I_peak · (w_total/w_diff)²
    # when the power is not available in the sample — algebraically
    # identical when S_TB=1.
    I_peak_diff: list[float] = []
    for s in sweep:
        w_diff = s.get("w_diff")
        w_total = s.get("w_total")
        I_peak_actual = s.get("I_peak")
        S_TB_s = s.get("S_TB", 1.0)
        if (w_diff and w_total and I_peak_actual and S_TB_s > 0
                and w_diff > 0 and w_total > 0):
            # I_peak_actual = 2·P·τ·S_TB / (π·w_total²)
            # I_peak_diff   = 2·P·τ        / (π·w_diff²)
            ratio = (w_total ** 2) / (w_diff ** 2) / S_TB_s
            I_peak_diff.append((I_peak_actual * ratio) / 1e4)
        else:
            I_peak_diff.append(math.nan)

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Left y: I_peak curves (W/cm²).
    fig.add_trace(
        go.Scatter(
            x=x_km, y=I_peak_w_cm2, mode="lines",
            name="I_peak (actual)",
            line=dict(color=COLOR_PRIMARY, width=2),
            hovertemplate="I_peak: %{y:.3g} W/cm²<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=x_km, y=I_peak_diff, mode="lines",
            name="I_peak (diff-limited)",
            line=dict(color=COLOR_REFERENCE, width=1.5, dash="dash"),
            hovertemplate="I_peak,diff: %{y:.3g} W/cm²<extra></extra>",
        ),
        secondary_y=False,
    )

    # Right y: dimensionless 0–1 curves.
    fig.add_trace(
        go.Scatter(
            x=x_km, y=PIB, mode="lines", name="PIB",
            line=dict(color="#2e7d32", width=1.5),
            hovertemplate="PIB: %{y:.2f}<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=x_km, y=S_TB, mode="lines", name="S_TB",
            line=dict(color="#8e24aa", width=1.5, dash="dot"),
            hovertemplate="S_TB: %{y:.2f}<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=x_km, y=tau_atm, mode="lines", name="τ_atm",
            line=dict(color="#1565c0", width=1.5, dash="dot"),
            hovertemplate="τ_atm: %{y:.2f}<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title="On-target performance vs slant range",
        hovermode="x unified",
        height=PLOT_HEIGHT_PX,
        legend=dict(orientation="h", y=-0.2),
        margin=dict(l=60, r=60, t=50, b=60),
    )
    fig.update_xaxes(title_text="Slant range (km)")
    fig.update_yaxes(title_text="I_peak (W/cm²)", secondary_y=False)
    fig.update_yaxes(
        title_text="PIB / S_TB / τ_atm",
        range=[0, 1.05],
        secondary_y=True,
    )
    return fig


# ---------------------------------------------------------------------------
# Plot B — Time-to-Burn-Through vs Slant Range.
# ---------------------------------------------------------------------------
def plot_b_time_to_burnthrough(sweep: list[dict]) -> go.Figure:
    """Plot B: tau_BT (s, log y) and available_dwell reference vs range.

    The region where tau_BT < available_dwell is shaded faintly green
    to visualize the "engageable" range band per SPEC §5.2 Panel 2
    verdict definition.
    """
    x_km = _x_km(sweep)
    tau_BT = _log_safe(_get(sweep, "tau_BT"))
    dwell = _log_safe(_get(sweep, "available_dwell"))

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_km, y=tau_BT, mode="lines", name="τ_BT",
            line=dict(color=COLOR_PRIMARY, width=2),
            hovertemplate="τ_BT: %{y:.3g} s<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_km, y=dwell, mode="lines", name="available dwell",
            line=dict(color=COLOR_CAUTION, width=1.5, dash="dash"),
            hovertemplate="dwell: %{y:.3g} s<extra></extra>",
        )
    )

    # Shaded "engageable" region — wherever τ_BT < dwell, fill to dwell.
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

    fig.add_trace(
        go.Scatter(
            x=x_km + x_km[::-1],
            y=engageable_upper + engageable_lower[::-1],
            fill="toself",
            fillcolor="rgba(46,125,50,0.18)",
            line=dict(color="rgba(0,0,0,0)"),
            hoverinfo="skip",
            name="engageable band",
            showlegend=True,
        )
    )

    fig.update_layout(
        title="Time-to-burn-through vs slant range",
        hovermode="x unified",
        height=PLOT_HEIGHT_PX,
        legend=dict(orientation="h", y=-0.2),
        margin=dict(l=60, r=30, t=50, b=60),
    )
    fig.update_xaxes(title_text="Slant range (km)")
    fig.update_yaxes(title_text="Time (s)", type="log")
    return fig


# ---------------------------------------------------------------------------
# Plot C — Beam Diameter vs Range with Individual Contributions.
# ---------------------------------------------------------------------------
def plot_c_beam_diameter_breakdown(sweep: list[dict]) -> go.Figure:
    """Plot C: 1/e² diameter contributions vs slant range.

    Curves (all diameters in cm):
      - d_total = 2·w_total (solid, primary color)
      - d_diff_pure = 2·w0·sqrt(1+(L/z_R)²)  (dashed reference)
      - d_M² excess = 2·w_diff − d_diff_pure
      - d_turb = 2·w_turb
      - d_jit  = 2·w_jit
    """
    x_km = _x_km(sweep)

    def _d_cm(sweep_key: str) -> list[float]:
        """Return 2·<sweep_key> in centimeters (sweep_key is a 1/e² radius)."""
        return [2.0 * float(s.get(sweep_key, math.nan)) * 100.0 for s in sweep]

    d_total = _d_cm("w_total")
    d_diff = _d_cm("w_diff")
    d_turb = _d_cm("w_turb")
    d_jit = _d_cm("w_jit")

    # d_diff_pure: 2·w0·sqrt(1 + (L/zR)²). w0 and zR are per-sample;
    # L is the sample's range.
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

    # d_M²_excess = d_diff − d_diff_pure (the quantity M² adds on top
    # of the pure-Gaussian diffraction limit).
    d_m2_excess = [
        (d - dp) if (isinstance(d, float) and isinstance(dp, float)
                    and math.isfinite(d) and math.isfinite(dp)) else math.nan
        for d, dp in zip(d_diff, d_diff_pure)
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_km, y=d_total, mode="lines", name="d_total (2·w_total)",
            line=dict(color=COLOR_PRIMARY, width=2.5),
            hovertemplate="d_total: %{y:.3g} cm<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_km, y=d_diff_pure, mode="lines", name="d_diff (pure)",
            line=dict(color=COLOR_REFERENCE, width=1.5, dash="dash"),
            hovertemplate="d_diff: %{y:.3g} cm<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_km, y=d_m2_excess, mode="lines", name="d_M² excess",
            line=dict(color="#8e24aa", width=1.5, dash="dot"),
            hovertemplate="d_M²: %{y:.3g} cm<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_km, y=d_turb, mode="lines", name="d_turb",
            line=dict(color="#00897b", width=1.5, dash="dot"),
            hovertemplate="d_turb: %{y:.3g} cm<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_km, y=d_jit, mode="lines", name="d_jit",
            line=dict(color="#e65100", width=1.5, dash="dot"),
            hovertemplate="d_jit: %{y:.3g} cm<extra></extra>",
        )
    )

    fig.update_layout(
        title="Beam diameter vs slant range",
        hovermode="x unified",
        height=PLOT_HEIGHT_PX,
        legend=dict(orientation="h", y=-0.2),
        margin=dict(l=60, r=30, t=50, b=60),
    )
    fig.update_xaxes(title_text="Slant range (km)")
    fig.update_yaxes(title_text="1/e² diameter (cm)")
    return fig


__all__ = [
    "plot_a_on_target_performance",
    "plot_b_time_to_burnthrough",
    "plot_c_beam_diameter_breakdown",
]
