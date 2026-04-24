"""Unit tests for ``ui/components.py`` helpers that have pure return values.

The only ``components.py`` helper that produces a testable return value is
``format_value`` — every other helper writes to Streamlit and is exercised
by the live app rather than by a unit test. This file pins the formatter's
SPEC v1.10 §5.3 item 8 behavior:

  * 3 significant figures by default.
  * Comma thousands-separator at magnitudes >= 1000.
  * Scientific notation (``"m.mm × 10^n"`` with Unicode × and superscript
    digits) when ``|value| < 0.01`` or ``|value| >= 1e5``.
  * Non-breaking space (U+00A0) between value and unit.
  * Em-dash (``—``) for ``None`` / ``NaN`` / ``inf``.

A regression in any of these rules would silently skew every number on
screen, so they get a focused test file rather than being folded in with
a physics-module test.

References:
    SPEC.md §5.3 item 8 — numerical display conventions.
    ui/components.py::format_value — the implementation under test.
    CLAUDE.md §5.1 — test-authoring conventions.
"""

from __future__ import annotations

import math

import pytest

from ui.components import format_value


# Non-breaking space between value and unit.
_NBSP = "\u00a0"


# =============================================================================
# Fixed-point formatting
# =============================================================================

class TestFixedPoint:
    """The default, non-sci-notation path: magnitudes in [0.01, 1e5)."""

    def test_small_magnitude_three_sig_figs(self) -> None:
        assert format_value(0.847, "") == "0.847"

    def test_medium_magnitude_three_sig_figs(self) -> None:
        # 45.7 picks a value that is not a floating-point halfway case, so
        # the rounding result is stable across platforms.
        assert format_value(45.7, "") == "45.7"

    def test_magnitude_10000(self) -> None:
        # Just under the 1e5 sci-notation boundary — fixed-point with comma.
        # Integer digits are always shown in full; sig_figs is a minimum-
        # precision target, not a digit cap. Matches the design-document
        # example "12,450 m".
        assert format_value(12450.0, "m") == f"12,450{_NBSP}m"

    def test_comma_thousands_separator(self) -> None:
        # Same rule as test_magnitude_10000 — 4 integer digits survive.
        assert format_value(1234.0, "") == "1,234"

    def test_zero(self) -> None:
        assert format_value(0, "kW") == f"0{_NBSP}kW"

    def test_negative_value(self) -> None:
        assert format_value(-42.7, "K") == f"-42.7{_NBSP}K"


# =============================================================================
# Scientific-notation formatting
# =============================================================================

class TestScientificNotation:
    """Magnitudes outside [0.01, 1e5) render in sci notation."""

    def test_small_value_uses_sci(self) -> None:
        # 1.23e-6 → "1.23 × 10⁻⁶"
        result = format_value(0.00000123, "W/cm²")
        assert result == f"1.23 × 10⁻⁶{_NBSP}W/cm²"

    def test_large_value_uses_sci(self) -> None:
        # 1.23e6 → "1.23 × 10⁶"
        result = format_value(1.23e6, "")
        assert result == "1.23 × 10⁶"

    def test_boundary_below_sci_low_uses_sci(self) -> None:
        # 9.99e-3 is below 0.01, sci notation.
        result = format_value(0.00999, "")
        assert "× 10" in result

    def test_boundary_at_sci_low_uses_fixed(self) -> None:
        # 0.01 exactly is at the boundary and uses fixed-point.
        result = format_value(0.01, "")
        assert "× 10" not in result

    def test_boundary_at_sci_high_uses_sci(self) -> None:
        # 1e5 exactly is at the upper boundary and uses sci notation.
        result = format_value(1e5, "")
        assert "× 10" in result

    def test_superscript_digit_mapping(self) -> None:
        # Verify each exponent glyph is the correct Unicode superscript.
        assert format_value(1.0e12, "") == "1.00 × 10¹²"
        assert format_value(1.0e-8, "") == "1.00 × 10⁻⁸"

    def test_uses_unicode_times_not_ascii_x(self) -> None:
        # U+00D7 MULTIPLICATION SIGN — not ASCII "x" and not "*".
        result = format_value(1.5e6, "")
        assert "×" in result  # U+00D7
        assert "x" not in result.lower()[:10]
        assert "*" not in result


