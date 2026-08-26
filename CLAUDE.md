# CLAUDE.md — Project briefing for Claude Code

## FIRST ACTION, EVERY SESSION
Read `FYP_PROJECT_MEMORY.md` fully before doing anything. It contains the
complete project history: every dataset, every pipeline decision, every
result, and the reasoning behind them. Do not re-derive or contradict
decisions recorded there without the user's explicit approval.

## What this project is
Final Year Project (Ng Cheng Xin, TP071136, APU): an equity-weighted
geospatial decision-intelligence system for EV charging placement in the
Greater Klang Valley. The ANALYTICS ENGINE IS COMPLETE AND VALIDATED, and the
STREAMLIT DASHBOARD IS BUILT AND RUNNING: a cover/landing screen (`app/Home.py`),
the Executive Overview, and six tool pages (CDI Explorer, Recommendations,
Forecast, What-If, Validation & Data, Investment Scenario). Remaining work is
optional polish and the user's outstanding tasks (API-key revocation).

## Architecture rules (do not violate)
1. **Artifact pattern.** Heavy computation lives in `pipeline/` scripts that
   write files into `processed_data/`. The app in `app/` ONLY READS those
   files. Never recompute pipeline logic inside the app.
2. **Instant interactivity trick.** `hex_cdi_v1.csv` stores CDI *components*
   separately (pop_n, act_n, equity_mult, supply_n, supply_gap,
   nearest_station_km). The weight slider and the Operator/Government toggle
   are pure arithmetic on these columns — milliseconds, no pipeline calls:

       cdi = 100 * (w_pop*pop_n + w_act*act_n) * equity * supply_gap / CDI_SCALE

   equity = equity_mult (Government) or 1.0 (Operator); w_act = 1 - w_pop;
   supply_gap = 1 - supply_n.

   **CDI_SCALE is a FROZEN CONSTANT, not the maximum of the current frame.**
   It is the raw maximum under the validated baseline — Government lens,
   equity ON, w_pop 0.50 / w_act 0.50 — computed once by stage 06 and
   persisted to `processed_data/cdi_scale.json`. The app reads it via
   `data.load_cdi_scale()`; `app/lib/cdi.py` and `app/pages/5_WhatIf.py` both
   divide by it. NEVER reintroduce `raw.max()` on the frame being displayed.

   Why: `raw.max()` is itself a function of the settings. Dividing each lens
   by its own maximum meant the Operator lens divided by 0.9162 instead of
   1.1371 and every score inflated ~24%, so turning the equity lens OFF
   appeared to *double* the deserts (38 -> 75 hexes) with nobody's access
   having changed. A frozen scale makes settings commensurable: CDI 60 means
   the same absolute severity everywhere.

   **Consequence, and it is CORRECT — do not "fix" it:** CDI = 100 marks the
   worst hex *only under the baseline*. The Operator lens peaks around 80.6
   (below 100), and demand-raising settings legitimately exceed 100 — w_pop
   1.00 peaks at 108.8. Values above 100 clamp to the top colour on the 0-100
   ramp; that is a legend limitation, not a scaling bug.

   Reference values: baseline 38 severe hexes / 756,330 people; Operator
   29 / 585,205; w_pop 1.00 78 / 2,107,544.
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
- Full pipeline refresh: `python run_pipeline.py`   (globs `[0-9][0-9]_*.py`,
  so it now runs 02-09 **and 11** — see the traps section before running it)
- Single stage:          `python pipeline/06_build_cdi.py`
- Operator model:        `python pipeline/11_operator_model.py`  (~20 min)
- Coefficient read-out:  `python pipeline/11b_operator_coefficients.py` (read-only)
- Dashboard:             `streamlit run app/Home.py`
- Environment:           venv at C:\Users\anson\fyp_env (outside OneDrive)

## Current state
- Pipeline stages 02-11: built, validated, reproduced on the user's machine.
- **Stage 11 — operator siting model (DIAGNOSTIC ONLY).** A supervised model of
  where commercial operators actually built (target: has_station per hex, 222
  of 4,003). It learns the market's revealed preference *including its bias*;
  deploying its ranking would reproduce the inequity the CDI exists to correct.
  Never present it as a siting recommendation — its value is the CONTRAST with
  stages 06/07, shown live in the What-If scenario comparison. `11b` is a
  read-only companion that re-derives the same fits for the full coefficient
  and SHAP tables; it re-searches no hyperparameters.
- **Stage 11 outputs are PAIRED to the committed `hex_cdi_v1.csv`** (commit
  a1da38f ships both). Regenerating stage 06 in isolation silently breaks that
  pairing — see the traps section.
- The income effect from stage 11 is SUGGESTIVE, NOT SIGNIFICANT: the
  spatial-block bootstrap CI crosses zero. `poi_residential` is the finding
  that survives (CI [-0.843, -0.265], 99.3% of draws negative). Lead with
  "charging follows commercial siting, not residential need", not with income.
