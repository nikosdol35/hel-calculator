# M8 — Material burn-through

**Files:** `physics/m8_burnthrough.py`, `physics/m8_material_tables.py`
**Outputs:** `tau_BT`, `T_surface_peak`, `E_delivered`, `failure_mode`

## Formulas implemented (code ↔ SPEC ↔ source)

| Code line | Expression | SPEC | Primary citation | Status |
|---|---|---|---|---|
| 128–131 | `dx = min(50 µm, thickness/20)`; re-solve dx exactly | §3 M8 | Explicit-FD grid prescription | verified |
| 132 | `α_diff = k / (ρ·c_p)` | §3 M8 | Elementary thermal diffusivity | verified |
| 133 | `dt = 0.4 · dx² · ρ·c_p / k` | §3 M8 | Explicit-FD stability (CFL-like) | verified; safety factor 0.4 |
| 136 | `h_conv = 10 + 6.2·√v_tgt` | §3 M8 | Natural + forced flat-plate convection fit | HIGH UNCERTAINTY — SPEC §10.6 |
| 161 | `conv_loss = h·(T_s − T_amb)` | §3 M8 | Newton's law of cooling | verified |
| 162 | `rad_loss = ε·σ_SB·(T_s⁴ − T_amb⁴)` | §3 M8 | Stefan-Boltzmann grey-body | verified |
| 163 | `net_surface_flux = A_λ·I − conv − rad` | §3 M8 | Energy balance at x=0 | verified |
| 196 | Interior: `T_new[i] = T[i] + r·(T[i-1]−2T[i]+T[i+1])` | §3 M8 | Central-difference explicit FD | verified (Carslaw & Jaeger §8) |
| 206 | Surface ghost-cell: `T_new[0] = T[0] + 2r·(T[1]−T[0]) + r·(2dx/k)·q_net` | §3 M8 | Ghost-cell Neumann BC | verified |
| 210 | Insulated backside: `T_new[-1] = T[-1] + 2r·(T[-2]−T[-1])` | §3 M8 | Zero-flux ghost cell | verified |
| 213 | Convective backside: ghost-cell with `−h·(T_back−T_amb)` | §3 M8 | Convective BC ghost cell | verified |
| 167–174 | Melt: clamp `T_s = T_fail`, accumulate `melt_energy` against `ρ·L_f·thickness` | §3 M8 | Stefan condition (simplified) | verified |
| 177–185 | Decomposition: `T_s ≥ T_fail` sustained ≥ 0.05 s | §3 M8 | Engineering criterion | verified |
| 186–190 | Vent: `T_s ≥ 420 K` (LiPo) | §3 M8 | Sandia SAND2014-18253 | verified |
| 230 | `E_delivered = A_λ · I · tau_BT` | §3 M8 | Time-integrated absorbed flux | verified |
| 277–289 | Linear-in-wavelength A_λ interp | §3 M8 | Bounded, near-linear quantity | verified |

## Constants used

| Constant | Value | Units | Source | Status |
|---|---|---|---|---|
| `_DX_TARGET` (line 41) | 5.0e-5 | m | SPEC §3 M8 — 50 µm target grid | verified |
| `_N_MIN` (line 42) | 21 | — | 20 intervals minimum (SPEC §3 M8) | verified |
| `_STABILITY_SAFETY` (line 43) | 0.4 | — | Explicit-FD Fourier-number safety factor; `r = α·dt/dx² = 0.4 < 0.5` | verified |
| `_SIM_TIMEOUT_S` (line 44) | 60.0 | s | SPEC §3 M8 integration timeout | verified |
| `_DECOMP_SUSTAIN_S` (line 45) | 0.05 | s | SPEC §3 M8 decomposition hold time | verified |
| `10` + `6.2·√v_tgt` (line 136) | W/(m²·K) | Engineering convection correlation | Incropera & DeWitt §7 + free-convection baseline ~10 W/m²K | HIGH UNCERTAINTY — SPEC §10.6 |
| `EMISSIVITY_IR_DEFAULT` (tables.py 22) | 0.85 | — | SPEC §3 M8 default across materials | verified (engineering default) |
| `SIGMA_SB` (tables.py 25) | 5.670374419e-8 | W/(m²·K⁴) | CODATA 2018 exact | verified |

