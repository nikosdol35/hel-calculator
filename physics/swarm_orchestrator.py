"""Time-stepped engagement simulation engine for the Swarm Analyzer.

Consumes a ``SwarmScenario`` and produces a ``SwarmEngagementResult``.

The simulation walks forward in time at ``scenario.dt_s`` (default
0.05 s) until every drone is in a terminal state (DESTROYED / LEAKED
/ TIMEOUT) or the global ``t_max_s`` ceiling is hit. Each timestep:

  1. Promote WAITING drones to DETECTED when they enter R_detect_max.
  2. Move every alive drone forward by ``velocity * dt``; mark LEAK
     when range crosses R_min.
  3. Advance the BD state machine:
       - SLEWING(target, t_arrive): if t ≥ t_arrive, switch to ENGAGING.
       - ENGAGING(target): run the lightweight HEL chain
         (M4+M5+M7) at the target's CURRENT range, accumulate
         absorbed energy. Mark KILL when E_cum ≥ 0.83 · E_fail.
       - IDLE: invoke the scheduler. If a candidate exists, slew
         to it; otherwise the simulation ends.

When the BD switches targets mid-burn, the abandoned drone's
cumulative_E is preserved. If the BD comes back, it picks up where
it left off — the heat absorbed earlier doesn't vanish during slew.
This is the realistic engagement model.

The lightweight chain (~5 ms per call) is wrapped in an LRU cache
keyed on (range rounded to 0.1 m, atmospheric inputs, σ_jit). Cache
hit rate on a typical 15-drone scenario is ~90% — drops simulation
runtime from ~6 s to ~1 s.

Pure module — no Streamlit imports, no I/O.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Any

from physics import m1_laser_source, m2_beam_director
from physics.geometry_family import _compute_irradiance_at_R, _LUMPED_TO_PDE_RATIO
from physics.m8_material_tables import EMISSIVITY_IR_DEFAULT, MATERIAL_PROPERTIES
from physics.swarm_drone_types import DRONE_TYPES, get_drone_type
from physics.swarm_kinematics import (
    bearing_to_drone_deg,
    closing_rate_mps,
    position_at,
    range_to_bd_m,
    time_to_leak_s,
    total_switch_time_s,
)
from physics.swarm_scenario import Drone, SwarmScenario
from physics.swarm_scheduler import pick_target


# ---------------------------------------------------------------------------
# Output dataclasses (per plan §3.6)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TimingBreakdown:
    """How wall-clock simulation time was spent."""
    slew_total_s: float
    engage_total_s: float
    idle_total_s: float


@dataclass(frozen=True)
class Event:
    """One state transition in the simulation log."""
    t_s: float
    drone_id: int | None
    kind: str   # "DETECT" | "SLEW_START" | "ENGAGE_START" | "KILL" | "LEAK" | "TIMEOUT"


@dataclass(frozen=True)
class DroneOutcome:
    """Per-drone simulation result. Frozen so the whole result is
    immutable + hashable.

    ``engage_starts_s`` and ``engage_durations_s`` may have multiple
    entries when the BD switched away mid-burn and came back later.
    """
    drone_id: int
    drone_type_key: str
    verdict: str                          # "KILL" | "LEAK" | "TIMEOUT"
    detect_time_s: float | None
    engage_starts_s: tuple[float, ...]
    engage_durations_s: tuple[float, ...]
    slew_time_to_first_engage_s: float
    cumulative_absorbed_J_per_cm2: float
    E_fail_J_per_cm2: float
    range_at_outcome_m: float
    bearing_at_outcome_deg: float
    outcome_time_s: float


@dataclass(frozen=True)
class SwarmEngagementResult:
    """Output of ``run_swarm_simulation``."""
    drones: tuple[DroneOutcome, ...]
    n_killed: int
    n_leaked: int
    n_timeout: int
    first_leak_time_s: float | None
    total_engagement_time_s: float
    timing_breakdown: TimingBreakdown
    closest_leak_range_m: float | None
    slew_fraction: float
    summary_hash: str
    assumptions_flagged: tuple[str, ...]
    event_log: tuple[Event, ...]


# ---------------------------------------------------------------------------
# Standing assumptions list (per plan §3.9)
# ---------------------------------------------------------------------------

STANDING_ASSUMPTIONS: tuple[str, ...] = (
    "Detection probability Pd = 1 (perfect tracker)",
    "Drones move in straight lines at constant velocity (no evasive maneuvering)",
    "Atmospheric blooming assumed steady-state during engagement",
    "Single beam director, single drone engaged at a time",
    "Laser switches on/off instantly (rise/fall time neglected; ~50 ms vs ~3 s burn)",
    "2D engagement: BD slews azimuth only; all drones at BD altitude",
    "σ_jit constant across slew profile (no rate-induced jitter increase)",
    "Lumped-mass thermal failure threshold (0.83 · E_fail), no catastrophic kill modeling",
    "Broadside drone aspect (worst-case absorbed area)",
    "Reference simplification: M6 blooming Strehl = 1.0, w_bloom = 0",
)


# ---------------------------------------------------------------------------
# Internal mutable simulation state (NOT exposed to consumers)
# ---------------------------------------------------------------------------

@dataclass
class _SimDrone:
    """Mutable per-drone state during the simulation. Converted to
    a frozen ``DroneOutcome`` at end of run."""
    drone_id: int
    drone_type_key: str
    initial_position_m: tuple[float, float]
    velocity_mps: tuple[float, float]
    state: str                    # WAITING / DETECTED / ENGAGED / DESTROYED / LEAKED / TIMEOUT
    detect_time_s: float | None = None
    engage_starts_s: list[float] = field(default_factory=list)
    engage_ends_s: list[float] = field(default_factory=list)
    cumulative_absorbed_J_per_cm2: float = 0.0
    E_fail_J_per_cm2: float = 0.0
    A_lambda: float = 0.0          # absorption coefficient at the laser λ
    range_at_outcome_m: float = 0.0
    bearing_at_outcome_deg: float = 0.0
    outcome_time_s: float | None = None

    @property
    def position_m(self) -> tuple[float, float]:
        # Mutated each timestep by the orchestrator's main loop.
        return self.initial_position_m  # placeholder, overwritten

    @property
    def is_alive(self) -> bool:
        return self.state in ("WAITING", "DETECTED", "ENGAGED")


# ---------------------------------------------------------------------------
# E_fail / A_λ resolution from drone presets + HEL inputs
# ---------------------------------------------------------------------------

def _e_fail_jpcm2(drone_type_key: str, T_ambient_K: float) -> float:
    """Lumped-mass failure-fluence requirement (J/cm²) for the
    drone's preset material + thickness.

    E_fail [J/m²] = ρ · c_p · thickness · (T_fail − T_ambient)
    Result returned in J/cm² to pair naturally with W/cm² flux.
    """
    drone_type = get_drone_type(drone_type_key)
    props = MATERIAL_PROPERTIES[drone_type.material]
    delta_T = float(props["T_fail"]) - float(T_ambient_K)
    if delta_T <= 0:
        # Pathological: ambient hotter than failure temp → E_fail = 0.
        # Treat as instantaneously killable.
        return 0.0
    e_fail_jpm2 = (
        float(props["rho"]) * float(props["c_p"])
        * float(drone_type.thickness_m) * delta_T
    )
    return e_fail_jpm2 * 1.0e-4


def _resolve_a_lambda(drone_type_key: str, wavelength_m: float) -> float:
    """Pick the right A_λ for the drone's material at the laser
    wavelength. Pulled from the existing M8 absorptivity table; if
    the drone preset overrides it, use the override."""
    from physics.m8_material_tables import A_LAMBDA_TABLE

    drone_type = get_drone_type(drone_type_key)
    if drone_type.a_lambda_hint is not None:
        return drone_type.a_lambda_hint
    table_row = A_LAMBDA_TABLE.get(drone_type.material)
    if table_row is None:
        # Defensive: fall back to a mid-range default.
        return 0.5
    # The HEL chain interpolates between the four canonical wavelengths;
    # for the swarm sim we can take the value at the closest tabulated
    # wavelength (precision below the lumped-mass model's accuracy).
    canonical_lambdas = (1.06e-6, 1.07e-6, 1.55e-6, 2.05e-6)
    idx = min(
        range(len(canonical_lambdas)),
        key=lambda i: abs(canonical_lambdas[i] - wavelength_m),
    )
    return float(table_row[idx])


# ---------------------------------------------------------------------------
# Lightweight HEL chain wrapper + LRU cache
# ---------------------------------------------------------------------------

def _hel_inputs_with_d_aim(hel_inputs: dict, drone_type_key: str) -> dict:
    """Pass through the HEL inputs unchanged — the swarm sim uses the
    user's sidebar ``d_aim`` setting (the BD's aimpoint bucket
    diameter, an operator tactical choice) rather than deriving one
    from the drone's mass. This keeps the cross-check against HEL
    Calculator apples-to-apples and matches the engineering intent
    of d_aim (aimpoint quality, not target size).

    Kept as a function (rather than dropping the call) so a future
    refinement can plug in drone-aware bucket adjustment without a
    call-site change.
    """
    return dict(hel_inputs)


def _make_irradiance_fn(
    hel_inputs: dict,
    w0: float,
    zR: float,
    P_exit: float,
):
    """Build a closure that computes (I_peak, I_avg_aim) at one
    range, with an internal LRU cache keyed on rounded range.

    The closure captures the HEL inputs + M1/M2 outputs once per
    simulation; subsequent calls only vary ``R``. Using lru_cache on
    a closure means the cache is per-simulation, no cross-run
    bleeding.
    """
    @lru_cache(maxsize=4096)
    def cached(R_rounded: float) -> tuple[float, float] | None:
        return _compute_irradiance_at_R(hel_inputs, R_rounded, w0, zR, P_exit)

    def lookup(R_m: float) -> tuple[float, float] | None:
        # Round to 0.1 m so adjacent timesteps land on the same key.
        return cached(round(R_m, 1))

    return lookup, cached


# ---------------------------------------------------------------------------
# M1/M2 setup — reused from the HEL Calculator
# ---------------------------------------------------------------------------

def _resolve_m1_m2(hel_inputs: dict) -> tuple[float, float, float]:
    """Run M1 (laser geometry) + M2 (beam director) once per
    simulation. Returns (w0, zR, P_exit) — the constants the
    lightweight chain needs."""
    m1_out = m1_laser_source.compute({
        "wavelength": hel_inputs["wavelength"],
        "M2": hel_inputs["M2"],
        "D": hel_inputs["D"],
        "P0": hel_inputs["P0"],
    })
    m2_out = m2_beam_director.compute({
        "P0": hel_inputs["P0"],
        "eta_opt": hel_inputs["eta_opt"],
    })
    return (
        float(m1_out["w0"]),
        float(m1_out["zR"]),
        float(m2_out["P_exit"]),
    )


# ---------------------------------------------------------------------------
# Main simulation entry point
# ---------------------------------------------------------------------------

def run_swarm_simulation(scenario: SwarmScenario) -> SwarmEngagementResult:
    """Run the time-stepped swarm engagement simulation.

    Pure function: same input → same output. The output is hashable,
    so golden tests can compare summary hashes for regression detection.
    """
    # ── M1/M2 setup (once) ───────────────────────────────────────
    w0, zR, P_exit = _resolve_m1_m2(scenario.hel_inputs)

    # ── Per-drone constants (E_fail, A_λ) ────────────────────────
    sim_drones: list[_SimDrone] = []
    for d in scenario.drones:
        e_fail = _e_fail_jpcm2(d.drone_type_key, scenario.hel_inputs["T_ambient"])
        a_lambda = _resolve_a_lambda(d.drone_type_key, scenario.hel_inputs["wavelength"])
        # Initial state: WAITING if outside R_detect_max at t=0,
        # else DETECTED.
        initial_range = math.sqrt(d.position_m[0] ** 2 + d.position_m[1] ** 2)
        initial_state = (
            "DETECTED" if initial_range <= scenario.R_detect_max_m else "WAITING"
        )
        sim_drones.append(_SimDrone(
            drone_id=d.drone_id,
            drone_type_key=d.drone_type_key,
            initial_position_m=d.position_m,
            velocity_mps=d.velocity_mps,
            state=initial_state,
            detect_time_s=(0.0 if initial_state == "DETECTED" else None),
            E_fail_J_per_cm2=e_fail,
            A_lambda=a_lambda,
        ))

    # Pre-loop: log DETECT events for drones that start inside the
    # detection envelope. (The main loop only logs DETECT for the
    # WAITING → DETECTED transition.)
    initial_events: list[Event] = []
    for d in sim_drones:
        if d.state == "DETECTED" and d.detect_time_s == 0.0:
            initial_events.append(Event(0.0, d.drone_id, "DETECT"))

    # Mutable per-drone position cache — recomputed each step.
    positions: dict[int, tuple[float, float]] = {
        d.drone_id: d.initial_position_m for d in sim_drones
    }

    # ── Per-scenario lightweight-chain closure ───────────────────
    # Build hel_inputs once per drone TYPE (d_aim varies by drone).
    # We pre-build lookup functions per drone-type-key so the cache
    # works correctly when drones of different types share the BD.
    irradiance_fns_by_type: dict[str, Any] = {}
    for type_key in {d.drone_type_key for d in scenario.drones}:
        type_inputs = _hel_inputs_with_d_aim(scenario.hel_inputs, type_key)
        lookup, _cached = _make_irradiance_fn(type_inputs, w0, zR, P_exit)
        irradiance_fns_by_type[type_key] = lookup

    # ── BD state machine ─────────────────────────────────────────
    bd_state = "IDLE"
    bd_target_id: int | None = None
    bd_t_arrive: float | None = None
    bd_bearing_deg = scenario.bd_kinematics.initial_bearing_deg

    # ── Bookkeeping ──────────────────────────────────────────────
    events: list[Event] = list(initial_events)
    slew_total_s = 0.0
    engage_total_s = 0.0
    idle_total_s = 0.0
    first_leak_time_s: float | None = None

    # ── Main loop ────────────────────────────────────────────────
    t = 0.0
    dt = scenario.dt_s

    def _state_for_scheduler() -> list[dict]:
        return [
            {
                "drone_id": d.drone_id,
                "position_m": positions[d.drone_id],
                "velocity_mps": d.velocity_mps,
                "state": d.state,
            }
            for d in sim_drones
        ]

    def _estimate_tau_BT_for_easiest_kill(d_state: dict) -> float:
        drone = next(d for d in sim_drones if d.drone_id == d_state["drone_id"])
        rng = range_to_bd_m(d_state["position_m"])
        lookup = irradiance_fns_by_type[drone.drone_type_key]
        result = lookup(rng)
        if result is None:
            return float("inf")
        _, I_avg_wpcm2 = result
        absorbed_flux = drone.A_lambda * I_avg_wpcm2
        if absorbed_flux <= 0:
            return float("inf")
        return _LUMPED_TO_PDE_RATIO * drone.E_fail_J_per_cm2 / absorbed_flux

    while t <= scenario.t_max_s:
        # 1a. Promote WAITING → DETECTED.
        for d in sim_drones:
            if d.state == "WAITING":
                positions[d.drone_id] = position_at(
                    d.initial_position_m, d.velocity_mps, t
                )
                if range_to_bd_m(positions[d.drone_id]) <= scenario.R_detect_max_m:
                    d.state = "DETECTED"
                    d.detect_time_s = t
                    events.append(Event(t, d.drone_id, "DETECT"))

        # 1b. Update positions of alive drones; mark LEAK on R_min.
        for d in sim_drones:
            if not d.is_alive:
                continue
            positions[d.drone_id] = position_at(
                d.initial_position_m, d.velocity_mps, t
            )
            if d.state == "WAITING":
                continue
            r = range_to_bd_m(positions[d.drone_id])
            if r < scenario.R_min_m:
                d.state = "LEAKED"
                d.range_at_outcome_m = r
                d.bearing_at_outcome_deg = bearing_to_drone_deg(
                    positions[d.drone_id]
                )
                d.outcome_time_s = t
                events.append(Event(t, d.drone_id, "LEAK"))
                if first_leak_time_s is None:
                    first_leak_time_s = t
                # If BD was engaging this drone, drop back to IDLE.
                if bd_target_id == d.drone_id and bd_state == "ENGAGING":
                    if d.engage_starts_s and len(d.engage_ends_s) < len(d.engage_starts_s):
                        d.engage_ends_s.append(t)
                    bd_state = "IDLE"
                    bd_target_id = None

        # 2. Advance BD state machine.
        if bd_state == "SLEWING":
            slew_total_s += dt
            if t >= bd_t_arrive:
                bd_state = "ENGAGING"
                target = next(d for d in sim_drones if d.drone_id == bd_target_id)
                # Snap BD bearing to current target bearing.
                bd_bearing_deg = bearing_to_drone_deg(positions[target.drone_id])
                target.state = "ENGAGED"
                target.engage_starts_s.append(t)
                events.append(Event(t, target.drone_id, "ENGAGE_START"))

        elif bd_state == "ENGAGING":
            engage_total_s += dt
            target = next(d for d in sim_drones if d.drone_id == bd_target_id)
            # Track the target — BD stays on it (no extra time cost).
            bd_bearing_deg = bearing_to_drone_deg(positions[target.drone_id])
            r = range_to_bd_m(positions[target.drone_id])
            lookup = irradiance_fns_by_type[target.drone_type_key]
            irr = lookup(r)
            if irr is not None:
                _, I_avg_wpcm2 = irr
                target.cumulative_absorbed_J_per_cm2 += (
                    target.A_lambda * I_avg_wpcm2 * dt
                )
                if (
                    target.cumulative_absorbed_J_per_cm2
                    >= _LUMPED_TO_PDE_RATIO * target.E_fail_J_per_cm2
                ):
                    target.state = "DESTROYED"
                    target.range_at_outcome_m = r
                    target.bearing_at_outcome_deg = bd_bearing_deg
                    target.outcome_time_s = t
                    target.engage_ends_s.append(t)
                    events.append(Event(t, target.drone_id, "KILL"))
                    bd_state = "IDLE"
                    bd_target_id = None

        elif bd_state == "IDLE":
            idle_total_s += dt
            scheduler_state = _state_for_scheduler()
            next_id = pick_target(
                scenario.strategy,
                scheduler_state,
                scenario.R_min_m,
                estimate_tau_BT_s=_estimate_tau_BT_for_easiest_kill,
            )
            if next_id is not None:
                next_target = next(d for d in sim_drones if d.drone_id == next_id)
                target_bearing = bearing_to_drone_deg(positions[next_id])
                t_switch = total_switch_time_s(
                    bearing_from_deg=bd_bearing_deg,
                    bearing_to_deg=target_bearing,
                    max_rate_dps=scenario.bd_kinematics.max_slew_rate_dps,
                    max_accel_dps2=scenario.bd_kinematics.max_slew_accel_dps2,
                    settling_time_s=scenario.bd_kinematics.settling_time_s,
                    reacquire_time_s=scenario.bd_kinematics.reacquire_time_s,
                )
                bd_state = "SLEWING"
                bd_target_id = next_id
                bd_t_arrive = t + t_switch
                events.append(Event(t, next_id, "SLEW_START"))
            # else: no candidates → loop will exit on next check.

        # 3. End-of-loop check.
        if all(d.state in ("DESTROYED", "LEAKED", "TIMEOUT") for d in sim_drones):
            break
        # Defensive: if BD is IDLE and there are no engageable drones,
        # advance time by dt anyway so WAITING drones can get detected.
        # If everyone alive is WAITING and no one closes, t_max ends it.
        t += dt

    # ── Mark any leftover DETECTED/ENGAGED drones as TIMEOUT ─────
    for d in sim_drones:
        if d.state in ("DETECTED", "ENGAGED", "WAITING"):
            d.state = "TIMEOUT"
            r = range_to_bd_m(positions[d.drone_id])
            d.range_at_outcome_m = r
            d.bearing_at_outcome_deg = bearing_to_drone_deg(positions[d.drone_id])
            d.outcome_time_s = t
            if d.engage_starts_s and len(d.engage_ends_s) < len(d.engage_starts_s):
                d.engage_ends_s.append(t)
            events.append(Event(t, d.drone_id, "TIMEOUT"))

    # ── Build the immutable output ───────────────────────────────
    outcomes: list[DroneOutcome] = []
    _verdict_for_state = {
        "DESTROYED": "KILL",
        "LEAKED": "LEAK",
        "TIMEOUT": "TIMEOUT",
    }
    for d in sim_drones:
        verdict = _verdict_for_state.get(d.state, d.state)
        # Slew-to-first-engage time: difference between the SLEW_START
        # event and the first ENGAGE_START for this drone.
        slew_first = 0.0
        if d.engage_starts_s:
            first_engage = d.engage_starts_s[0]
            for ev in events:
                if ev.drone_id == d.drone_id and ev.kind == "SLEW_START":
                    slew_first = first_engage - ev.t_s
                    break
        engage_durations = tuple(
            end - start
            for start, end in zip(d.engage_starts_s, d.engage_ends_s)
        )
        outcomes.append(DroneOutcome(
            drone_id=d.drone_id,
            drone_type_key=d.drone_type_key,
            verdict=verdict,
            detect_time_s=d.detect_time_s,
            engage_starts_s=tuple(d.engage_starts_s),
            engage_durations_s=engage_durations,
            slew_time_to_first_engage_s=max(0.0, slew_first),
            cumulative_absorbed_J_per_cm2=d.cumulative_absorbed_J_per_cm2,
            E_fail_J_per_cm2=d.E_fail_J_per_cm2,
            range_at_outcome_m=d.range_at_outcome_m,
            bearing_at_outcome_deg=d.bearing_at_outcome_deg,
            outcome_time_s=d.outcome_time_s if d.outcome_time_s is not None else t,
        ))

    n_killed = sum(1 for o in outcomes if o.verdict == "KILL")
    n_leaked = sum(1 for o in outcomes if o.verdict == "LEAK")
    n_timeout = sum(1 for o in outcomes if o.verdict == "TIMEOUT")

    closest_leak = None
    if n_leaked:
        closest_leak = min(
            o.range_at_outcome_m for o in outcomes if o.verdict == "LEAK"
        )

    total_engagement_time = max((o.outcome_time_s for o in outcomes), default=0.0)
    timing = TimingBreakdown(
        slew_total_s=slew_total_s,
        engage_total_s=engage_total_s,
        idle_total_s=idle_total_s,
    )
    slew_fraction = (
        slew_total_s / total_engagement_time if total_engagement_time > 0 else 0.0
    )

    summary_payload = json.dumps({
        "n_killed": n_killed,
        "n_leaked": n_leaked,
        "n_timeout": n_timeout,
        "first_leak_time_s": (
            None if first_leak_time_s is None else round(first_leak_time_s, 3)
        ),
        "total": round(total_engagement_time, 3),
        "drone_verdicts": [(o.drone_id, o.verdict) for o in outcomes],
    }, sort_keys=True)
    summary_hash = hashlib.sha256(summary_payload.encode("utf-8")).hexdigest()[:16]

    return SwarmEngagementResult(
        drones=tuple(outcomes),
        n_killed=n_killed,
        n_leaked=n_leaked,
        n_timeout=n_timeout,
        first_leak_time_s=first_leak_time_s,
        total_engagement_time_s=total_engagement_time,
        timing_breakdown=timing,
        closest_leak_range_m=closest_leak,
        slew_fraction=slew_fraction,
        summary_hash=summary_hash,
        assumptions_flagged=STANDING_ASSUMPTIONS,
        event_log=tuple(events),
    )


__all__ = [
    "run_swarm_simulation",
    "SwarmEngagementResult",
    "DroneOutcome",
    "TimingBreakdown",
    "Event",
    "STANDING_ASSUMPTIONS",
]
