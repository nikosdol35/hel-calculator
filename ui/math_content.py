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

    return {entry.key: entry for entry in rows}


MATH_CONTENT: dict[str, MetricEntry] = _entries()


__all__ = [
    "MATH_CONTENT",
    "MODULE_ORDER",
    "MODULE_TITLES",
    "MetricEntry",
    "ProvenanceFlag",
]
