"""Hand-curated formula + explanation records for the math tab.

Per the plan ``docs/math_tab_plan_2026-04-25.md`` §9, every orchestrator
output key gets a ``MetricEntry`` record carrying its formula in LaTeX,
plain-language explanations (short + full), citation chain, code
reference, dependency graph, and provenance flags.

The content is hand-typed against ``physics/m*.py`` and the
``validation/derivations/`` markdown — there is no auto-extraction. A
coverage test in ``tests/test_math_tab.py`` enforces that every output
key the orchestrator emits has a record here, and a LaTeX-validity test
checks for balanced braces in every ``formula_latex`` string.

PR 1 of the math-tab roll-out covers M1, M2, M3 (9 numeric entries).
PRs 2 and 3 add the remaining 32 numeric entries plus the 4 categorical
verdicts; PR 4 adds the constants table and worked example; PR 5 adds
the Markdown export.

Distinguishing the two dependency fields, per plan §9:

  * ``formula_dependencies`` — *intermediate* values the formula
    references (other orchestrator output keys). Used for the symbolic
    substitution rendered in Full view ("with current values: ...").
  * ``sensitivity_inputs`` — *raw user input keys* to perturb by ±10 %
    when the §7.4 sensitivity bar runs. Independent from
    ``formula_dependencies`` because we want to attribute the metric's
    sensitivity to user-controllable knobs, not to opaque intermediates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ProvenanceFlag(Enum):
    """Trust/origin badges shown next to a metric in Full view.

    Per plan §7.5 these are the three signals the validation campaign
    surfaces: an audit-pinned formula, a HIGH-UNCERTAINTY value, and an
    independently-replicated metric.
    """

    CLAUDE_71_INVARIANT = "claude_71"
    HIGH_UNCERTAINTY = "high_uncertainty"
    REPLICATED = "replicated"


@dataclass(frozen=True)
class MetricEntry:
    """A row in the math tab, one per orchestrator output key.

    Field semantics are documented per attribute. The dataclass is
    frozen so accidental mutation at render time is caught; the math
    tab is a read-only view.
    """

    # --- Identification --------------------------------------------------
    key: str                       # orchestrator output key, e.g. "I_peak"
    module: str                    # short module tag, e.g. "M7"
    display_name: str              # human-readable, e.g. "Peak irradiance"
    symbol_latex: str              # for inline use, e.g. r"I_\text{peak}"

    # --- Units. Formulas are in SI (matches the implementation); values
    # are scaled for display by the existing _DISPLAY_SCALE in
    # ui/outputs.py. The display unit itself is NOT stored here — the
    # renderer pulls it from ``ui.labels.output_unit(key)`` so the math
    # tab can never drift from what the per-tab metric cards show.
    unit_si: str                   # raw SI unit, e.g. "W/m^2"

    # --- Classification flags --------------------------------------------
    is_categorical: bool = False   # True for failure_mode, laser_class, …
    is_solver_based: bool = False  # True for tau_BT, T_surface_peak, E_delivered
    is_iterated: bool = False      # True for S_TB, w_bloom, N_D, w_total

    # --- Math content (None for categorical) -----------------------------
    formula_latex: str | None = None
    formula_text: str | None = None     # ASCII fallback for export / search
    formula_dependencies: tuple[str, ...] = field(default_factory=tuple)
    sensitivity_inputs: tuple[str, ...] = field(default_factory=tuple)

    # --- Plain-language content -----------------------------------------
    explanation_short: str = ""    # 1-2 sentence "what it means"
    explanation_full: str = ""     # 3-5 sentence expert version

    # --- Provenance ------------------------------------------------------
    citation: str = ""             # "Siegman 1986 §17 / SPEC §3 M7 / CLAUDE §7.1"
    code_ref: str = ""             # "physics/m7_spot_pib.py" or
                                   # "physics/m7_spot_pib.py::compute"
    derivation_link: str = ""      # "validation/derivations/m7_spot.md"
    provenance: tuple[ProvenanceFlag, ...] = field(default_factory=tuple)
    assumptions: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Module-level metadata (used by the renderer for section headers and the
# quick-jump index).
# ---------------------------------------------------------------------------

MODULE_TITLES: dict[str, str] = {
    "M1":  "Laser source",
    "M2":  "Power link (beam director)",
    "M3":  "Engagement geometry",
    "M4":  "Atmosphere",
    "M5":  "Atmospheric turbulence",
    "M6":  "Thermal blooming",
    "M7":  "Spot size and power-in-the-bucket",
    "M8":  "Burn-through",
    "M9":  "Eye-safety / NOHD",
    "M10": "Power and thermal resources",
    "ORC": "Orchestrator (M6↔M7 iteration)",
}

# The render order. PR 1 only ships M1, M2, M3; the remaining modules
# are placeholders that the renderer will skip (no entries) until
# subsequent PRs land their content.
MODULE_ORDER: tuple[str, ...] = (
    "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10", "ORC",
)


# ---------------------------------------------------------------------------
# Metric entries. PR 1 — modules M1, M2, M3 (9 numeric entries).
#
# Citations follow the "Source-author Year §section / SPEC §3 Mn / [optional
# CLAUDE §7.1 / SPEC §10 flag]" convention so a reader can trace each
# formula to (a) its primary literature source, (b) its SPEC contract
# entry, (c) any audit-sensitivity flag.
#
# code_ref is file-only or file::function; line numbers drift, so per
# plan §11 we don't pin them.
#
# formula_text is the ASCII fallback used by Markdown export and the
# search filter. Keep it close to the Python implementation so
# experienced readers can map it line-for-line back to physics/m*.py.
# ---------------------------------------------------------------------------


def _entries() -> dict[str, MetricEntry]:
    """Build the MATH_CONTENT dict. Wrapped in a function so the file
    parses fast at import time and so the dict is freshly constructed
    if a hot-reload tool re-imports it."""
    rows: list[MetricEntry] = []

    # =========================================================================
    # M1 — Laser source
    # =========================================================================

    rows.append(MetricEntry(
        key="theta_diff",
        module="M1",
        display_name="Diffraction-limited divergence",
        symbol_latex=r"\theta_\text{diff}",
        unit_si="rad",
        formula_latex=r"\theta_\text{diff} = \dfrac{M^{2} \cdot 4 \lambda}{\pi \, D}",
        formula_text="theta_diff = M^2 * 4 * lambda / (pi * D)",
        formula_dependencies=(),  # all inputs are user-supplied
        sensitivity_inputs=("M2", "wavelength", "D"),
        explanation_short=(
            "How fast a perfect beam spreads as it leaves the aperture. "
            "Sets the ultimate floor on spot size at any range — even a "
            "flawless system cannot do better than this."
        ),
        explanation_full=(
            "Full-angle 1/e² divergence in the Siegman convention. The factor "
            "of 4 (rather than 2) converts from beam radius to beam diameter. "
            "M² (the beam-quality factor) inflates this by however much the "
            "real beam departs from the ideal Gaussian: M² = 1 is "
            "diffraction-limited; M² = 2 doubles the divergence."
        ),
        citation="Siegman 1986 §17 / SPEC §3 M1",
        code_ref="physics/m1_laser_source.py::compute",
        derivation_link="validation/derivations/m1_source.md",
        provenance=(),
        assumptions=(
            "Gaussian beam (TEM_00 mode); the M² formalism captures any "
            "departure from the ideal as a single multiplier.",
        ),
    ))

    rows.append(MetricEntry(
        key="w0",
        module="M1",
        display_name="Launch beam radius",
        symbol_latex=r"w_{0}",
        unit_si="m",
        formula_latex=r"w_{0} = \dfrac{D}{2}",
        formula_text="w0 = D / 2",
        formula_dependencies=(),
        sensitivity_inputs=("D",),
        explanation_short=(
            "The 1/e² beam radius right at the laser exit aperture, taken to "
            "fill the aperture exactly. Half of the aperture diameter."
        ),
        explanation_full=(
            "v1 assumes the beam fills the exit aperture (a typical "
            "engineering simplification for HEL systems where the aperture "
            "diameter is the physical knob the operator changes). A real "
            "system might under-fill the aperture; that case is out of v1 "
            "scope."
        ),
        citation="SPEC §3 M1",
        code_ref="physics/m1_laser_source.py::compute",
        derivation_link="validation/derivations/m1_source.md",
        provenance=(),
        assumptions=(
            "Beam fully fills the exit aperture — under-filling not modelled "
            "in v1.",
        ),
    ))

    rows.append(MetricEntry(
        key="zR",
        module="M1",
        display_name="Rayleigh range",
        symbol_latex=r"z_{R}",
        unit_si="m",
        formula_latex=r"z_{R} = \dfrac{\pi \, w_{0}^{\,2}}{\lambda}",
        formula_text="zR = pi * w0^2 / lambda",
        formula_dependencies=("w0",),
        sensitivity_inputs=("D", "wavelength"),
        explanation_short=(
            "Distance over which a Gaussian beam stays roughly the same size "
            "as it was at the launch aperture. Beyond this, the beam is "
            "spreading non-trivially with distance."
        ),
        explanation_full=(
            "Computed in the M² = 1 reference form; M² appears separately in "
            "the propagation law for spot size at the target. Closer than zR "
            "the beam is essentially collimated; far past zR it has fully "
            "entered the diffraction-spreading regime."
        ),
        citation="Siegman 1986 §17 / SPEC §3 M1",
        code_ref="physics/m1_laser_source.py::compute",
        derivation_link="validation/derivations/m1_source.md",
        provenance=(),
        assumptions=(),
    ))

    rows.append(MetricEntry(
        key="I_exit",
        module="M1",
        display_name="Exit-aperture peak irradiance",
        symbol_latex=r"I_\text{exit}",
        unit_si="W/m^2",
        formula_latex=r"I_\text{exit} = \dfrac{2 \, P_{0}}{\pi \, w_{0}^{\,2}}",
        formula_text="I_exit = 2 * P0 / (pi * w0^2)",
        formula_dependencies=("w0",),
        sensitivity_inputs=("P0", "D"),
        explanation_short=(
            "Brightest point of the beam right at the laser exit aperture, "
            "before it has had a chance to spread or lose anything to the "
            "atmosphere."
        ),
        explanation_full=(
            "The factor of 2 in the numerator is the Gaussian peak — for a "
            "circular Gaussian beam the on-axis intensity is twice the "
            "average over the 1/e² disk. This is one of the eleven "
            "audit-sensitive invariants pinned in CLAUDE §7.1."
        ),
        citation="Siegman 1986 §17 / SPEC §3 M1 / CLAUDE §7.1",
        code_ref="physics/m1_laser_source.py::compute",
        derivation_link="validation/derivations/m1_source.md",
        provenance=(ProvenanceFlag.CLAUDE_71_INVARIANT,
                    ProvenanceFlag.REPLICATED),
        assumptions=(),
    ))

    # =========================================================================
    # M2 — Power link (beam director)
    # =========================================================================

    rows.append(MetricEntry(
        key="P_exit",
        module="M2",
        display_name="Power leaving the beam director",
        symbol_latex=r"P_\text{exit}",
        unit_si="W",
        formula_latex=r"P_\text{exit} = \eta_\text{opt} \cdot P_{0}",
        formula_text="P_exit = eta_opt * P0",
        formula_dependencies=(),  # both are user inputs
        sensitivity_inputs=("eta_opt", "P0"),
        explanation_short=(
            "How much of the laser's output power survives the optical train "
            "(mirrors, beam-shaping optics, the director itself) and actually "
            "leaves the system pointed at the target."
        ),
        explanation_full=(
            "The optical-train transmission η_opt is a single user input that "
            "lumps together every loss between the laser head and the open "
            "aperture (Fresnel losses, dichroic splits, contamination on "
            "mirrors, etc.). Typical values are 0.7 to 0.9; the input is "
            "constrained to [0.5, 0.99] in v1."
        ),
        citation="SPEC §3 M2",
        code_ref="physics/m2_beam_director.py::compute",
        derivation_link="validation/derivations/m2_power_link.md",
        provenance=(),
        assumptions=(
            "Lumped optical-train transmission; v1 does not break out "
            "individual surface losses.",
        ),
    ))

    # =========================================================================
    # M3 — Engagement geometry
    # =========================================================================

    rows.append(MetricEntry(
        key="R_slant",
        module="M3",
        display_name="Slant range",
        symbol_latex=r"R_\text{slant}",
        unit_si="m",
        formula_latex=r"R_\text{slant} = R",
        formula_text="R_slant = R   (user input passed through; see notes)",
        formula_dependencies=(),
        sensitivity_inputs=("R",),
        explanation_short=(
            "The straight-line distance from the laser emplacement to the "
            "target. Always at least as long as the horizontal (ground) "
            "range — the difference grows when the two altitudes differ."
        ),
        explanation_full=(
            "v1 simplification per the geometry contract: the user-input "
            "range R is the slant range directly (the user is expected to "
            "supply the line-of-sight distance, not the ground distance). "
            "The horizontal-range R_h is then derived below by Pythagoras. "
            "The validator rejects geometries where the altitude difference "
            "exceeds R (a clearly infeasible engagement)."
        ),
        citation="SPEC §3 M3",
        code_ref="physics/m3_geometry.py::compute",
        derivation_link="validation/derivations/m3_director.md",
        provenance=(),
        assumptions=(
            "User-input R is taken to be the slant (line-of-sight) range, "
            "not the horizontal ground range.",
        ),
    ))

    rows.append(MetricEntry(
        key="R_h",
        module="M3",
        display_name="Horizontal (ground) range",
        symbol_latex=r"R_{h}",
        unit_si="m",
        formula_latex=(
            r"R_{h} = \sqrt{R_\text{slant}^{\,2} - (H_t - H_e)^{\,2}}"
        ),
        formula_text="R_h = sqrt(R_slant^2 - (H_t - H_e)^2)",
        formula_dependencies=("R_slant",),
        sensitivity_inputs=("R", "H_e", "H_t"),
        explanation_short=(
            "Distance the target is from the laser measured along the ground, "
            "ignoring altitude. Useful when the target is close to overhead."
        ),
        explanation_full=(
            "Pythagorean decomposition of the slant range into a horizontal "
            "and a vertical leg. When the target altitude equals the "
            "emplacement altitude, R_h equals R_slant; for steep elevations "
            "(high target, near overhead) R_h is much shorter than R_slant."
        ),
        citation="SPEC §3 M3",
        code_ref="physics/m3_geometry.py::compute",
        derivation_link="validation/derivations/m3_director.md",
        provenance=(),
        assumptions=(),
    ))

    rows.append(MetricEntry(
        key="elevation_angle",
        module="M3",
        display_name="Elevation angle",
        symbol_latex=r"\varepsilon",
        unit_si="rad",
        formula_latex=(
            r"\varepsilon = \arctan\!\left(\dfrac{H_t - H_e}{R_{h}}\right)"
        ),
        formula_text="elevation_angle = arctan((H_t - H_e) / R_h)",
        formula_dependencies=("R_h",),
        sensitivity_inputs=("H_e", "H_t", "R"),
        explanation_short=(
            "The angle the laser must point above horizontal to hit the "
            "target. Zero for level engagements; positive when the target "
            "is above the emplacement."
        ),
        explanation_full=(
            "Reported in degrees in the UI. For a target at sea level engaged "
            "from a tower, the elevation is slightly negative (the beam "
            "depresses); for an air target above a ground emplacement it is "
            "positive. The numerical inverse-tangent uses ``math.atan2`` so "
            "the limit at R_h = 0 (target directly overhead) is well-defined."
        ),
        citation="SPEC §3 M3",
        code_ref="physics/m3_geometry.py::compute",
        derivation_link="validation/derivations/m3_director.md",
        provenance=(),
        assumptions=(
            "Flat-Earth geometry; Earth-curvature corrections are not "
            "applied at v1's slant ranges (≤ 50 km).",
        ),
    ))

    rows.append(MetricEntry(
        key="available_dwell",
        module="M3",
        display_name="Available dwell window",
        symbol_latex=r"t_\text{dwell}",
        unit_si="s",
        formula_latex=(
            r"t_\text{dwell} = "
            r"\dfrac{2 \, R \, \tan(\text{FOV}/2)}{v_\text{tgt}}"
        ),
        formula_text="t_dwell = 2 * R * tan(FOV/2) / v_tgt   [FOV = 5°]",
        formula_dependencies=(),
        sensitivity_inputs=("R", "v_tgt"),
        explanation_short=(
            "How long the target stays inside the engagement basket given a "
            "5° default field of view and the target's velocity. The "
            "engagement is feasible when this exceeds the time to "
            "burn-through."
        ),
        explanation_full=(
            "First-order geometric heuristic, deliberately simple: the target "
            "moves perpendicular to the line of sight at v_tgt and stays in "
            "the FOV for the time it takes to cross the basket diameter. v1 "
            "uses a fixed 5° FOV — a full tracker-dependent model (slew "
            "limits, target maneuver, line-of-sight masking) is deferred to "
            "v2 per the deferred-items closeout."
        ),
        citation="SPEC §3 M3 / SPEC §10.5 (HIGH UNCERTAINTY)",
        code_ref="physics/m3_geometry.py::compute",
        derivation_link="validation/derivations/m11_dwell.md",
        provenance=(ProvenanceFlag.HIGH_UNCERTAINTY,),
        assumptions=(
            "5° default FOV; target moves perpendicular to line-of-sight at "
            "constant v_tgt; no slew-rate, line-of-sight-masking, or "
            "multi-target prioritization model.",
        ),
    ))

    # =========================================================================
    # M4 — Atmosphere
    # =========================================================================

    rows.append(MetricEntry(
        key="alpha_mol_abs",
        module="M4",
        display_name="Molecular absorption coefficient",
        symbol_latex=r"\alpha_\text{mol,abs}",
        unit_si="1/m",
        formula_latex=(
            r"\alpha_\text{mol,abs}(\lambda, \text{RH}) = "
            r"\alpha_\text{table}(\lambda) \cdot "
            r"\dfrac{\text{RH}}{\text{RH}_\text{ref}}"
        ),
        formula_text=(
            "alpha_mol_abs = lookup(lambda) * (RH / 0.60)   "
            "[McClatchey table, log-log interp; sea-level baseline 60% RH]"
        ),
        formula_dependencies=(),
        sensitivity_inputs=("wavelength", "RH"),
        explanation_short=(
            "How strongly the air's gas molecules (mostly water vapour at "
            "near-infrared wavelengths) absorb the laser light. Looked up "
            "from a sea-level table at the chosen wavelength and scaled "
            "linearly with humidity."
        ),
        explanation_full=(
            "The table holds engineering placeholders sourced from the "
            "McClatchey AFCRL atlas at the four validated wavelengths "
            "(1.06, 1.07, 1.55, 2.05 µm). Values between table points are "
            "log-log interpolated. The linear humidity scaling against a "
            "60 %-RH baseline is a sea-level engineering simplification — "
            "for slant paths through high altitude (where humidity drops "
            "fast with altitude) this overstates absorption near the upper "
            "end of the path."
        ),
        citation="McClatchey AFCRL-TR-72-0497 1972",
        code_ref="physics/m4_atmosphere.py::compute",
        derivation_link="validation/derivations/m4_atmosphere.md",
        provenance=(ProvenanceFlag.HIGH_UNCERTAINTY,),
        assumptions=(
            "Sea-level table; linear RH scaling; wavelength interpolation "
            "in log-log space.",
            "Baseline humidity 60 % per the McClatchey reference atmosphere.",
        ),
    ))

    rows.append(MetricEntry(
        key="alpha_mol_scat",
        module="M4",
        display_name="Molecular scattering coefficient",
        symbol_latex=r"\alpha_\text{mol,scat}",
        unit_si="1/m",
        formula_latex=(
            r"\alpha_\text{mol,scat}(\lambda) = "
            r"\alpha_\text{table}(\lambda)"
        ),
        formula_text=(
            "alpha_mol_scat = lookup(lambda)   "
            "[Rayleigh-derived table; no humidity scaling]"
        ),
        formula_dependencies=(),
        sensitivity_inputs=("wavelength",),
        explanation_short=(
            "Rayleigh scattering from gas molecules — the same physics that "
            "makes the daytime sky blue, but at infrared wavelengths the "
            "effect is small (scales as 1/λ⁴)."
        ),
        explanation_full=(
            "Tabulated at the four validated wavelengths and held constant "
            "with humidity (Rayleigh scattering depends on number density, "
            "which is dominated by N₂ and O₂, not water vapour). Values "
            "are typically 5-10 × smaller than the absorption coefficient "
            "at the same wavelength, so this is a minor contributor to "
            "total atmospheric extinction in the NIR."
        ),
        citation="McClatchey AFCRL-TR-72-0497 1972",
        code_ref="physics/m4_atmosphere.py::compute",
        derivation_link="validation/derivations/m4_atmosphere.md",
        provenance=(ProvenanceFlag.HIGH_UNCERTAINTY,),
        assumptions=(
            "Sea-level table; humidity-independent.",
        ),
    ))

    rows.append(MetricEntry(
        key="alpha_aer_abs",
        module="M4",
        display_name="Aerosol absorption coefficient",
        symbol_latex=r"\alpha_\text{aer,abs}",
        unit_si="1/m",
        formula_latex=(
            r"\alpha_\text{aer,abs} = "
            r"f_\text{abs} \cdot \alpha_\text{aer,total}"
        ),
        formula_text=(
            "alpha_aer_abs = 0.05 * alpha_aer_total   "
            "[5%/95% absorption/scattering split for typical aerosols]"
        ),
        formula_dependencies=(),
        sensitivity_inputs=("V", "wavelength"),
        explanation_short=(
            "How much of the laser power the suspended particles in the "
            "atmosphere (dust, smoke, sea salt, water droplets) absorb. "
            "Set to 5 % of the total aerosol extinction; the other 95 % "
            "scatters."
        ),
        explanation_full=(
            "The total aerosol extinction is computed from the Kruse "
            "visibility formula and split between absorption and "
            "scattering using a 5 / 95 fraction typical of mixed boundary-"
            "layer aerosols. Smoke or dust-dominated atmospheres absorb a "
            "larger fraction; clean maritime aerosols absorb less. The "
            "split is an engineering default — vehicle-specific or "
            "environment-specific data should override when available."
        ),
        citation="Kruse 1962 / SPEC §3 M4",
        code_ref="physics/m4_atmosphere.py::compute",
        derivation_link="validation/derivations/m4_atmosphere.md",
        provenance=(),
        assumptions=(
            "5 % absorption / 95 % scattering split — engineering default.",
        ),
    ))

    rows.append(MetricEntry(
        key="alpha_aer_scat",
        module="M4",
        display_name="Aerosol scattering coefficient",
        symbol_latex=r"\alpha_\text{aer,scat}",
        unit_si="1/m",
        formula_latex=(
            r"\alpha_\text{aer,scat} = \dfrac{3.91}{V} "
            r"\left(\dfrac{0.55\,\mu\text{m}}{\lambda}\right)^{q(V)}"
        ),
        formula_text=(
            "alpha_aer_scat = (3.91/V) * (0.55um/lambda)^q(V)   "
            "[Kruse visibility formula]"
        ),
        formula_dependencies=(),
        sensitivity_inputs=("V", "wavelength"),
        explanation_short=(
            "Scattering by suspended particles, dominated by Mie scattering. "
            "Drops fast as visibility improves (the V in the denominator) "
            "and depends weakly on wavelength through the q(V) exponent."
        ),
        explanation_full=(
            "The Kruse formula relates beam attenuation to the human-eye "
            "visibility V (in km), with the wavelength-dependent exponent "
            "q(V) capturing the size distribution of typical aerosol "
            "populations: q ≈ 1.6 for very clear air, dropping toward 0 in "
            "fog. The 3.91 prefactor converts the contrast-threshold "
            "definition of visibility (2 % per the WMO standard) into a 1/e "
            "extinction. v1 uses the original Kruse 1962 piecewise q(V); "
            "modern data assimilates more aerosol types but the engineering "
            "answer remains within a factor of ~2."
        ),
        citation="Kruse 1962 §III / SPEC §3 M4",
        code_ref="physics/m4_atmosphere.py::compute",
        derivation_link="validation/derivations/m4_atmosphere.md",
        provenance=(),
        assumptions=(
            "Kruse visibility model; q(V) piecewise; 0.55 µm reference "
            "wavelength.",
        ),
    ))

    rows.append(MetricEntry(
        key="alpha_atm",
        module="M4",
        display_name="Total atmospheric extinction",
        symbol_latex=r"\alpha_\text{atm}",
        unit_si="1/m",
        formula_latex=(
            r"\alpha_\text{atm} = "
            r"\alpha_\text{mol,abs} + \alpha_\text{mol,scat} + "
            r"\alpha_\text{aer,abs} + \alpha_\text{aer,scat}"
        ),
        formula_text=(
            "alpha_atm = alpha_mol_abs + alpha_mol_scat + "
            "alpha_aer_abs + alpha_aer_scat"
        ),
        formula_dependencies=(
            "alpha_mol_abs", "alpha_mol_scat",
            "alpha_aer_abs", "alpha_aer_scat",
        ),
        sensitivity_inputs=("V", "RH", "wavelength"),
        explanation_short=(
            "Sum of the four ways the atmosphere can take energy out of "
            "the beam: gas absorption, gas scattering, aerosol absorption, "
            "and aerosol scattering."
        ),
        explanation_full=(
            "Reported as an extinction coefficient with units of inverse "
            "length. The Beer–Lambert law turns this into the transmission "
            "fraction (next row) by exponentiating the negative product of "
            "α and the slant range. In typical NIR HEL conditions, aerosol "
            "scattering dominates the sum, especially in low-visibility "
            "weather (fog, dust, haze)."
        ),
        citation="SPEC §3 M4",
        code_ref="physics/m4_atmosphere.py::compute",
        derivation_link="validation/derivations/m4_atmosphere.md",
        provenance=(),
        assumptions=(),
    ))

    rows.append(MetricEntry(
        key="tau_atm",
        module="M4",
        display_name="Atmospheric transmission",
        symbol_latex=r"\tau_\text{atm}",
        unit_si="",
        formula_latex=(
            r"\tau_\text{atm} = "
            r"\exp\!\left(-\alpha_\text{atm} \cdot R_\text{slant}\right)"
        ),
        formula_text="tau_atm = exp(-alpha_atm * R_slant)",
        formula_dependencies=("alpha_atm", "R_slant"),
        sensitivity_inputs=("V", "RH", "wavelength", "R"),
        explanation_short=(
            "What fraction of the laser power survives the trip through "
            "the atmosphere from the emplacement to the target."
        ),
        explanation_full=(
            "The Beer–Lambert exponential decay law, with the total "
            "extinction coefficient as the rate and the slant range as the "
            "path. At short ranges (sub-km) atmospheric losses are usually "
            "modest; at multi-kilometre ranges or in poor visibility the "
            "exponential bites hard — a τ_atm of 0.5 means half the power "
            "never reaches the target."
        ),
        citation="Beer–Lambert / SPEC §3 M4",
        code_ref="physics/m4_atmosphere.py::compute",
        derivation_link="validation/derivations/m4_atmosphere.md",
        provenance=(),
        assumptions=(
            "Single homogeneous-atmosphere α along the slant — no path "
            "stratification by altitude in v1.",
        ),
    ))

    # =========================================================================
    # M5 — Atmospheric turbulence
    # =========================================================================

    rows.append(MetricEntry(
        key="Cn2_integrated",
        module="M5",
        display_name="Path-integrated turbulence",
        symbol_latex=r"\int C_n^{2}",
        unit_si="m^(1/3)",
        formula_latex=(
            r"\int_{0}^{L} C_n^{2}(z) \cdot \left(\dfrac{z}{L}\right)^{5/3} dz"
        ),
        formula_text=(
            "Cn2_integrated = integral_0^L Cn^2(z) * (z/L)^(5/3) dz   "
            "[scipy.integrate.quad over HV-5/7 profile along slant path]"
        ),
        formula_dependencies=("R_slant",),
        sensitivity_inputs=("R", "Cn2_ground", "v_HV", "H_e", "H_t"),
        explanation_short=(
            "A weighted integral of how turbulent the air is along the "
            "beam path. The (z/L)^(5/3) weighting puts more emphasis on "
            "turbulence near the target than near the laser — that's where "
            "spreading hurts most for a diverging beam."
        ),
        explanation_full=(
            "The kernel of the spherical-wave Fried-parameter formula. The "
            "Cn² profile itself is the Hufnagel-Valley HV-5/7 model with "
            "the upper-atmosphere wind v_HV and the ground-level Cn² as "
            "user inputs; altitude along the slant is interpolated linearly "
            "between H_e and H_t. The integral is evaluated numerically "
            "with scipy.integrate.quad — adaptive, well-behaved at z = 0 "
            "where the (z/L)^(5/3) weighting vanishes."
        ),
        citation="Andrews & Phillips 2005 §6.5",
        code_ref="physics/m5_turbulence.py::compute",
        derivation_link="validation/derivations/m5_turbulence.md",
        provenance=(ProvenanceFlag.REPLICATED,),
        assumptions=(
            "HV-5/7 profile; linear-altitude slant-path interpolation; "
            "scipy.integrate.quad numerical integration.",
        ),
    ))

    rows.append(MetricEntry(
        key="r0_sph",
        module="M5",
        display_name="Spherical-wave Fried parameter",
        symbol_latex=r"r_{0}^\text{sph}",
        unit_si="m",
        formula_latex=(
            r"r_{0}^\text{sph} = "
            r"\left(0.423 \cdot k^{2} \cdot \int C_n^{2}\right)^{-3/5}"
        ),
        formula_text="r0_sph = (0.423 * k^2 * Cn2_integrated)^(-3/5)",
        formula_dependencies=("Cn2_integrated",),
        sensitivity_inputs=("R", "wavelength", "Cn2_ground", "v_HV"),
        explanation_short=(
            "The largest aperture diameter for which atmospheric "
            "turbulence is not yet the dominant limit. A smaller r₀ means "
            "the atmosphere is broadening the beam more aggressively."
        ),
        explanation_full=(
            "The spherical-wave form (the −3/5 power and the 0.423 "
            "prefactor) is the appropriate one for a diverging HEL beam "
            "leaving a finite aperture; the plane-wave form would over-"
            "estimate r₀ for short ranges. This is one of the eleven "
            "audit-pinned formulas in the project."
        ),
        citation=(
            "Andrews & Phillips 2005 §6.5; Fried 1966 / SPEC §3 M5 / "
            "CLAUDE §7.1"
        ),
        code_ref="physics/m5_turbulence.py::compute",
        derivation_link="validation/derivations/m5_turbulence.md",
        provenance=(ProvenanceFlag.CLAUDE_71_INVARIANT,
                    ProvenanceFlag.REPLICATED),
        assumptions=(
            "Spherical-wave Kolmogorov regime; isotropic turbulence; "
            "weak-turbulence limit (no scintillation modeling).",
        ),
    ))

    rows.append(MetricEntry(
        key="w_turb",
        module="M5",
        display_name="Turbulent broadening (1/e² radius)",
        symbol_latex=r"w_\text{turb}",
        unit_si="m",
        formula_latex=(
            r"w_\text{turb} = \dfrac{2 \, L}{k \cdot r_{0}^\text{sph}}"
        ),
        formula_text="w_turb = 2 * L / (k * r0_sph)",
        formula_dependencies=("r0_sph", "R_slant"),
        sensitivity_inputs=("R", "wavelength", "Cn2_ground", "v_HV"),
        explanation_short=(
            "How much the spot at the target is enlarged by atmospheric "
            "turbulence alone. Adds in quadrature with the diffraction, "
            "jitter, and blooming contributions to the total spot size."
        ),
        explanation_full=(
            "The engineering form 2L/(k·r₀) (rather than the rigorous "
            "2L/(k·ρ₀) with ρ₀ = 2.1·r₀) — pinned in the project's "
            "audit-sensitivity list. Conservative for typical HEL ranges; "
            "the rigorous coherence-length form gives a slightly smaller "
            "broadening but is harder to defend without invoking the full "
            "Andrews-Phillips long-term-average derivation."
        ),
        citation=(
            "Andrews & Phillips 2005 §6.5 / SPEC §3 M5 / CLAUDE §7.1"
        ),
        code_ref="physics/m5_turbulence.py::compute",
        derivation_link="validation/derivations/m5_turbulence.md",
        provenance=(ProvenanceFlag.CLAUDE_71_INVARIANT,
                    ProvenanceFlag.REPLICATED),
        assumptions=(
            "Engineering long-term form; weak-turbulence regime.",
        ),
    ))

    # =========================================================================
    # M6 — Thermal blooming
    # =========================================================================
    # All three M6 metrics are post-iteration values from the M6↔M7
    # fixed-point loop. The Full view includes a banner pointing at
    # the iteration count diagnostic.

    rows.append(MetricEntry(
        key="N_D",
        module="M6",
        display_name="Gebhardt distortion number",
        symbol_latex=r"N_{D}",
        unit_si="",
        is_iterated=True,
        formula_latex=(
            r"N_{D} = 4\sqrt{2} \cdot "
            r"\dfrac{P \cdot \alpha_\text{abs} \cdot |dn/dT|}"
            r"{c_p \, \rho \, v_\perp \, w^{3}} \cdot L^{2}"
        ),
        formula_text=(
            "N_D = 4*sqrt(2) * P * alpha_abs * |dn/dT| * L^2 / "
            "(c_p * rho_air * v_perp * w_tgt^3)"
        ),
        formula_dependencies=("alpha_atm", "R_slant"),
        sensitivity_inputs=(
            "P0", "eta_opt", "v_perp", "T_ambient", "P_atm", "RH", "R",
        ),
        explanation_short=(
            "A dimensionless number that says how strongly the laser is "
            "heating the air on its path. Below 5 the heating is "
            "negligible; between 5 and 30 the engineering scaling is "
            "trustworthy; above 30 the model is no longer reliable."
        ),
        explanation_full=(
            "Gebhardt's classic blooming distortion number, with the "
            "4√2 prefactor pinned in the project's audit-sensitivity list. "
            "The dn/dT factor uses the Gladstone-Dale form with explicit "
            "temperature-dependence so non-standard atmospheric "
            "conditions (hot day, low pressure) flow through correctly. "
            "Computed post-convergence from the M6↔M7 iteration — see "
            "the orchestrator iteration count for how many passes the "
            "current run took."
        ),
        citation=(
            "Gebhardt 1990 *Proc. SPIE* 1221 / SPEC §3 M6 / CLAUDE §7.1"
        ),
        code_ref="physics/m6_blooming.py::compute",
        derivation_link="validation/derivations/m6_blooming.md",
        provenance=(ProvenanceFlag.CLAUDE_71_INVARIANT,),
        assumptions=(
            "Steady-state blooming; cross-wind-dominated convection of "
            "the heated channel.",
            "Gladstone-Dale dn/dT with T-dependence (CLAUDE §7.1 form).",
        ),
    ))

    rows.append(MetricEntry(
        key="S_TB",
        module="M6",
        display_name="Thermal-blooming Strehl",
        symbol_latex=r"S_\text{TB}",
        unit_si="",
        is_iterated=True,
        formula_latex=(
            r"S_\text{TB} = \dfrac{1}{1 + \left(N_{D}/5\right)^{2}}"
        ),
        formula_text="S_TB = 1 / (1 + (N_D/5)^2)",
        formula_dependencies=("N_D",),
        sensitivity_inputs=(
            "P0", "eta_opt", "v_perp", "T_ambient", "P_atm", "RH", "R",
        ),
        explanation_short=(
            "What fraction of the diffraction-limited peak irradiance "
            "survives thermal blooming. 1.0 means blooming is irrelevant; "
            "values near 0 mean almost all of the energy has been "
            "scattered out of the central peak by the heated air."
        ),
        explanation_full=(
            "Smith's empirical Strehl form, with the cutoff at N_D = 5 "
            "matching the regime above which blooming begins to "
            "appreciably degrade peak irradiance. Used by the M7 spot "
            "module to scale the on-axis irradiance, separately from how "
            "blooming also broadens the spot (the w_bloom contribution)."
        ),
        citation="Smith 1977; Gebhardt 1990 / SPEC §3 M6",
        code_ref="physics/m6_blooming.py::compute",
        derivation_link="validation/derivations/m6_blooming.md",
        provenance=(),
        assumptions=(
            "Smith's empirical Strehl scaling; valid for 5 ≤ N_D ≤ 30.",
        ),
    ))

    rows.append(MetricEntry(
        key="w_bloom",
        module="M6",
        display_name="Blooming spot broadening",
        symbol_latex=r"w_\text{bloom}",
        unit_si="m",
        is_iterated=True,
        formula_latex=(
            r"w_\text{bloom} = \begin{cases} 0 & \text{if } N_{D} < 5 \\ "
            r"0.3 \cdot w \cdot \sqrt{(N_{D}/5)^{2} - 1} & "
            r"\text{if } 5 \le N_{D} \le 30 \\ "
            r"\text{(flagged)} & \text{if } N_{D} > 30 \end{cases}"
        ),
        formula_text=(
            "w_bloom = 0                                if N_D < 5\n"
            "        = 0.3 * w * sqrt((N_D/5)^2 - 1)    if 5 <= N_D <= 30\n"
            "        = (computed but flagged)           if N_D > 30"
        ),
        formula_dependencies=("N_D", "w_total"),
        sensitivity_inputs=(
            "P0", "eta_opt", "v_perp", "T_ambient", "P_atm", "RH", "R",
        ),
        explanation_short=(
            "How much the heated air channel broadens the spot at the "
            "target on top of diffraction, turbulence, and jitter. Zero "
            "when blooming is weak; flagged as out-of-validity when N_D "
            "exceeds 30."
        ),
        explanation_full=(
            "An empirical broadening allocation — the 0.3 factor splits "
            "Gebhardt's total wavefront distortion between Strehl-on-the-"
            "peak (captured by S_TB) and pure spot broadening (this "
            "metric). The factor itself is engineering, not first-"
            "principles — see the project's HIGH UNCERTAINTY list. Above "
            "N_D = 30 the model is outside its derivation domain and "
            "the result is reported with an assumption flag."
        ),
        citation=(
            "Sprangle et al NRL/MR/6790-08-9141; Gebhardt 1976, 1990 / "
            "SPEC §10.4 (HIGH UNCERTAINTY)"
        ),
        code_ref="physics/m6_blooming.py::compute",
        derivation_link="validation/derivations/m6_blooming.md",
        provenance=(ProvenanceFlag.HIGH_UNCERTAINTY,),
        assumptions=(
            "Engineering 0.3 broadening fraction (NRL-derived).",
            "Validity envelope 5 ≤ N_D ≤ 30; outside this range the value "
            "still computes but is flagged.",
        ),
    ))

    # =========================================================================
    # M7 — Spot size and power-in-the-bucket
    # =========================================================================
    # w_turb is M5's pass-through; not duplicated here.

    rows.append(MetricEntry(
        key="w_diff",
        module="M7",
        display_name="Diffraction spot radius at target",
        symbol_latex=r"w_\text{diff}",
        unit_si="m",
        formula_latex=(
            r"w_\text{diff}(L) = w_{0} \cdot "
            r"\sqrt{1 + \left(\dfrac{M^{2} L}{z_{R}}\right)^{2}}"
        ),
        formula_text="w_diff = w0 * sqrt(1 + (M^2 * L / zR)^2)",
        formula_dependencies=("w0", "zR", "R_slant"),
        sensitivity_inputs=("D", "M2", "wavelength", "R"),
        explanation_short=(
            "How wide the beam would still be at the target if the "
            "atmosphere were perfectly clear, perfectly still, and the "
            "mount perfectly steady. The diffraction floor on spot size."
        ),
        explanation_full=(
            "The exact-Gaussian propagation law — NOT the far-field "
            "asymptote ``M²·λL/(π·w₀)`` which under-predicts by 2× to "
            "15× at typical engagement ranges. This is one of the "
            "eleven audit-pinned formulas. Closer than zR the beam is "
            "still essentially collimated; far past zR it grows roughly "
            "linearly with range."
        ),
        citation=(
            "Siegman 1986 §17 / SPEC §3 M7 / CLAUDE §7.1"
        ),
        code_ref="physics/m7_spot_pib.py::compute",
        derivation_link="validation/derivations/m7_spot.md",
        provenance=(ProvenanceFlag.CLAUDE_71_INVARIANT,
                    ProvenanceFlag.REPLICATED),
        assumptions=(
            "Exact-Gaussian propagation (NOT the far-field asymptote).",
        ),
    ))

    rows.append(MetricEntry(
        key="w_jit",
        module="M7",
        display_name="Jitter broadening (1/e² radius)",
        symbol_latex=r"w_\text{jit}",
        unit_si="m",
        formula_latex=(
            r"w_\text{jit} = 2 \, \sigma_\text{jit} \cdot L"
        ),
        formula_text="w_jit = 2 * sigma_jit * L",
        formula_dependencies=("R_slant",),
        sensitivity_inputs=("sigma_jit", "R"),
        explanation_short=(
            "How much pointing wobble at the laser source enlarges the "
            "long-term-average spot at the target."
        ),
        explanation_full=(
            "The per-axis RMS jitter angle σ_jit gets converted to a "
            "1/e² radius via the factor of 2 — pinned in the project's "
            "audit-sensitivity list. (Some references erroneously use a "
            "factor of √2 for 2D radial jitter; the v1 input is per-axis "
            "RMS, so the conversion is symbol-level identical to the σ → "
            "1/e² Gaussian-beam-radius rule.)"
        ),
        citation="SPEC §3 M7 / CLAUDE §7.1",
        code_ref="physics/m7_spot_pib.py::compute",
        derivation_link="validation/derivations/m7_spot.md",
        provenance=(ProvenanceFlag.CLAUDE_71_INVARIANT,),
        assumptions=(
            "σ_jit is per-axis RMS; long-term-average spot convention.",
        ),
    ))

    rows.append(MetricEntry(
        key="w_total",
        module="M7",
        display_name="Total spot radius at target",
        symbol_latex=r"w_\text{total}",
        unit_si="m",
        is_iterated=True,
        formula_latex=(
            r"w_\text{total} = "
            r"\sqrt{w_\text{diff}^{2} + w_\text{turb}^{2} + "
            r"w_\text{jit}^{2} + w_\text{bloom}^{2}}"
        ),
        formula_text=(
            "w_total = sqrt(w_diff^2 + w_turb^2 + w_jit^2 + w_bloom^2)"
        ),
        formula_dependencies=("w_diff", "w_turb", "w_jit", "w_bloom"),
        sensitivity_inputs=(
            "P0", "M2", "D", "wavelength", "sigma_jit", "R",
            "Cn2_ground", "v_HV", "v_perp", "RH",
        ),
        explanation_short=(
            "The four broadening sources combined in quadrature — the "
            "1/e² radius of the long-term-average spot the target "
            "actually sees. Drives both peak irradiance and "
            "power-in-the-bucket downstream."
        ),
        explanation_full=(
            "Quadrature combination of four independent broadening "
            "mechanisms: diffraction (set by aperture and wavelength), "
            "turbulence (atmospheric Cn²), jitter (mount wobble), and "
            "blooming (heated-air refraction). Pinned in the project's "
            "audit-sensitivity list — the rule that the four mechanisms "
            "add in quadrature, NOT in any other functional form, is "
            "the one most often gotten wrong by engineering scaling "
            "codes that double-count turbulence as both a Strehl and "
            "a broadening."
        ),
        citation="SPEC §3 M7 / CLAUDE §7.1",
        code_ref="physics/m7_spot_pib.py::compute",
        derivation_link="validation/derivations/m7_spot.md",
        provenance=(ProvenanceFlag.CLAUDE_71_INVARIANT,
                    ProvenanceFlag.REPLICATED),
        assumptions=(
            "Four broadening mechanisms statistically independent — valid "
            "in the long-term-average regime.",
        ),
    ))

    rows.append(MetricEntry(
        key="d_spot",
        module="M7",
        display_name="Total spot diameter at target",
        symbol_latex=r"d_\text{spot}",
        unit_si="m",
        formula_latex=r"d_\text{spot} = 2 \cdot w_\text{total}",
        formula_text="d_spot = 2 * w_total",
        formula_dependencies=("w_total",),
        sensitivity_inputs=(
            "P0", "M2", "D", "wavelength", "sigma_jit", "R",
            "Cn2_ground", "v_HV", "v_perp", "RH",
        ),
        explanation_short=(
            "Twice the 1/e² radius — the diameter typically reported in "
            "engineering trade studies and the value compared against "
            "the aimpoint bucket diameter."
        ),
        explanation_full=(
            "Pure unit conversion. Plotted directly on the engagement-tab "
            "spot-vs-bucket chart and used as the visual scale for the "
            "spot-size diagnostics."
        ),
        citation="SPEC §3 M7",
        code_ref="physics/m7_spot_pib.py::compute",
        derivation_link="validation/derivations/m7_spot.md",
        provenance=(),
        assumptions=(),
    ))

    rows.append(MetricEntry(
        key="I_peak",
        module="M7",
        display_name="Peak irradiance at target",
        symbol_latex=r"I_\text{peak}",
        unit_si="W/m^2",
        formula_latex=(
            r"I_\text{peak} = "
            r"\dfrac{2 \, P_\text{exit} \, \tau_\text{atm} \, S_\text{TB}}"
            r"{\pi \, w_\text{total}^{\,2}}"
        ),
        formula_text=(
            "I_peak = 2 * P_exit * tau_atm * S_TB / (pi * w_total^2)"
        ),
        formula_dependencies=("P_exit", "tau_atm", "S_TB", "w_total"),
        sensitivity_inputs=(
            "P0", "eta_opt", "M2", "D", "wavelength", "sigma_jit", "R",
            "V", "RH", "Cn2_ground", "v_HV", "v_perp",
        ),
        explanation_short=(
            "Brightest point in the beam at the target. The factor of 2 "
            "is the on-axis Gaussian peak; the S_TB factor accounts for "
            "thermal blooming dimming the peak."
        ),
        explanation_full=(
            "The peak irradiance an idealised single point on the target "
            "would see. Compares against the material's thermal "
            "absorption to drive the burn-through model. The "
            "Strehl-on-numerator convention (S_TB applies before the "
            "1/w² spreading) matches the project's audit-pinned "
            "decomposition of total spot vs Strehl."
        ),
        citation=(
            "Siegman 1986 §17 / Born & Wolf 1980 §8 / SPEC §3 M7 / "
            "CLAUDE §7.1"
        ),
        code_ref="physics/m7_spot_pib.py::compute",
        derivation_link="validation/derivations/m7_spot.md",
        provenance=(ProvenanceFlag.CLAUDE_71_INVARIANT,),
        assumptions=(
            "Gaussian beam profile at the target (long-term-average).",
        ),
    ))

    rows.append(MetricEntry(
        key="PIB_fraction",
        module="M7",
        display_name="Power-in-the-bucket fraction",
        symbol_latex=r"\eta_\text{PIB}",
        unit_si="",
        formula_latex=(
            r"\eta_\text{PIB} = "
            r"1 - \exp\!\left(-\dfrac{2 \, R_\text{aim}^{2}}"
            r"{w_\text{total}^{\,2}}\right) "
            r"\quad \text{with } R_\text{aim} = d_\text{aim}/2"
        ),
        formula_text=(
            "PIB = 1 - exp(-2 * R_aim^2 / w_total^2)   "
            "[R_aim = d_aim/2 — RADIUS, not diameter]"
        ),
        formula_dependencies=("w_total",),
        sensitivity_inputs=(
            "d_aim", "P0", "M2", "D", "wavelength", "sigma_jit", "R",
        ),
        explanation_short=(
            "The fraction of the beam's total power that lands inside "
            "the user-specified aimpoint disk at the target."
        ),
        explanation_full=(
            "Closed-form for a Gaussian beam against a circular aperture. "
            "The factor of 2 in the exponent and the use of the bucket "
            "RADIUS (not diameter) are pinned in the project's "
            "audit-sensitivity list — both errors are common in scaling "
            "codes that have been ported between conventions. PIB → 1 "
            "when w_total ≪ R_aim; PIB → 0 when w_total ≫ R_aim."
        ),
        citation="Born & Wolf 1980 §8 / SPEC §3 M7 / CLAUDE §7.1",
        code_ref="physics/m7_spot_pib.py::compute",
        derivation_link="validation/derivations/m7_spot.md",
        provenance=(ProvenanceFlag.CLAUDE_71_INVARIANT,),
        assumptions=(
            "Gaussian beam against circular aperture; bucket centred on "
            "the aimpoint.",
        ),
    ))

    rows.append(MetricEntry(
        key="P_aim",
        module="M7",
        display_name="Power deposited in the bucket",
        symbol_latex=r"P_\text{aim}",
        unit_si="W",
        formula_latex=(
            r"P_\text{aim} = "
            r"P_\text{exit} \cdot \tau_\text{atm} \cdot S_\text{TB} \cdot "
            r"\eta_\text{PIB}"
        ),
        formula_text=(
            "P_aim = P_exit * tau_atm * S_TB * PIB"
        ),
        formula_dependencies=("P_exit", "tau_atm", "S_TB", "PIB_fraction"),
        sensitivity_inputs=(
            "P0", "eta_opt", "M2", "D", "wavelength", "sigma_jit", "R",
            "V", "RH", "d_aim",
        ),
        explanation_short=(
            "The actual wattage deposited inside the aimpoint disk after "
            "every loss is accounted for: optics (η_opt), atmosphere "
            "(τ_atm), blooming (S_TB), and bucket spillover (PIB)."
        ),
        explanation_full=(
            "The single number that drives the burn-through calculation: "
            "everything downstream in M8 begins with P_aim divided by the "
            "bucket area. A sensitivity bar against this metric tells the "
            "operator which knob (laser power, optics quality, weather, "
            "aimpoint size) most directly moves the on-target "
            "deliverable."
        ),
        citation="SPEC §3 M7",
        code_ref="physics/m7_spot_pib.py::compute",
        derivation_link="validation/derivations/m7_spot.md",
        provenance=(),
        assumptions=(),
    ))

    rows.append(MetricEntry(
        key="I_avg_aim",
        module="M7",
        display_name="Average irradiance in the bucket",
        symbol_latex=r"I_\text{avg,aim}",
        unit_si="W/m^2",
        formula_latex=(
            r"I_\text{avg,aim} = "
            r"\dfrac{P_\text{aim}}{\pi \, R_\text{aim}^{2}}"
        ),
        formula_text=(
            "I_avg_aim = P_aim / (pi * R_aim^2)   [R_aim = d_aim/2]"
        ),
        formula_dependencies=("P_aim",),
        sensitivity_inputs=(
            "P0", "eta_opt", "M2", "D", "wavelength", "sigma_jit", "R",
            "V", "RH", "d_aim",
        ),
        explanation_short=(
            "Average power per unit area inside the aimpoint disk. Less "
            "intuitive than the peak but matches the assumption M8 makes "
            "about uniform front-face heating across the aimpoint."
        ),
        explanation_full=(
            "The burn-through solver uses this rather than the peak "
            "irradiance because its 1-D heat-conduction model is "
            "implicitly an average over the bucket area. For a tightly-"
            "focused beam where the spot is much smaller than the "
            "bucket, average and peak converge; for a loosely-focused "
            "beam where the spot is much larger than the bucket, the "
            "average is several times smaller than the peak."
        ),
        citation="SPEC §3 M7",
        code_ref="physics/m7_spot_pib.py::compute",
        derivation_link="validation/derivations/m7_spot.md",
        provenance=(),
        assumptions=(
            "Bucket-averaged irradiance — appropriate when M8's 1-D heat "
            "model is the downstream consumer.",
        ),
    ))

    return {entry.key: entry for entry in rows}


MATH_CONTENT: dict[str, MetricEntry] = _entries()


__all__ = [
    "MATH_CONTENT",
    "MODULE_ORDER",
    "MODULE_TITLES",
    "MetricEntry",
    "ProvenanceFlag",
]
