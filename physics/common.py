"""Shared validation helpers used by every physics module.

Pure functions, no state, no side effects. Signatures match ARCHITECTURE.md
§4.3 contract. Only helpers needed for implemented modules are present;
the remaining ARCH §4.3 helper (validate_enum) lands alongside its first
consuming module (M5)."""

import math

from physics.m4_data_tables import VALIDATED_WAVELENGTHS_M


def validate_positive(value: float, name: str) -> None:
    """Raise ValueError if value is not strictly positive."""
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value}")


def validate_range(value: float, name: str, lo: float, hi: float) -> None:
    """Raise ValueError if value is outside the inclusive [lo, hi] range."""
    if not (lo <= value <= hi):
        raise ValueError(f"{name} must be in [{lo}, {hi}], got {value}")


def wavelength_in_validated_set(wavelength_m: float, tol_nm: float = 5.0) -> bool:
    """True iff wavelength is within tol_nm of one of the four SPEC §3
    validated wavelengths (1.06, 1.07, 1.55, 2.05 µm). Default tolerance
    is 5 nm per ARCHITECTURE.md §4.3."""
    tol_m = tol_nm * 1e-9
    return any(abs(wavelength_m - ref) <= tol_m for ref in VALIDATED_WAVELENGTHS_M)


def interp_log_space(x: float, x_table: list[float], y_table: list[float]) -> float:
    """Log-log linear interpolation between tabulated values.

    Both x and y values must be strictly positive. x_table must be
    monotonically increasing. For x inside [x_table[0], x_table[-1]],
    linearly interpolates in (log(x), log(y)) space. For x outside that
    range, clamps to the nearest endpoint (caller flags the extrapolation).

    Per ARCHITECTURE.md §4.3 contract."""
    if len(x_table) != len(y_table) or len(x_table) < 2:
        raise ValueError("x_table and y_table must be same length ≥ 2")

    if x <= x_table[0]:
        return y_table[0]
    if x >= x_table[-1]:
        return y_table[-1]

    for i in range(len(x_table) - 1):
        lx, rx = x_table[i], x_table[i + 1]
        if lx <= x <= rx:
            ly, ry = y_table[i], y_table[i + 1]
            t = (math.log(x) - math.log(lx)) / (math.log(rx) - math.log(lx))
            return math.exp(math.log(ly) + t * (math.log(ry) - math.log(ly)))

    raise ValueError(f"x={x} not bracketed by x_table; table not monotonic?")
