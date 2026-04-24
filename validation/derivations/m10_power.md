# M10 — Power and thermal budget

**File:** `physics/m10_power_thermal.py`
**Outputs:** `P_in`, `Q_waste`, `t_sustain`, `engagement_viable`, `duty_cycle_limit`, `engagements_per_hour`

## Formulas implemented (code ↔ SPEC ↔ source)

| Code line | Expression | SPEC | Primary citation | Status |
|---|---|---|---|---|
| 79 | `P_in = P0 / η_wallplug` | §3 M10 | Elementary efficiency | verified |
| 80 | `Q_waste = P_in − P0 = P0·(1/η − 1)` | §3 M10 | Energy balance | verified |
| 86–88 | Steady-state branch: `t_sustain = ∞`, `duty = 1` | §3 M10 | `Q_waste ≤ Q_cool` → no coolant accumulation | verified |
| 93 | Transient: `t_sustain = C_thermal·dT_max / (Q_waste − Q_cool)` | §3 M10 | Lumped-mass energy balance | verified |
| 95 | `recovery_time = C_thermal·dT_max / Q_cool` | §3 M10 | Same lumped mass, cooling branch | verified |
| 96 | `duty = t_sustain / (t_sustain + recovery_time)` | §3 M10 | Engineering duty cycle | verified |
| 105 | `engagements_per_hour = 3600 · duty / t_engagement` | §3 M10 | Elementary arithmetic | verified |
| 107 | `engagement_viable = (t_engagement ≤ t_sustain)` | §3 M10 | Threshold comparison | verified |

## Constants used

| Constant | Value | Units | Source |
|---|---|---|---|
| `3600` (line 88, 105) | 3600 | s/hour | Elementary unit conversion |

No other constants in M10. All inputs are user-supplied, and bounds are:
- `η_wallplug ∈ [0.05, 0.50]` (line 50) — sanity range for HEL cooling-efficiency; diode-pumped fiber lasers typically 0.25–0.40.
- `dT_max ∈ [5, 80] K` (line 54) — coolant dT-rise tolerance; tight for precision-optics coolant, looser for bulk cooling loops.

## Derivation

### Lumped-mass model

The coolant loop is treated as a single thermal capacitance `C_thermal` (units J/K) with a constant cooling-plant capacity `Q_cool` (units W). Waste heat `Q_waste` enters the capacitance at a constant rate during the engagement; coolant temperature rises from baseline.

Energy balance during the engagement:

```
C_thermal · dT/dt = Q_waste − Q_cool                    (transient regime)
```

Integrating from T = T_baseline at t = 0 to T = T_baseline + dT_max at t = t_sustain:

```
C_thermal · dT_max = (Q_waste − Q_cool) · t_sustain
t_sustain = C_thermal · dT_max / (Q_waste − Q_cool)              (line 93)
```

This is the time for coolant to reach the dT_max limit — beyond which laser performance degrades (thermal lensing in the gain medium, wavelength drift, power derate) or an interlock trips.

### Steady-state branch

If `Q_waste ≤ Q_cool`, the cooling plant can remove waste heat as fast as it is generated. Coolant dT does not rise above the steady-state offset; `t_sustain = ∞` and duty cycle is 1 (line 86–88).

### Recovery time

After the engagement ends, cooling continues at `Q_cool`; temperature returns to baseline at:

```
recovery_time = C_thermal · dT_max / Q_cool                      (line 95)
```

### Duty cycle

One run-recover cycle has duration `t_sustain + recovery_time`; during `t_sustain` the laser fires, during `recovery_time` it is down. Long-term duty cycle:

```
duty_cycle_limit = t_sustain / (t_sustain + recovery_time)       (line 96)
```

At `Q_cool → Q_waste` (limit): `recovery_time → ∞` but `t_sustain → ∞` faster (both denominators). Actually as `Q_cool → Q_waste⁻`, `t_sustain → ∞` via the `Q_waste − Q_cool → 0` denominator, while `recovery_time` is finite. So `duty → 1` smoothly — consistent with the steady-state branch at the boundary.

At `Q_cool → 0`: `recovery_time → ∞` and `duty → 0` — single-shot regime. Code handles this explicitly (line 99–104) with a flag.

### Engagements per hour

Converting duty cycle to rate:

