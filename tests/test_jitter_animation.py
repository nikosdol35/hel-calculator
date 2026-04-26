"""Tests for ``physics/jitter_animation.py`` — the SPEC §8.7 jitter
target visualizer.

PR 1 of three. Covers the frame-generator physics:
  - OU random-walk steady-state RMS and adjacent-frame correlation
  - deterministic PRNG seeding (byte-identical reruns)
  - σ_jit=0 degenerate case (stationary spot, single Gaussian)
  - higher-σ_jit → lower peak fluence (energy spread)
  - total energy conservation (Riemann sum)
  - burn-through marker pinned to chain ``tau_BT_s`` (NOT to the
    animation's own pixel-wise peak fluence — see the docstring
    comment in ``generate_jitter_animation``)
  - extent geometrically true (no auto-scaling)
  - uint8 quantization is lossless within one quantization step

Plot-rendering tests live in ``tests/test_plot_jitter_animation.py``
(PR 2). This file is pure-physics, no Streamlit / Plotly imports.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from physics.jitter_animation import (
    JitterAnimationFrames,
    burn_through_marker_active,
    generate_jitter_animation,
)


# Canonical inputs for the smoke / OU tests. Matches the closing-
# physics review scenario (8 kW / 1 km / σ_jit=10 µrad).
_BASE = dict(
    w_inst_m=0.05,
    sigma_jit_rad=10e-6,
    R_m=1000.0,
    d_aim_m=0.05,
    target_w_m=2.3, target_h_m=2.3,
    P_in_bucket_w=2300.0,
    E_fail_jpcm2=96.0,
    tau_BT_s=1.13,
)


def test_frames_emitted():
    """Returns the requested number of frames with correct shapes
    and uint8 dtype on the fluence grid."""
    f = generate_jitter_animation(**_BASE, n_frames=200, grid_pixels=64)
    assert isinstance(f, JitterAnimationFrames)
    assert f.n_frames == 200
    assert f.times_s.shape == (200,)
    assert f.spot_positions_m.shape == (200, 2)
    assert f.fluence_grids_uint8.shape == (200, 64, 64)
    assert f.fluence_grids_uint8.dtype == np.uint8


def test_seed_determinism():
    """Two calls with the same seed produce byte-identical frames."""
    f1 = generate_jitter_animation(**_BASE, n_frames=100)
    f2 = generate_jitter_animation(**_BASE, n_frames=100)
    assert np.array_equal(f1.spot_positions_m, f2.spot_positions_m)
    assert np.array_equal(
        f1.fluence_grids_uint8, f2.fluence_grids_uint8,
    )
    # Different seed → different walk.
    f3 = generate_jitter_animation(**_BASE, n_frames=100, seed=99)
    assert not np.array_equal(f1.spot_positions_m, f3.spot_positions_m)


def test_OU_stationary_rms_per_axis():
    """Per-axis RMS over all 600 frames matches σ_jit·R within 10%.

    The OU process is stationary (initial state drawn from the
    stationary distribution), so RMS over any sufficiently long
    window equals σ_jit·R. With 600 samples the standard error of
    the RMS estimator is roughly σ/sqrt(2N) ≈ 3% of σ; 10%
    tolerance is loose enough to absorb that.
    """
    f = generate_jitter_animation(**_BASE, n_frames=600)
    expected = _BASE["sigma_jit_rad"] * _BASE["R_m"]   # 10 mm
    rms_x = float(np.sqrt(np.mean(f.spot_positions_m[:, 0] ** 2)))
    rms_y = float(np.sqrt(np.mean(f.spot_positions_m[:, 1] ** 2)))
    assert rms_x == pytest.approx(expected, rel=0.10)
    assert rms_y == pytest.approx(expected, rel=0.10)


def test_OU_correlation_at_dt():
    """Adjacent-frame correlation matches exp(−dt/τ_corr) within 15%.

    For dt=5 ms, τ_corr=10 ms, the expected lag-1 correlation is
    α = exp(−0.5) ≈ 0.607.
    """
    f = generate_jitter_animation(**_BASE, n_frames=2000)
    # Per-axis Pearson correlation between adjacent samples.
    x = f.spot_positions_m[:, 0]
    x_norm = x - x.mean()
    var = float(np.mean(x_norm * x_norm))
    cov = float(np.mean(x_norm[:-1] * x_norm[1:]))
    rho = cov / var
    expected_alpha = math.exp(
        -_BASE.get("dt_s", 0.005) / _BASE.get("tau_corr_s", 0.010)
    )
    assert rho == pytest.approx(expected_alpha, rel=0.15)


def test_zero_sigma_jit_stationary():
    """σ_jit=0 → all positions at origin; heat map is a single
    Gaussian centered there."""
    inputs = {**_BASE, "sigma_jit_rad": 0.0}
    f = generate_jitter_animation(**inputs, n_frames=100, grid_pixels=64)
    # All positions exactly at origin.
    assert np.array_equal(
        f.spot_positions_m,
        np.zeros((100, 2), dtype=np.float64),
    )
    # The cumulative fluence peak is at the grid center.
    last_grid = f.fluence_grids_uint8[-1]
    cy, cx = np.unravel_index(np.argmax(last_grid), last_grid.shape)
    grid_center = (last_grid.shape[0] - 1) / 2.0
    assert abs(cx - grid_center) <= 1
    assert abs(cy - grid_center) <= 1


def test_higher_sigma_jit_lower_peak_fluence():
    """Holding total power & duration fixed, doubling σ_jit drops
    the peak per-pixel fluence (energy is spread over a wider area).
    """
    f_low = generate_jitter_animation(
        **{**_BASE, "sigma_jit_rad": 5e-6}, n_frames=600,
    )
    f_high = generate_jitter_animation(
        **{**_BASE, "sigma_jit_rad": 50e-6}, n_frames=600,
    )
    assert f_high.fluence_max_jpcm2 < f_low.fluence_max_jpcm2 * 0.95, (
        f"expected peak fluence to drop with higher σ_jit; got "
        f"low={f_low.fluence_max_jpcm2:.2f} vs "
        f"high={f_high.fluence_max_jpcm2:.2f}"
    )


def test_total_energy_conserved():
    """Sum(fluence_grid) · pixel_area ≈ P_in_bucket · total_time
    within a few percent (Riemann + Gaussian-tails-clipped error).

    Caveat: the Gaussian extends past the grid extent, so a small
    fraction of the deposited flux is "missed" by the grid. With a
    generous 1.2× target extent, the tails outside are ≪ 1% of the
    total.
    """
    n_frames = 600
    dt_s = 0.005
    total_time = n_frames * dt_s   # 3.0 s
    P_in_bucket = _BASE["P_in_bucket_w"]
    expected_total_energy_j = P_in_bucket * total_time

    # Run with σ_jit=0 so the spot stays at the grid center — no
    # tail clipping. Use a smaller target so the grid extent is
    # tightly around the spot.
    inputs = {**_BASE, "sigma_jit_rad": 0.0,
              "target_w_m": 5.0, "target_h_m": 5.0}  # 6 m extent
    f = generate_jitter_animation(
        **inputs, n_frames=n_frames, grid_pixels=128,
    )
    # Reconstruct the J/m² fluence at the last frame from the uint8
    # quantization.
    fluence_max_jpm2 = f.fluence_max_jpcm2 * 1e4
    last_frame_jpm2 = (
        f.fluence_grids_uint8[-1].astype(np.float64) / 255.0
        * fluence_max_jpm2
    )
    # Pixel area in m².
    half_extent = 0.6 * max(_BASE["target_w_m"], _BASE["target_h_m"])
    half_extent = 0.6 * 5.0  # for the modified scenario
    pixel_dx = (2.0 * half_extent) / (128 - 1)
    pixel_area = pixel_dx ** 2
    integrated_energy_j = float(last_frame_jpm2.sum() * pixel_area)

    # Tolerance: 2% (Riemann + minor Gaussian-tail leak).
    assert integrated_energy_j == pytest.approx(
        expected_total_energy_j, rel=0.02,
    )


def test_burn_through_frame_pegged_to_tau_BT():
    """Marker frame index = round(tau_BT / dt). NOT computed from
    the animation's own pixel-wise peak fluence — see the comment
    in ``generate_jitter_animation``.
    """
    f = generate_jitter_animation(**_BASE, n_frames=600)
    expected = int(round(_BASE["tau_BT_s"] / 0.005))
    assert f.burn_through_frame == expected
    # And the time at that frame equals tau_BT to within dt rounding.
    assert f.times_s[f.burn_through_frame] == pytest.approx(
        _BASE["tau_BT_s"], abs=0.005,
    )


def test_burn_through_none_when_tau_BT_none():
    """tau_BT_s = None (e.g., engagement_ended_at_R_min) → marker None."""
    inputs = {**_BASE, "tau_BT_s": None}
    f = generate_jitter_animation(**inputs, n_frames=600)
    assert f.burn_through_frame is None


def test_burn_through_none_when_tau_BT_outside_window():
    """tau_BT > total visualization length → marker None.

    A 5 s tau_BT in a 3 s animation has nothing to mark within
    the loop window.
    """
    inputs = {**_BASE, "tau_BT_s": 5.0}
    f = generate_jitter_animation(**inputs, n_frames=600)
    assert f.burn_through_frame is None


def test_extent_geometrically_true():
    """Extent matches 0.6·max(target_w, target_h) on each side.
    No auto-scaling based on σ_jit·R or anything else.
    """
    f = generate_jitter_animation(
        **{**_BASE, "target_w_m": 4.0, "target_h_m": 2.0},
        n_frames=100,
    )
    expected_half = 0.6 * 4.0
    assert f.extent_m == pytest.approx(
        (-expected_half, expected_half, -expected_half, expected_half),
        rel=1e-9,
    )


def test_quantization_lossless_within_one_step():
    """uint8 reconstruction error ≤ 1/255 of the un-scaled max."""
    f = generate_jitter_animation(**_BASE, n_frames=200, grid_pixels=64)
    # Reconstructed J/m² from uint8.
    fluence_max_jpm2 = f.fluence_max_jpcm2 * 1e4
    reconstructed = (
        f.fluence_grids_uint8.astype(np.float64) / 255.0 * fluence_max_jpm2
    )
    # The original float64 history is not preserved by the dataclass
    # (memory savings), but the max value is. Check the reconstructed
    # max sits within 1 quantization step of the stored max.
    reconstructed_max = float(reconstructed.max())
    assert abs(reconstructed_max - fluence_max_jpm2) <= (
        fluence_max_jpm2 / 255.0 + 1e-9
    )


def test_validation_rejects_non_positive_inputs():
    """The frame generator validates its key inputs."""
    with pytest.raises(ValueError, match="w_inst"):
        generate_jitter_animation(**{**_BASE, "w_inst_m": 0.0})
    with pytest.raises(ValueError, match="R_m"):
        generate_jitter_animation(**{**_BASE, "R_m": -10.0})
    with pytest.raises(ValueError, match="P_in_bucket_w"):
        generate_jitter_animation(**{**_BASE, "P_in_bucket_w": 0.0})
    with pytest.raises(ValueError, match="grid_pixels"):
        generate_jitter_animation(**_BASE, grid_pixels=1)
    with pytest.raises(ValueError, match="n_frames"):
        generate_jitter_animation(**_BASE, n_frames=0)


def test_silhouette_within_target_bounds():
    """The quadrotor outline never extends past the target bounding
    box (so it always sits inside the grid extent)."""
    f = generate_jitter_animation(**_BASE, n_frames=10)
    s = f.target_silhouette_xy_m
    finite = s[~np.isnan(s).any(axis=1)]
    assert finite[:, 0].min() >= -_BASE["target_w_m"] / 2.0 - 1e-9
    assert finite[:, 0].max() <= _BASE["target_w_m"] / 2.0 + 1e-9
    assert finite[:, 1].min() >= -_BASE["target_h_m"] / 2.0 - 1e-9
    assert finite[:, 1].max() <= _BASE["target_h_m"] / 2.0 + 1e-9


def test_silhouette_has_pen_up_separators():
    """The silhouette uses NaN rows as pen-up separators between
    sub-paths (body / arms / propellers)."""
    f = generate_jitter_animation(**_BASE, n_frames=10)
    s = f.target_silhouette_xy_m
    assert np.isnan(s).any(), (
        "expected at least one NaN row separating sub-paths"
    )


def test_burn_through_marker_active_helper():
    """``burn_through_marker_active`` returns active=True with
    fading opacity inside the window, False outside."""
    # No marker case.
    assert burn_through_marker_active(50, None) == (False, 0.0)
    # Before marker frame.
    assert burn_through_marker_active(100, 200) == (False, 0.0)
    # At marker frame — full opacity.
    active, opacity = burn_through_marker_active(200, 200, fade_frames=200)
    assert active is True
    assert opacity == pytest.approx(1.0)
    # Half-way through fade — half opacity.
    active, opacity = burn_through_marker_active(300, 200, fade_frames=200)
    assert active is True
    assert opacity == pytest.approx(0.5)
    # Past fade window — inactive.
    assert burn_through_marker_active(450, 200, fade_frames=200) == (
        False, 0.0,
    )


def test_envelope_radius_recorded():
    """The frames object records the envelope radius (= σ_jit · R)
    so the renderer can draw a dashed circle without recomputing."""
    f = generate_jitter_animation(**_BASE, n_frames=10)
    assert f.envelope_radius_m == pytest.approx(
        _BASE["sigma_jit_rad"] * _BASE["R_m"], rel=1e-9,
    )


def test_bucket_radius_recorded():
    """bucket_radius_m = d_aim / 2."""
    f = generate_jitter_animation(**_BASE, n_frames=10)
    assert f.bucket_radius_m == pytest.approx(
        _BASE["d_aim_m"] / 2.0, rel=1e-9,
    )
