# HEL Engineering Calculator

*Version 1.1 — landing page (post-audit fixes): added data-handling note, softened wavelength-interpolation phrasing, softened mobile-support claim, added response-time expectation.*

A web-based engineering calculator for High-Energy Laser (HEL) systems in Counter-UAS applications. Models beam propagation, atmospheric attenuation, turbulence, thermal blooming, target burn-through, laser safety (NOHD), and system-level power and thermal budgets — all from a single browser tab, no installation required.

**Live URL:** [hel-calculator.streamlit.app](https://hel-calculator.streamlit.app) *(subject to availability at deployment)*

---

## What This Tool Does

Enter your engagement parameters across six panels — laser source, beam director, geometry, atmosphere, aimpoint and material, system resources — and the tool computes:

- **On-target performance** as a function of range (peak irradiance, power-in-the-bucket, spot size)
- **Time-to-burn-through** for the selected material and thickness
- **Laser hazard footprint** (NOHD, reported in both top-hat and Gaussian-peak conventions)
- **System feasibility** (prime power draw, waste heat, sustainable engagement duration)
- **Diagnostic breakdowns** (spot-growth contributions, atmospheric extinction components)

Three interactive plots and five numeric output panels show the results, with a dynamically-updating assumptions panel that surfaces every modeling choice made to produce the numbers.

---

## How to Use

1. Open the URL above in any modern browser. Desktop is the primary target; tablet and phone will work but the layout is not mobile-optimized.
2. Enter the shared username and password when prompted. *Ask the tool owner for credentials if you don't have them.*
3. Fill in the six input panels on the left with your scenario parameters. Defaults are loaded for a typical C-UAS engagement.
4. Click **Run Analysis**. The plots and output panels update within a few seconds.
5. Review the **Assumptions** panel alongside the results — it tells you which values are defaults, which are interpolated, and which are flagged as having high uncertainty.
6. To run a trade study, change any parameter and the displays update automatically.

A **Run Validation Suite** button in the sidebar lets you verify the tool's physics against 29 built-in test cases on demand; a green result means all equations are computing correctly.

---

## Scope and Limitations

**Modeled in v1:**
- Gaussian beam, collimated (focus at infinity)
- Continuous-wave (CW) operation
- Validated wavelengths: 1.06, 1.07, 1.55, 2.05 µm (interpolated between; reduced-confidence flag outside)
- Seven target materials: Anodized aluminum, CFRP, GFRP, polycarbonate, ABS, EPP foam, LiPo cell
- Slant ranges up to 50 km accepted; typical C-UAS engagements are 500 m – 5 km, where the physics models are most reliable

**Out of scope for v1** (planned for future versions):
- Adaptive optics / wavefront correction
- Focus-on-target geometry
- Pulsed operation
- User accounts or saved parameter sets
- Programmatic API

**Data handling:** The tool does not log user inputs, does not persist data between sessions, and has no telemetry or analytics. Every session starts from the defaults; closing the browser discards whatever you entered. Other users of the tool cannot see your inputs or results.

---

## Accuracy and Trust

Every physics formula in the tool cites its source — Andrews & Phillips for turbulence, Gebhardt for thermal blooming, ANSI Z136.1 for laser safety, Carslaw & Jaeger for heat conduction, and several others. The full reference list is in `SPEC.md` Appendix B.

The tool has been developed through a documented discipline of plan revisions, independent math audits, and automated regression testing. The `docs/Plan_v0p8.docx` file in this repository records the design rationale and audit history. The full implementation contract is in `SPEC.md`; the project structure is in `ARCHITECTURE.md`; the validation-suite guide is in `TESTING.md`.

**A note on uncertainty.** Several input values — material absorptivities, atmospheric absorption coefficients, coolant thermal capacity defaults — are literature-sourced engineering estimates with potentially large error bars. These are flagged with "HIGH UNCERTAINTY" in the tool's output and in the source documentation. For any formal trade study or program-critical analysis, the user should override defaults with measured or program-specific values.

---

## Giving Feedback

If you find a bug, get a result that looks physically wrong, or want a feature added:

- **Send a short description to the tool owner** — the URL you were working with, the inputs you used, and what looked off. A screenshot is ideal.
- For bugs: note any error messages you see in the browser.
- For feature requests: describe what you wanted the tool to do, not how you think it should do it — the implementation decision lives in `SPEC.md` and requires a documented update.

---

## Repository Contents

| File | Purpose |
|---|---|
| `SPEC.md` | Implementation contract: every equation, every validation case, every input and output |
| `ARCHITECTURE.md` | File layout, function signatures, inter-component rules, data flow |
| `TESTING.md` | Validation-suite guide and tolerance philosophy |
| `CLAUDE.md` | Behavioral rules for the AI code assistant working on this project |
| `docs/Plan_v0p8.docx` | Project plan and design rationale (reference) |
| `physics/` | The physics core (Python, numpy, scipy) |
| `tests/` | The automated validation suite (29 test cases) |
| `ui/` | The Streamlit web interface |
| `requirements.txt` | Pinned Python dependencies |

---

## Credit and License

Tool authored with Claude (Anthropic) as the code assistant. Physics content derives from the cited published literature; code is the work product of the authoring team. Contact the tool owner regarding permitted use.

---

*This tool is an engineering aid. It does not replace program-specific modeling, field testing, or formal safety analysis. Results are informative for trade studies, not authoritative for deployment decisions.*
