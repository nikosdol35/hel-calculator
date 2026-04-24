"""M5 Cn² path integral — numerical-methods validation.

Package 3 Layer 3.3 per `validation/README.md` and
`validation/methods/m5_r0_integral.md`. These tests exercise the
*numerics* of `physics/m5_turbulence.py`'s path integral independently
of SPEC §3 M5's physics validation cases:

  - 3.3.1 Closed-form 3/8 identity on the constant-Cn² branch at
          machine precision.
  - 3.3.3 Grid-refinement: tighten scipy.integrate.quad epsrel to
          1e-12; result changes < 1e-6.
  - 3.3.4 Edge cases: near-minimum (50 m) and near-maximum (50 km)
          slant range; integral monotone in L, finite, positive.

References:
- Fried 1966, *J. Opt. Soc. Am.* 56, 1372 — 5/3 spherical weighting.
- Andrews & Phillips 2005, §6 and §12 — spherical r₀ and HV-5/7.
- Piessens et al. 1983, *QUADPACK* — the algorithm scipy.quad wraps.
- SPEC §3 M5.
"""

from __future__ import annotations

import math

import pytest
from scipy.integrate import quad

from physics import m5_turbulence


def _constant_inputs(**overrides) -> dict:
    """A minimal set of valid M5 inputs on the constant-Cn² branch.
    SPEC §3 M5 canonical uniform-profile case at R=5 km, λ=1.07 µm."""
    base = {
        "cn2_model": "constant",
        "Cn2_value": 1.0e-14,
        "Cn2_ground": 1.7e-14,    # unused on constant branch but _validate_inputs checks the range
        "v_HV": 21.0,             # unused on constant branch but _validate_inputs checks the range
        "wavelength": 1.07e-6,
        "R_slant": 5000.0,
        "H_e": 0.0,
        "H_t": 0.0,
    }
    base.update(overrides)
    return base


