# CLAUDE.md — Project briefing for Claude Code

## FIRST ACTION, EVERY SESSION
Read `FYP_PROJECT_MEMORY.md` fully before doing anything. It contains the
complete project history: every dataset, every pipeline decision, every
result, and the reasoning behind them. Do not re-derive or contradict
decisions recorded there without the user's explicit approval.

## What this project is
Final Year Project (Ng Cheng Xin, TP071136, APU): an equity-weighted
geospatial decision-intelligence system for EV charging placement in the
Greater Klang Valley. The ANALYTICS ENGINE IS COMPLETE AND VALIDATED.
The remaining work is the STREAMLIT DASHBOARD described in `PLAN.md`.

## Architecture rules (do not violate)
1. **Artifact pattern.** Heavy computation lives in `pipeline/` scripts that
   write files into `processed_data/`. The app in `app/` ONLY READS those
   files. Never recompute pipeline logic inside the app.
2. **Instant interactivity trick.** `hex_cdi_v1.csv` stores CDI *components*
   separately (pop_n, act_n, equity_mult, supply_n, nearest_station_km).
   Weight sliders / Operator-Government toggle / radius slider are pure
   arithmetic on these columns — milliseconds, no pipeline calls:
       cdi = 100 * norm( (w_pop*pop_n + w_act*act_n) * equity * (1 - supply_n) )
   (equity term replaced by 1.0 in Operator view; norm = divide by max.)
3. **Run location.** All pipeline scripts assume CWD = repo root
   (paths like `processed_data/...` are relative). `run_pipeline.py` enforces this.
4. **Schema stability.** Do not rename columns in processed_data outputs.
   If a schema change is truly needed, update FYP_PROJECT_MEMORY.md in the
   same commit and tell the user explicitly.
5. **Secrets.** API keys live in `.env` only (see `.env.example`).
   Never hardcode keys, never commit `.env`.
6. **Style.** Follow the existing pipeline script style: numbered STEP
   banners, printed evidence, audit files for anything that changes data.

## Commands
- Full pipeline refresh: `python run_pipeline.py`   (stages 02-09, in order)
- Single stage:          `python pipeline/06_build_cdi.py`
- Dashboard:             `streamlit run app/Home.py`
- Environment:           venv at C:\Users\anson\fyp_env (outside OneDrive)

## Current state
- Pipeline stages 02-09: built, validated, reproduced on the user's machine.
- Key headline results are in FYP_PROJECT_MEMORY.md (CDI, 20 recommended
  sites, +1.05M coverage, 24k-port 2030 gap, 17.6% backtest MAPE).
- Dashboard: NOT built. `app/Home.py` is a minimal working stub.
  Build order and full page specs: `PLAN.md`.

## Working style with this user
- Undergraduate student, non-native English: explain plainly, no jargon walls.
- Build one page at a time; show it running; get confirmation; commit; next.
- Commit messages: short imperative ("add CDI map page with weight toggle").
- The user verifies every milestone by running it themselves — make that easy.
