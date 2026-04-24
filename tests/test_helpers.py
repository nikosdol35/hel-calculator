"""Helper-function unit tests (Package 2 Layer 2.6).

Every small utility that the physics modules build on top of gets its
own focused test here — validation helpers in `physics.common`, the
log-log interpolator, the M8 A_λ lookup, the M9 piecewise MPE formula,
and the laser-class enumeration. These functions are too small to earn
their own validation case in SPEC §3, yet a regression in any one of
them would silently corrupt every module that calls it.

Coverage goals per validation/README.md Layer 2.6:
    - `interp_log_space`: node values, log-log linearity, boundary clamp.
    - `wavelength_in_validated_set`: 4 validated wavelengths, ±5 nm edge.
    - `validate_positive` / `validate_range` / `validate_enum`: raise at
      boundary (inclusive vs exclusive explicit).
    - `_lookup_A_lambda`: exact at each tabulated λ, interp at midpoints,
      clamp below 1.06 µm and above 2.05 µm.
    - `_mpe_irradiance_wpm2`: continuity across the `t = 18 µs` and
      `t = 10 s` joins; Band A ↔ Band B transition at λ = 1.4 µm.
    - `_classify`: behaviour at each of the ANSI power thresholds
      (0.39 mW, 1 mW, 5 mW, 500 mW).
"""

from __future__ import annotations

import pytest

from physics.common import (
    interp_log_space,
    validate_enum,
    validate_positive,
    validate_range,
    wavelength_in_validated_set,
)
from physics.m4_data_tables import VALIDATED_WAVELENGTHS_M
from physics.m8_burnthrough import _lookup_A_lambda
from physics.m8_material_tables import A_LAMBDA_TABLE, A_LAMBDA_TABLE_WAVELENGTHS_M
from physics.m9_nohd import _classify, _mpe_irradiance_wpm2


# ---------------------------------------------------------------------------
# interp_log_space
# ---------------------------------------------------------------------------


def test_interp_log_space_exact_at_nodes() -> None:
    """At every x_table node the interpolator must return the exact
    tabulated y value — no floating-point drift, no off-by-one."""
    xs = [1.0, 2.0, 4.0, 8.0, 16.0]
    ys = [10.0, 20.0, 40.0, 80.0, 160.0]
    for x, y in zip(xs, ys):
        assert interp_log_space(x, xs, ys) == pytest.approx(y, rel=1e-12)


def test_interp_log_space_linear_in_log_log() -> None:
    """For a table that follows y = x^p exactly, the interpolator is
    linear in (log x, log y) so interpolated points must match x^p at
    machine precision. Tests the core claim of the helper."""
    p = 1.7
    xs = [1.0, 2.0, 4.0, 8.0, 16.0]
    ys = [x ** p for x in xs]
    for x in (1.3, 2.7, 5.5, 11.0):
        expected = x ** p
        assert interp_log_space(x, xs, ys) == pytest.approx(expected, rel=1e-12)


def test_interp_log_space_constant_table_returns_constant() -> None:
    """A flat y_table must produce a flat interpolant. Regression guard
    against ever sneaking a non-zero slope into the formula."""
    xs = [1.0, 10.0, 100.0, 1000.0]
    ys = [0.5, 0.5, 0.5, 0.5]
    for x in (1.0, 2.5, 42.0, 999.9):
        assert interp_log_space(x, xs, ys) == pytest.approx(0.5, rel=1e-12)


def test_interp_log_space_clamps_below_first_node() -> None:
    """Below the table left edge the helper must return y_table[0]
    unchanged — the caller is responsible for flagging the extrapolation
    (e.g., M4 does via `assumptions_flagged`)."""
    xs = [1.0, 2.0, 4.0]
    ys = [10.0, 20.0, 40.0]
    assert interp_log_space(0.001, xs, ys) == pytest.approx(10.0, rel=1e-12)
    assert interp_log_space(1.0, xs, ys) == pytest.approx(10.0, rel=1e-12)


def test_interp_log_space_clamps_above_last_node() -> None:
    """Above the table right edge the helper must return y_table[-1]."""
    xs = [1.0, 2.0, 4.0]
    ys = [10.0, 20.0, 40.0]
    assert interp_log_space(1000.0, xs, ys) == pytest.approx(40.0, rel=1e-12)
    assert interp_log_space(4.0, xs, ys) == pytest.approx(40.0, rel=1e-12)