def _hv_inputs(**overrides) -> dict:
    """SPEC §3 M5.5 canonical HV-5/7 case (ground-level slant)."""
    base = {
        "cn2_model": "HV_5_7",
        "Cn2_value": 1.0e-14,
        "Cn2_ground": 1.7e-14,
        "v_HV": 21.0,
        "wavelength": 1.07e-6,
        "R_slant": 5000.0,
        "H_e": 0.0,
        "H_t": 0.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 3.3.1 — Closed-form 3/8 identity on the constant-Cn² branch
# ---------------------------------------------------------------------------


def test_m5_numerics_constant_3_8_identity() -> None:
    """On the `cn2_model='constant'` branch, Cn2_integrated must equal
    Cn² · L · 3/8 at machine precision.

    The `3/8` comes from the closed-form definite integral
        ∫₀^L (z/L)^(5/3) dz = L · 3/8
    which is algebraic, not numerical; any drift here would mean the
    exponent (should be 5/3) or the normalisation (should be 3/8)
    regressed. CLAUDE §7.1 pins both together via the spherical/plane
    r₀ ratio — this test adds a direct single-float-multiply guard.
    """
    inputs = _constant_inputs()
    result = m5_turbulence.compute(inputs)

    expected = inputs["Cn2_value"] * inputs["R_slant"] * (3.0 / 8.0)
    # rel = 1e-12: this is one float multiply. Any drift is float64
    # noise; tighter would catch the multiplication's rounding itself.
    # Looser would hide a regression in the exponent or the 3/8 factor.
    assert result["Cn2_integrated"] == pytest.approx(expected, rel=1e-12), (
        f"Constant-Cn² branch Cn2_integrated={result['Cn2_integrated']:.6e} "
        f"disagrees with closed-form Cn²·L·3/8={expected:.6e} at machine "
        f"precision — the 5/3 exponent or 3/8 normalisation has drifted "
        f"(CLAUDE §7.1 invariant; SPEC §3 M5)"
    )


# ---------------------------------------------------------------------------
# 3.3.3 — Grid-refinement stability under tightened quad epsrel
# ---------------------------------------------------------------------------


def test_m5_numerics_hv_grid_refinement() -> None:
    """The HV-5/7 branch uses scipy.integrate.quad at default epsrel
    (1.49e-8). Tightening to epsrel=1e-12 must change Cn2_integrated by
    less than 1 ppm (1e-6 relative). A larger delta would mean default-
    tolerance quadrature is silently leaking error inside the SPEC
    §3 M5 2 % physics envelope.

    The test manually re-integrates the HV-5/7 integrand with the
    tightened tolerance and compares to the value produced by
    `m5_turbulence.compute` at the default. Both should agree to far
    tighter than the SPEC 2 % bound.
    """
    inputs = _hv_inputs()
    result = m5_turbulence.compute(inputs)

    # Re-implement the HV-5/7 integrand locally and re-integrate with a
    # very tight tolerance. This must match the code in m5_turbulence.py
    # line-for-line — any drift is caught by the agreement assertion.
    H_e = inputs["H_e"]
    H_t = inputs["H_t"]
    v_HV = inputs["v_HV"]
    Cn2_ground = inputs["Cn2_ground"]
    L = inputs["R_slant"]

    def cn2_at_altitude(h: float) -> float:
        if h < 0.0:
            h = 0.0
        high_alt = 0.00594 * (v_HV / 27.0) ** 2 * (1.0e-5 * h) ** 10 * math.exp(-h / 1000.0)
        boundary = 2.7e-16 * math.exp(-h / 1500.0)
        ground = Cn2_ground * math.exp(-h / 100.0)
        return high_alt + boundary + ground

    def integrand(z: float) -> float:
        h = H_e + (H_t - H_e) * (z / L)
        return cn2_at_altitude(h) * (z / L) ** (5.0 / 3.0)

    tight_integral, _ = quad(integrand, 0.0, L, epsabs=1.0e-30, epsrel=1.0e-12)

    # rel = 1e-6: seven decades tighter than the SPEC 2 % physics bound.
    # Default quad epsrel is 1.49e-8 — the gap between that and the
    # re-run at 1e-12 must be well below 1e-6, otherwise the default
    # quadrature is leaking measurable error.
    assert result["Cn2_integrated"] == pytest.approx(tight_integral, rel=1e-6), (
        f"HV-5/7 integral at default epsrel={result['Cn2_integrated']:.6e} "
        f"disagrees with epsrel=1e-12 re-run={tight_integral:.6e} by more "
        f"than 1 ppm — scipy.integrate.quad default tolerance is leaking "
        f"error inside the SPEC §3 M5 2 % physics envelope"
    )


# ---------------------------------------------------------------------------
# 3.3.4 — Edge cases: short and long path
# ---------------------------------------------------------------------------


def test_m5_numerics_edge_case_short_path() -> None:
    """At R_slant = 50 m (minimum of SPEC §3 M5 input range), the HV-5/7
    integrand is dominated by the ground layer `Cn2_ground·exp(-h/100)`
    since the slant path spans only tens of metres of altitude. The
    integral must be finite, positive, and yield r0_sph larger than
    the same profile at 5 km (shorter paths → weaker accumulation).
    """
    inputs_short = _hv_inputs(R_slant=50.0)
    inputs_long = _hv_inputs(R_slant=5000.0)

    short = m5_turbulence.compute(inputs_short)
    long = m5_turbulence.compute(inputs_long)

    # Finiteness and sign — the numerics must not produce NaN/negative
    # at the short-path boundary.
    assert math.isfinite(short["Cn2_integrated"]) and short["Cn2_integrated"] > 0
    assert math.isfinite(short["r0_sph"]) and short["r0_sph"] > 0
    assert math.isfinite(short["w_turb"]) and short["w_turb"] > 0

    # Monotonicity: longer path accumulates more Cn² => larger integral,
    # smaller r0. Strict inequality expected since the ground layer is
    # non-zero at every altitude along both paths.
    assert short["Cn2_integrated"] < long["Cn2_integrated"]
    assert short["r0_sph"] > long["r0_sph"]


def test_m5_numerics_edge_case_long_path() -> None:
    """At R_slant = 50 km (maximum of SPEC §3 M5 input range) with
    H_e = 0, H_t = 5 km, the slant path crosses the HV high-altitude
    turn-on regime (where `(1e-5·h)^10` becomes non-negligible near
    h ≈ 10 km but is still small at 5 km). The integral must remain
    finite and positive, and the monotonicity check below must hold
    for at-altitude paths of equal length.

    The naive intuition "longer path → more turbulence" does NOT hold
    against the short-low-altitude reference: the HV profile decays
    exponentially with scale heights 1000 m and 1500 m, so a long path
    that climbs to 5 km traverses mostly high-altitude low-Cn² air,
    and the spherical-wave weighting `(z/L)^(5/3)` further suppresses
    the near-emitter high-turbulence contribution — making the long-
    path integrated Cn² SMALLER than the short-near-ground reference.
    The test validates this correctly-counterintuitive behaviour is
    preserved (any code change that made the long path produce a
    larger integrated value would be a regression from the HV profile).
    """
    inputs_ref = _hv_inputs(R_slant=5000.0, H_t=500.0)
    inputs_long = _hv_inputs(R_slant=50_000.0, H_t=5000.0)

    ref = m5_turbulence.compute(inputs_ref)
    long = m5_turbulence.compute(inputs_long)

    # Finiteness at the long-path boundary — no NaN from the altitude
    # polynomial term at h up to 5 km.
    assert math.isfinite(long["Cn2_integrated"]) and long["Cn2_integrated"] > 0
    assert math.isfinite(long["r0_sph"]) and long["r0_sph"] > 0
    assert math.isfinite(long["w_turb"]) and long["w_turb"] > 0

    # HV profile is exponentially dominated at low altitude; a long
    # climbing path sees mostly low-Cn² air. The weighted integral is
    # smaller, so r0 is larger on the long path than on the short
    # boundary-layer reference. This is the physically correct ordering.
    assert long["Cn2_integrated"] < ref["Cn2_integrated"]
    assert long["r0_sph"] > ref["r0_sph"]

    # But w_turb = 2L/(k·r0) scales with path length, so the longer
    # path still produces a wider turbulence-broadened spot despite
    # the smaller integrated Cn². Order-of-magnitude check.
    assert long["w_turb"] > ref["w_turb"]
