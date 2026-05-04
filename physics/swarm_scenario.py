"""Scenario data model + JSON serialization for the Swarm Analyzer.

Defines the immutable dataclasses that describe a swarm engagement
scenario before the simulation runs:

  * ``Drone`` — one drone's initial state (position, velocity, type).
  * ``BDKinematics`` — beam-director slew/settle/reacquire parameters.
  * ``SwarmScenario`` — the full scenario container: drones + BD +
    sidebar inputs (HEL params, atmosphere, R_min, detection range,
    strategy, timestep).

Plus JSON round-trip via ``to_json`` / ``from_json``. The on-disk
schema is versioned (``"version": "1"``) so we can evolve later
without breaking saved scenarios. ``from_json`` validates the schema
version and the drone-type keys; bad inputs raise ``ValueError``
with a clear message instead of silently producing garbage.

No Streamlit imports — pure module, easy to test in isolation.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from typing import Any

from physics.swarm_drone_types import DRONE_TYPES


# Schema version bumped on any backward-incompatible change to the
# JSON shape. ``from_json`` rejects unknown versions.
SCENARIO_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class Drone:
    """One drone in the swarm scenario.

    Attributes:
      drone_id: stable integer ID, assigned at scenario-build time.
        IDs are deterministic so test golden-scenarios round-trip.
      drone_type_key: key into ``swarm_drone_types.DRONE_TYPES``
        (``"commercial_quad"`` / ``"mini_fixed_wing"`` /
        ``"group1_kamikaze"``).
      position_m: starting (x, y) position in metres, BD at origin.
      velocity_mps: velocity vector (vx, vy) in m/s. The simulation
        moves the drone in a straight line at constant velocity.
    """
    drone_id: int
    drone_type_key: str
    position_m: tuple[float, float]
    velocity_mps: tuple[float, float]

    def __post_init__(self):
        if self.drone_type_key not in DRONE_TYPES:
            raise ValueError(
                f"unknown drone_type_key {self.drone_type_key!r}; "
                f"valid keys: {sorted(DRONE_TYPES.keys())}"
            )
        if len(self.position_m) != 2 or len(self.velocity_mps) != 2:
            raise ValueError(
                "position_m and velocity_mps must be 2-tuples (x, y)"
            )

    @property
    def speed_mps(self) -> float:
        vx, vy = self.velocity_mps
        return math.sqrt(vx * vx + vy * vy)

    @property
    def initial_range_m(self) -> float:
        x, y = self.position_m
        return math.sqrt(x * x + y * y)

    @property
    def initial_bearing_deg(self) -> float:
        """Bearing from BD (origin) to drone, in degrees [-180, 180]."""
        x, y = self.position_m
        return math.degrees(math.atan2(y, x))


@dataclass(frozen=True)
class BDKinematics:
    """Beam-director slewing parameters.

    Defaults are the generic "mid-class HEL turret" values from the
    plan §1 (60 deg/s, 120 deg/s², 0.2 s settle, 0.15 s reacquire).
    Operator-overridable per simulation.

    Attributes:
      max_slew_rate_dps: peak angular rate the BD can sustain (deg/s).
      max_slew_accel_dps2: acceleration to reach max rate (deg/s²).
      settling_time_s: post-slew mechanical settling.
      reacquire_time_s: tracker re-lock onto the new target.
      initial_bearing_deg: BD's starting bearing at t=0; the first
        slew is FROM this bearing TO the first scheduled target.
    """
    max_slew_rate_dps: float = 60.0
    max_slew_accel_dps2: float = 120.0
    settling_time_s: float = 0.2
    reacquire_time_s: float = 0.15
    initial_bearing_deg: float = 0.0

    def __post_init__(self):
        if self.max_slew_rate_dps <= 0 or self.max_slew_accel_dps2 <= 0:
            raise ValueError(
                "BD slew rate and accel must be positive"
            )
        if self.settling_time_s < 0 or self.reacquire_time_s < 0:
            raise ValueError(
                "BD settling and reacquire times must be non-negative"
            )


@dataclass(frozen=True)
class SwarmScenario:
    """Complete swarm engagement scenario — input to the orchestrator.

    Carries everything the simulation needs:
      - a tuple of drones (initial states)
      - BD kinematics
      - the HEL sidebar inputs (a flat dict — same keys the HEL
        chain consumes; lets us reuse the lightweight chain helper
        without re-mapping)
      - simulation-control knobs (R_min, detection range, strategy,
        timestep)

    Frozen + immutable so it can be hashed for the lightweight-chain
    LRU cache and the sensitivity panel's session-state cache.
    """
    drones: tuple[Drone, ...]
    bd_kinematics: BDKinematics
    hel_inputs: dict
    R_min_m: float = 100.0
    R_detect_max_m: float = 3000.0
    strategy: str = "earliest_leak_first"
    dt_s: float = 0.05
    t_max_s: float = 300.0

    def __post_init__(self):
        if self.strategy not in (
            "earliest_leak_first", "closest_first", "easiest_kill_first"
        ):
            raise ValueError(
                f"unknown strategy {self.strategy!r}; valid: "
                f"earliest_leak_first / closest_first / easiest_kill_first"
            )
        if self.dt_s <= 0 or self.t_max_s <= 0:
            raise ValueError("dt_s and t_max_s must be positive")
        if self.R_min_m <= 0 or self.R_detect_max_m <= 0:
            raise ValueError("R_min_m and R_detect_max_m must be positive")
        if self.R_detect_max_m <= self.R_min_m:
            raise ValueError(
                "R_detect_max_m must be greater than R_min_m"
            )
        # Drone-id uniqueness (defensive — the UI assigns them
        # uniquely, but a hand-written JSON could collide).
        ids = [d.drone_id for d in self.drones]
        if len(ids) != len(set(ids)):
            raise ValueError("drone IDs must be unique")

    # ------------------------------------------------------------------
    # JSON serialization
    # ------------------------------------------------------------------
    def to_json(self) -> str:
        """Serialize to a stable JSON string. Used by the "Download
        scenario" UI button and by the golden-test harness."""
        payload = {
            "version": SCENARIO_SCHEMA_VERSION,
            "drones": [
                {
                    "drone_id": d.drone_id,
                    "drone_type_key": d.drone_type_key,
                    "position_m": list(d.position_m),
                    "velocity_mps": list(d.velocity_mps),
                }
                for d in self.drones
            ],
            "bd_kinematics": asdict(self.bd_kinematics),
            "hel_inputs": dict(self.hel_inputs),
            "R_min_m": self.R_min_m,
            "R_detect_max_m": self.R_detect_max_m,
            "strategy": self.strategy,
            "dt_s": self.dt_s,
            "t_max_s": self.t_max_s,
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, json_blob: str) -> "SwarmScenario":
        """Parse a JSON blob back into a SwarmScenario. Raises
        ``ValueError`` with a descriptive message on bad input —
        invalid JSON, wrong schema version, unknown drone type,
        missing required field."""
        try:
            payload = json.loads(json_blob)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise ValueError(
                f"invalid JSON: expected object, got {type(payload).__name__}"
            )

        version = payload.get("version")
        if version != SCENARIO_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported scenario schema version {version!r}; "
                f"this build expects {SCENARIO_SCHEMA_VERSION!r}"
            )

        try:
            drones = tuple(
                Drone(
                    drone_id=int(d["drone_id"]),
                    drone_type_key=str(d["drone_type_key"]),
                    position_m=tuple(d["position_m"]),
                    velocity_mps=tuple(d["velocity_mps"]),
                )
                for d in payload["drones"]
            )
            bd = BDKinematics(**payload["bd_kinematics"])
            return cls(
                drones=drones,
                bd_kinematics=bd,
                hel_inputs=dict(payload["hel_inputs"]),
                R_min_m=float(payload.get("R_min_m", 100.0)),
                R_detect_max_m=float(payload.get("R_detect_max_m", 3000.0)),
                strategy=str(payload.get("strategy", "earliest_leak_first")),
                dt_s=float(payload.get("dt_s", 0.05)),
                t_max_s=float(payload.get("t_max_s", 300.0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"scenario JSON missing or malformed: {exc}"
            ) from exc


__all__ = [
    "Drone",
    "BDKinematics",
    "SwarmScenario",
    "SCENARIO_SCHEMA_VERSION",
]