def test_interp_log_space_mismatched_lengths_raises() -> None:
    """Length mismatch or a 1-element table is a bug the helper must
    detect — the alternative is a silent IndexError deep in a physics
    module."""
    with pytest.raises(ValueError, match="same length"):
        interp_log_space(1.0, [1.0, 2.0], [1.0])
    with pytest.raises(ValueError, match="same length"):
        interp_log_space(1.0, [1.0], [1.0])


# ---------------------------------------------------------------------------
# wavelength_in_validated_set
# ---------------------------------------------------------------------------


def test_wavelength_validated_set_exact_matches() -> None:
    """All four SPEC §3 validated wavelengths must be recognised."""
    for lam in VALIDATED_WAVELENGTHS_M:
        assert wavelength_in_validated_set(lam) is True


def test_wavelength_validated_set_within_default_tolerance() -> None:
    """Default tolerance is 5 nm per ARCHITECTURE §4.3: ±5 nm from any
    reference wavelength is still considered validated. ±6 nm is not.

    NOTE: 1.06 µm and 1.07 µm are only 10 nm apart, so an offset that
    appears to fall outside one reference's ±5 nm window can still land
    inside the adjacent reference's. This test uses the isolated
    wavelengths 1.55 µm and 2.05 µm (neighbour distances ≥ 480 nm) so
    the ±6 nm rejection check is unambiguous.
    """
    isolated = [1.55e-6, 2.05e-6]
    for lam in isolated:
        assert wavelength_in_validated_set(lam + 5.0e-9) is True
        assert wavelength_in_validated_set(lam - 5.0e-9) is True
        assert wavelength_in_validated_set(lam + 6.0e-9) is False
        assert wavelength_in_validated_set(lam - 6.0e-9) is False

    # For the 1.06 / 1.07 µm cluster, the ±5 nm acceptance still holds
    # but ±6 nm depends on which neighbour it's closest to. We verify
    # the acceptance side only for these.
    for lam in (1.06e-6, 1.07e-6):
        assert wavelength_in_validated_set(lam + 5.0e-9) is True
        assert wavelength_in_validated_set(lam - 5.0e-9) is True


def test_wavelength_validated_set_custom_tolerance() -> None:
    """A widened tol_nm parameter expands the window; a 0-nm tolerance
    demands exact match.

    Uses the 2.05 µm reference (nearest neighbour 1.55 µm is 500 nm
    away) so a 10 nm offset does not accidentally land on another
    validated wavelength at tol_nm=0.
    """
    assert wavelength_in_validated_set(2.05e-6 + 10.0e-9, tol_nm=15.0) is True
    assert wavelength_in_validated_set(2.05e-6 + 10.0e-9, tol_nm=0.0) is False
    assert wavelength_in_validated_set(2.05e-6, tol_nm=0.0) is True


def test_wavelength_validated_set_far_wavelengths_rejected() -> None:
    """Wavelengths far outside the validated set (e.g., visible green,
    thermal IR) must be rejected regardless of tolerance."""
    assert wavelength_in_validated_set(532e-9) is False
    assert wavelength_in_validated_set(10.6e-6) is False


# ---------------------------------------------------------------------------
# validate_positive / validate_range / validate_enum
# ---------------------------------------------------------------------------


def test_validate_positive_accepts_positive_values() -> None:
    """Any strictly positive float must pass silently."""
    for v in (1e-30, 1e-3, 1.0, 1e6):
        validate_positive(v, "x")  # no raise


def test_validate_positive_rejects_zero_and_negative() -> None:
    """Zero is NOT positive; the helper uses `<= 0` so 0.0 must raise."""
    with pytest.raises(ValueError, match="must be > 0"):
        validate_positive(0.0, "x")
    with pytest.raises(ValueError, match="must be > 0"):
        validate_positive(-1.0, "x")


def test_validate_range_inclusive_boundaries() -> None:
    """The `[lo, hi]` docstring notation is inclusive on BOTH ends —
    the implementation uses `lo <= v <= hi`. Lock that in."""
    validate_range(0.0, "x", 0.0, 1.0)   # lo allowed
    validate_range(1.0, "x", 0.0, 1.0)   # hi allowed
    validate_range(0.5, "x", 0.0, 1.0)


def test_validate_range_rejects_outside() -> None:
    """A value just below lo or just above hi must raise with the
    range shown in the error so the user can pinpoint the bad input."""
    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        validate_range(-1e-9, "x", 0.0, 1.0)
    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        validate_range(1.0 + 1e-9, "x", 0.0, 1.0)


