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
  so it now runs 02-09 **and 11, 12, 13** — see the traps section first)
- Single stage:          `python pipeline/06_build_cdi.py`
- Operator model:        `python pipeline/11_operator_model.py`  (~20 min)
- Forecast benchmark:    `python pipeline/12_forecast_comparison.py` (~6 min)
- Equity metrics:        `python pipeline/13_equity_metrics.py`  (seconds)
- Coefficient read-out:  `python pipeline/11b_operator_coefficients.py` (read-only)
- Dashboard:             `streamlit run app/Home.py`
- Environment:           venv at C:\Users\anson\fyp_env (outside OneDrive)

## Current state
- Pipeline stages 02-13: built, validated, reproduced on the user's machine.
- **Stage 11 — operator siting model (DIAGNOSTIC ONLY).** A supervised model of
  where commercial operators actually built (target: has_station per hex, 222
  of 4,003). It learns the market's revealed preference *including its bias*;
  deploying its ranking would reproduce the inequity the CDI exists to correct.
  Never present it as a siting recommendation — its value is the CONTRAST with
  stages 06/07, shown live in the What-If scenario comparison. `11b` is a
  read-only companion that re-derives the same fits for the full coefficient
  and SHAP tables; it re-searches no hyperparameters.
  **Do not oversell the champion.** XGBoost tuned leads by 0.0036 over
  RandomForest tuned on random CV and 0.0040 over RandomForest BASE on spatial
  CV -- and the runner-up is not the same build in the two schemes. Stage 11
  picks the champion on random-CV PR-AUC alone (`11_operator_model.py:556`) and
  then checks the spatial scheme; what recommends XGBoost is that it leads under
  BOTH, not the margin, which is noise on 222 positives. Any of the top three
  tree ensembles supports the same conclusions. The Market Logic page says this
  in its own words -- do not "tighten" it into a claim of a clear win.
  Related, and easy to misread: ablation sets **A, C, E, G, H score at least as
  well under spatial CV as under random CV** (C by the most, +0.0037). That is
  not an anomaly -- none of them carries a coordinate or district identity, so
  spatial blocking has nothing to strip. The set that DROPS is **D** (-0.0044),
  the only one with lat/lon and district dummies, which is exactly the expected
  signature. (B drops most at -0.0246, but it is a 3-feature set and noisy.)
- **Stage 11 outputs are PAIRED to the committed `hex_cdi_v1.csv`** (commit
  a1da38f ships both). Regenerating stage 06 in isolation silently breaks that
  pairing — see the traps section.
- **Stage 13 — equity metrics (standard inequality measures).**
  Population-weighted Gini / Atkinson / Theil on charger accessibility
  (= supply_raw, READ from stage 06, not recomputed, so it is consistent with
  the CDI by construction). Restates the equity finding in measures comparable
  to published work rather than the bespoke CDI. Headline: KV Gini
  **0.4969 -> 0.4753** under the 20 recommended sites, but **-> 0.5053** under
  the market's own predicted next 20 — the market raises TOTAL accessibility
  (mean 5.58 -> 6.03) while making its distribution MORE unequal. All four
  measures agree on direction, and the ranking survives decay 1.0 / 1.5 / 2.0.
- **Stage 12 — forecasting benchmark (parallel to 09, does not replace it).**
  Six models x base/tuned, rolling-origin backtest (980 folds, 0 failures),
  MASE-led, plus a 2030 plausibility check that catches BOTH runaway
  extrapolation and models that "pass" by not growing. 09 and its outputs are
  untouched; the dashboard still reads forecast_kv_monthly.csv. See trap 12.
- The income effect from stage 11 is SUGGESTIVE, NOT SIGNIFICANT: the
  spatial-block bootstrap CI crosses zero. `poi_residential` is the finding
  that survives (CI [-0.843, -0.265], 99.3% of draws negative). Lead with
  "charging follows commercial siting, not residential need", not with income.
