"""Tests for ``ui.plots.plot_jitter_target_animation`` — the SPEC §8.7
plot constructor.

PR 2 of three. Verifies the Plotly Frames structure, axis aspect lock,
speed handling, looping configuration, silhouette presence, and the
None-frames empty-frame fallback.

The frame data itself is checked in ``tests/test_jitter_animation.py``
(PR 1).
"""
from __future__ import annotations

import pytest

from physics.jitter_animation import generate_jitter_animation
from ui.plots import plot_jitter_target_animation


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


def _frames(**overrides):
    return generate_jitter_animation(
        **{**_BASE, **overrides}, n_frames=200, grid_pixels=64,
    )


def test_plot_smoke():
    """Constructs a valid Plotly figure with the expected number of
    frames and traces."""
    f = _frames()
    fig = plot_jitter_target_animation(f)
    # Six traces in the static layer: heatmap + silhouette + bucket
    # + envelope + comet + spot.
    assert len(fig.data) == 6
    assert fig.frames is not None
    assert len(fig.frames) == f.n_frames
    # First trace is the heatmap; second is the silhouette.
    assert fig.data[0].type == "heatmap"
    assert fig.data[1].type == "scatter"


def test_plot_axes_locked_aspect_square():
    """Y-axis scale is anchored to x-axis with ratio 1.0 so a circle
    on the heatmap plane displays as a circle, not an ellipse."""
    f = _frames()
    fig = plot_jitter_target_animation(f)
    assert fig.layout.yaxis.scaleanchor == "x"
    assert fig.layout.yaxis.scaleratio == 1.0


def test_plot_extent_in_mm():
    """Axes labelled in mm; extent matches the frames' extent
    converted from m."""
    f = _frames()
    fig = plot_jitter_target_animation(f)
    expected_low = f.extent_m[0] * 1000.0
    expected_high = f.extent_m[1] * 1000.0
    assert fig.layout.xaxis.range == (
        pytest.approx(expected_low),
        pytest.approx(expected_high),
    )


def test_plot_speed_affects_frame_duration():
    """Speed = 1× → 5 ms; 0.5× → 10 ms; 0.2× → 25 ms."""
    f = _frames()
    for speed, expected_ms in [(1.0, 5.0), (0.5, 10.0), (0.2, 25.0)]:
        fig = plot_jitter_target_animation(f, speed=speed)
        # The Play button's animation args carry the per-frame duration.
        play_button = fig.layout.updatemenus[0].buttons[0]
        assert play_button.label == "Play"
        duration = play_button.args[1]["frame"]["duration"]
        assert duration == pytest.approx(expected_ms), (
            f"speed={speed}× should give frame duration {expected_ms} ms, "
            f"got {duration}"
        )


def test_plot_loops():
    """Animation config has loop=True and mode='immediate'."""
    f = _frames()
    fig = plot_jitter_target_animation(f)
    play_button = fig.layout.updatemenus[0].buttons[0]
    args = play_button.args[1]
    assert args.get("mode") == "immediate"
    assert args.get("loop") is True


def test_plot_play_pause_reset_buttons_present():
    """All three controls are wired up via updatemenus."""
    f = _frames()
    fig = plot_jitter_target_animation(f)
    labels = [b.label for b in fig.layout.updatemenus[0].buttons]
    assert "Play" in labels
    assert "Pause" in labels
    assert "Reset" in labels


def test_plot_slider_present():
    """A scrubbing slider is wired up."""
    f = _frames()
    fig = plot_jitter_target_animation(f)
    assert fig.layout.sliders is not None
    assert len(fig.layout.sliders) == 1
    # Slider has at least one step per ~10 frames.
    n_steps = len(fig.layout.sliders[0].steps)
    assert n_steps > 0
    assert n_steps <= f.n_frames


def test_plot_silhouette_present():
    """The UAV silhouette trace is present in the figure."""
    f = _frames()
    fig = plot_jitter_target_animation(f)
    # Trace[1] is the silhouette per the layer ordering.
    silhouette = fig.data[1]
    assert silhouette.type == "scatter"
    # It has data points (the quadrotor outline).
    assert len(silhouette.x) > 0


def test_plot_bucket_circle_present():
    """The dashed bucket circle is in the figure with the correct
    legend label."""
    f = _frames()
    fig = plot_jitter_target_animation(f)
    # Trace[2] is the bucket per the layer ordering.
    bucket = fig.data[2]
    assert bucket.type == "scatter"
    assert "Bucket" in bucket.name
    assert bucket.line.dash == "dash"


def test_plot_envelope_circle_present():
    """The dotted jitter envelope circle is in the figure with the
    correct legend label."""
    f = _frames()
    fig = plot_jitter_target_animation(f)
    # Trace[3] is the envelope per the layer ordering.
    envelope = fig.data[3]
    assert envelope.type == "scatter"
    assert "Jitter envelope" in envelope.name
    assert envelope.line.dash == "dot"


def test_plot_burn_through_annotation_when_marker_present():
    """Frames within the burn-through fade window carry the
    '✓ Burn-through at t=...' annotation."""
    # Use τ_BT = 0.5 s so the marker (frame 100) sits inside the
    # 200-frame test window.
    f = generate_jitter_animation(
        **{**_BASE, "tau_BT_s": 0.5}, n_frames=200, grid_pixels=64,
    )
    fig = plot_jitter_target_animation(f)
    burn_idx = f.burn_through_frame
    assert burn_idx is not None
    # Frame at the burn-through index should carry the annotation
    # at full opacity.
    annotations_at_burn = list(fig.frames[burn_idx].layout.annotations)
    assert len(annotations_at_burn) == 1
    assert "Burn-through" in annotations_at_burn[0].text
    assert annotations_at_burn[0].opacity == pytest.approx(1.0)
    # A frame well before the burn-through has no annotation.
    pre_idx = max(0, burn_idx - 100)
    annotations_pre = list(fig.frames[pre_idx].layout.annotations)
    assert len(annotations_pre) == 0


def test_plot_no_burn_through_annotation_when_no_marker():
    """When tau_BT is None or out of window, no frame carries a
    burn-through annotation."""
    f = generate_jitter_animation(
        **{**_BASE, "tau_BT_s": None}, n_frames=100,
    )
    fig = plot_jitter_target_animation(f)
    for frame in fig.frames:
        annos = list(frame.layout.annotations or [])
        assert len(annos) == 0


def test_plot_none_frames_renders_empty_frame():
    """A None input renders the always-render frame fallback."""
    fig = plot_jitter_target_animation(None)
    assert len(fig.data) == 0
