"""Material property tables for M8 burn-through.

Seven materials per CLAUDE §7.3 — adding an eighth requires a SPEC
update plus a new entry here plus a new test case. Every A_λ value
carries HIGH UNCERTAINTY (SPEC §10.2) and M8 flags the default-lookup
path accordingly; the user is expected to override with measured or
program-specific values when available.

Sources:
  - Metals (Al): ASM Handbook Vol. 2.
  - CFRP/GFRP: manufacturer datasheets (Hexcel 8552, Toray T700, OCV
    E-glass). v1 engineering averages — vendor variance is ±20–40%.
  - Polycarbonate, ABS, EPP: ASM Engineered Plastics Handbook; Matweb.
  - LiPo: Sandia Labs reports (SAND2014-18253, SAND2018-12007) for
    vent onset temperature and bulk thermal-cell averages.
"""


# IR emissivity — SPEC §3 M8 says 0.85 for all materials as a default
# (relatively minor effect below ~1000 K; Al dominant contributor where
# this matters is typically modeled separately in higher-fidelity work).
EMISSIVITY_IR_DEFAULT = 0.85

# Stefan-Boltzmann constant, W/(m²·K⁴).
SIGMA_SB = 5.670374419e-8


# Each entry: ρ [kg/m³], c_p [J/(kg·K)], k [W/(m·K)], T_fail [K],
# L_f [J/kg] (None for decomposition/vent modes), failure_mode [str].
MATERIAL_PROPERTIES: dict[str, dict] = {
    "anodized_Al": {
        "rho": 2700.0,
        "c_p": 900.0,
        "k": 200.0,
        "T_fail": 933.0,       # melt point, K
        "L_f": 397_000.0,      # J/kg (397 kJ/kg)
        "failure_mode": "melt",
    },
    "CFRP": {
        "rho": 1600.0,
        "c_p": 1000.0,
        "k": 7.0,
        "T_fail": 600.0,
        "L_f": None,
        "failure_mode": "decomposition",
    },
    "GFRP": {
        "rho": 1900.0,
        "c_p": 800.0,
        "k": 0.4,
        "T_fail": 600.0,
        "L_f": None,
        "failure_mode": "decomposition",
    },
    "polycarbonate": {
        "rho": 1200.0,
        "c_p": 1200.0,
        "k": 0.2,
        "T_fail": 700.0,
        "L_f": None,
        "failure_mode": "decomposition",
    },
    "ABS": {
        "rho": 1050.0,
        "c_p": 1400.0,
        "k": 0.17,
        "T_fail": 670.0,
        "L_f": None,
        "failure_mode": "decomposition",
    },
    "EPP_foam": {
        "rho": 30.0,
        "c_p": 1900.0,
        "k": 0.04,
        "T_fail": 620.0,       # ignition onset
        "L_f": None,
        "failure_mode": "decomposition",
    },
    "LiPo": {
        "rho": 1800.0,
        "c_p": 1000.0,
        "k": 0.5,
        "T_fail": 420.0,       # vent onset per Sandia
        "L_f": None,
        "failure_mode": "vent",
    },
}

MATERIALS = tuple(MATERIAL_PROPERTIES.keys())


# Absorptivity A_λ, tabulated at SPEC §3 validated wavelengths (m).
# Linear interpolation in wavelength between tabulated points (NOT
# log-log like M4 — A_λ is already a bounded, near-linear quantity).
A_LAMBDA_TABLE_WAVELENGTHS_M = (1.06e-6, 1.07e-6, 1.55e-6, 2.05e-6)

A_LAMBDA_TABLE: dict[str, tuple[float, float, float, float]] = {
    "anodized_Al":    (0.30, 0.30, 0.25, 0.20),
    "CFRP":           (0.85, 0.85, 0.85, 0.85),
    "GFRP":           (0.40, 0.40, 0.45, 0.55),
    "polycarbonate":  (0.10, 0.10, 0.30, 0.60),
    "ABS":            (0.70, 0.70, 0.75, 0.85),
    "EPP_foam":       (0.50, 0.50, 0.55, 0.70),
    "LiPo":           (0.30, 0.30, 0.35, 0.45),
}
