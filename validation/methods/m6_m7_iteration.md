# M6↔M7 fixed-point iteration — numerical-methods validation

**Scope.** This note validates the *numerics* of the fixed-point loop
between M6 (thermal blooming) and M7 (spot & PIB) that lives in
`physics/orchestrator.py::_iterate_m6_m7`. The SPEC §3 M6 and M7
validation tests pin the *physics* of each module at one or two
operating points; what neither of them exercises is the coupled-loop
behaviour (convergence, non-convergence path, path-independence,
self-consistency of the converged fixed point). That's what this
document and `tests/test_m6_m7_convergence.py` do.

The goal is the Package 3 acceptance gate from `validation/README.md`
Layer 3.2: **the M6↔M7 loop converges, flags non-convergence cleanly,
and produces a self-consistent converged state.**

---

## 1. The loop implemented

`orchestrator._iterate_m6_m7` alternates single-pass calls to M7 and M6
until the relative change of `w_total` between successive passes falls
below `_DEFAULT_TOL = 0.01` (1 %) or the iteration count reaches
`_DEFAULT_MAX_ITER = 10`, whichever comes first.

Seeds:
- `S_TB = 1.0` (no blooming on the first M7 call)
- `w_bloom = 0.0` (no blooming broadening on the first M7 call)

Body of iteration *n*:

```
w_total_n = M7(inputs, S_TB_{n-1}, w_bloom_{n-1}).w_total
N_D_n, S_TB_n, w_bloom_n = M6(..., w_at_target=w_total_n)
if |w_total_n − w_total_{n-1}| / w_total_{n-1} < tol: STOP
```

Non-convergence appends a SPEC §3 M6 flag to
`out6['assumptions_flagged']`; the loop never raises. The merged
orchestrator result exposes `m67_iteration_count` and `m67_converged`
so the UI can badge the outcome.

References:
- Gebhardt, F. G., "Twenty-five years of thermal blooming: an overview,"
  *Proc. SPIE* 1221 (1990), 2–25 — the Smith-Strehl / broadening formulas
  M6 implements (CLAUDE §7.1 4√2 prefactor).
- SPEC §3 M6 "Iterative coupling with M7".
- Ortega & Rheinboldt, *Iterative Solution of Nonlinear Equations in
  Several Variables* (1970) — textbook background for fixed-point
  contraction analysis.

---

## 2. Why the fixed point exists at all

The loop is a scalar fixed-point map on `w_total ≥ w_diff_floor`:

```
g(w) = quadrature( w_diff, w_turb, w_jit, w_bloom(w, N_D(w)) )
```

Inspection: `N_D ∝ 1/w³` (Gebhardt), and when `N_D ≥ 5`,
`w_bloom ∝ w · √((N_D/5)² − 1)`. At small `w`, `N_D` is huge,
`w_bloom` is large, so `g(w)` is pushed outward. At large `w`, `N_D`
drops fast (cubic), so `w_bloom` retreats and `g(w)` relaxes toward
`√(w_diff² + w_turb² + w_jit²)`. The monotone-decreasing `N_D(w)` paired
with the monotone-increasing `w_bloom(w, N_D)` gives a contraction on
most of the operating envelope; divergence is expected only inside the
`N_D > _N_VALIDITY = 30` catastrophic-blooming regime where the
Smith-Strehl approximation itself breaks down (SPEC §3 M6).

The tests below verify the contraction numerically without relying on
analytical contraction-rate bounds (which would demand a full Jacobian
study of the Gebhardt formula — out of scope for Package 3).

---

## 3. Validation checks

The tests in `tests/test_m6_m7_convergence.py` exercise the loop along
five axes. Each numbered subsection maps 1-to-1 with a test function.

### 3.1 Convergence sweep over legal operating points

