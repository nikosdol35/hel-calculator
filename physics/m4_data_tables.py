"""Data tables consumed by physics/m4_atmosphere.py and shared by other
modules that need the SPEC §3 validated-wavelength set.

Scope note: only VALIDATED_WAVELENGTHS_M is populated in the M1 commit
because that is the only constant M1's wavelength-check path needs.
ALPHA_MOL_ABSORPTION_1_PER_KM and ALPHA_MOL_SCATTERING_1_PER_KM
(ARCHITECTURE.md §7.1) land in the M4 commit alongside their module."""


VALIDATED_WAVELENGTHS_M = (1.06e-6, 1.07e-6, 1.55e-6, 2.05e-6)
