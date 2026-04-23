"""Data tables consumed by physics/m4_atmosphere.py and shared by other
modules that need the SPEC §3 validated-wavelength set.

α_mol tables are sea-level, mid-latitude summer, 60% RH baseline per
SPEC §3 M4. Values are HIGH UNCERTAINTY engineering placeholders per
SPEC §10.1 — refine against HITRAN/MODTRAN before any formal trade
study. RH scaling for absorption is linear: α(RH) = α(0.60)·(RH/0.60).
Scattering is RH-independent to first order.
"""


VALIDATED_WAVELENGTHS_M = (1.06e-6, 1.07e-6, 1.55e-6, 2.05e-6)


ALPHA_MOL_ABSORPTION_1_PER_KM = {
    1.06e-6: 0.045,
    1.07e-6: 0.065,
    1.55e-6: 0.190,
    2.05e-6: 0.490,
}


ALPHA_MOL_SCATTERING_1_PER_KM = {
    1.06e-6: 0.005,
    1.07e-6: 0.005,
    1.55e-6: 0.010,
    2.05e-6: 0.010,
}
