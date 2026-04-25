"""Sensitivity-analysis helper for the math tab's Full view.

For each numeric metric in the math tab, the Full view shows a small
inline sensitivity bar: what happens to that metric when each
upstream user input is perturbed by ±10 %?

Implementation cost (per plan §7.4): the perturbation re-runs the
orchestrator at +10 % and -10 % on each numeric user input. There are
~22 numeric user inputs in v1, so up to ~44 cached orchestrator calls
per session — *independent* of how many metrics the perturbation
informs (each cached run feeds every metric that depends on that
input). At ~150 ms per orchestrator call this is roughly 7 s of
one-time computation per session, then cached.

The cache key is ``(frozen_inputs_tuple, input_key, sign)`` — the
existing ``frozen_inputs`` tuple from ``ui/app.py`` is reused as the
session-stable portion. ``st.cache_data`` enforces hashability so we
build the tuple from sorted (key, value) pairs the same way
``ui/app.py::run_full_chain_cached`` does.

This module is import-light: it does not import ``ui.outputs`` or
``ui.math_content`` to avoid a circular dependency, and it does not
reference ``streamlit`` at module load time so it can be unit-tested
outside a Streamlit script context.
"""
from __future__ import annotations

from typing import Mapping


# Inputs that are categorical (string-valued or enumerated) and can't be
# meaningfully perturbed by ±10 %. Sensitivity for these is omitted.
_NON_NUMERIC_INPUTS: frozenset[str] = frozenset({
    "cn2_model",
    "material",
    "backside_BC",
})

# Inputs that are user-controllable but where ±10 % isn't physically
# meaningful (e.g. a fixed validated wavelength). Sensitivity for these
# is also omitted by default; callers can override per-metric in the
# MetricEntry.sensitivity_inputs tuple if they want.
_FIXED_OR_SPECIAL: frozenset[str] = frozenset({
    "wavelength",   # only four validated values; perturbation falls outside set
})


def _safe_perturb(value: float, sign: int) -> float:
    """Return ``value * (1 + sign · 0.10)`` clamped above 0.

    sign is +1 or -1. The clamp guarantees we don't generate negative
    inputs (e.g. perturbing already-zero v_perp by -10 %).
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return float("nan")
    perturbed = value * (1.0 + sign * 0.10)
    if perturbed < 0:
        return 0.0
    return perturbed


def compute_sensitivity_for_metric(
    metric_key: str,
    sensitivity_inputs: tuple[str, ...],
    base_result: dict,
    base_inputs: Mapping[str, object],
    perturbation_runner,
) -> dict[str, float]:
    """Return a dict ``{input_name: signed_pct_change_in_metric}``.

    For each input in ``sensitivity_inputs``, calls
    ``perturbation_runner(input_key, sign)`` to get the perturbed
    orchestrator result and computes the relative change in the
    metric of interest.

    Args:
        metric_key: orchestrator output key whose sensitivity we want.
        sensitivity_inputs: user-input keys to perturb (per the
            ``MetricEntry.sensitivity_inputs`` field).
        base_result: orchestrator result at the unperturbed inputs.
        base_inputs: the user-input dict (we read each input's base
            value from here for the +10 % / −10 % perturbation).
        perturbation_runner: callable taking ``(input_key, sign)`` →
            perturbed merged-result dict. Caller-supplied so this
            module stays decoupled from streamlit and from the actual
            orchestrator wiring.

    Returns:
        dict mapping each successfully-perturbed input to the signed
        percent change in the metric. Inputs that are non-numeric,
        absent, zero-valued, or that produce a non-finite metric in
        the perturbed result are omitted from the output.

        The percent change reported is the average of the absolute
        magnitudes of the +10 % and -10 % changes — a single
        sensitivity number per input. The sign carried is the sign of
        the +10 % change (so a positive number means "metric goes up
        when the input goes up").
    """
    base_value = base_result.get(metric_key)
    if base_value is None or isinstance(base_value, (str, bool)):
        return {}
    try:
        base_f = float(base_value)
    except (TypeError, ValueError):
        return {}
    if base_f == 0.0:
        # Can't compute relative change; skip whole metric.
        return {}

    out: dict[str, float] = {}
    for input_key in sensitivity_inputs:
        if input_key in _NON_NUMERIC_INPUTS or input_key in _FIXED_OR_SPECIAL:
            continue
        v = base_inputs.get(input_key)
        if v is None or isinstance(v, (str, bool)):
            continue
        if not isinstance(v, (int, float)):
            continue

        try:
            r_plus = perturbation_runner(input_key, +1)
            r_minus = perturbation_runner(input_key, -1)
        except Exception:
            # Perturbation may push inputs out of validator bounds for
            # extreme starting values; skip silently rather than
            # propagating to a Streamlit-level exception.
            continue

        m_plus = r_plus.get(metric_key)
        m_minus = r_minus.get(metric_key)
        if m_plus is None or m_minus is None:
            continue
        try:
            m_plus_f = float(m_plus)
            m_minus_f = float(m_minus)
        except (TypeError, ValueError):
            continue
        if not (
            -1e30 < m_plus_f < 1e30 and -1e30 < m_minus_f < 1e30
        ):
            continue

        plus_pct = 100.0 * (m_plus_f - base_f) / base_f
        minus_pct = 100.0 * (m_minus_f - base_f) / base_f
        # Average absolute magnitude, signed by the +10 % direction.
        avg_mag = (abs(plus_pct) + abs(minus_pct)) / 2.0
        sign = 1.0 if plus_pct >= 0 else -1.0
        out[input_key] = sign * avg_mag

    return out


def format_sensitivity_line(sens: Mapping[str, float],
                             *, top_n: int = 3) -> str:
    """Format the sensitivity dict as a one-line string for the Full
    view. Only the top-N most influential inputs are shown to avoid
    cluttering the row; the rest are hidden under "..." if there are
    more.

    Returns "(no sensitivity data)" when the dict is empty (e.g. the
    metric is categorical or its base value is zero).
    """
    if not sens:
        return "(no sensitivity data — categorical metric or zero base value)"
    # Sort by absolute influence, descending.
    ordered = sorted(sens.items(), key=lambda kv: abs(kv[1]), reverse=True)
    top = ordered[:top_n]
    parts: list[str] = []
    for input_key, pct in top:
        parts.append(f"{input_key}: ±{abs(pct):.1f}%")
    extra = len(ordered) - top_n
    if extra > 0:
        parts.append(f"+{extra} more")
    return "Sensitivity (±10% perturbation): " + " · ".join(parts)


__all__ = [
    "compute_sensitivity_for_metric",
    "format_sensitivity_line",
]
