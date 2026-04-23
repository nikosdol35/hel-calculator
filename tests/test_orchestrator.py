"""Unit tests for the physics-layer chain coordinator.

The orchestrator wires M1→M10 in dependency order and owns the M6↔M7
fixed-point loop. Pre-v1.4 this module lived in ``ui/`` and could not
be tested (ARCH §2 forbids ``tests/`` → ``ui/`` imports); after the
SPEC v1.4 / ARCH v1.3 relocation it lives in ``physics/`` and gets
direct unit-test coverage for the first time.

These tests do NOT validate physics (M1–M10 have their own SPEC §3
validation suites). They validate the *coordinator* behavior:

  1. The public entry point runs against the canonical-inputs fixture
     and returns the merged dict documented in the module docstring.
  2. The M6↔M7 fixed-point loop converges on the canonical inputs.
  3. Non-convergence is flagged (not raised) when the loop can't meet
     the tolerance within max_iter.
  4. ``ValueError`` from any per-module ``_validate_inputs`` propagates
     unchanged out of the orchestrator.
  5. The ``by_module`` namespace carries every module's output dict.
  6. The aggregated ``assumptions_flagged`` list is de-duplicated.

**SPEC v1.5 note:** ``canonical_inputs`` uses ``cn2_model='HV_5_7'``
(the SPEC §5.1 Panel D default). Between slice-2a commit 1 and SPEC
v1.5 the M5 module raised ``NotImplementedError`` for that model, and
this file carried a ``_chain_inputs`` helper that pinned the value to
``'constant'``. SPEC v1.5 implements HV_5_7 against a dedicated §3 M5.5
validation case, so the workaround is removed — tests now run against
the canonical fixture directly.
"""

import pytest

from physics import orchestrator
from physics.orchestrator import run_full_chain


# --- Test 1: canonical-inputs smoke + output-contract check ------------------


# Keys a Streamlit caller expects out of the orchestrator — one representative
# key from each SPEC §3 module so the smoke test fails loudly if wiring to any
# module breaks, without being so exhaustive that adding a new output key
# becomes a test-update chore.
_REQUIRED_KEYS_PER_MODULE = (
    "theta_diff",          # M1
    "P_exit",              # M2
    "R_slant",             # M3
    "alpha_atm",           # M4
    "r0_sph",              # M5
    "S_TB",                # M6
    "w_total",             # M7
    "tau_BT",              # M8
    "NOHD_tophat",         # M9
    "P_in",                # M10
)

_ORCHESTRATOR_KEYS = (
    "assumptions_flagged",
    "by_module",
    "m67_iteration_count",
    "m67_converged",
)


def test_orchestrator_canonical_inputs_runs_without_raising(canonical_inputs):
    """Sanity check: canonical inputs produce a complete result dict.

    If any per-module input contract drifts from what the orchestrator
    feeds it, this test fails before the physics-level tests even run.
    """
    result = run_full_chain(canonical_inputs)
    missing = [k for k in _REQUIRED_KEYS_PER_MODULE if k not in result]
    assert not missing, f"Orchestrator output missing module keys: {missing}"
    missing = [k for k in _ORCHESTRATOR_KEYS if k not in result]
    assert not missing, f"Orchestrator output missing its own keys: {missing}"


# --- Test 2: M6↔M7 convergence on canonical inputs ---------------------------


def test_orchestrator_m67_loop_converges_on_canonical_inputs(canonical_inputs):
    """Canonical C-UAS engagement (3 kW, 1.5 km, CFRP): blooming is weak
    and the coupled spot should converge within a handful of passes.

    Guards against a regression in which the loop hits max_iter on a
    routine engagement — which would silently attach a non-convergence
    flag and quietly understate or overstate w_total in every live
    calculation on the canonical operating point.
    """
    result = run_full_chain(canonical_inputs)
    assert result["m67_converged"] is True, (
        "M6↔M7 loop failed to converge on the canonical SPEC §5.1 inputs "
        f"(iterations={result['m67_iteration_count']}). A routine engagement "
        "must converge; investigate before shipping."
    )
    assert 1 <= result["m67_iteration_count"] <= 10


# --- Test 3: non-convergence is flagged, not raised --------------------------