- Key headline results are in FYP_PROJECT_MEMORY.md (CDI, 20 recommended
  sites, +1.05M coverage, 24k-port 2030 gap, 17.6% backtest MAPE).
- Dashboard: BUILT & running (`streamlit run app/Home.py`). Entry is a
  cover/landing screen (`app/Home.py`); `app/pages/` holds Overview (1) + six
  tools — CDI Explorer (2), Recommendations (3), Forecast (4), What-If (5),
  Validation & Data (6_Trust), Investment Scenario (7). All share `app/lib/`
  helpers. Full page specs in `PLAN.md`.
- Validation: live cross-checks done — Google Places coverage + manual PlugShare
  per-zone verification of the Klang desert hexes (recorded in
  `operator_crosscheck_template.csv` + FYP_PROJECT_MEMORY.md).
- Remaining: dashboard fixes listed in `docs/DASHBOARD_REVIEW_2026-08-24.md`,
  optional visual polish (`POLISH.md` — see trap 9 for what is already done),
  and the user's OCM/Google API-key revocation (STILL UNCONFIRMED).

## Known-stale traps (audited 2026-08-26 — read before trusting this file)
Things earlier sessions invalidated. Each one has bitten or nearly bitten.

1. **`raw.max()` normalisation is GONE.** Rule 2 above used to say
   "norm = divide by max". Any code, doc or memory that still says that is
   describing a fixed bug. See rule 2 for what replaced it.
2. **`hex_cdi_v1.csv` is NOT byte-reproducible.** Re-running stage 06 under the
   current libraries (numpy 2.5.1 / pandas 3.0.3) shifts the last 2-4 float
   digits: `lat`/`lon` by ~3e-15 (straight from h3, untouched by our code),
   `supply_raw` ~5e-12, `cdi` ~2e-11. Headline numbers are unaffected (still 1
   hex at 100.0, 38 >= 50, 756,330 people) but the file is no longer
   byte-identical, and 3,968 of 4,003 rows change. **Do not regenerate stage 06
   just to "refresh" it** — restore from git instead. The committed CSV is the
   reference the stage-11 artifacts were computed against.
3. **`run_pipeline.py` now sweeps in stage 11.** It globs `[0-9][0-9]_*.py`, so
   a "full refresh" runs 02-09 *plus* `11_operator_model.py` (~20 min) *and*
   regenerates stage 06, hitting trap 2. `11b_operator_coefficients.py` is not
   matched (third char is `b`, not `_`). Run stages individually unless a full
   rebuild is genuinely wanted.
4. **`fyp_env` does not satisfy `requirements-pipeline.txt`.** As of 2026-08-26
   `prophet` and `python-dotenv` are MISSING, so stage 09 (forecast) and the
   `00_collectors/` scripts will fail on import. scikit-learn, scipy, xgboost,
   lightgbm, shap and statsmodels were installed during the stage-11 build.
   Run `pip install -r requirements-pipeline.txt` before assuming a stage runs.
5. **`processed_data/operator_*.csv` is now an ambiguous glob.** It matches both
   the seven stage-11 outputs and the pre-existing, unrelated
   `operator_crosscheck_template.csv` (the manual PlugShare validation). Use
   explicit paths when staging or deleting.
6. **`operator_market_forecast.csv` cannot yield sites.** It is a district-level
   summary (14 rows, no coordinates). Per-hex sites come from
   `operator_model_scores.csv`. The What-If market preset reads the latter.
7. **The radius slider is not a CDI control.** Rule 2 used to list it alongside
   the weight/lens controls. It lives on the Trust page (6_Trust.py) and drives
   the coverage-radius curve; it does not enter the CDI formula.
8. **What-If's 5-station cap applies to manual placement only.** The two preset
   scenarios load 20 sites each by design.
9. **POLISH.md is partly out of date.** Item 2 (cover screen) and item 4
   (desert-zone "zone type" column) are DONE — though item 4's classifier is
   wrong: it labels zones by mean CDI alone, so the smallest zone by population
   is tagged "large population". Item 1 (dark-on-dark sweep) and item 3
   (WorldPop raster) remain open. Full page-by-page findings, including the
   dead "Inspect a hex" dropdown and the number-formatting inconsistencies, are
   in `docs/DASHBOARD_REVIEW_2026-08-24.md`.
10. **Sidebar page labels are raw filenames** ("WhatIf" with no space) and
    disagree with the Overview cards and page titles. Cosmetic, still open.

## Working style with this user
- Undergraduate student, non-native English: explain plainly, no jargon walls.
- Build one page at a time; show it running; get confirmation; commit; next.
- Commit messages: short imperative ("add CDI map page with weight toggle").
- The user verifies every milestone by running it themselves — make that easy.