```
engagements_per_hour = (seconds_per_hour · duty) / seconds_per_engagement
                     = 3600 · duty / t_engagement                (line 105)
```

### Engagement viability

Boolean threshold (line 107):

```
engagement_viable ⟺ t_engagement ≤ t_sustain
```

In the steady-state branch this is always `True` (any finite engagement is ≤ ∞). In the transient branch, the engagement is viable only if `t_engagement` fits inside the single-run window `t_sustain`.

## Known simplifications

- **Single lumped thermal mass.** A real HEL cooling loop has multiple stages (gain medium, pump diodes, optics, heat exchanger, coolant reservoir) each with its own C and Q_max. The lumped-mass model treats them as one; numerically equivalent to the weakest-link stage with the smallest `C_thermal · dT_max / (Q_waste_stage − Q_cool_stage)`.
- **Q_waste held constant during engagement.** In reality, gain-medium temperature rises during an engagement causing η to droop, increasing Q_waste. Conservative for viability (underestimates Q_waste at end of engagement).
- **Q_cool held at rated capacity during recovery.** Real chillers have transient behaviour; rated capacity is an average. For short engagements (< 10 s) this is accurate; for multi-minute duty cycles the real recovery is slightly slower.
- **No ramp-up of P0.** Assumes P0 jumps instantly from 0 to full at engagement start. For HEL systems with soft-start (50–200 ms) the waste-heat integral is marginally lower.
- **Does not model ambient-air-cooled final-stage heat rejection.** Q_cool is abstracted as a single number; users pick it.

## Cross-check

Canonical scenario (C-UAS 1500 m preset): P0 = 3000 W, η = 0.30, Q_cool = 8000 W, C_thermal = 40000 J/K, dT_max = 20 K, t_engagement = 5 s (from M8 tau_BT).

Hand computation:
- `P_in = 3000 / 0.30 = 10000 W = 10 kW`.
- `Q_waste = 10000 − 3000 = 7000 W = 7 kW`.
- `Q_waste (7 kW) ≤ Q_cool (8 kW)` → steady-state branch.
- `t_sustain = ∞`.
- `duty_cycle_limit = 1.0`.
- `engagements_per_hour = 3600 / 5 = 720`.
- `engagement_viable = True`.

Second scenario — undersized chiller: same inputs but `Q_cool = 4000 W`.
- `Q_waste (7 kW) > Q_cool (4 kW)` → transient branch.
- `t_sustain = 40000 · 20 / (7000 − 4000) = 800000 / 3000 = 266.7 s`.
- `recovery_time = 40000 · 20 / 4000 = 200 s`.
- `duty = 266.7 / (266.7 + 200) = 266.7 / 466.7 = 0.571`.
- `engagements_per_hour = 3600 · 0.571 / 5 = 411`.
- `engagement_viable = True` (5 s ≪ 266 s).

Third scenario — 30 kW laser, rocket engagement: P0 = 30000 W, η = 0.25, Q_cool = 30000 W, C = 100000 J/K, dT_max = 15 K, t_engagement = 2 s.
- `P_in = 30000 / 0.25 = 120 kW`; `Q_waste = 90 kW > Q_cool = 30 kW`.
- `t_sustain = 100000 · 15 / (90000 − 30000) = 1500000 / 60000 = 25.0 s`.
- `recovery_time = 100000 · 15 / 30000 = 50 s`.
- `duty = 25 / 75 = 0.333`; engagements/hour = 3600·0.333/2 = 600.
- `engagement_viable = True` (2 s < 25 s).

Independent verification with `physics/m10_power_thermal.py:compute` reproduces all values exactly.

## Cross-reference to CLAUDE §7.1

M10 has no CLAUDE §7.1 audit-sensitive items — it is elementary arithmetic over engineering parameters. The only concerns are:
- The multiplicative 3600 s/h is trivially verified.
- The `duty_cycle_limit` formula as `t_sustain / (t_sustain + recovery_time)` (line 96) assumes the run-recover cycle is repeated indefinitely; if the user wants a single-shot engagement they should ignore `duty_cycle_limit` and `engagements_per_hour`.
- Boundary behaviour at `Q_cool = 0` (line 97–104) and at `Q_waste = Q_cool` (steady-state branch boundary, line 84) are handled explicitly; no division-by-zero.
