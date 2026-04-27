"""Jitter target visualizer — pre-computes Plotly Frames animation data.

Per SPEC §8.7 (illustrative). Consumes existing M5/M7/M8 outputs;
does not modify any chain output. Renders an Ornstein-Uhlenbeck
random walk of the laser spot on the target plane plus a cumulative
fluence heat map.

Pinned inputs (from SPEC §3):
  - w_inst    = √(w_diff² + w_turb² + w_bloom²)   (M5/M6/M7)
  - σ_jit · R                                      (M7 jitter envelope)
  - P_in_bucket = P₀ · η_opt · τ_atm · PIB        (M7 throughput)
  - d_aim                                          (user input)
  - E_fail = ρ · c_p · thickness · (T_fail − T_amb)  (lumped-mass, M8)

Illustrative parameters (NOT pinned to a SPEC formula):
  - τ_corr = 10 ms                  (typical 100 Hz electromechanical bandwidth)
  - Ornstein-Uhlenbeck random walk  (stationary RMS pinned to σ_jit · R)
  - Total visualization length 3 s, looping
  - Frame timing dt = 5 ms

The visualizer does not change ``tau_BT`` or any chain output —
M8 already accounts for jitter via the broader ``w_total``. The
animation is purely a render of what M7's ``w_jit²`` term means
geometrically.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


# Animation-shape constants. Tuned 2026-04-26 (v2) to land the figure
# JSON well under Streamlit Cloud's reverse-proxy WebSocket message
# cap (~4 MB observed). The original 600 frames × 96 px × 6 traces
# pushed ~28 MB and produced "Failed to process WebSocket message
# (404)" errors that froze the sidebar and downstream plots.
#
# Final budget (300 × 48² × dynamic-only frame deduplication):
#   Heatmap data:  300 × 48² × ~3 B JSON = ~2.0 MB
#   Spot + comet:  300 × ~5 KB each = ~3.0 MB
#   Static layers (1×, lifted to figure level): ~10 KB
#   Total figure JSON: ~3-4 MB. Well under proxy limit.
_DEFAULT_DT_S = 0.005           # 5 ms per frame (smooth OU motion)
_DEFAULT_TAU_CORR_S = 0.010     # 10 ms electromechanical bandwidth
_DEFAULT_N_FRAMES = 300         # 1.5-second loop (was 600 / 3-second)
_DEFAULT_GRID_PIXELS = 48       # 48×48 (was 96×96)
_DEFAULT_SEED = 42

# Burn-through marker fade window — annotation present from
# burn_through_frame to burn_through_frame + this many frames.
# At dt=5 ms, 200 frames = 1 s fade.
_MARKER_FADE_FRAMES = 200


@dataclass(frozen=True)
class JitterAnimationFrames:
    """Pre-computed animation frames for the jitter visualizer.

    All spatial quantities in target-frame meters with origin at the
    bucket centre. Fluence is quantized to uint8 with the un-scaled
    maximum (``fluence_max_jpcm2``) stored separately so the colorbar
    reads in J/cm² when rendered.

    Frozen dataclass — fields are not reassigned, but the underlying
    NumPy arrays are still mutable in memory. Callers must not mutate
    the arrays in place.
    """
    times_s: np.ndarray              # shape (N,), 0 .. (N-1)·dt
    spot_positions_m: np.ndarray     # shape (N, 2), OU random walk
    fluence_grids_uint8: np.ndarray  # shape (N, P, P), quantized 0..255
    fluence_max_jpcm2: float         # colorbar reference (J/cm²)
    extent_m: tuple[float, float, float, float]   # (xmin, xmax, ymin, ymax)
    burn_through_frame: int | None   # first frame where peak ≥ E_fail
    target_silhouette_xy_m: np.ndarray  # shape (M, 2), quadrotor outline
    bucket_radius_m: float
    spot_radius_m: float             # w_inst (instantaneous 1/e²)
    envelope_radius_m: float         # σ_jit · R
    dt_s: float
    n_frames: int


def generate_jitter_animation(
    *,
    w_inst_m: float,
    sigma_jit_rad: float,
    R_m: float,
    d_aim_m: float,
    target_w_m: float,
    target_h_m: float,
    P_in_bucket_w: float,
    E_fail_jpcm2: float | None,
    tau_BT_s: float | None = None,
    n_frames: int = _DEFAULT_N_FRAMES,
    grid_pixels: int = _DEFAULT_GRID_PIXELS,
    dt_s: float = _DEFAULT_DT_S,
    tau_corr_s: float = _DEFAULT_TAU_CORR_S,
    seed: int = _DEFAULT_SEED,
) -> JitterAnimationFrames:
    """Generate the Plotly-animation-ready frame sequence.

    Pure NumPy. ~0.5 s on the canonical scenario. Caller (Streamlit)
    wraps in ``@st.cache_data`` so re-runs hit the cache.

    Args:
      w_inst_m: instantaneous spot 1/e² radius
                (= √(w_diff² + w_turb² + w_bloom²)).
      sigma_jit_rad: per-axis jitter RMS (radians).
      R_m: slant range to the target (m).
      d_aim_m: aimpoint bucket diameter (m).
      target_w_m, target_h_m: target silhouette bounding box (m).
      P_in_bucket_w: in-bucket optical power
                     (= P₀ · η_opt · τ_atm · PIB).
      E_fail_jpcm2: lumped-mass failure fluence (J/cm²).
                    None → no burn-through marker (e.g., missing
                    material lookup).
      tau_BT_s: trajectory burn-through time (informational only;
                the burn-through frame is found by inspecting the
                fluence grid, not by indexing tau_BT).
      n_frames: number of animation frames. Default 600.
      grid_pixels: per-axis pixel count for the fluence grid.
                   Default 96.
      dt_s: per-frame physical time step. Default 5 ms.
      tau_corr_s: jitter correlation time. Default 10 ms.
      seed: PRNG seed for the OU random walk. Default 42.

    Returns:
      JitterAnimationFrames with N=n_frames frames of animation data.

    Raises:
      ValueError: when w_inst_m, R_m, P_in_bucket_w, or grid_pixels
                  are non-positive.
    """
    if not (w_inst_m > 0):
        raise ValueError(f"w_inst_m must be positive, got {w_inst_m!r}")
    if not (R_m > 0):
        raise ValueError(f"R_m must be positive, got {R_m!r}")
    if not (P_in_bucket_w > 0):
        raise ValueError(
            f"P_in_bucket_w must be positive, got {P_in_bucket_w!r}"
        )
    if not (grid_pixels > 1):
        raise ValueError(
            f"grid_pixels must be > 1, got {grid_pixels!r}"
        )
    if not (n_frames > 0):
        raise ValueError(f"n_frames must be positive, got {n_frames!r}")

    rng = np.random.default_rng(seed)

    # ── Ornstein-Uhlenbeck random walk on the target plane.
    # Stationary RMS = σ_jit · R per axis (matches M7's w_jit² envelope).
    # α = exp(-dt/τ_corr) is the lag-1 autocorrelation; sqrt(1-α²) is
    # the noise-injection weight that keeps variance stationary.
    # Initial position drawn from N(0, σ_pos) so frame 0 is already
    # in steady state — no warm-up transient.
    sigma_pos_m = float(sigma_jit_rad) * float(R_m)
    alpha = math.exp(-float(dt_s) / float(tau_corr_s))
    noise_scale = sigma_pos_m * math.sqrt(max(0.0, 1.0 - alpha * alpha))

    positions = np.empty((n_frames, 2), dtype=np.float64)
    if sigma_pos_m > 0:
        positions[0] = rng.normal(0.0, sigma_pos_m, size=2)
        for i in range(1, n_frames):
            positions[i] = (
                alpha * positions[i - 1]
                + noise_scale * rng.standard_normal(2)
            )
    else:
        # σ_jit = 0 — degenerate: spot stationary at origin every
        # frame. The "perfect aim" comparison case.
        positions[:] = 0.0

    # ── Spatial grid — fixed extent, geometrically true. The half-
    # extent covers 60% of the larger target dimension on each side,
    # giving a 1.2 × target view. No auto-scaling per frame.
    half_extent = 0.6 * max(float(target_w_m), float(target_h_m))
    extent_m = (-half_extent, half_extent, -half_extent, half_extent)
    xs = np.linspace(-half_extent, half_extent, grid_pixels)
    ys = np.linspace(-half_extent, half_extent, grid_pixels)
    X, Y = np.meshgrid(xs, ys)

    # Pixel area for the energy-conservation test guarantee.
    pixel_dx_m = (2.0 * half_extent) / (grid_pixels - 1)
    _ = pixel_dx_m  # informational; not stored

    # ── Per-frame Gaussian flux deposition + cumulative integration.
    # The deposited intensity is a Gaussian centered at (x0, y0) with
    # 1/e² radius w_inst. Peak intensity:
    #   I_peak = 2 · P_in_bucket / (π · w_inst²)   (Gaussian peak)
    # Per-frame fluence at pixel (x, y):
    #   ΔE(x, y) = I_peak · exp(-2·r² / w_inst²) · dt
    # Cumulative E(x, y, t) = Σ ΔE over frames ≤ t.
    fluence_jpm2 = np.zeros((grid_pixels, grid_pixels), dtype=np.float64)
    fluence_history = np.empty(
        (n_frames, grid_pixels, grid_pixels), dtype=np.float64,
    )
    peak_intensity_const = (
        2.0 * float(P_in_bucket_w) / (math.pi * w_inst_m * w_inst_m)
    )
    inv_w_sq = 1.0 / (w_inst_m * w_inst_m)
    # E_fail_jpcm2 is not used for marker detection (see note below)
    # — kept in the API as informational so future rendering code can
    # build hover text like "X% of E_fail".
    _ = E_fail_jpcm2

    for i in range(n_frames):
        x0, y0 = positions[i]
        r_sq = (X - x0) ** 2 + (Y - y0) ** 2
        flux_now = peak_intensity_const * np.exp(-2.0 * r_sq * inv_w_sq)
        fluence_jpm2 += flux_now * dt_s
        fluence_history[i] = fluence_jpm2

    # ── Burn-through marker frame is pinned to the chain's
    # ``tau_BT`` (M8 trajectory τ_BT), NOT to the animation's own
    # pixel-wise peak-fluence threshold. Reason: the animation
    # deposits flux instantaneously at the wandering spot's
    # center (1/e² radius ``w_inst``), while M8's PDE integrates
    # against the time-averaged broader spot of radius ``w_total``.
    # The two models diverge on "when does the hottest pixel hit
    # E_fail" — a stationary view of M8's evolution would peg
    # burn-through earlier than the wandering-pixel view here.
    # Anchoring to the chain's tau_BT keeps the marker consistent
    # with the headline τ_BT shown elsewhere on the Engagement tab.
    if (tau_BT_s is not None and tau_BT_s > 0
            and not math.isnan(float(tau_BT_s))
            and not math.isinf(float(tau_BT_s))):
        candidate = int(round(float(tau_BT_s) / float(dt_s)))
        if 0 <= candidate < n_frames:
            burn_through_frame: int | None = candidate
        else:
            burn_through_frame = None
    else:
        burn_through_frame = None

    # ── Quantize fluence to uint8 for memory efficiency.
    # Keep the un-scaled max in J/cm² so the renderer can build a
    # human-readable colorbar.
    fluence_max_jpm2 = float(fluence_history.max())
    fluence_max_jpcm2 = fluence_max_jpm2 * 1e-4
    if fluence_max_jpm2 > 0:
        scaled = (fluence_history / fluence_max_jpm2) * 255.0
    else:
        # Degenerate case: P_in_bucket = 0 (or σ_jit so large that
        # all energy missed the target frame). Should never trigger
        # in practice given the validators above.
        scaled = fluence_history
    fluence_grids_uint8 = (
        np.clip(scaled, 0.0, 255.0).astype(np.uint8)
    )

    target_silhouette = _build_quadrotor_outline(
        float(target_w_m), float(target_h_m),
    )

    return JitterAnimationFrames(
        times_s=np.arange(n_frames, dtype=np.float64) * dt_s,
        spot_positions_m=positions,
        fluence_grids_uint8=fluence_grids_uint8,
        fluence_max_jpcm2=fluence_max_jpcm2,
        extent_m=extent_m,
        burn_through_frame=burn_through_frame,
        target_silhouette_xy_m=target_silhouette,
        bucket_radius_m=float(d_aim_m) / 2.0,
        spot_radius_m=float(w_inst_m),
        envelope_radius_m=sigma_pos_m,
        dt_s=float(dt_s),
        n_frames=int(n_frames),
    )


def _build_quadrotor_outline(w_m: float, h_m: float) -> np.ndarray:
    """Stylized X-frame quadrotor outline as a closed polyline.

    Geometry:
      - Central body: small filled square (~12% of span).
      - Four arms: from body corners out to the four propeller hubs.
      - Four propeller circles: at ±(w/2 - r_prop), ±(h/2 - r_prop),
        radius ~10% of the smaller span.

    Returns a single closed polyline (M, 2) with `nan` rows used as
    pen-up separators between sub-paths so a Plotly Scatter trace can
    render the whole silhouette in one trace.
    """
    half_w = w_m / 2.0
    half_h = h_m / 2.0
    body_half = 0.06 * min(w_m, h_m)
    prop_r = 0.10 * min(w_m, h_m)
    # Propeller hub centres slightly inset so propellers fit inside
    # the target bounding box.
    prop_x = half_w - prop_r
    prop_y = half_h - prop_r

    # Helper: closed rectangle [(−hx, −hy), (hx, −hy), (hx, hy), (−hx, hy)]
    def _rect(hx: float, hy: float, cx: float = 0.0, cy: float = 0.0):
        return np.array(
            [
                [cx - hx, cy - hy],
                [cx + hx, cy - hy],
                [cx + hx, cy + hy],
                [cx - hx, cy + hy],
                [cx - hx, cy - hy],
            ],
            dtype=np.float64,
        )

    # Helper: circle as N-point polyline.
    def _circle(cx: float, cy: float, r: float, n_pts: int = 24):
        theta = np.linspace(0.0, 2.0 * math.pi, n_pts, endpoint=True)
        return np.stack(
            [cx + r * np.cos(theta), cy + r * np.sin(theta)], axis=1,
        )

    # Helper: line segment.
    def _segment(p0: tuple[float, float], p1: tuple[float, float]):
        return np.array([p0, p1], dtype=np.float64)

    # `nan` row to "pen-up" between sub-paths.
    pen_up = np.array([[np.nan, np.nan]])

    parts: list[np.ndarray] = [
        _rect(body_half, body_half),  # body square
        pen_up,
        _segment((-body_half, -body_half), (-prop_x, -prop_y)),  # SW arm
        pen_up,
        _segment((body_half, -body_half), (prop_x, -prop_y)),    # SE arm
        pen_up,
        _segment((body_half, body_half), (prop_x, prop_y)),      # NE arm
        pen_up,
        _segment((-body_half, body_half), (-prop_x, prop_y)),    # NW arm
        pen_up,
        _circle(-prop_x, -prop_y, prop_r),
        pen_up,
        _circle(prop_x, -prop_y, prop_r),
        pen_up,
        _circle(prop_x, prop_y, prop_r),
        pen_up,
        _circle(-prop_x, prop_y, prop_r),
    ]
    return np.vstack(parts)


def burn_through_marker_active(
    frame_index: int,
    burn_through_frame: int | None,
    fade_frames: int = _MARKER_FADE_FRAMES,
) -> tuple[bool, float]:
    """Return ``(active, opacity)`` for the burn-through marker on
    a given frame.

    The marker exists from ``burn_through_frame`` to
    ``burn_through_frame + fade_frames``, with linear opacity decay
    from 1.0 to 0.0 over that window. Outside the window: inactive.
    Used by ``plot_jitter_target_animation`` to emit per-frame
    annotation visibility.
    """
    if burn_through_frame is None:
        return (False, 0.0)
    if frame_index < burn_through_frame:
        return (False, 0.0)
    elapsed = frame_index - burn_through_frame
    if elapsed >= fade_frames:
        return (False, 0.0)
    opacity = 1.0 - (elapsed / fade_frames)
    return (True, opacity)


__all__ = [
    "JitterAnimationFrames",
    "burn_through_marker_active",
    "generate_jitter_animation",
]