**Claim.** On random draws from the SPEC §5.1 Panel A–F input envelope
(legal per each module's `_validate_inputs`), the loop converges to
1 % relative change in `w_total` within the default 10-iteration cap at
least 90 % of the time. Failures are limited to the
catastrophic-blooming regime (N_D > 30) or unphysical combinations the
UI would never present.

**Test.** Hypothesis strategy sampling 30 random operating points from
a tightened envelope (inside the SPEC Panel A–F ranges but pruned to
avoid v_perp→0 and extreme Cn²); assert `m67_converged` is True for
≥ 27 of 30 (90 %). For each point, assert `m67_iteration_count ≤ 10`.

**Tolerance rationale.** 90 % is conservative; `_DEFAULT_MAX_ITER = 10`
is 2× the empirical ceiling seen on the SPEC §3 M6 case set. A <90 %
convergence rate would indicate the default cap is too tight.

### 3.2 Non-convergence handling — catastrophic blooming

**Claim.** When the operating point falls inside the catastrophic-
blooming regime (`N_D ≫ 30`), the loop must (a) terminate within
`max_iter`, (b) set `m67_converged = False`, (c) append the SPEC §3 M6
"did not converge" flag to `assumptions_flagged`, and (d) return
finite, non-NaN numeric outputs from the last pass (so the downstream
M8/M10 chain can still render a diagnostic — a hard crash is the wrong
behaviour for a safety tool).

**Test.** Construct a pathological case: small `v_perp` (near 1 m/s),
high `P0`, long range, low visibility. Verify the M6 pass reports
`N_D > _N_VALIDITY = 30` and the loop sets `m67_converged = False`.
Independently verify that the SPEC-mandated flag is present and no
output is NaN/Inf.

### 3.3 Self-consistency of the converged fixed point

**Claim.** After a converged pass, feeding the reported `w_total` back
through one extra M6 pass must reproduce `S_TB` to within 1 % — the
same tolerance the iteration itself was running against. A >1 % drift
would mean the reported output is not a fixed point of the stated map.

**Test.** Run the full chain on the canonical C-UAS inputs. Assert
`m67_converged = True`. Extract `w_total`, `alpha_atm`, `R_slant`,
`v_perp`, `T_ambient`, `P_atm`, `P_exit` from the merged result. Call
`m6_blooming.compute` directly with those inputs and compare the
returned `S_TB` to the reported `S_TB`. Relative difference < 1 %.

**Tolerance rationale.** 1 % matches the loop's own stopping tolerance
(`_DEFAULT_TOL = 0.01`). A tighter tolerance would be chasing the
difference between the last-iterate S_TB and the true S_TB, which the
loop by construction does not drive below 1 %.

### 3.4 Path-independence under initial-guess perturbation

**Claim.** The final converged `w_total` must be independent (to within
2 %) of the seed passed into M7 on the first pass. The orchestrator
seeds `S_TB = 1, w_bloom = 0`; an alternative seed (e.g.,
`S_TB = 0.5, w_bloom = 0.5·w_diff`) that still satisfies M6's
`_validate_inputs` must converge to the same fixed point.

**Test.** Monkeypatch the seed into `_iterate_m6_m7` via a wrapper that
runs the loop manually, first with the canonical seed and then with a
perturbed seed (S_TB = 0.5, w_bloom = 0.5·w_total_canonical). Assert
the two converged `w_total` values agree within 2 %.

**Tolerance rationale.** 2 % is 2× the loop's stopping tolerance: both
runs terminate on a 1 % step, so their end-states can differ by up to
2× the tolerance in the worst case. Agreement tighter than 1 % would
demand the loop iterate an extra pass past convergence; accepting 2 %
matches what the stopping rule can actually deliver.

### 3.5 Monotone / oscillation-free sequence after warmup

**Claim.** The sequence `w_total^(n)` is eventually monotone (no
oscillation) on at least 80 % of the canonical-sweep points. Two-cycle
oscillation would signal a weak contraction (gain near 1) or a sign
error in the M6 broadening term.

**Test.** On ten random draws from the convergence-sweep strategy, log
the full `w_total^(n)` trace inside a re-implementation of the loop.
Assert that for ≥ 8 of 10 points, the trace from iteration 2 onward
is monotone (either non-increasing or non-decreasing). The warmup skip
(iteration 1) is necessary because the first M7 pass uses the
`S_TB = 1, w_bloom = 0` seed which systematically underestimates
`w_total` on the first step.

**Tolerance rationale.** 80 % not 100 %: two-cycle behaviour near the
N_D = 5 broadening-onset boundary is expected (the `max(0, ...)` switch
introduces a discontinuity in the iteration map) and is not a bug.
Anything below 80 % would suggest the stopping rule is catching
mid-oscillation noise rather than true convergence.

---

## 4. What this validation does not cover

- **Analytical contraction-rate bound.** The Ortega-Rheinboldt
  Banach-fixed-point argument would require a full Jacobian of
  `g(w) = quadrature(w_diff, w_turb, w_jit, w_bloom(w, N_D(w)))`. We
  verify contraction numerically only.
- **The 0.3 broadening scaling (SPEC §10.4 HIGH UNCERTAINTY).** That
  constant sets `w_bloom` magnitude but not the qualitative dynamics
  of the loop; Package 4 reviews its literature basis.
- **The Smith-Strehl formula** `S_TB = 1/(1 + (N_D/5)²)` itself. It's
  a SPEC §3 M6 physics choice, tested for physics in
  `tests/test_m6_blooming.py`.
- **Alternative coupling schemes** (e.g., Aitken acceleration, under-
  relaxation). SPEC §3 M6 specifies plain fixed-point iteration; we
  validate the scheme SPEC requires, not variants.

---

## 5. Acceptance

This note is green when `tests/test_m6_m7_convergence.py` is green on
CI. The tests are independent of `tests/test_m6_blooming.py` and
`tests/test_m7_spot_pib.py` — the SPEC validation files check each
module's *physics*, this file checks the *loop dynamics* that couples
them.
