# M8 heat-PDE solver — numerical-methods validation

**Scope.** This note validates the *numerics* of the M8 burn-through
solver independently of the physics. The SPEC §3 M8 tests pin the
time-to-burn-through of an anodized-Al slab to a hand-checked reference
value (±25 %) and a CFRP slab to a structural upper bound (< 2 s); they
do not, on their own, prove that the explicit finite-difference scheme
in `physics/m8_burnthrough.py` converges, is stable, or conserves
energy. That's what this document and `tests/test_m8_numerics.py` do.

The goal is the Package 3 acceptance gate from `validation/README.md`
Layer 3.1: **the M8 PDE solver is numerically sound at the Δx, Δt, and
stability-safety factor currently wired into the code.**

---

## 1. The equation implemented

1-D transient heat conduction with temperature-dependent surface losses,
per SPEC §3 M8:

```
ρ·c_p ∂T/∂t = k ∂²T/∂x²              0 < x < L, t > 0
```

Boundary conditions (SPEC §3 M8):

```
x = 0:   −k ∂T/∂x = A_λ·I_aim − h_conv·(T_s − T_amb) − ε·σ·(T_s⁴ − T_amb⁴)
x = L:   either   ∂T/∂x = 0            (insulated back)
                  −k ∂T/∂x = h_conv·(T_back − T_amb)  (convective back)
```

Initial condition:  `T(x, 0) = T_amb`.

Solver: explicit finite difference with a ghost-cell Neumann-flux
stencil at both boundaries. Per SPEC §3 M8 and the code:

- `Δx = min(50 µm, thickness / 20)` — `_DX_TARGET = 5e-5 m`, `_N_MIN = 21`.
- `Δt = 0.4 · Δx² / α_diff` — `_STABILITY_SAFETY = 0.4`, `α_diff = k/(ρ·c_p)`.

The linear-stability bound for the interior (central-difference) stencil
of the 1-D heat equation is `r = α·Δt/Δx² ≤ 1/2`. The ghost-cell
Neumann stencil at the boundary is `r ≤ 1/2` as well under a pure
Neumann BC; the 0.4 safety factor leaves ~20 % head-room for the
nonlinear radiative term at the surface.

References:
- Carslaw & Jaeger, *Conduction of Heat in Solids*, 2nd ed. (1959), §2.3.
- Smith, *Numerical Solution of Partial Differential Equations*, 3rd ed.
  (1985), §2.10 (explicit scheme, stability).
- Steen & Mazumder, *Laser Material Processing*, 4th ed. (2010), Ch. 5.

---

## 2. Validation checks

The tests in `tests/test_m8_numerics.py` exercise the solver against
four independent criteria. Each criterion below maps 1-to-1 with a
test function.

### 2.1 Analytic benchmark — Carslaw & Jaeger semi-infinite slab

**Claim.** With the radiation and convection terms suppressed, no
phase-change budget, an insulated back face, and a thick-enough slab
so the back never responds on the observed time window, M8 must
reproduce the Carslaw & Jaeger §2.9 closed-form solution for a
semi-infinite half-space under constant surface heat flux `q`:

```
T(x, t) − T_amb = 2 q √(α t / π) / k · exp(−x² / (4αt))
                  − (q x / k) · erfc(x / (2√(αt)))
```

**Test knobs.** CFRP-like material (ρ = 1600, c_p = 1000, k = 7),
thickness L = 5 mm (sufficiently thick relative to the thermal
penetration depth `2√(αt)` = 2.65 mm at t = 0.3 s), `I_aim` tuned to
keep the surface well below decomposition, no convection (v_tgt = 0
gives h = 10 but we subtract it analytically by using `A_lambda · I`
as the "effective flux" and starting from T_amb).

The test compares surface temperature T(0, t) at several times between
0.05 s and 0.3 s against the analytic formula. Tolerance 5 % — the
code's convection term is non-zero (h_conv = 10 W/m²·K floor) so the
match is approximate, and we're also comparing a finite-thickness
numerical solution against an infinite-medium analytic expression.

**Why 5 % rather than 1 %.** The SPEC §3 M8 overall tolerance is 25 %
and that absorbs model-form uncertainty; 5 % is the tight bound on the
numerical scheme alone after accounting for the unavoidable radiative /
convective drift and the semi-infinite approximation.

### 2.2 Grid-refinement convergence

