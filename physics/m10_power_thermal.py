"""M10 — Power & Thermal Budget per SPEC §3 M10.

Computes prime power draw, waste heat, and whether the cooling loop
can sustain a requested engagement duration under a single-lumped-mass
coolant model. Typical use: `t_engagement` comes from M8's `tau_BT`,
and the orchestrator reports `engagement_viable` alongside burn-through
time so the user sees the two failure modes (optical vs thermal) on
equal footing.

Equations (SPEC §3 M10):
    P_in    = P0 / η_wallplug
    Q_waste = P_in − P0

    Steady-state branch (Q_waste ≤ Q_cool):
        t_sustain         = ∞
        duty_cycle_limit  = 1.0
    Transient branch (Q_waste > Q_cool):
        t_sustain         = C_thermal · dT_max / (Q_waste − Q_cool)
        recovery_time     = C_thermal · dT_max / Q_cool
        duty_cycle_limit  = t_sustain / (t_sustain + recovery_time)

    engagement_viable    = (t_engagement ≤ t_sustain)
    engagements_per_hour = 3600 · duty_cycle_limit / t_engagement

The lumped-mass model treats the coolant loop as a single thermal
capacitance C_thermal with a constant sink rate Q_cool. Q_waste is
assumed constant over the engagement (P0 doesn't ramp). These are
first-order engineering assumptions and are always flagged.

References:
    SPEC §3 M10 for formulas and defaults.
    Perram et al., *An Introduction to Laser Weapon Systems* (DEPS
        2010) for HEL cooling-loop conventions.
"""

import math

from physics.common import validate_positive, validate_range


def _validate_inputs(inputs: dict) -> None:
    required = (
        "P0", "eta_wallplug", "Q_cool", "C_thermal", "dT_max", "t_engagement",
    )
    missing = [k for k in required if k not in inputs]
    if missing:
        raise ValueError(f"M10 missing required inputs: {missing}")

    validate_positive(inputs["P0"], "P0")
    validate_range(inputs["eta_wallplug"], "eta_wallplug", 0.05, 0.50)
    if inputs["Q_cool"] < 0:
        raise ValueError(f"Q_cool must be ≥ 0, got {inputs['Q_cool']}")
    validate_positive(inputs["C_thermal"], "C_thermal")
    validate_range(inputs["dT_max"], "dT_max", 5.0, 80.0)
    validate_positive(inputs["t_engagement"], "t_engagement")


def compute(inputs: dict) -> dict:
    """Compute power/thermal budget and engagement viability.

    Args:
        inputs: dict with keys P0 [W], eta_wallplug [—], Q_cool [W],
            C_thermal [J/K], dT_max [K], t_engagement [s].

    Returns:
        dict with keys P_in [W], Q_waste [W], t_sustain [s or inf],
        engagement_viable [bool], duty_cycle_limit [0..1],
        engagements_per_hour [float], assumptions_flagged [list[str]].
    """
    _validate_inputs(inputs)

    p0 = inputs["P0"]
    eta = inputs["eta_wallplug"]
    q_cool = inputs["Q_cool"]
    c_thermal = inputs["C_thermal"]
    dT_max = inputs["dT_max"]
    t_engagement = inputs["t_engagement"]

    p_in = p0 / eta
    q_waste = p_in - p0

    flags: list[str] = []

    if q_waste <= q_cool:
        # Steady-state: cooling matches (or exceeds) dissipation indefinitely.
        t_sustain = math.inf
        duty_cycle_limit = 1.0
        engagements_per_hour = 3600.0 / t_engagement
    else:
        # Transient: coolant heats from baseline to baseline+dT_max over
        # t_sustain, then must shed that stored heat at Q_cool to return
        # to baseline before the next engagement.
        t_sustain = (c_thermal * dT_max) / (q_waste - q_cool)
        if q_cool > 0:
            recovery_time = (c_thermal * dT_max) / q_cool
            duty_cycle_limit = t_sustain / (t_sustain + recovery_time)
        else:
            # No active cooling: can never recover — single-shot thermally.
            duty_cycle_limit = 0.0
            flags.append(
                "Q_cool=0: no active cooling; duty_cycle_limit=0 and the "
                "system is single-shot thermally (recovery is passive / "
                "not modeled here)."
            )
        engagements_per_hour = 3600.0 * duty_cycle_limit / t_engagement

    engagement_viable = (t_engagement <= t_sustain)

    if not engagement_viable:
        flags.append(
            f"t_engagement {t_engagement:.3g} s exceeds t_sustain "
            f"{t_sustain:.3g} s — cooling loop will reach dT_max before "
            "burn-through; engagement is thermally not viable."
        )

    # CLAUDE §4.5 always-on: disclose the modeling assumptions that a
    # user needs to check before citing these numbers.
    flags.append(
        "Single lumped-mass coolant model (C_thermal, Q_cool). Q_waste "
        "held constant over the engagement (P0 not ramped) and Q_cool "
        "held at rated capacity throughout the run-recover cycle "
        "(SPEC §3 M10)."
    )

    return {
        "P_in": p_in,
        "Q_waste": q_waste,
        "t_sustain": t_sustain,
        "engagement_viable": engagement_viable,
        "duty_cycle_limit": duty_cycle_limit,
        "engagements_per_hour": engagements_per_hour,
        "assumptions_flagged": flags,
    }
