"""Compatibility shim — re-exports color and sizing constants from ``ui.theme``.

As of ARCHITECTURE.md v1.6 the canonical source of every visual token is
``ui/theme.py``. This file is retained during Phase 3 PR 1 only, so that
``ui/outputs.py`` and ``ui/plots.py`` — which still import from
``ui.style`` — keep working while the theme layer lands without touching
every import site. PR 2 migrates both consumers to import directly from
``ui.theme`` and this shim is deleted.

Do NOT add new constants here. Anything new goes in ``ui.theme`` directly.

References:
    ARCHITECTURE.md §6.6 (v1.6) — shim contract.
    ARCHITECTURE.md §6.8 (v1.6) — ``ui.theme`` public API.
"""

from ui.theme import (  # noqa: F401 — re-export for backward compatibility
    COLOR_CAUTION,
    COLOR_PRIMARY,
    COLOR_REFERENCE,
    COLOR_SUCCESS,
    COLOR_WARNING,
    PLOT_HEIGHT_PX,
)

__all__ = [
    "COLOR_PRIMARY",
    "COLOR_REFERENCE",
    "COLOR_SUCCESS",
    "COLOR_WARNING",
    "COLOR_CAUTION",
    "PLOT_HEIGHT_PX",
]
