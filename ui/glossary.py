"""Concept-level glossary for the "How it's calculated" tab.

Each entry explains the *concept* (what is "diffraction"? what is "Strehl"?)
in 2-3 sentences targeted at a reader who has never seen the term. This is
distinct from the per-metric "What it means" string in ``ui/math_content.py``,
which explains the *role* of a particular metric in the engagement story.

Plan: ``docs/math_tab_plan_2026-04-25.md`` §10 (closed list of 22 entries).
The list is intentionally small so junior-engineer readers see a finite,
walkable lexicon rather than a dump of every technical term in the SPEC.

When the math tab introduces a new concept that does not yet have a glossary
entry, add it here and reference it from the corresponding ``MetricEntry``;
``tests/test_math_tab.py`` enforces that every Greek-letter / non-trivial
symbol referenced in a formula has a glossary cross-reference.
"""
from __future__ import annotations


# Keys: short canonical name as it would appear inline (lowercase preferred,
# but title case where a proper-noun reading is natural).
# Values: 2-3 sentence definition. No SPEC § references in user-facing copy
# (test_copy_style.py rule).

GLOSSARY: dict[str, str] = {
    "1/e² radius": (
        "The radial distance at which a Gaussian beam's intensity falls to "
        "1/e² ≈ 13.5 % of its peak. The canonical beam-size measure throughout "
        "this tool — when you see 'beam radius' or 'spot radius', this is what "
        "is meant."
    ),
    "Aimpoint": (
        "The disk on the target the operator is trying to deposit energy into, "
        "set by the user-input aimpoint diameter. The 'power-in-the-bucket' "
        "calculation reports what fraction of total beam power lands inside "
        "this disk."
    ),
    "Beam-quality factor (M²)": (
        "A dimensionless multiplier that captures how much wider a real beam is "
        "than an ideal Gaussian of the same nominal size. M² = 1 is a perfect "
        "single-mode beam; typical high-power lasers run M² between 1.1 and 2. "
        "Values above 3 indicate substantial beam-quality degradation."
    ),
    "Burn-through": (
        "The point at which the laser has heated the target enough to defeat "
        "it, by melting through a metal skin, decomposing a polymer, or venting "
        "a sealed cell. The time to reach this point is the headline result "
        "for the engagement-viability question."
    ),
    "Cn² (refractive-index structure parameter)": (
        "A measure of how strongly the air's optical refractive index varies "
        "from point to point at small scales — the underlying physical cause "
        "of atmospheric turbulence. Cn² is altitude-dependent and varies "
        "across the day, peaking near the ground in mid-afternoon."
    ),
    "Diffraction": (
        "The unavoidable spreading of any beam of light as it propagates, set "
        "by the wavelength and the size of the aperture it came out of. Even "
        "a perfect optical system produces a diffraction-limited spot — this "
        "is physics, not an engineering imperfection."
    ),
    "Dwell time": (
        "How long the laser must continuously illuminate the target to deliver "
        "the energy that defeats it. The engagement is feasible when the "
        "available dwell window (set by target kinematics and beam-director "
        "limits) exceeds the time-to-burn-through computed by the thermal model."
    ),
    "Failure mode": (
        "How the target fails when enough energy has been deposited. Three "
        "modes are tabulated: melt (metal skins reaching their melting point), "
        "decomposition (polymer matrix breaking down before melting), and "
        "vent (sealed cells like LiPo batteries reaching their vent threshold)."
    ),
    "Fried parameter (r₀)": (
        "The largest aperture diameter for which atmospheric turbulence is not "
        "the dominant limit on resolution along the slant path. A small r₀ "
        "(say, a few centimetres) means turbulence wins over diffraction; a "
        "large r₀ (a metre or more) means the atmosphere is essentially clear."
    ),
    "Gebhardt distortion number (N_D)": (
        "A dimensionless number that measures how strongly thermal blooming is "
        "bending the beam — when the laser heats the air it passes through, "
        "the heated air bends subsequent light away from the original path. "
        "N_D below 5 is negligible; 5–30 is well-modelled; above 30 the model "
        "is no longer trustworthy."
    ),
    "Jitter": (
        "Random pointing wobble of the beam director, expressed as a per-axis "
        "RMS angle. Multiple sources contribute (mount vibration, gimbal "
        "noise, residual tracking error); the input field receives the total "
        "in-band RMS for one axis."
    ),
    "Maximum permissible exposure (MPE)": (
        "The highest irradiance level at which a typical eye can tolerate "
        "direct exposure for a stated duration without expected damage, per "
        "the ANSI laser-safety standard. The tool reports the MPE for the "
        "user's wavelength and exposure time."
    ),
    "Nominal ocular hazard distance (NOHD)": (
        "The distance from the laser source beyond which the beam irradiance "
        "is below the maximum permissible exposure. People standing closer "
        "than the NOHD risk eye damage from direct or specular reflected "
        "viewing; people standing farther than the NOHD do not."
    ),
    "Power-in-the-bucket (PIB)": (
        "The fraction of total beam power that lands inside the user's "
        "aimpoint disk at the target. Closely tied to spot size — when the "
        "spot grows larger than the bucket, PIB drops and most of the energy "
        "is wasted on the surroundings."
    ),
    "Rayleigh range (zR)": (
        "The propagation distance over which a Gaussian beam stays roughly "
        "the same size as it was at the launch aperture. Closer than zR the "
        "beam is essentially collimated; far past zR it has fully entered "
        "the diffraction-spreading regime."
    ),
    "Slant range": (
        "The straight-line distance from the laser emplacement to the target. "
        "Distinct from horizontal (ground) range when the emplacement and "
        "target are at different altitudes — the slant is always longer."
    ),
    "Strehl ratio": (
        "The ratio of actual peak irradiance on target to what a perfect "
        "system would produce. A Strehl of 1.0 means the system delivers "
        "diffraction-limited brightness; lower values mean some fraction of "
        "the energy is being scattered out of the central peak."
    ),
    "Thermal blooming": (
        "Beam distortion caused by the laser heating the air it passes "
        "through — the heated air's refractive index changes, bending later "
        "light away from the original path and broadening the spot. Worst at "
        "high power, low wind, and high humidity."
    ),
    "Top-hat vs Gaussian-peak NOHD": (
        "Two different conventions for computing the ocular hazard distance. "
        "Top-hat assumes uniform intensity across the beam (ANSI default); "
        "Gaussian-peak uses the on-axis peak intensity (more conservative for "
        "single-mode HEL beams). The tool reports both — pick the convention "
        "that matches the safety case being made."
    ),
    "Transmission (atmospheric, τ_atm)": (
        "The fraction of laser power that survives the trip through the "
        "atmosphere from emplacement to target. Combines absorption and "
        "scattering by air molecules and aerosols. Drops fast at long ranges "
        "or in high-aerosol conditions like fog or rain."
    ),
    "Wallplug efficiency": (
        "The fraction of electrical input power that emerges as laser output "
        "power. A 30 % wallplug-efficient laser at 3 kW output requires 10 kW "
        "of electrical input and dumps 7 kW as waste heat that the cooling "
        "system has to remove."
    ),
    "Wavelength (λ)": (
        "The colour of the laser light, measured in micrometres. The four "
        "wavelengths the tool is validated against are 1.06, 1.07, 1.55, "
        "and 2.05 µm — typical near-infrared HEL operating points. Other "
        "wavelengths still compute but carry a reduced-confidence flag."
    ),
}


__all__ = ["GLOSSARY"]
