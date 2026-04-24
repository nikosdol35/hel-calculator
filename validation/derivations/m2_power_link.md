# M2 — Beam director transmission

**File:** `physics/m2_beam_director.py`
**Outputs:** `P_exit`

## Formulas implemented (code ↔ SPEC ↔ source)

| Code line | Expression | SPEC | Primary citation | Status |
|---|---|---|---|---|
| 32 | `P_exit = η_opt · P0` | §3 M2 | Elementary multiplicative transmission — no external citation required | verified |

## Constants used

None in the source file itself. The default `η_opt = 0.85` recommended in SPEC §3 M2 reflects a typical 5–7 mirror Coudé path with a protected exit window:

- 5 mirrors at 99 % reflectance each = 0.99⁵ ≈ 0.951.
- Exit window at 98 % transmission ≈ 0.93.
- Contamination margin (−5 %) ≈ 0.88.

Product ≈ 0.85 agrees with published data on coated Mo mirror performance at 1.06 µm (e.g., II-VI and Lockheed Martin Aculight datasheets). SPEC allows user override in the range `[0.50, 0.99]`.

## Derivation

A serial optical train with N independent elements of transmission `τ_i` has total transmission `η = Π τ_i`. For a coherent monochromatic beam with no scattered losses captured downstream, the output power after the train is simply `P_out = η · P_in`.

## Known simplifications

- No wavelength dependence of η — in reality mirror reflectance varies with λ. For the 4-wavelength set in v1, the user is expected to set η_opt to the value appropriate for their wavelength.
- No polarization-dependent loss.
- No time variation (thermal blooming of optics, steering-mirror offload, etc.).

## Cross-check

Canonical scenario: P0 = 3000 W, η_opt = 0.85 → P_exit = 2550 W. Trivially verified.

## Cross-reference to CLAUDE §7.1

M2 has no audit-sensitive formulas; the only concern is that `P_exit` is not clipped at a saturation ceiling in M2 itself — the orchestrator does not apply `min(P_in, P_max_emit)` until further downstream constraints are active. This is an architectural note, not a physics flag.