def test_validate_enum_accepts_allowed() -> None:
    """Strings in the allowed list pass; case-sensitive."""
    validate_enum("HV_5_7", "cn2_model", ["HV_5_7", "const"])
    validate_enum("const", "cn2_model", ["HV_5_7", "const"])


def test_validate_enum_rejects_unknown() -> None:
    """A value outside the allowed list must raise, and the message must
    show the allowed options so the user doesn't have to read the code."""
    with pytest.raises(ValueError, match="must be one of"):
        validate_enum("HV57", "cn2_model", ["HV_5_7", "const"])
    with pytest.raises(ValueError, match="must be one of"):
        validate_enum("hv_5_7", "cn2_model", ["HV_5_7", "const"])  # case-sensitive


# ---------------------------------------------------------------------------
# _lookup_A_lambda (M8 absorptivity table)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("material", list(A_LAMBDA_TABLE.keys()))
def test_lookup_A_lambda_exact_at_tabulated_points(material: str) -> None:
    """At every tabulated wavelength the lookup must return the table
    value verbatim. No interpolation flag, no drift."""
    table = A_LAMBDA_TABLE[material]
    for wl, expected in zip(A_LAMBDA_TABLE_WAVELENGTHS_M, table):
        a, flag = _lookup_A_lambda(material, wl)
        assert a == pytest.approx(expected, rel=1e-12)
        assert flag is None, (
            f"Exact-node lookup for {material} @ {wl*1e6:.3f} µm raised "
            f"an interpolation flag: {flag!r}"
        )


def test_lookup_A_lambda_linear_interp_at_midpoint() -> None:
    """Halfway between two tabulated points the lookup is the average
    of the two endpoint values (linear-in-wavelength per M8 docstring).
    GFRP goes 0.40 → 0.45 between 1.07 and 1.55 µm; midpoint is 0.425."""
    wl_mid = 0.5 * (1.07e-6 + 1.55e-6)
    a, flag = _lookup_A_lambda("GFRP", wl_mid)
    assert a == pytest.approx(0.425, rel=1e-9)
    assert flag is not None and "interpolated" in flag.lower()


def test_lookup_A_lambda_clamp_below_range() -> None:
    """For λ below 1.06 µm the lookup clamps to the first column and
    raises a 'reduced confidence' flag. Anodized Al 0.30 is the floor."""
    a, flag = _lookup_A_lambda("anodized_Al", 0.9e-6)
    assert a == pytest.approx(0.30, rel=1e-12)
    assert flag is not None and "below" in flag.lower()


def test_lookup_A_lambda_clamp_above_range() -> None:
    """For λ above 2.05 µm the lookup clamps to the last column and
    flags. Polycarbonate goes up to 0.60 at 2.05 µm."""
    a, flag = _lookup_A_lambda("polycarbonate", 3.0e-6)
    assert a == pytest.approx(0.60, rel=1e-12)
    assert flag is not None and "above" in flag.lower()


# ---------------------------------------------------------------------------
# _mpe_irradiance_wpm2 (M9 ANSI Z136.1 piecewise)
# ---------------------------------------------------------------------------


def test_mpe_band_a_continuity_at_18us_join() -> None:
    """ANSI Z136.1 Band A switches from 5e-3/t to 1.8e-3·t^(-1/4) at
    t = 18 µs. Values either side of the join must agree — if they
    don't, the standard was transcribed wrong."""
    t = 18.0e-6
    mpe_just_below = _mpe_irradiance_wpm2(1.07e-6, t * 0.999)
    mpe_just_above = _mpe_irradiance_wpm2(1.07e-6, t * 1.001)
    # Both formulas are designed to meet here. Allow 1 % slack to absorb
    # the 0.1 % step on either side of the join.
    assert mpe_just_below == pytest.approx(mpe_just_above, rel=0.01)


def test_mpe_band_a_continuity_at_10s_join() -> None:
    """Band A switches from 1.8e-3·t^(-1/4) to the chronic 1.0e-3 at
    t = 10 s. At t = 10 the repeated-pulse formula evaluates to
    1.8e-3·10^(-1/4) ≈ 1.01e-3, which matches the chronic value to ~1%.
    ANSI's own table accepts that small step."""
    lam = 1.07e-6
    mpe_just_below = _mpe_irradiance_wpm2(lam, 10.0 - 1e-6)
    mpe_just_above = _mpe_irradiance_wpm2(lam, 10.0 + 1e-6)
    assert mpe_just_below == pytest.approx(mpe_just_above, rel=0.02)


