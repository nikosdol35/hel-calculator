# M3 — Engagement geometry

**File:** `physics/m3_geometry.py`
**Outputs:** `R_slant`, `R_h`, `elevation_angle`, `available_dwell`

## Formulas implemented (code ↔ SPEC ↔ source)

| Code line | Expression | SPEC | Primary citation | Status |
|---|---|---|---|---|
| 57 | `R_slant = R` (pass-through) | §3 M3 | — | verified |
| 58 | `R_h = √(R² − (H_t − H_e)²)` | §3 M3 | Elementary Euclidean geometry | verified |
| 59 | `elevation_angle = atan2(ΔH, R_h)` | §3 M3 | Elementary trigonometry | verified |
| 61–65 | `available_dwell = 2R·tan(FOV/2) / v_tgt` | §3 M3 + §10.5 | Engagement-basket heuristic (SPEC §10.5) | verified but HIGH UNCERTAINTY |

## Constants used

| Constant | Value | Units | Source |
|---|---|---|---|
| `_FOV_DEG_DEFAULT` (line 17) | 5.0 | deg | SPEC §10.5 heuristic — HIGH UNCERTAINTY; deferred-to-v2 full tracker model |

Input bounds: `H_e ∈ [0, 3000] m`, `R ∈ [50, 50000] m`, `H_t ∈ [0, 5000] m`, `v_tgt ∈ [0, 100] m/s`, `v_perp ∈ [0, 30] m/s`. All ranges audited in `input_bounds_audit.md`.

## Derivation

Given emplacement altitude `H_e` and target altitude `H_t`, the height differential `ΔH = H_t − H_e` and the user-input slant range `R`. The geometry is a right triangle with hypotenuse `R`, vertical leg `|ΔH|`, horizontal leg `R_h`:

```
R_h = √(R² − ΔH²)           [Pythagoras]
elevation_angle = atan2(ΔH, R_h)   [positive looking up]
```

Feasibility: `R ≥ |ΔH|` is required, enforced at line 52–55 with an explicit `ValueError` (fail-fast; no silent coercion).

The `available_dwell` heuristic assumes the target crosses a conical engagement basket of half-angle `FOV/2` centered on the emplacement-target line of sight. The basket has linear extent `2·R·tan(FOV/2)` at slant range R; the target traverses this at speed `v_tgt`, giving the dwell window:

```
available_dwell = 2·R·tan(FOV/2) / v_tgt
```

At `v_tgt = 0` (stationary target), dwell is infinite.

**SPEC §10.5 HIGH UNCERTAINTY flag.** This is a deliberately-simple heuristic. A real tracker dwell depends on gimbal dynamics, target maneuver, jitter envelope, slew-rate limits, and sensor acquisition. The 5° FOV is a conservative mid-range value for a pointing-servo acquisition window.

## Known simplifications

- Flat-earth geometry — curvature neglected. Error at max range 50 km ≈ 50² / (2·6371) ≈ 0.2 m drop, smaller than jitter.
- No atmospheric refraction correction.
- `_FOV_DEG_DEFAULT` is fixed; the full tracker-dependent dwell model is v2.
- `v_perp` is captured in M3 inputs for contractual cleanliness but consumed by M6 (thermal blooming); M3 does not use it.

## Cross-check

Canonical scenario (C-UAS 1500 m preset): H_e = 2 m, R = 1500 m, H_t = 200 m, v_tgt = 20 m/s.

Hand computation:
- ΔH = 200 − 2 = 198 m.
- R_h = √(1500² − 198²) = √(2,250,000 − 39,204) = √2,210,796 = 1486.87 m.
- elevation_angle = atan2(198, 1486.87) = 0.1325 rad = 7.59°.
- available_dwell = 2·1500·tan(2.5°) / 20 = 3000·0.04366 / 20 = 6.55 s.

## Cross-reference to CLAUDE §7.1

M3 has no audit-sensitive formulas. The SPEC §10.5 flag is explicit in every output; this derivation file confirms the heuristic is not silently promoted to a defended value.