- Key headline results are in FYP_PROJECT_MEMORY.md (CDI, 20 recommended
  sites, +1.05M coverage, 24k-port 2030 gap, 17.6% backtest MAPE).
- Dashboard: BUILT & running (`streamlit run app/Home.py`). Entry is a
  cover/landing screen (`app/Home.py`); `app/pages/` holds Overview (1) + SEVEN
  tools — CDI Explorer (2_CDI_Map), Recommendations (3_Sites), Market Logic (4),
  Forecast (5), What-If (6), Validation & Data (7_Trust), Investment Scenario
  (8). Pages 5-8 were renumbered when Market Logic was inserted at 4; Streamlit
  strips the numeric prefix, so the URLs (/Forecast, /WhatIf, /Trust,
  /Investment) did NOT change. All share `app/lib/` helpers; `data.py` is still
  the only module that touches the filesystem. Full page specs in `PLAN.md`.
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
   byte-identical. **Do not regenerate stage 06 just to "refresh" it** —
   restore from git instead. The committed CSV is the reference the stage-11
   artifacts were computed against.
   CAUTION when measuring this: the rows also come back in a DIFFERENT ORDER
   (trap 19), so a positional row-by-row diff wildly overstates it — it reports
   ~3,968 of 4,003 rows changed and `lat` differing by 0.39 degrees. Align on
   `h3_index` first. Aligned, the real drift is: `pop_est`, `activity_score`
   and `nearest_station_km` EXACT; `lat` 3.1e-15 (272 rows), `supply_raw`
   4.8e-12 (357 rows), `cdi` 2.4e-11 (1,467 rows).
3. **`run_pipeline.py` sweeps in stages 11, 12 AND 13.** It globs `[0-9][0-9]_*.py`,
   so a "full refresh" runs 02-09 *plus* `11_operator_model.py` (~20 min) *plus*
   `12_forecast_comparison.py` (~6 min) *and* regenerates stage 06, hitting
   trap 2. `11b_operator_coefficients.py` is not matched (third char is `b`,
   not `_`). Run stages individually unless a full rebuild is genuinely wanted.
4. **Check `fyp_env` against `requirements-pipeline.txt` before running a stage.**
   It has repeatedly been missing packages the file already lists. `prophet` and
   `python-dotenv` were missing until 2026-08-30 (stage 09 and `00_collectors/`
   failed on import); scikit-learn, scipy, xgboost, lightgbm, shap and
   statsmodels were installed during the stage-11 build. Run
   `pip install -r requirements-pipeline.txt` rather than assuming.
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
   in `docs/DASHBOARD_REVIEW_2026-08-24.md`. Review items CLOSED: A1-A6, D1-D4,
   D7 and D8. **D7 is now closed on all three interactive maps** — CDI Explorer,
   Sites and What-If all call `mapping.fit_view_state()` (Web Mercator per-axis
   solve, tighter axis wins), giving ~9.9 for the full grid against the old
   hand-picked 9.1 / 8.7, and the Explorer's fit follows the district
   multiselect. Pass the container's REAL width: longitude binds for 15 of the
   127 district subsets and an over-stated width clips the sides. STILL OPEN,
   deliberately deferred by the user: D5 (sidebar multiselect clipping), D6
   (CDI legend position) and the sidebar naming (trap 10). POLISH.md item 1
   (dark-on-dark sweep) is effectively done for the pages touched; item 3
   (WorldPop) is untouched and is the real fix for trap 21.
10. **Sidebar page labels are raw filenames** ("WhatIf" with no space) and
    disagree with the Overview cards and page titles. Cosmetic, still open.
11. **`KV_SHARE` is 0.629, and the derivation JSON says 0.6286.** They were
    desynchronised for the whole project. Stage 09 now READS the JSON and rounds
    to 3 dp, which reproduces 0.629 bit-exactly, and aborts if the JSON ever
    stops rounding to it. Using the raw 0.6286 moves the policy cap 6,290 ->
    6,286/month and shifts the 2030 forecast, port requirement and district
    gaps -- i.e. published numbers. Change it only as a deliberate regeneration.