def test_mpe_band_b_continuity_at_10s_join() -> None:
    """Band B switches from 0.56·t^(-3/4) to chronic 0.1 at t = 10 s.
    0.56·10^(-3/4) = 0.0996 ≈ 0.1 — designed to meet at the join."""
    lam = 1.55e-6
    mpe_just_below = _mpe_irradiance_wpm2(lam, 10.0 - 1e-6)
    mpe_just_above = _mpe_irradiance_wpm2(lam, 10.0 + 1e-6)
    assert mpe_just_below == pytest.approx(mpe_just_above, rel=0.01)


def test_mpe_band_boundary_at_1400nm() -> None:
    """λ = 1.400 µm sits at the Band A / Band B boundary. The code uses
    `<=` for Band A, so 1.400 µm exactly takes the Band A branch;
    1.400 µm + 1 pm takes Band B. The MPE values across the boundary
    are expected to DIFFER (Band B is eye-safer, larger MPE) — this is
    the ANSI-prescribed step, not a bug. Test guards the direction."""
    t = 1.0
    mpe_band_a = _mpe_irradiance_wpm2(1.400e-6, t)
    mpe_band_b = _mpe_irradiance_wpm2(1.400e-6 + 1e-12, t)
    # Band B MPE is much larger (retinal hazard ends at 1.4 µm).
    assert mpe_band_b > mpe_band_a * 10.0


def test_mpe_band_a_chronic_value_1e_3_wpcm2() -> None:
    """The chronic Band A MPE is pinned at 1.0 mW/cm² = 10 W/m² — this
    is the number the user sees in the UI at t_exp > 10 s and must never
    drift."""
    mpe = _mpe_irradiance_wpm2(1.07e-6, 100.0)
    assert mpe == pytest.approx(10.0, rel=1e-12)


def test_mpe_band_b_chronic_value_0_1_wpcm2() -> None:
    """The chronic Band B MPE is pinned at 0.1 W/cm² = 1000 W/m²."""
    mpe = _mpe_irradiance_wpm2(1.55e-6, 100.0)
    assert mpe == pytest.approx(1000.0, rel=1e-12)


def test_mpe_rejects_wavelength_below_band_a() -> None:
    """λ < 0.400 µm is out of scope and must raise."""
    with pytest.raises(ValueError, match="Band A lower edge"):
        _mpe_irradiance_wpm2(0.3e-6, 0.25)


# ---------------------------------------------------------------------------
# _classify (ANSI Z136.1 / IEC 60825-1 power-class enumeration)
# ---------------------------------------------------------------------------


def test_classify_class_4_above_half_watt() -> None:
    """HEL ≫ 500 mW → Class 4 always. Every realistic user input in
    Panel A lands here."""
    assert _classify(3000.0) == "Class 4"
    assert _classify(1.0) == "Class 4"
    # Strictly > 0.5 W branch.
    assert _classify(0.5 + 1e-9) == "Class 4"


def test_classify_class_3b_band() -> None:
    """(0.005, 0.5] W is Class 3B. The code uses `> 0.5` for Class 4,
    so 0.5 W exactly is Class 3B."""
    assert _classify(0.5) == "Class 3B"
    assert _classify(0.1) == "Class 3B"
    assert _classify(0.005 + 1e-9) == "Class 3B"


def test_classify_class_3r_band() -> None:
    """(0.001, 0.005] W is Class 3R."""
    assert _classify(0.005) == "Class 3R"
    assert _classify(0.003) == "Class 3R"
    assert _classify(0.001 + 1e-9) == "Class 3R"


def test_classify_class_1m_band() -> None:
    """(0.00039, 0.001] W is Class 1M."""
    assert _classify(0.001) == "Class 1M"
    assert _classify(0.0005) == "Class 1M"
    assert _classify(0.00039 + 1e-9) == "Class 1M"


def test_classify_class_1_below_threshold() -> None:
    """P0 ≤ 0.39 mW is Class 1 (eye-safe under all viewing conditions)."""
    assert _classify(0.00039) == "Class 1"
    assert _classify(1e-6) == "Class 1"
    assert _classify(0.0) == "Class 1"