# =============================================================================
# Non-finite values → em-dash
# =============================================================================

class TestNonFinite:
    """None, NaN, and inf render as an em-dash (U+2014)."""

    def test_none(self) -> None:
        assert format_value(None, "s") == "—"

    def test_nan(self) -> None:
        assert format_value(float("nan"), "W") == "—"

    def test_positive_inf(self) -> None:
        assert format_value(float("inf"), "m") == "—"

    def test_negative_inf(self) -> None:
        assert format_value(-math.inf, "") == "—"

    def test_non_numeric_string(self) -> None:
        # Strings that can't coerce to float return the em-dash, not a traceback.
        assert format_value("not a number", "K") == "—"  # type: ignore[arg-type]


# =============================================================================
# Unit handling
# =============================================================================

class TestUnits:
    """Unit always non-breaking-spaced; empty unit yields no trailing space."""

    def test_non_breaking_space_before_unit(self) -> None:
        result = format_value(3.14, "m")
        assert _NBSP in result
        assert result.endswith(f"{_NBSP}m")

    def test_no_unit_no_trailing_space(self) -> None:
        result = format_value(3.14, "")
        assert result == "3.14"
        assert not result.endswith(" ")

    def test_unicode_unit_preserved(self) -> None:
        # Common output units use µ, °, ², ⁻¹ etc. — emitted verbatim.
        assert format_value(1.5, "µrad").endswith(f"{_NBSP}µrad")
        assert format_value(20.0, "°C").endswith(f"{_NBSP}°C")
        assert format_value(5.0, "W/cm²").endswith(f"{_NBSP}W/cm²")


# =============================================================================
# Sig-figs parameter
# =============================================================================

class TestSigFigs:
    """sig_figs controls the precision both in fixed and scientific branches."""

    def test_four_sig_figs_fixed(self) -> None:
        assert format_value(0.8472, "", sig_figs=4) == "0.8472"

    def test_four_sig_figs_sci(self) -> None:
        # 1.2345e-6 with sig_figs=4 → "1.235 × 10⁻⁶" (mantissa to 4 digits)
        result = format_value(1.2345e-6, "", sig_figs=4)
        assert result == "1.235 × 10⁻⁶"

    def test_two_sig_figs_fractional(self) -> None:
        # sig_figs=2 drops a fractional digit rather than rounding the
        # integer part (which is always preserved — see TestFixedPoint).
        assert format_value(0.8472, "", sig_figs=2) == "0.85"


# =============================================================================
# Integer inputs
# =============================================================================

class TestIntegerInput:
    """Integer inputs round-trip through format_value without losing commas."""

    def test_small_int(self) -> None:
        assert format_value(7, "s") == f"7.00{_NBSP}s"

    def test_large_int_uses_comma(self) -> None:
        assert format_value(50_000, "") == "50,000"

    def test_very_large_int_uses_sci(self) -> None:
        # 1,000,000 > 1e5 → sci notation.
        result = format_value(1_000_000, "m")
        assert "× 10" in result


# =============================================================================
# Approx check — not a format test, but a smoke test that the formatter
# never raises on the canonical inputs engineers will throw at it.
# =============================================================================

CANONICAL_VALUES: tuple[tuple[float | None, str], ...] = (
    # (value, unit)
    (1.234e-9,   "W/cm²"),   # extreme-small irradiance
    (1.234e9,    "W"),        # extreme-large power
    (0.0,        ""),         # zero
    (-273.15,    "°C"),       # negative
    (42.0,       "s"),        # typical time
    (None,       "kW"),       # missing
    (float("nan"), "m"),      # NaN propagation
)


@pytest.mark.parametrize("value, unit", CANONICAL_VALUES)
def test_format_value_never_raises(value: float | None, unit: str) -> None:
    """The formatter is the single gate for every number on screen. It
    must never raise — even on ``None``, ``NaN``, or extreme magnitudes —
    because an exception here crashes the whole result surface."""
    result = format_value(value, unit)
    assert isinstance(result, str)
    assert result  # never empty