12. **Stage 12 says the forecast headline is defensible for a different reason
    than the report gives.** "Prophet 17.6% vs ARIMA 37.5%" reproduces exactly,
    and MASE ranks the same order on that split -- but under rolling origin
    (980 folds) Prophet base falls to rank 5 of 10 at h=6 and ETS wins. The
    single 2025 split flattered it. Prophet remains the right choice for the
    2030 projection because its logistic trend is the only one that saturates
    (6,230/mo against the 6,290 ceiling); SARIMA has the best AIC in the study
    and extrapolates to 57-81x the ceiling. Claim bounded extrapolation, not
    short-horizon accuracy.
13. **Both figure-producing stages have a `--figures-only` mode. USE IT.**
    `python pipeline/06_build_cdi.py --figures-only`   -> redraws cdi_map.png
    `python pipeline/12_forecast_comparison.py --figures-only` -> redraws both
    forecast PNGs. Each reloads the committed CSVs, recomputes nothing that
    lands in a CSV, and writes only PNGs. A normal re-run of stage 06 hits
    trap 2 (float drift across 3,968 rows of hex_cdi_v1.csv) and a normal
    re-run of stage 12 costs ~6 minutes and rewrites five CSVs -- for a figure
    change, both are pure damage. Hash processed_data/ before and after to
    confirm only the PNG moved.
14. **CDI colour is FIXED over 0-100 and extends, not adapts, above it.**
    `theme.cdi_to_rgb(v, over_max=...)` keeps the inferno ramp anchored to
    0-100 so a value has the same colour at every lens and weight, and fades
    from the inferno ceiling toward white above 100 (weight 1.00 peaks at
    108.8). Do NOT make the whole ramp adaptive -- that would undo the frozen
    denominator's comparability. `ui.cdi_legend(max_cdi)` draws the matching
    bar and states the true range.
15. **One number format for every table:** `ui.int_col()` / `ui.num_col()`.
    Declaring `format="%d"` ad hoc is what produced 129556 in a table beside
    129,556 on the card next to it (review item A4).
16. **The 5.3x holdout figure is the DEMAND LAYER's, not the CDI's.**
    `08_validate.py` tests three predictors: `demand_blend` (pop_n + act_n, no
    supply gap, no equity) = **5.3x** chance at top-10%; `pop_only` = 4.5x;
    `operator_cdi` (demand x gap) = **2.7x, deliberately lower** because the
    gap term demotes already-served areas while the test rewards predicting
    where operators DID build. Never write "the CDI recovers held-out stations
    at 5.3x" -- wrong predictor, and it is not the CDI. Corrected on the Trust
    page and flagged in FYP_PROJECT_MEMORY.md; the memory file's line 136-137
    has always been right, its line 193 is a pre-results plan.
17. **KNOWN, DELIBERATELY UNFIXED: `pop_newly_covered` is 12 people low.**
    `07_recommender.py:90` writes `int(pop[newly].sum())` -- truncation, not
    `round()` -- so each of the 20 sites loses a fractional part (0.19, 0.83,
    0.33, ...) totalling **12.2949**. Hence the published **1,052,353** in the
    CSV vs **1,052,365.2949** recomputed live on the What-If page. Both
    describe the identical 252 hexes; the baseline (`nearest_station_km <=
    2.0`) and the haversine are the same in both, and the sum of FLOAT
    marginals equals the union exactly, so truncation is the ONLY cause.
    Change `int(` -> `round(` ONLY at a final full regeneration -- it moves a
    figure already published in the report.
18. **`operator_crosscheck_template.csv` is the ONLY artifact holding
    hand-entered data.** Stage 08 MERGES into it -- `merge_preserving_manual()`
    refreshes the seven computed columns and carries everything else across on
    `h3_index`. Do NOT "simplify" that back to a plain `to_csv()`: the old code
    rewrote 12 columns over a 15-column file and destroyed the PlugShare
    fieldwork on every full run, silently. Every run now prints
    "MANUAL VALUES PRESERVED: n of m" and warns if a manual row no longer
    matches a selected zone.
