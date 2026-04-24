# M11 — Engagement dwell heuristic

**Scope note.** SPEC and ARCHITECTURE treat the dwell-window calculation as conceptually distinct from pure slant-range geometry (M3), but the v1 code places the formula in `physics/m3_geometry.py` (line 61–65) to avoid a one-line separate module. This derivation documents the dwell heuristic as a logically-separate concern; the code hand-off is the line pointer above.

**File:** `physics/m3_geometry.py` (lines 17, 61–65)
**Output:** `available_dwell`

## Formula implemented (code ↔ SPEC ↔ source)

| Code line | Expression | SPEC | Primary citation | Status |
|---|---|---|---|---|
| 17 | `_FOV_DEG_DEFAULT = 5.0°` | §3 M3 + §10.5 | Engineering heuristic | HIGH UNCERTAINTY — SPEC §10.5 |
| 61 | `fov_rad = radians(_FOV_DEG_DEFAULT)` | §3 M3 | Deg→rad | verified |
| 62–63 | `if v_tgt == 0: available_dwell = ∞` | §3 M3 | Stationary-target convention | verified |
| 65 | `available_dwell = 2·R · tan(FOV/2) / v_tgt` | §3 M3 | Engagement-basket heuristic | verified formula; HIGH UNCERTAINTY on coefficient |

## Constants used

| Constant | Value | Units | Source | Status |
|---|---|---|---|---|
| `_FOV_DEG_DEFAULT` (m3_geometry.py:17) | 5.0 | deg | SPEC §10.5 mid-range tracker-acquisition FOV | HIGH UNCERTAINTY — SPEC §10.5 |

## Derivation

### Engagement-basket geometry

The engagement basket is a cone of half-angle `FOV/2` centered on the emplacement-target line of sight. At slant range R, the basket has linear cross-section:

```
basket_width = 2·R·tan(FOV/2)
```

A target traversing perpendicular to the line of sight at speed `v_tgt` crosses this width in time:

```
available_dwell = basket_width / v_tgt = 2·R·tan(FOV/2) / v_tgt          (line 65)
```

At `v_tgt = 0` the target is stationary — nominally infinite dwell, coded as `float("inf")` (line 63).

### Why 5°

The `_FOV_DEG_DEFAULT = 5°` is an engineering mid-range for a pointing-servo acquisition window. Real tracker dwell is dominated by:

1. **Slew-rate limits** of the gimbal (typical 50–200°/s).
2. **Target maneuver** (for UAS/rocket targets, lateral acceleration up to several g).
3. **Jitter envelope** (already captured in M7).
4. **Sensor acquisition** — Track While Scan vs Track While Engage transition time.

A 5° FOV is a commonly cited figure for the union of these — narrow enough to not trivially give infinite dwell, wide enough to not under-predict for gently-maneuvering targets. It is explicitly SPEC §10.5 HIGH UNCERTAINTY and flagged on every M3 call (line 67–69).

**Why not smaller** (e.g., 1°): would under-predict for targets that pass close to directly overhead (short crossing distance even at 1° FOV at 10+ km range).

**Why not larger** (e.g., 10°): would over-predict for real track-engage windows where the tracker must stabilize after acquisition before firing is authorized.

### Sensitivity

At R = 1500 m, v_tgt = 20 m/s, FOV = 5°:
- `basket_width = 2·1500·tan(2.5°) = 3000·0.04366 = 131 m`.
- `available_dwell = 131/20 = 6.55 s`.

Changing FOV from 5° to 3° would give `available_dwell = 3.93 s` (a 40% reduction). The heuristic is first-order sensitive to FOV — this is why it carries a HIGH UNCERTAINTY flag.

At R = 10000 m, v_tgt = 80 m/s (long-range cruise-missile scenario), FOV = 5°:
- `basket_width = 2·10000·tan(2.5°) = 873 m`.
- `available_dwell = 873/80 = 10.9 s`.

Typical numbers are a few seconds to tens of seconds — consistent with field-reported HEL engagements where track and engage windows of 3–15 s are cited.

## Known simplifications

- **Fixed FOV** independent of range and target class. A real tracker narrows FOV with acquisition maturity and target velocity. SPEC §10.5 flags this for v2 re-scoping.
- **Linear cross-flight** — assumes the target moves perpendicular to LoS at constant speed `v_tgt`. Closing-trajectory or turning targets have different geometry.
- **No tracker dynamics** — ignores slew rate, acquisition latency, track-to-engage transition.
- **No sensor constraints** — ignores plume masking, aspect changes, countermeasure dispensing.
- **No environmental occlusion** — ignores cloud transit, terrain masking, solar glare.
- **v_tgt = 0 → infinite dwell** — physically correct for a stationary target (static UAS, ground vehicle), but the coolant/power limits (M10) still apply.

## Cross-check

Canonical scenario (C-UAS 1500 m preset): R = 1500 m, v_tgt = 20 m/s, FOV = 5° (default).

Hand computation:
- `tan(2.5°) = 0.04366`.
- `basket_width = 2 · 1500 · 0.04366 = 130.98 m`.
- `available_dwell = 130.98 / 20 = 6.549 s`.

Independent verification with `physics/m3_geometry.py:compute` returns `available_dwell = 6.549 s` to 4 sig figs. ✓

Edge case: v_tgt = 0 → `available_dwell = inf` ✓ (tested in Layer 2 helper tests).

## Cross-reference to CLAUDE §7.1

M11 has no CLAUDE §7.1 invariants — there is no specific previous-audit error to guard against. The entire concern is:

- **SPEC §10.5 HIGH UNCERTAINTY on the 5° FOV** — flagged in every M3 call's `assumptions_flagged` output.
- **Layer 4 decision point.** During Package 4 (HIGH UNCERTAINTY closeout), the team decides: (a) keep 5° with a better-defended rationale, (b) make FOV a user input, or (c) defer the full tracker-dependent dwell model to v2 (current SPEC §10.5 position).

The dwell heuristic is included in the validation tree because `available_dwell` is presented to the user as a defended number on Plot B (engageable band / dwell vs burn-through); every number the tool prints must trace back to its derivation even if the derivation is "engineering heuristic with an explicit uncertainty flag."
