"""Phase 1 scaffold entry point. Verifies Streamlit Cloud deploys from
this repository. Real UI (panels, plots, orchestrator) arrives in Phase 2
per ARCHITECTURE.md §6.1."""

import streamlit as st

st.set_page_config(page_title="HEL Calculator", layout="wide")

st.title("HEL Engineering Calculator")
st.caption("Phase 1 scaffold — implementation begins Phase 2.")

st.info(
    "This is the repository scaffold. The six input panels, three plots, "
    "and five output panels described in SPEC.md §5 are not yet implemented."
)

st.markdown(
    "**Contract documents:** see `SPEC.md`, `ARCHITECTURE.md`, `TESTING.md`, "
    "`CLAUDE.md`, and `README.md` in the repository."
)