### Material property table (tables.py 30–87)

| Material | ρ (kg/m³) | c_p (J/kg·K) | k (W/m·K) | T_fail (K) | L_f (J/kg) | Failure mode |
|---|---|---|---|---|---|---|
| anodized_Al | 2700 | 900 | 200 | 933 | 397 000 | melt |
| CFRP | 1600 | 1000 | 7.0 | 600 | — | decomposition |
| GFRP | 1900 | 800 | 0.4 | 600 | — | decomposition |
| polycarbonate | 1200 | 1200 | 0.2 | 700 | — | decomposition |
| ABS | 1050 | 1400 | 0.17 | 670 | — | decomposition |
| EPP_foam | 30 | 1900 | 0.04 | 620 | — | decomposition |
| LiPo | 1800 | 1000 | 0.5 | 420 | — | vent |

Sources (from tables.py docstring):
- **anodized_Al** — ASM Handbook Vol. 2 (aluminium 6061-T6 typical).
- **CFRP** — Hexcel 8552/Toray T700 datasheets; vendor variance ±20–40%.
- **GFRP** — OCV E-glass datasheet.
- **polycarbonate, ABS, EPP** — ASM Engineered Plastics Handbook; Matweb aggregated.
- **LiPo** — Sandia SAND2014-18253, SAND2018-12007 (18650 cell bulk averages; vent onset 420 K).

### A_λ absorptivity table (tables.py 95–105)

Tabulated at `(1.06, 1.07, 1.55, 2.05) µm`. All 28 values HIGH UNCERTAINTY (SPEC §10.2).

| Material | 1.06 µm | 1.07 µm | 1.55 µm | 2.05 µm | Notes |
|---|---|---|---|---|---|
| anodized_Al | 0.30 | 0.30 | 0.25 | 0.20 | Aluminum oxide coating; decreases into NIR |
| CFRP | 0.85 | 0.85 | 0.85 | 0.85 | Carbon is near-perfect absorber |
| GFRP | 0.40 | 0.40 | 0.45 | 0.55 | Glass + epoxy; absorption rises at 2 µm |
| polycarbonate | 0.10 | 0.10 | 0.30 | 0.60 | Transparent at 1 µm, strong C-H at 2 µm |
| ABS | 0.70 | 0.70 | 0.75 | 0.85 | Pigmented; relatively flat |
| EPP_foam | 0.50 | 0.50 | 0.55 | 0.70 | Low-density polymer |
| LiPo | 0.30 | 0.30 | 0.35 | 0.45 | Metal-cased cell exterior |

All values flagged SPEC §10.2 HIGH UNCERTAINTY — refine via Bergstrom 2007 or measured data before formal use.

## Derivation

### 1-D transient conduction PDE

Fourier heat equation in one spatial dimension (thickness direction), no internal heat generation:

```
ρ·c_p·∂T/∂t = k·∂²T/∂x²          0 ≤ x ≤ L
```

(Carslaw & Jaeger 1959 §1.6.) With thermal diffusivity `α = k/(ρ·c_p)`:

```
∂T/∂t = α · ∂²T/∂x²
```

### Surface boundary condition (x = 0)

Energy balance at the illuminated face:

```
absorbed laser flux = conducted flux into the material + convective loss + radiative loss
```

```
A_λ · I_aim = −k·(∂T/∂x)|_{x=0} + h·(T_s − T_amb) + ε·σ_SB·(T_s⁴ − T_amb⁴)
```

Rearranged (line 163):

```
−k·∂T/∂x|_{x=0} = A_λ·I_aim − h·(T_s − T_amb) − ε·σ_SB·(T_s⁴ − T_amb⁴)   =  q_net
```

### Backside BC (x = L)

- **Insulated:** `∂T/∂x|_{x=L} = 0` — appropriate for a thin panel isolated from a structure.
- **Convective:** `−k·∂T/∂x|_{x=L} = h·(T_back − T_amb)` — convective coupling to ambient air.

### Explicit FD discretization

Central difference in space, forward Euler in time:

```
T_new[i] = T[i] + r · (T[i−1] − 2·T[i] + T[i+1])     for interior 0 < i < N-1
r = α · dt / dx²                                     (Fourier number per step)
```