def test_orchestrator_flags_non_convergence_instead_of_raising(canonical_inputs):
    """With a pathologically tight tolerance (1e-20) the loop cannot meet
    the stop criterion in 10 iterations on any real input set. The helper
    must exit via max_iter, set ``converged=False``, and append the SPEC
    §3 M6 non-convergence flag rather than raising.

    We exercise ``_iterate_m6_m7`` directly because the public
    ``run_full_chain`` doesn't expose the tolerance knobs — the two-layer
    separation is what lets us inject the test knobs without widening
    the public API.
    """
    from physics import (
        m1_laser_source,
        m2_beam_director,
        m3_geometry,
        m4_atmosphere,
        m5_turbulence,
    )

    u = canonical_inputs
    # Re-run the upstream chain so _iterate_m6_m7 gets valid out1..out5.
    out1 = m1_laser_source.compute(
        {k: u[k] for k in ("P0", "M2", "D", "wavelength")}
    )
    out2 = m2_beam_director.compute(
        {k: u[k] for k in ("P0", "eta_opt")}
    )
    out3 = m3_geometry.compute(
        {k: u[k] for k in ("H_e", "R", "H_t", "v_tgt", "v_perp")}
    )
    out4 = m4_atmosphere.compute({
        "V": u["V"],
        "RH": u["RH"],
        "T_ambient": u["T_ambient"],
        "wavelength": u["wavelength"],
        "R_slant": out3["R_slant"],
    })
    out5 = m5_turbulence.compute({
        "cn2_model": u["cn2_model"],
        "Cn2_value": u["Cn2_value"],
        "Cn2_ground": u["Cn2_ground"],
        "v_HV": u["v_HV"],
        "wavelength": u["wavelength"],
        "R_slant": out3["R_slant"],
        "H_e": u["H_e"],
        "H_t": u["H_t"],
    })

    out7, out6, iters, converged = orchestrator._iterate_m6_m7(
        u, out1, out2, out3, out4, out5,
        max_iter=10, tol=1e-20,
    )
    assert converged is False
    assert iters == 10
    non_conv_flags = [
        f for f in out6["assumptions_flagged"] if "did not converge" in f
    ]
    assert non_conv_flags, (
        "Non-convergence must attach a descriptive flag so the UI "
        "surfaces it in Panel 4 (SPEC §3 M6)."
    )


# --- Test 4: per-module ValueError propagates --------------------------------


def test_orchestrator_validation_error_propagates(canonical_inputs):
    """A bad P0 (negative) should trip M1's ``_validate_inputs`` and
    the ValueError must propagate out of ``run_full_chain`` unchanged —
    the UI click handler catches it and renders the message next to the
    panel that fed the bad value.

    If the orchestrator silently swallowed the exception, Panel A would
    accept garbage and the user would see a nonsense result downstream.
    """
    bad_inputs = {**canonical_inputs, "P0": -1000.0}
    with pytest.raises(ValueError):
        run_full_chain(bad_inputs)


# --- Test 5: by_module namespace is populated --------------------------------


def test_orchestrator_by_module_namespace_present(canonical_inputs):
    """``outputs.py`` Panel 1 uses ``result["by_module"]["m6"]`` to pull
    M6 Strehl numbers alongside M7 spot numbers — the flat-merge strips
    the namespace, so the namespaced view is a first-class contract.
    """
    result = run_full_chain(canonical_inputs)
    assert "by_module" in result
    by_mod = result["by_module"]
    assert isinstance(by_mod, dict)
    expected_keys = {"m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9", "m10"}
    assert set(by_mod.keys()) == expected_keys
    for key, sub in by_mod.items():
        assert isinstance(sub, dict), f"by_module[{key!r}] is not a dict"
        # every module's sub-dict must carry its own assumptions_flagged
        assert "assumptions_flagged" in sub, (
            f"by_module[{key!r}] missing assumptions_flagged — "
            f"required by the SPEC §2 module interface contract"
        )


# --- Test 6: aggregated assumptions_flagged is de-duplicated -----------------


def test_orchestrator_flags_are_deduplicated(canonical_inputs):
    """Multiple modules may independently flag the same assumption
    (e.g. "wavelength outside validated set" can come up in M1, M4, M9).
    The orchestrator must dedupe while preserving first-seen order so
    Panel 4 shows a clean list.

    This test is intentionally content-agnostic: it does not hard-code
    which flag strings appear. It only asserts the dedup invariant, so
    it does not have to be edited every time a module adds a new flag.
    """
    result = run_full_chain(canonical_inputs)
    flags = result["assumptions_flagged"]
    assert isinstance(flags, list)
    assert len(flags) == len(set(flags)), (
        "Duplicate entries found in aggregated assumptions_flagged: "
        f"{[f for f in flags if flags.count(f) > 1]}"
    )
