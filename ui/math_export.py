"""Markdown export for the math tab.

Renders the entire math tab — glossary, per-module metric rows,
constants table, worked example — as a self-contained Markdown
document. Engineers download the .md and share it as the supporting
document with their trade-study deliverables; opens cleanly in any
Markdown viewer (GitHub, VS Code, Obsidian, etc.) including the
LaTeX equations rendered as fenced math blocks.

Per plan §7.6 of ``docs/math_tab_plan_2026-04-25.md``: PDF export is
deferred to a follow-on PR; v1 ships only the Markdown path because
a Markdown file is already sufficient fidelity for a trade-study
attachment and is air-gap-friendly (no headless-browser dependency).

Pure function: takes the orchestrator result dict, returns a string.
No streamlit imports, no I/O — easy to unit-test in isolation.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ui.constants_table import CONSTANTS_BY_MODULE, total_constant_count
from ui.glossary import GLOSSARY
from ui.labels import output_unit
from ui.math_content import MATH_CONTENT, MODULE_ORDER, MODULE_TITLES
from ui.worked_example import (
    WALKTHROUGH_STEPS, WORKED_EXAMPLE_INPUTS, compute_worked_example,
)


def _format_md_value(key: str, value, unit: str) -> str:
    """Format one value for the Markdown export.

    Mirrors ``_format_value_for_math_tab`` in ui/outputs.py so the
    exported document and the on-screen tab agree on every rendered
    number. Imported lazily to keep this module's import surface
    free of streamlit (the on-screen path uses st.markdown but the
    underlying ``format_value`` helper is streamlit-free).
    """
    from ui.components import format_value
    from ui.outputs import _scale

    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "yes" if value else "no"
    scaled = _scale(key, float(value))
    return format_value(scaled, unit)


def _render_metric_md(entry, result: dict, *, include_full: bool) -> str:
    """Render one MetricEntry as a Markdown block. The ``include_full``
    flag controls whether the Full-derivation content (citation,
    code ref, depends-on, assumptions) is emitted alongside the
    Simple-view content."""
    si_value = result.get(entry.key)
    unit = output_unit(entry.key)
    rendered = _format_md_value(entry.key, si_value, unit)

    chunks: list[str] = []
    chunks.append(
        f"#### {entry.display_name} · `{entry.key}`"
        + (f" · {unit}" if unit else "")
    )
    chunks.append(f"**Value (this run):** {rendered}")

    if entry.is_iterated:
        iter_count = result.get("m67_iteration_count")
        iter_text = (
            f"this run: {int(iter_count)} iterations"
            if isinstance(iter_count, (int, float))
            else "iteration count unknown"
        )
        chunks.append(
            f"_Computed via the blooming–focusing self-consistency "
            f"iteration ({iter_text} to 1 % tolerance)._"
        )

    # Formula block.
    if entry.is_categorical:
        chunks.append("_Categorical (verdict) output — set by the rule below._")
        if entry.formula_text:
            chunks.append("```\n" + entry.formula_text + "\n```")
    elif entry.is_solver_based:
        if entry.formula_latex is not None:
            chunks.append("$$\n" + entry.formula_latex + "\n$$")
        if entry.formula_text:
            chunks.append("```\n" + entry.formula_text + "\n```")
    elif entry.formula_latex is not None:
        chunks.append("$$\n" + entry.formula_latex + "\n$$")

    # Plain-language explanation.
    if entry.explanation_short:
        chunks.append(entry.explanation_short)

    # Full-view content.
    if include_full:
        if entry.explanation_full:
            chunks.append(f"**Why this formula.** {entry.explanation_full}")
        if entry.citation:
            chunks.append(f"**Citation:** {entry.citation}")
        if entry.code_ref:
            chunks.append(f"**Implemented at:** `{entry.code_ref}`")
        if entry.derivation_link:
            chunks.append(f"**Full derivation:** `{entry.derivation_link}`")
        if entry.formula_dependencies:
            deps = ", ".join(f"`{d}`" for d in entry.formula_dependencies)
            chunks.append(f"**Depends on:** {deps}")
        if entry.provenance:
            badges: list[str] = []
            for flag in entry.provenance:
                # Use enum.value rather than .name so the export is
                # platform-stable (no CamelCase tokens).
                badges.append(f"`{flag.value}`")
            chunks.append(f"**Provenance:** {' · '.join(badges)}")
        if entry.assumptions:
            chunks.append("**Assumptions:**")
            for a in entry.assumptions:
                chunks.append(f"- {a}")

    return "\n\n".join(chunks)


def _render_glossary_md() -> str:
    chunks: list[str] = ["## Glossary", ""]
    chunks.append(
        f"_{len(GLOSSARY)} concept-level definitions targeted at "
        f"readers new to laser-engagement physics._"
    )
    chunks.append("")
    for term, definition in GLOSSARY.items():
        chunks.append(f"### {term}")
        chunks.append("")
        chunks.append(definition)
        chunks.append("")
    return "\n".join(chunks)


def _render_constants_md() -> str:
    chunks: list[str] = ["## Constants & physical sources", ""]
    chunks.append(
        f"_{total_constant_count()} explicit entries across the "
        f"physics modules. Each value traces to its primary "
        f"literature source. HIGH UNCERTAINTY badges flag entries "
        f"currently held as engineering defaults._"
    )
    chunks.append("")
    for group_title, entries in CONSTANTS_BY_MODULE.items():
        chunks.append(f"### {group_title}")
        chunks.append("")
        chunks.append("| Name | Value | Units | Source | Verdict | Code |")
        chunks.append("|---|---|---|---|---|---|")
        for c in entries:
            cells = [
                c.name.replace("|", "\\|"),
                c.value.replace("|", "\\|"),
                c.units.replace("|", "\\|") if c.units else "—",
                c.source.replace("|", "\\|"),
                c.verdict.replace("|", "\\|"),
                f"`{c.code_ref}`",
            ]
            chunks.append("| " + " | ".join(cells) + " |")
        chunks.append("")
    return "\n".join(chunks)


def _render_bibliography_md() -> str:
    """Render the Bibliography & references section as Markdown.

    Mirrors ``ui.outputs._render_bibliography_section`` so the UI and
    the Markdown export read identically. Two tables: 13 cited
    primary references then 10 supplementary canonical books.
    """
    from ui.bibliography import (
        PRIMARY_REFERENCES, SUPPLEMENTARY_REFERENCES,
    )

    chunks: list[str] = ["## Bibliography & references", ""]
    chunks.append(
        "_Every formula in this tool traces to one of the primary "
        "references below. Supplementary works are widely-used "
        "canonical texts for users who want to study the field "
        "deeper._"
    )
    chunks.append("")

    def _table(entries) -> None:
        chunks.append(
            "| # | Author(s) | Title | Year | Publisher | Where used / topic |"
        )
        chunks.append("|---|---|---|---|---|---|")
        for i, e in enumerate(entries, start=1):
            # Pre-escape pipes (Python 3.11 doesn't allow backslashes
            # inside f-string expressions — PEP 701 lifted this only
            # in 3.12). Hoist the replacement here.
            title_escaped = e.title.replace("|", "\\|")
            cells = [
                str(i),
                e.authors.replace("|", "\\|"),
                f"*{title_escaped}*",
                e.year.replace("|", "\\|"),
                e.publisher.replace("|", "\\|"),
                e.used_for.replace("|", "\\|"),
            ]
            chunks.append("| " + " | ".join(cells) + " |")
        chunks.append("")

    chunks.append("### Primary references (cited in physics modules)")
    chunks.append("")
    _table(PRIMARY_REFERENCES)
    chunks.append("### Supplementary reading")
    chunks.append("")
    _table(SUPPLEMENTARY_REFERENCES)
    return "\n".join(chunks)


def _render_worked_example_md() -> str:
    walkthrough = compute_worked_example()
    chunks: list[str] = ["## Worked example — c_uas at 1 km", ""]
    chunks.append(
        "_Static teaching artifact at a fixed reference scenario "
        "(3 kW · 1 km · 1.07 µm · CFRP · 0.25 s exposure). The values "
        "in this section do not follow your sidebar inputs; the "
        "per-metric rows above carry your live numbers._"
    )
    chunks.append("")
    chunks.append("**Scenario inputs:**")
    chunks.append("")
    chunks.append("| Input | Value |")
    chunks.append("|---|---|")
    for k, v in WORKED_EXAMPLE_INPUTS.items():
        chunks.append(f"| `{k}` | {v} |")
    chunks.append("")

    for step in WALKTHROUGH_STEPS:
        chunks.append(f"### {step.section_title}")
        chunks.append("")
        chunks.append(f"_{step.given}_")
        chunks.append("")
        chunks.append(step.narrative)
        chunks.append("")
        # One bullet per metric in the step with the live computed
        # value beside it.
        for key in step.metric_keys:
            entry = MATH_CONTENT.get(key)
            if entry is None:
                continue
            si_value = walkthrough.result.get(key)
            unit = output_unit(key)
            rendered = _format_md_value(key, si_value, unit)
            chunks.append(
                f"- **{entry.display_name}** "
                f"(`{key}`): {rendered}"
            )
        chunks.append("")
    return "\n".join(chunks)


def to_markdown(result: dict, *, include_full: bool = True) -> str:
    """Render the complete math tab as a Markdown document.

    Args:
        result: the merged orchestrator result the math tab is
            currently displaying — same dict the per-metric
            ``Value (this run)`` cells consume.
        include_full: when True (the default) the export carries the
            Full-derivation content for every metric (citation, code
            ref, dependency chain, assumptions). Pass False to emit
            a Simple-view-only document.

    Returns:
        A self-contained Markdown string ready to be written to a
        ``.md`` file or attached to an email.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    chunks: list[str] = []

    # Header / TOC.
    chunks.append("# How it's calculated — math, formulas, and traceable values")
    chunks.append("")
    chunks.append(
        f"_Generated by the HEL calculator on {timestamp}. "
        f"Every formula traces to a primary literature source; every "
        f"value matches the orchestrator output for the inputs the "
        f"user had loaded at export time._"
    )
    chunks.append("")
    chunks.append("**Contents:**")
    chunks.append("")
    chunks.append("- [Glossary](#glossary)")
    for module_id in MODULE_ORDER:
        if any(e.module == module_id for e in MATH_CONTENT.values()):
            slug = module_id.lower()
            title = MODULE_TITLES[module_id]
            chunks.append(f"- [{module_id} — {title}](#{slug})")
    chunks.append("- [Constants & sources](#constants--physical-sources)")
    chunks.append("- [Worked example — c_uas at 1 km](#worked-example--c_uas-at-1-km)")
    chunks.append("- [Bibliography & references](#bibliography--references)")
    chunks.append("")

    # Glossary first.
    chunks.append(_render_glossary_md())
    chunks.append("")

    # Per-module metric rows.
    for module_id in MODULE_ORDER:
        module_entries = [
            e for e in MATH_CONTENT.values() if e.module == module_id
        ]
        if not module_entries:
            continue
        chunks.append(f"## {module_id} — {MODULE_TITLES[module_id]}")
        chunks.append("")
        for entry in module_entries:
            chunks.append(_render_metric_md(
                entry, result, include_full=include_full,
            ))
            chunks.append("")
            chunks.append("---")
            chunks.append("")

    # Constants table.
    chunks.append(_render_constants_md())
    chunks.append("")

    # Worked example.
    chunks.append(_render_worked_example_md())
    chunks.append("")

    # Bibliography & references — mirror of the on-screen section.
    chunks.append(_render_bibliography_md())
    chunks.append("")

    return "\n".join(chunks)


__all__ = ["to_markdown"]