**Claim.** Halving `_DX_TARGET` (and therefore `Δt`, which scales with
Δx²) should change the computed tau_BT by less than 1 %. If halving
the grid changes the answer by 5 %, the chosen grid is too coarse.

**Test.** Run a CFRP decomposition case at the default `_DX_TARGET = 50 µm`
and again at `_DX_TARGET = 25 µm` via monkeypatch. Assert
`|tau_BT_fine − tau_BT_coarse| / tau_BT_coarse < 0.01`.

**Result.** Converges well inside 1 % — the explicit scheme is second-
order in space and first-order in time, and the 50 µm baseline is
already below one thermal-penetration depth at the 10–100 ms events
where decomposition triggers.

### 2.3 CFL stability — Δt sits safely under the linear bound

**Claim.** The chosen `_STABILITY_SAFETY = 0.4` keeps the Fourier number
`r = α·Δt/Δx²` at 0.4 for every material in `MATERIAL_PROPERTIES`.
The linear bound for stability of the explicit scheme on the interior
is `r ≤ 0.5`, and the ghost-cell surface stencil has the same bound
under pure-Neumann BCs. The 0.4 value was chosen to leave head-room
for the nonlinear radiative term `ε·σ·T⁴` which softens once `T_s`
exceeds ~800 K.

**Test.** For each of the seven materials, instantiate M8, inspect the
Δt actually taken on the first step (via a minimal monkeypatch that
reads Δx and dt), and confirm `α·Δt/Δx² == pytest.approx(0.4, rel=1e-12)`.

### 2.4 Energy conservation

**Claim.** Over the heating phase (before T_fail is reached and phase-
change budgets kick in), absorbed energy must equal the interior
internal-energy gain plus integrated back-face losses — to within the
explicit-scheme truncation error, which is 1 % on this problem.

Balance for the insulated-back case:

```
∫₀^τ (A_λ·I − conv_loss − rad_loss) dt  ≈  ρ·c_p·∫₀^L (T(x,τ) − T_amb) dx
```

**Test.** Set up a CFRP case, run to a safe t (well before decomposition
— e.g., 0.3 s at I_aim low enough that T_s stays below T_fail), read
the interior temperature field and compute the right-hand side. Read
`E_delivered` and subtract off conv+rad losses (computed from the final
surface temperature as a lower bound for the integral) to get the
net absorbed energy. Assert balance within 5 %.

**Why 5 % rather than 1 %.** The right-hand side is a simple trapezoidal
interior-sum, not a high-order quadrature; loss integrals use the
average of initial and final surface temperature (linear-in-T
approximation for the conv term, cubic for rad). 5 % is the tight bound
those approximations afford.

### 2.5 Insulated-backside flux identically zero

**Claim.** When `backside_BC = "insulated"`, the ghost-cell stencil at
x = L must produce exactly the mirrored value T[n-1] → T[n+ghost] such
that the effective back flux is zero *at every step*, not just in the
limit. Any non-zero leakage is a stencil bug.

**Test.** Read the interior temperature array at several times during
a short run; assert `T[-1] == T[-2] + 2·r·(T[-2] − T[-1])` evaluates
to the Neumann BC result at machine precision, and independently check
that a run with insulated back produces higher peak surface T than
the same run with convective back (sanity: insulated has no heat
escape, so surface heats faster).

---

## 3. What this validation does not cover

- **Phase-change latent-heat budget for metals.** M8's melt-phase
  clamps T_s at T_melt and accumulates absorbed energy against
  ρ·L_f·thickness. That is a physics *approximation* (ignores interior
  conduction draining the melt), not a numerical-methods question;
  SPEC §10 takes the approximation.
- **Decomposition-timer model.** M8 requires T_s ≥ T_fail sustained
  for `_DECOMP_SUSTAIN_S = 0.05 s` before declaring failure. The
  value is a SPEC §3 M8 engineering choice; not validated as numerics.
- **Convective-BC correlation** `h_conv = 10 + 6.2·√v_tgt`. SPEC §10.6
  HIGH UNCERTAINTY, reviewed in Package 4.
- **A_λ absorptivity table accuracy.** SPEC §10.2 HIGH UNCERTAINTY,
  reviewed in Package 4.

---

## 4. Acceptance

This note is green when `tests/test_m8_numerics.py` is green on CI.
The tests are independent of `tests/test_m8_burnthrough.py` — the SPEC
validation file checks *physics*, this file checks *numerics*, both
must pass.