Stability (von Neumann): `r ≤ 0.5`. The code uses `r = 0.4` (line 43, 133) — safety factor 0.8.

### Ghost-cell Neumann BC

For a Neumann condition `−k·∂T/∂x = q` at x = 0, introduce a ghost node `T[−1]` such that

```
T[1] − T[−1]       2·dx
─────────── = ────── · q ,     i.e. T[−1] = T[1] + (2·dx/k)·q
   2·dx              k
```

Substituting into the central-difference stencil at i = 0:

```
T_new[0] = T[0] + r · (T[−1] − 2·T[0] + T[1])
         = T[0] + r · (2·T[1] − 2·T[0] + (2·dx/k)·q)
         = T[0] + 2·r·(T[1] − T[0]) + r·(2·dx/k)·q            (line 206)
```

The factor-of-2 on the interior-difference term (`2r` not `r`) is characteristic of the ghost-cell method and is **often omitted in error** (a bug that halves the near-surface heat penetration rate). The code carries it correctly. Analogous stencil at x = L (lines 210, 213) with zero flux (insulated) or `−h·(T_back−T_amb)` (convective).

### Grid sizing

`dx = min(50 µm, thickness/20)` (line 128). Rationale:
- 50 µm is a fine-enough step that the surface-temperature rise is well-resolved on metals (thermal penetration depth at ms scales is ~100 µm for Al, ~50 µm for polymers).
- `thickness/20` ensures at least 20 intervals — resolves the thermal wave for thin targets.
- After `n_nodes = round(thickness/dx)+1`, dx is re-solved so `thickness = (n_nodes−1)·dx` exactly (line 131) — avoids a cumulative thickness error.

### Time step

`dt = 0.4 · dx² · ρ·c_p / k = 0.4 · dx²/α` (line 133). For Al (α = 8.2e-5) at dx = 50 µm:
- `dt = 0.4 · (5e-5)² / 8.2e-5 = 0.4 · 3.05e-5 = 1.22e-5 s = 12 µs`.

For polycarbonate (α = 1.4e-7) at dx = 50 µm:
- `dt = 0.4 · (5e-5)² / 1.4e-7 = 7.1e-3 s = 7.1 ms`.

Timeout `60 s / 7.1 ms = 8450 steps` max — comfortable.

### Melt handling (metals, Al)

Stefan condition: once `T_s ≥ T_fail` (melt point), the surface is clamped at T_fail (phase-front Dirichlet BC, line 202). Net absorbed flux at the surface accumulates against the latent-heat budget:

```
melt_energy += net_surface_flux · dt          (line 170)
melt_budget  = ρ · L_f · thickness            (line 146)
```

When `melt_energy ≥ melt_budget`, burn-through declared; `tau_BT = t` (line 171–174).

**Engineering simplification.** This assumes the full thickness melts in parallel — the energy budget is `ρ · L_f · thickness` not `ρ · L_f · δ_front(t)` with a moving front. For aluminium (k = 200, high diffusivity), the interior reaches T_melt before the front has traveled a small fraction of the thickness, so the full-thickness budget is approximately right. For low-k metals it would over-estimate the time. Not a concern for the v1 material set (only Al is metal).

### Decomposition and vent

Non-melting modes — failure when surface temperature reaches a decomposition/vent threshold:
- **Decomposition** (CFRP, GFRP, PC, ABS, EPP): `T_s ≥ T_fail` sustained for `_DECOMP_SUSTAIN_S = 0.05 s` (line 179–183). The 50 ms hold avoids declaring failure on numerical transients; it is an engineering threshold, not a rigorous pyrolysis model. Above `T_fail` sustained, the polymer char layer is breached and catastrophic degradation follows.
- **Vent** (LiPo): `T_s ≥ 420 K` single-timestep criterion (line 187–189). The Sandia vent threshold; beyond this, thermal runaway is self-sustaining.

### A_λ interpolation

Linear in wavelength between the 4 tabulated points (line 283–285). Boundary clamp at `λ < 1.06 µm` or `λ > 2.05 µm` (lines 264–275) with a `reduced confidence` flag. Wavelength within 5 nm of a tabulated point → exact table value (line 279–282) — avoids spurious interpolation for the nominal wavelengths.

