# KV EV Charging Intelligence (FYP — Ng Cheng Xin TP071136)

Equity-weighted geospatial system: charging-desert index (CDI), site
recommendations, demand forecast to 2030, Streamlit dashboard.

## Structure
- `pipeline/` — numbered batch stages (02-09) writing to `processed_data/`
- `app/` — Streamlit dashboard (reads artifacts only)
- `raw_data/`, `processed_data/` — data (raw_data git-ignored)
- `CLAUDE.md` — Claude Code briefing | `PLAN.md` — dashboard spec
- `FYP_PROJECT_MEMORY.md` — full project history & results

## Setup
python -m venv (outside OneDrive) -> `pip install -r requirements.txt`
Copy your `raw_data/` and `processed_data/` folders into repo root.

## Run
- Refresh everything: `python run_pipeline.py`
- Dashboard: `streamlit run app/Home.py`  (always from repo root)