19. **The hex grid ROW ORDER is not deterministic between runs.**
    `04_hex_population.py:50` accumulates cells into a Python `set()` and
    line 69 iterates it. Set iteration order for strings depends on
    `PYTHONHASHSEED`, which Python randomises per process. The grid is the same
    4,003 cells every time, in a different order. Consequences, all measured on
    a full scratch run: **1 of the 20 recommended sites changes**
    (`8865050b3dfffff` -> `8865050959fffff`; same district split, identical
    1,052,353 total coverage — the greedy hit a tie and `np.argmax` broke it by
    first index); DBSCAN zone labels shuffle; stage 11's KMeans spatial blocks
    and CV folds shift, moving ablation PR-AUC by up to 0.043 and champion
    PR-AUC 0.5128 -> 0.5159 (champion stays XGBoost tuned).
    **It can also orphan the PlugShare fieldwork:** stage 08 picks zones with
    `nlargest` on `activity_score` / `cdi`, so a tie broken differently selects
    different hexes, and the manual rows no longer match. Stage 08 now WARNS
    and names the orphaned row (trap 18) rather than dropping it silently.
    One `sorted()` at line 69 fixes all of this — but it changes the one
    recommended site and every stage-11 number, so do it at a deliberate
    regeneration, not casually.
20. **Prophet's uncertainty band is not seeded.** In `09_forecast.py`, the
    point forecast `policy_cap` / `accel_cap` is stable to 8e-5 across runs,
    but `policy_lo` / `policy_hi` move by up to **73 registrations/month
    (19%)** — Prophet samples the interval. The Forecast page plots that band,
    so it visibly shifts between regenerations. Everything derived from the
    point forecast (2030 stock, port requirement, district gaps) is stable.