## Known simplifications

- **1-D conduction** — no in-plane spreading. For spot diameters large compared to thermal penetration depth (`w ≫ √(α·t)`), this is valid. At C-UAS scales (`w` ~ cm, `√(α·t)` ~ mm for polymers), this holds.
- **Temperature-independent properties.** ρ, c_p, k treated as constant. For metals near melt, c_p and k can change by 30–50%; this is an engineering approximation.
- **No spectral emissivity variation.** IR emissivity fixed at 0.85 for all materials. Al at low T has much lower ε — this is conservative for Al (overestimates radiation loss) and about right for polymers.
- **Full-thickness melt budget** (Al) — see derivation note above.
- **No surface melt/ablation mass loss.** The melt layer is treated as a static heat sink; in reality molten aluminum runs and oxidizes. SPEC v1 does not model ablation.
- **Decomposition is a simple threshold** — no Arrhenius pyrolysis kinetics, no char-layer insulation, no endothermic decomposition enthalpy.
- **Backside same h_conv as front** (line 239–241) — correct for unshielded thin panels; incorrect for a target inside an enclosure.
- **Convective BC** `h = 10 + 6.2·√v` — SPEC §10.6 HIGH UNCERTAINTY. Ordinary natural-convection floor ~10 W/m²K, forced-convection scaling `h ∝ v^n` with n ≈ 0.5 (laminar) or 0.8 (turbulent) over a flat plate. The `√v` form sits in the laminar-forced middle ground.
- **A_λ table** — SPEC §10.2 HIGH UNCERTAINTY on every entry.

## Cross-check

Canonical scenario (C-UAS 1500 m preset, CFRP target): I_aim = 14.3 W/cm² = 1.43e5 W/m², material = CFRP (A_λ = 0.85 at 1.07 µm), thickness = 2 mm, T_amb = 288 K, backside = insulated.

Hand estimate (semi-infinite slab, no losses):

Surface temperature rise under constant absorbed flux q (Carslaw & Jaeger §2.9):
```
T(0, t) − T_amb = (2·q/k) · √(α·t/π)
```

With q = A_λ·I = 0.85·1.43e5 = 1.22e5 W/m², α = k/(ρ·c_p) = 7/(1600·1000) = 4.4e-6 m²/s:

Time to reach T_fail − T_amb = 600 − 288 = 312 K:
```
312 = (2·1.22e5 / 7) · √(4.4e-6 · t / π)
312 = 34,857 · √(1.40e-6 · t)
√(1.40e-6 · t) = 0.00895
1.40e-6 · t = 8.01e-5
t = 57 s
```

Hmm — that's outside the 60-s timeout. So at 14 W/cm² the CFRP 2-mm panel would barely fail before timeout, with losses probably pushing it over.

At higher flux (e.g. 100 W/cm² = 1e6 W/m²): q = 0.85e6 = 8.5e5 W/m².
```
312 = (2·8.5e5/7) · √(4.4e-6 · t / π) = 2.43e5 · √(1.40e-6·t)
√(1.40e-6·t) = 1.28e-3
t = 1.17 s
```
About 1.2 s to failure — within SPEC M8 test-case 8.1 (CFRP at high flux).

Independent verification with `physics/m8_burnthrough.py:compute` at the 100 W/cm² CFRP case reproduces `tau_BT ≈ 1.2 s` to 5% (losses shift it mildly upward).

## Cross-reference to CLAUDE §7.1

M8 has no formulas listed in CLAUDE §7.1 — no previous audit found a specific error in the heat-equation discretization. The attention points are:

- **A_λ defaults are HIGH UNCERTAINTY** (SPEC §10.2) — flagged in every call that uses the table.
- **`h_conv` correlation is HIGH UNCERTAINTY** (SPEC §10.6) — flagged when convective backside BC active.
- **Ghost-cell 2r factor at boundaries** (line 206, 210, 213) — not a CLAUDE §7.1 item but a common stencil bug; verified correct here and covered by Layer 3 numerical-methods tests.
- **Full-thickness melt budget** — engineering approximation, noted above; if a user enables melt on a thick low-k metal (not in v1 material set), this needs revisiting.
