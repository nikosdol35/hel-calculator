# M4 log-log interpolation — numerical-methods validation

**Scope.** This note validates the *numerics* of
`physics/common.py::interp_log_space`, the log-log linear interpolator
that `physics/m4_atmosphere.py` uses to look up molecular-absorption
and -scattering coefficients at an arbitrary wavelength from the SPEC
§3 M4 four-point validated-wavelength table. The SPEC §3 M4 cases pin
the *physics* (α_atm, τ_atm at specific wavelengths); they do not, on
their own, prove the interpolator is exact on its claimed class of
tables or clamps correctly at the endpoints.

The goal is the Package 3 acceptance gate from `validation/README.md`
Layer 3.4: **the log-log interpolator is algebraically exact on
power-law tables, returns node values at machine precision, and
clamps (rather than extrapolates) below / above the table range.**

---

## 1. The interpolator implemented

`physics/common.py::interp_log_space(x, x_table, y_table)`:

```
if x ≤ x_table[0]:       return y_table[0]        # left clamp
if x ≥ x_table[-1]:      return y_table[-1]       # right clamp

find i such that x_table[i] ≤ x ≤ x_table[i+1]
t = (log x − log x_table[i]) / (log x_table[i+1] − log x_table[i])
return exp( log y_table[i] + t · (log y_table[i+1] − log y_table[i]) )
```

i.e., linear interpolation in `(log x, log y)` space between adjacent
table nodes, with explicit endpoint clamps outside the table range.

### 1.1 How M4 uses it

```python
alpha_mol_abs_per_km  = interp_log_space(λ, [1.06e-6, 1.07e-6, 1.55e-6, 2.05e-6],
                                             [0.045, 0.065, 0.190, 0.490]) · (RH / 0.60)
alpha_mol_scat_per_km = interp_log_space(λ, […], [0.005, 0.005, 0.010, 0.010])
```

Outside the `[1.06 µm, 2.05 µm]` band the caller is responsible for
flagging the extrapolation via `assumptions_flagged` — the
interpolator silently clamps, which is the correct behaviour here
(α_mol values outside the table are SPEC §10.1 HIGH UNCERTAINTY
anyway; extrapolating log-linearly to, say, 10 µm would produce a
confidently-wrong number, which is worse than a clamped one with a
user-visible flag).

### 1.2 Why log-log, not linear

Molecular absorption and scattering coefficients typically follow
power-law wavelength dependence (`α ∝ λ^(-4)` for Rayleigh, `α ∝
λ^(-n)` for near-IR water absorption). Linear interpolation between
nodes on such a power law would under- or over-shoot the true curve
by tens of percent; log-log linear interpolation is *algebraically
exact* on any pure power-law table. The SPEC §3 M4 four-point table
is a coarse sampling of what are themselves power-law-ish curves, so
log-log is the right choice.

References:
- Kruse, P. W. et al., *Elements of Infrared Technology* (Wiley 1962),
  Ch. 5 — aerosol wavelength scaling.
- McClatchey, R. A. et al., *Optical Properties of the Atmosphere*,
  AFCRL Technical Report 72-0497 (1972) — source table for the SPEC
  §3 M4 α_mol values (HIGH UNCERTAINTY per SPEC §10.1).
- SPEC §3 M4 "Atmospheric extinction".
- ARCHITECTURE §4.3 — `interp_log_space` contract.

---

## 2. Validation checks

Every numerical claim about `interp_log_space` is exercised in
`tests/test_helpers.py` (Package 2 Layer 2.6). Each subsection below
maps to a concrete test function.

### 2.1 Constant table returns constant

**Claim.** For any flat `y_table = [c, c, …, c]`, the interpolator
returns `c` everywhere — no drift from the log-space arithmetic, no
rounding-error accumulation even when the sample `x` is far from a
node.

**Test.** `test_interp_log_space_constant_table_returns_constant` in
`tests/test_helpers.py`:
```python
xs = [1.0, 10.0, 100.0, 1000.0]
ys = [0.5, 0.5, 0.5, 0.5]
for x in (1.0, 2.5, 42.0, 999.9):
    assert interp_log_space(x, xs, ys) == pytest.approx(0.5, rel=1e-12)
```
`rel=1e-12` — this is a structural invariant; any drift is float64
noise accumulated across the log/exp pair, which must not exceed
machine precision on a constant input.