21. **Petaling's dasymetric population is ~4.2x too concentrated. Know the
    direction of this bias before a marker asks.**
    The POI-evidence gate at `04_hex_population.py:110-112` is
    `(res_poi >= 1) | (total_poi >= 3)`; hexes that fail it get weight 0 and
    therefore `pop_est` exactly 0. The documented `res_poi + 1` weight is
    applied ONLY to hexes that already passed — it never rescues one.
    Petaling has the thinnest OSM coverage in KV: **4.7 POIs per 1,000 people
    against KL's 20.6** (Klang has half Petaling's population and twice its
    POIs). So the gate discards **76% of Petaling's area — only 24% kept** —
    packing 2.33M people into 102 km2 at an implied **22,945/km2 against a true
    district density of ~5,422, a 4.2x overstatement**. All 446 excluded hexes
    have zero residential POIs and <=2 POIs of any kind; 436 have none at all.
    **USJ Taipan and Puchong Bandar are absent entirely** — zero POIs across
    ~14 km2 each, both dense townships. Subang airport and the Bukit Cherakah
    reserve are correctly empty. KL is the control: 98.9% of area kept,
    implied density within 1% of actual.
    SENSITIVITY (measured, two counterfactuals — `laplace` = no gate, weight
    `res_poi+1` everywhere; `uniform` = weight 1 everywhere, which over-corrects
    by populating the airport and the forest, so it is an upper bound):
      - **The Klang-vs-KL headline is INSULATED.** Klang 2 km coverage 47.2%
        and its 8 of 20 recommended sites are identical under BOTH variants;
        439,123 in deserts is identical under `laplace` and moves 4.2% under
        `uniform`. Stage 04 preserves district totals per district, so
        re-weighting Petaling cannot move a Klang `pop_est`. The only coupling
        is stage 06's global p99 cap on `pop_n` (24,010 -> 21,234 under
        `uniform` only), which lifts Klang `pop_n` ~10% and pushes 2 more hexes
        over CDI 50.
      - **KV-wide aggregates DO move:** overall 2 km coverage
        **79.3% -> 74.9% (`laplace`) / 62.1% (`uniform`)**; people in severe
        deserts 756,330 -> 702k / 614k; **Gini 0.497 -> 0.527 / 0.610**.
        Recommended sites: 20/20 unchanged under `laplace`, 15/20 under
        `uniform` (Klang's 8 identical in both).
      - **The bias runs AGAINST the thesis.** Under-tagging packs people into
        the well-served hexes, so coverage is OVERSTATED and inequality
        UNDERSTATED. Correcting it raises the Gini. The published figures are
        therefore CONSERVATIVE — say so if the OSM limitation is raised.
    Quote the district-level Klang-vs-KL comparison as the headline; treat
    "KV overall 79.3%" as the figure most sensitive to this. POLISH.md item 3
    (WorldPop 100 m raster) is the real fix and would remove the gate entirely.
22. **"No measurable demand" is a THIRD map channel, not a low CDI.** 2,175 of
    the 4,003 hexes have `pop_est == 0` AND `activity_score == 0`, so their CDI
    is 0 by construction. They used to be drawn at alpha 0 in the app and
    filtered out with `cdi > 0` in `cdi_map.png` -- i.e. as bare canvas. The
    trouble is that 41 hexes, ALL of them in Kuala Lumpur, also reach CDI 0 with
    real population and activity, because their `supply_raw` is at or above the
    p99 cap so `supply_gap` is exactly 0. Those are the BEST-SERVED hexes in the
    study area. Both groups rendered as the same dark shape, so "nobody lives
    here" (an OSM tagging gap -- trap 21) and "everybody here already has a
    charger" (a result) were indistinguishable.
    They are now separated by HUE, not lightness: no-demand hexes go to neutral
    slate off the inferno ramp (`theme.NO_DEMAND_FILL` / `NO_DEMAND_LINE`, and
    `NO_DEMAND_FACE` / `NO_DEMAND_EDGE` in `06_build_cdi.py`, which must stay in
    step), and every demand-bearing hex is drawn including at CDI 0
    (`cdi_to_rgb(..., zero_visible=True)`). `ui.cdi_legend(no_demand=n)` keys
    the slate field; the static figure gets a matching legend patch.
    Do NOT "clean this up" by folding the slate back onto the ramp -- that
    re-creates the ambiguity. The slate is still pickable on purpose: the hex
    inspector's low-coverage warning fires on exactly these hexes.
    The market-interest layer deliberately keeps its own full-frame colouring;
    a predicted probability is defined for an empty hex too, and splitting it
    would imply the model declines to score them.
23. **The greedy optimises `demand_gain`; the headline reports
    `pop_newly_covered`. They disagree on the order, deliberately.**
    `07_recommender.py:83` picks `argmax` of the sum of `demand_pressure` over
    the hexes a site newly covers -- and `demand_pressure` carries the EQUITY
    MULTIPLIER, so a lower-income district outranks a richer one at equal
    population. `demand_gain` is strictly decreasing down the 20; headcount is
    NOT (rank 3 brings 172,796 people against rank 1's 129,556). The Sites page
    used to say in two places that sites were "ranked by how many new people
    they bring", which was simply wrong; both now name demand gain, and the
    callout above the map states the two-quantity split. The worked example is
    derived from the CSV, never hardcoded -- trap 19 can reorder these.
    Related: the site table shows **Host hex CDI** beside **Catchment CDI**
    (population-weighted mean CDI within 2 km, computed display-side on stage-06
    values). Host CDI alone read as a contradiction on the sites the optimizer
    likes most -- rank 7 is a Gombak hex at CDI 0.2 with zero residents that
    covers 50,148 people; its catchment reads 37.7. Do not drop the second
    column: the first one on its own makes the recommender look broken.

## Working style with this user
- Undergraduate student, non-native English: explain plainly, no jargon walls.
- Build one page at a time; show it running; get confirmation; commit; next.
- Commit messages: short imperative ("add CDI map page with weight toggle").
- The user verifies every milestone by running it themselves — make that easy.
