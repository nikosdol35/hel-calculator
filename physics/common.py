"""Shared validation helpers used by every physics module.

Pure functions, no state, no side effects. Signatures match ARCHITECTURE.md
§4.3 contract. Only helpers needed for implemented modules are present;
the remaining ARCH §4.3 helpers (validate_enum, interp_log_space) land
alongside their first consuming module."""

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
