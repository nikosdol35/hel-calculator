"""Shared visual constants for the HEL calculator UI.

Pure constants, no logic. Imported by ``ui/plots.py`` (curve colors,
figure height) and ``ui/outputs.py`` (verdict traffic-light colors per
SPEC §5.2 Panel 2).

The palette is chosen to be color-blind safe (Okabe–Ito distinguishable
pairs) and high-contrast against Streamlit's default white background.

References:
    ARCHITECTURE.md §6.7 — file contract and color-constant names.
    SPEC.md §5.2 Panel 2 — three-tier verdict uses SUCCESS/WARNING/CAUTION.
"""

# ---------------------------------------------------------------------------
# Palette.
# ---------------------------------------------------------------------------
#: Primary brand color — used for the "actual" curve on every plot and
#: the Streamlit theme primary color (also pinned in .streamlit/config.toml).
COLOR_PRIMARY = "#1f4e79"

#: Neutral gray for diffraction-limited reference curves (always shown
#: dashed alongside the solid "actual" curve so the user sees how much
#: of the budget is spent on physics vs. engineering losses).
COLOR_REFERENCE = "#808080"

#: Traffic-light green: ENGAGEABLE verdict (margin ≥ 30%).
COLOR_SUCCESS = "#2e7d32"

#: Traffic-light amber: MARGINAL verdict (0% ≤ margin < 30%).
COLOR_WARNING = "#e65100"

#: Traffic-light red: NOT ENGAGEABLE verdict (margin < 0%).
COLOR_CAUTION = "#bf360c"

# ---------------------------------------------------------------------------
# Plot sizing.
# ---------------------------------------------------------------------------
#: Default Plotly figure height (px). Chosen to fit three plots stacked
#: in the main Streamlit column without scrolling at typical laptop
#: resolutions (1440×900).
PLOT_HEIGHT_PX = 420
