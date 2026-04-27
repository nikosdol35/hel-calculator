"""Regression guards for the 2026-04-27 metric-card tooltip redesign.

Before: ``metric_card`` rendered the optional ``tooltip`` string as a
browser-native hover popup via ``title=`` on the outer ``<div>``. Two
problems: users had to know to hover, and the popup floated over
neighbouring cards (visible in the user's Spot & Strehl screenshot).

After: the tooltip text is appended as an inline div underneath the
value row, in 12 px / fg.secondary styling. Visible at first read,
no hover required, no overlap onto adjacent cards.

These tests lock the contract:
  - Tooltip text is rendered as a ``hel-card-tooltip-inline`` div.
  - When ``tooltip`` is None or empty, no extra div is emitted.
  - ``title=`` attribute is NOT used (regression guard against
    re-introducing hover-only behaviour).

The tests stub ``streamlit.markdown`` so we can inspect the HTML
the function emits without spinning up a Streamlit runtime.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def captured_markdown():
    """Stub ``st.markdown`` and capture every call's HTML payload.

    Returns a list that accumulates each emitted HTML string. The
    function under test always passes ``unsafe_allow_html=True``,
    so the first positional arg is the HTML.
    """
    captured: list[str] = []

    def _fake_markdown(html, **kwargs):
        captured.append(html)

    with patch("streamlit.markdown", new=_fake_markdown):
        yield captured


def test_tooltip_renders_as_inline_div(captured_markdown):
    """A non-empty tooltip is appended as a
    ``hel-card-tooltip-inline`` div containing the tooltip text."""
    from ui.components import metric_card
    metric_card("X", 1.0, "kW", tooltip="hello world")
    html = captured_markdown[0]
    assert 'class="hel-card-tooltip-inline"' in html, (
        f"expected inline tooltip div; got {html!r}"
    )
    assert "hello world" in html


def test_no_tooltip_no_inline_div(captured_markdown):
    """When tooltip is None, no inline div is rendered."""
    from ui.components import metric_card
    metric_card("X", 1.0, "kW", tooltip=None)
    html = captured_markdown[0]
    assert "hel-card-tooltip-inline" not in html, (
        f"expected no inline div for tooltip=None; got {html!r}"
    )


def test_empty_tooltip_no_inline_div(captured_markdown):
    """An empty-string tooltip is treated the same as None."""
    from ui.components import metric_card
    metric_card("X", 1.0, "kW", tooltip="")
    html = captured_markdown[0]
    assert "hel-card-tooltip-inline" not in html


def test_no_title_attribute_on_outer_div(captured_markdown):
    """Regression guard: the prior browser-native hover tooltip used
    ``title=`` on the outer div. New behaviour is inline, so the
    title attribute must NOT be set anywhere.

    A reintroduced ``title=`` would re-introduce the floating
    browser tooltip that overlaps neighbouring cards (the original
    bug from the user's Spot & Strehl screenshot).
    """
    from ui.components import metric_card
    metric_card("X", 1.0, "kW", tooltip="some text that used to be a title")
    html = captured_markdown[0]
    assert " title=" not in html, (
        f"unexpected title= attribute (regression to hover-only "
        f"tooltip); got {html!r}"
    )


def test_tooltip_works_with_string_value(captured_markdown):
    """Non-numeric values (e.g. material name 'CFRP') render with
    inline tooltip just like numeric values."""
    from ui.components import metric_card
    metric_card("Material", "CFRP", tooltip="Carbon-fibre composite")
    html = captured_markdown[0]
    assert 'class="hel-card-tooltip-inline"' in html
    assert "Carbon-fibre composite" in html
    assert "CFRP" in html


def test_card_html_structure_label_value_tooltip(captured_markdown):
    """The three-block card structure renders in the expected order:
    label first, value-row second, tooltip third."""
    from ui.components import metric_card
    metric_card("Velocity", 42.0, "m/s", tooltip="target velocity")
    html = captured_markdown[0]
    label_idx = html.index('class="hel-card-label"')
    value_idx = html.index('class="hel-card-value-row"')
    tooltip_idx = html.index('class="hel-card-tooltip-inline"')
    assert label_idx < value_idx < tooltip_idx, (
        f"unexpected block order: label@{label_idx} value@{value_idx} "
        f"tooltip@{tooltip_idx}"
    )