### 2.2 Algebraic exactness on a pure power-law table

**Claim.** If the table itself follows `y = x^p` exactly, then the
log-log linear interpolant is `y(x) = x^p` for every `x` in the
table range — the interpolator is *algebraically exact* on this
class. This is what makes log-log the right choice for α_mol tables.

**Test.** `test_interp_log_space_linear_in_log_log` in
`tests/test_helpers.py`:
```python
p = 1.7
xs = [1.0, 2.0, 4.0, 8.0, 16.0]
ys = [x ** p for x in xs]
for x in (1.3, 2.7, 5.5, 11.0):
    expected = x ** p
    assert interp_log_space(x, xs, ys) == pytest.approx(expected, rel=1e-12)
```
`rel=1e-12` — the algebra is exact; any drift is float64 noise from
the log/exp chain. The test uses `p = 1.7` (non-integer, not a round
power of the log base) to exercise the full numerical path.

### 2.3 Node values — no off-by-one

**Claim.** At every `x = x_table[i]`, the interpolator returns exactly
`y_table[i]`. No drift from the interpolation step, no off-by-one
in the bracketing loop.

**Test.** `test_interp_log_space_exact_at_nodes` in
`tests/test_helpers.py`. Iterates over every `(x, y)` pair in the
table and asserts `interp_log_space(x, xs, ys) == approx(y, rel=1e-12)`.
Includes both endpoints (guards against off-by-one in the bracketing
`for i in range(len(xs)-1)` loop).

### 2.4 Endpoint clamping — no silent extrapolation

**Claim.** For `x < x_table[0]` the interpolator returns `y_table[0]`;
for `x > x_table[-1]` it returns `y_table[-1]`. Silent log-log
extrapolation outside the table would produce confidently-wrong
α_mol values at out-of-range wavelengths.

**Test.** `test_interp_log_space_clamps_below_first_node` and
`test_interp_log_space_clamps_above_last_node` in
`tests/test_helpers.py`:
```python
xs = [1.0, 2.0, 4.0]; ys = [10.0, 20.0, 40.0]
assert interp_log_space(0.001, xs, ys) == approx(10.0, rel=1e-12)  # far below
assert interp_log_space(1000.0, xs, ys) == approx(40.0, rel=1e-12)  # far above
assert interp_log_space(1.0, xs, ys)   == approx(10.0, rel=1e-12)  # on edge
assert interp_log_space(4.0, xs, ys)   == approx(40.0, rel=1e-12)  # on edge
```
`rel=1e-12` — clamping is a branch that returns a table entry
verbatim; nothing to drift.

### 2.5 Malformed input raises, not silently mis-interpolates

**Claim.** An `x_table` / `y_table` pair of mismatched length, or a
1-element table (insufficient to interpolate), must raise a clear
`ValueError`. Silent fall-through would manifest downstream as an
IndexError buried in M4.

**Test.** `test_interp_log_space_mismatched_lengths_raises` in
`tests/test_helpers.py` verifies both failure modes produce a
`ValueError` with `"same length"` in the message.

---

## 3. What this validation does not cover

- **The α_mol table values themselves** — SPEC §10.1 HIGH UNCERTAINTY,
  reviewed in Package 4. This note validates *how* M4 interpolates
  them, not *what* they are.
- **Extrapolation beyond the table.** The interpolator clamps by
  design; the SPEC wavelength range `[0.5 µm, 5 µm]` extends past
  both ends of the α_mol table, and M4 calls
  `wavelength_in_validated_set` + flags the assumption when the user
  supplies a wavelength off the four-point table. That flagging is
  tested in `tests/test_m4_atmosphere.py`, not here.
- **Alternative interpolation schemes** (cubic spline, PCHIP,
  Akima). SPEC §3 M4 specifies log-log linear; alternatives are not
  validated.
- **Non-monotonic `x_table`.** The interpolator assumes the table is
  strictly monotonically increasing and raises if it can't bracket
  `x`. A deliberately corrupted table is a caller bug, not a
  numerics concern.

---

## 4. Acceptance

This note is green when the five test functions in `tests/test_helpers.py`
listed under §2 remain green on CI. No new Package 3 test file is
created — Package 2 Layer 2.6 already wrote comprehensive coverage;
this note documents the numerical-methods framing for reviewer
traceability.
