# PROJECT_EXPLAINED.md — a study guide for the presentation

**Project:** Developing Geospatial Optimization and Demand Forecasting Model for Equitable EV Charging Infrastructure
**System name:** Charging Desert Index (CDI)
**Author:** Ng Cheng Xin · TP071136 · Asia Pacific University · FYP 2026
**Study area:** Greater Klang Valley — 7 districts (WP Kuala Lumpur, WP Putrajaya, Petaling, Hulu Langat, Gombak, Klang, Sepang)

> This document is a plain-language study aid. It explains the whole project from four angles — **Data**, **Algorithms/Models**, **Developer/Architecture**, and **Business**. Read it end-to-end before presenting. Nothing here changes the project; it only summarises what was built.

---

## The one-paragraph pitch

EV chargers in the Klang Valley are built where they make the most money — which means they cluster in rich, central Kuala Lumpur, while lower-income and residential suburbs (Klang worst of all) become **"charging deserts."** This project measures that gap **hex by hex** using an original, equity-weighted **Charging Desert Index**, **forecasts** how many EVs (and therefore chargers) the region will need by 2030, and **recommends** where to build next so the most underserved people get served first. It is delivered as an interactive dashboard with two lenses: a **government/equity** view and an **operator/commercial** view.

### Numbers to memorise (the headline evidence)

| Number | What it means |
|---|---|
| **756,330 people** | live in *severe* charging deserts (CDI ≥ 50); **439,123 of them in Klang alone** |
| **47.2% vs 98.0%** | share of people within 2 km of a public charger — **Klang vs KL** (KV overall 79.3%) |
| **7.4×** | gap in chargers-per-100k-people between best- and worst-served districts (Klang 1.68 vs Sepang 12.38) |
| **+1,052,353 people** | brought within 2 km by the **20 recommended sites** — lifts KV coverage 79.3% → **91.8%**, Klang 47.2% → 83.7% |
| **~23,952 ports** | the 2030 public-charger **gap** (24,819 needed vs 867 today) — about **2.5× the national 10,000 target** |
| **17.6% MAPE** | forecast error in back-testing (vs 37.5% for the ARIMA baseline) — lower is better |
| **5.3× chance** | how much better than random the demand model finds real stations (validation) |

---

# ANGLE 1 — THE DATA

Six real data sources feed the system. For each: what it is, how big, how it was cleaned, and why it matters.

### 1. JPJ vehicle registrations (the demand signal)
- **Source / size:** Road Transport Department (JPJ) registration records, `cars_2020…2026.csv` (7 files, **4.58 million rows** of all vehicles). Filtering to `fuel = electric` gives **97,951 EV registrations**, Jan 2020 → Mar 2026 (2026 is a partial year).
- **The cleaning problem ("Rakan Niaga"):** ~74% of EV records carry a **car dealer's** state ("Rakan Niaga" = business partner) instead of the buyer's real location. Using those labels wrongly pins most EVs to KL.
- **How it was fixed — the "national-anchored" method:**
  1. The **national monthly total** is counted from *all* records — the unreliable state label is **never used**, so this number is exact (97,951).
  2. The **KV share** is estimated only from the **genuine** (non-dealer) records' real geography (~25,449 of them), with Selangor scaled down to just its 5 KV districts by population → **KV share ≈ 62.9%** (with a 55%–70% sensitivity band). This lands right next to the report's earlier 60% assumption, which is reassuring.
- **Why it matters:** this is the raw demand history the 2030 forecast is built on. The fix removes a KL bias that would have skewed every downstream number.

### 2. DOSM population (who needs charging)
- **Source / size:** Department of Statistics Malaysia census, `population_district.csv` (**319,200 rows**, 2020–2024, broken down by sex/age/ethnicity).
- **Cleaning:** filtered to the 7 study districts, 2023 reference year, unit conversion (×1000), and the spelling "Ulu Langat" standardised to "Hulu Langat" everywhere → **7 clean district totals** (Petaling largest at 2.33 M, Putrajaya smallest at 118,800).
- **Why it matters:** population is the "how many people are affected" denominator. It is later spread across map cells (see dasymetric mapping) to say *where* the people are.

### 3. DOSM household income (the equity weight)
- **Source / size:** DOSM income survey, `hh_income_district.csv` (**318 rows**, 2019 & 2022). Cleaned to **7 district medians** for 2022 (Klang lowest at RM 8,203; Sepang highest at RM 12,608).
- **Why it matters:** income is the basis of the **equity multiplier** — poorer districts get their charging need weighted *up*, because they are the ones least likely to already have private/home charging.

### 4. DOSM district boundaries (the map skeleton)
- **Source:** the **official** DOSM administrative boundary file (`administrative_2_district.geojson`, pulled from DOSM's public GitHub) — the *same agency* as the income and population data, so names line up. Saved as `kv_districts_dosm.geojson` (7 polygons).
- **Why it matters:** an early version assigned stations to districts using rough rectangular "bounding boxes," which overlapped and mislabelled stations (e.g. inflating KL and Putrajaya). Switching to a proper **point-in-polygon** test fixed this. These polygons are also the outline from which the analysis grid is built.

### 5. OpenStreetMap points of interest (the activity proxy)
- **Source / size:** OSM places pulled with OSMnx, `KV_Demand_Proxies.csv` (~**108,831** POIs, 11 categories). Cleaned to `poi_kv_clean.csv` (**108,785**; dropped 9 near-empty tag columns and 46 "outside KV" rows). Shopping (35,910), work (30,527) and residential (15,913) make up ~76%.
- **Second cleaning pass:** OSM often tags one real place twice (a point *and* a building outline). **538 such double-tags** were merged (same name + category within ~350 m) → `poi_kv_clean_v2.csv`.
- **Why it matters:** we have no real "where do people drive and park" data, so POIs are the **proxy for charging demand** (malls, workplaces, condos = where cars sit long enough to charge). POIs also provide the *residential evidence* used to place population on the map.

### 6. EV charging stations (the supply)
- **Source / size:** three sources fused — **OpenChargeMap (OCM)**, **OpenStreetMap**, and **Google Places** — into `KV_Master_Fused_EV_Stations_FullDetails.csv` (**545 rows**).
- **Cleaning into `ev_stations_kv_clean_v2.csv` (535 rows):**
  - **District labels** re-done with the official polygon test (not bounding boxes).
  - **Access type** classified: **Public**, **Public (assumed – Google listing)**, or **Private (restricted)** — e.g. `[Restricted]` condo chargers are flagged private. This gives the crucial **`is_public_facing`** and **`is_operational`** flags.
  - **Honest imputation:** missing port counts are median-filled but **flagged** (`ports_imputed`); missing power is left blank (`power_known = false`) rather than inventing a number.
  - **Fuzzy cross-source dedup** (within 120 m + similar name/operator) removed the last duplicates.
- **The number that matters:** of 535 stations, **376 are public-facing AND operational** — this is the "supply" the whole analysis uses. (Raw station-share is deliberately *not* the headline, because it flatters KL; coverage and per-capita numbers are fairer.)

### Bonus — two external cross-checks (validation, not core data)
- **Google Places live sweep:** an independent count found ~564 public stations vs our 376 — but the extra ones cluster in already-served Petaling/KL, so the equity gap actually *widens* with fresher data.
- **PlugShare manual check** of the 4 worst Klang desert hexes: confirmed that public charging in Klang sits at **commercial nodes** (Aeon Mall, GM Klang, town centre, hotels) while residential areas stay empty — i.e. *charging follows commercial-ROI siting, not residential need.*

---

# ANGLE 2 — THE ALGORITHMS & MODELS

Every method, in plain language: what it's for, how it works, and how we know it's trustworthy.

### A. Dasymetric population mapping — "spread the people onto the map"
- **Purpose:** we only know population per *district* (7 numbers). The analysis needs population per small **map cell**. Simply splitting a district evenly would put people in forests and lakes.
- **How it works:** the region is tiled into **4,003 hexagons** (H3 resolution 8, each ~0.74 km²). A hexagon is judged **inhabited** if it has ≥1 residential POI or ≥3 POIs of any kind (**1,585 inhabited ≈ 40%**). Each inhabited hex gets a weight = (residential POIs + 1), capped at the district's 99th percentile so one mega-condo cell can't hog everything. District population is then split in proportion to these weights.
- **Validation:** by construction, **each district's hexes add back up to its exact official total** — this is checked and passes for all 7. (H3 = Uber's hexagonal grid system; "dasymetric" just means "distribute using extra evidence of where people actually live.")

### B. Dwell-time POI weighting — "not all places are equal for charging"
- **Purpose:** a shopping mall is a far better charging spot than a 7-Eleven, because cars park there for hours. We need to reflect that.
- **How it works:** every POI category is given a weight from 0 to 1 based on typical **parking/dwell time**: work 1.0, residential 1.0 (Malaysia's high-rise, no-home-charging segment), shopping/entertainment 0.7, transport 0.6, education/healthcare/food 0.5, etc. A hex's **activity score** is the sum of its POIs' weights. The weights live in one editable config block, so they can be justified and sensitivity-tested (not hidden magic numbers). Grounded in dwell-time literature (Andrenacci 2016, Pagany 2019).
- **Validation:** the activity layer is later shown to add real predictive signal over population alone (see holdout recall).

### C. The Charging Desert Index (CDI) — the heart of the project
- **Purpose:** one number per hex (0–100) for "how badly is this place an underserved charging desert."
- **The formula:**
  `CDI = 100 × normalise( DemandPressure × SupplyGap )`
  - **DemandPressure** = (0.5 × population + 0.5 × activity) × **equity multiplier**
    - equity multiplier = (KV median income ÷ district income), clipped to 0.75–1.35 — poorer districts nudged up, but the tilt can never dominate.
  - **SupplyGap** = 1 − Supply, where **Supply** = the sum of `exp(−distance / 1.5 km)` over all 376 public stations. This is a **"streetlight" decay**: a charger right on top of you counts a lot, one 3 km away barely counts.
  - **normalise** = divide by the biggest value, so CDI = 100 always marks the single worst hex.
- **Why multiply?** A desert needs **both** conditions: lots of people who need charging **AND** nothing nearby. Multiplying means zero demand → zero CDI (no false deserts in empty land).
- **Validation (three ways):**
  1. **Entropy weighting** (an objective, data-driven way to pick the population/activity blend) independently suggests ~0.47/0.53 — essentially the 50/50 we chose.
  2. **Sensitivity test:** even when the blend is swung hard or equity is switched off, **70–96% of the top-50 deserts stay the same** — the deserts are real, not an artefact of the weights.
  3. Every score **decomposes into reasons** ("24,010 residents, activity 386, ×1.24 equity, nearest charger 2.0 km") — explainability is a feature.

### D. Greedy maximal-coverage optimisation — "where to build next"
- **Purpose:** pick the best 20 new sites to cover the most underserved people.
- **How it works (Church & ReVelle 1974):** "covered" means a public charger within 2 km. Starting from the 376 existing stations, the algorithm repeatedly places **one** new site at the candidate hex that newly covers the **most demand-weighted, currently-uncovered population**, and repeats 20 times. Candidates are limited to hexes with real activity (a charger needs a host venue like a mall or car park).
- **Result:** coverage rises from **79.3% → 91.8%** (+1,052,353 people); Klang jumps **47.2% → 83.7%**.
- **Validation:** compared head-to-head against K-Means (below) on the same 20-site budget — greedy covers **1.05 M vs K-Means' 760 k people** — because greedy optimises the actual goal (coverage) directly.
- **A subtle point to defend:** a recommended site can sit in a *low*-CDI hex. That's correct — the CDI **diagnoses** where the problem is; the optimiser **prescribes** the best position to *serve* it (a 2 km circle placed at a pocket's edge covers the whole pocket).

### E. K-Means clustering — the comparison baseline
- **Purpose:** the report's original method; used here as an honest benchmark.
- **How it works:** demand-weighted K-Means finds 20 "gravity centres" of demand; centres are snapped to the nearest candidate hex, then scored for coverage the same way.
- **Result:** it finds sensible demand centres but covers less than greedy (~72%) — which is exactly the point: it clusters demand, it doesn't optimise coverage.

### F. DBSCAN clustering — naming the desert zones
- **Purpose:** group scattered high-CDI hexes into a few contiguous, nameable **desert zones**.
- **How it works:** DBSCAN (a density-based clusterer that needs no preset number of clusters) groups hexes with CDI ≥ 40 that are within ~1.6 km of each other. **87 desert hexes → 8 zones.**
- **Result / insight:** two *types* of desert emerge — **Petaling's zones are biggest by population** (moderate severity) while **Klang's zones are the most severe** (highest average CDI). This "two desert types" finding is shown explicitly on the dashboard.

### G. Prophet logistic demand forecast — "how many EVs/chargers by 2030"
- **Purpose:** project EV registrations to 2030 and convert them into a charger-shortfall number.
- **How it works:**
  - **Prophet** (Facebook's time-series tool) with **logistic growth** — an **S-curve** that levels off at a ceiling, which is the realistic shape for technology adoption.
  - The ceiling comes from **policy, not curve-fitting:** Malaysia's target of 15% of new vehicles being electric by 2030 → about 6,290 EV registrations/month for KV (a 30%-target "accelerated" scenario doubles that).
  - Compared against an **ARIMA(1,1,1)** statistical baseline (the report's original method).
  - **Flow → stock:** adding up registrations gives EVs on the road. Dividing by an EVs-per-charger ratio (10/15/20, with 15 central) gives ports needed; allocating by district population gives the per-district gap.
- **Validation — the back-test:** trained on data up to 2024 and tested on 2025 (a year demand *doubled* — a deliberately hard test). **Prophet-logistic error = 17.6% MAPE**, vs 28.5% (Prophet-linear) and 37.5% (ARIMA). So the a-priori design choice cut the baseline error by more than half. (MAPE = average % error; lower is better.)
- **Result:** KV EV stock ~61,568 today → **372,266 by end-2030** (policy). Chargers needed ≈ 24,819 vs 867 today → **gap ≈ 23,952 ports**, robust even if today's count is doubled.

### H. Validation suite — "why believe any of this"
- **Holdout recall:** hide 20% of real stations (10 random trials); do our demand layers point to where they are? The demand blend puts hidden stations in its **top 10% of hexes 5.3× more often than chance** — and adds real signal over population alone. Importantly, the full *operator* CDI (with the gap term) scores *lower* on this test **by design** — its whole job is to point *away* from already-served areas, so a good desert index *should not* just re-find existing stations.
- **Coverage-vs-radius curve, capacity-per-port table, and the operator cross-check** give three more independent angles that all agree Klang and Gombak are worst-served — agreement across unrelated measures is what makes the finding robust.

---

# ANGLE 3 — THE DEVELOPER / ARCHITECTURE VIEW

How the software is built and why it's structured this way.

### The golden rule: the "artifact pattern"
- **Heavy computation lives in the pipeline; the app only reads results.**
- `pipeline/` scripts do all the maths and **write CSV/GeoJSON/PNG files into `processed_data/`**.
- The Streamlit app in `app/` **only reads those files** — it never re-runs any pipeline logic.
- **Why:** this keeps the app fast and guarantees the dashboard can never "drift" from the validated analysis. What you present is exactly what the pipeline produced.

### The numbered pipeline (run in order by `run_pipeline.py`, ~30 s total)
| Stage | File | What it produces |
|---|---|---|
| 00 | `00_collectors/*` | raw data collection (OCM/OSM/Google stations, OSM POIs) — run rarely |
| 02 | `02_fix_stations.py` | clean stations (polygon districts, access flags, dedup) → `ev_stations_kv_clean_v2.csv` |
| 03 | `03_demand_series.py` | national-anchored EV demand series + KV share + district weights |
| 04 | `04_hex_population.py` | the 4,003-hex grid + dasymetric population |
| 05 | `05_poi_activity.py` | POI dedup + dwell-time activity per hex |
| 06 | `06_build_cdi.py` | the **Charging Desert Index** (`hex_cdi_v1.csv`) + hero map |
| 07 | `07_recommender.py` | 20 greedy sites + K-Means comparison + DBSCAN desert zones |
| 08 | `08_validate.py` | holdout recall, coverage curve, capacity, cross-check template |
| 09 | `09_forecast.py` | Prophet forecast + 2030 charger-gap table |

Each stage prints numbered "STEP" banners and writes audit files, so every change to the data is traceable. `run_pipeline.py` runs them in order and stops on the first error.

### The "instant interactivity" trick (the clever bit)
- The CDI file (`hex_cdi_v1.csv`) stores the **ingredients** of the index separately: `pop_n`, `act_n`, `equity_mult`, `supply_gap`, `nearest_station_km`, etc.
- So when the user moves the **weight slider** or flips the **Government/Operator toggle**, the app just re-does one line of arithmetic (`app/lib/cdi.py` → `recompute_cdi`):
  `CDI = 100 × normalise( (w_pop·pop_n + w_act·act_n) × equity × supply_gap )`
  — where equity = the stored multiplier (Government) or **1.0** (Operator), and `w_act = 1 − w_pop`.
- **No pipeline call, no recomputation of geography** — it updates in **milliseconds**. This is why the sliders feel instant.

### The Streamlit app structure
- **Entry point:** `app/Home.py` is a **cover / landing screen** (title, headline stats, "Enter Dashboard" button). Launch with `streamlit run app/Home.py`.
- **Pages** (`app/pages/`, shown in the sidebar in order): `1_Overview` (Executive Overview) → `2_CDI_Map` → `3_Sites` → `4_Forecast` → `5_WhatIf` → `6_Trust` (Validation & Data) → `7_Investment` (Investment Scenario).
- **Shared library** (`app/lib/`, the single source of truth so every page looks/behaves the same):
  - `data.py` — the **only** place that reads files; every loader is cached (`@st.cache_data`) so warm pages load in under a second.
  - `theme.py` — design tokens (colours, fonts) + all CSS in one place.
  - `ui.py` — reusable components (KPI cards, nav cards, HTML tables, panels).
  - `mapping.py` — shared pydeck map layers (stations, borders, dim-outside mask).
  - `cdi.py` — the live-recompute described above.
- **Maps** use pydeck's `H3HexagonLayer` (the CDI file already carries the `h3_index`, so no geometry conversion is needed at run time).

---

# ANGLE 4 — THE BUSINESS VIEW

Who uses this, what value it delivers, and the one thing it deliberately refuses to do.

### Two users, two lenses (same data, one toggle)
1. **Government / urban planner — the EQUITY lens (Government view, equity ON).**
   - **Wants:** to quantify the fairness gap, count underserved people, target subsidies, and track progress against Malaysia's 10,000-charger goal.
   - **Value delivered:** a defensible, hex-level map of where underserved residents are; the 20-site plan that lifts the worst district (Klang) from 47% to 84% coverage; alignment with **SDG 10 (reduced inequality)** and **SDG 11 (sustainable cities)**. The pitch to policymakers: *"MEVnet lists the socio-economic siting criteria; we're the tool that actually computes them."*
2. **Operator / Charge-Point Operator (CPO) — the COMMERCIAL lens (Operator view, equity OFF).**
   - **Wants:** ranked candidate sites *with reasons*, catchment population, distance to competitors, coverage gain, and a way to sanity-check the money.
   - **Value delivered:** de-risking a **RM 1.5–2 M-per-site** capital decision. Flipping the toggle to "Operator" removes the equity multiplier, so the map shows **pure market demand** — the same engine, ranked by commercial attractiveness instead of fairness. Page 6 (Investment Scenario Calculator) then lets them stress-test the business case for any candidate.

### Why revenue is deliberately NOT predicted — the "data-availability paradox"
- Real profitability depends on **utilisation** — how often each charger is actually used. That **session data is proprietary**: it is the operators' competitive moat, and there is **no public dataset** of who charges where and how often.
- So an honest system **cannot** predict revenue. Instead this project forecasts what *is* knowable from public data — **adoption** (how many EVs are coming) and **need** (where underserved people are) — and stops there.
- **Page 6 is therefore an *indicative scenario* tool, not a forecast.** It computes the *consequences of assumptions the user sets* (ports, sessions/day, tariff, CapEx…) and shows the **utilisation cliff** (a site that pays back in 3 years at high use can be badly under water at low use). Every output is labelled "indicative," with a prominent "not a revenue prediction" banner. This honesty is itself a selling point — it's why the tool is credible.

### What makes this project different (defensible differentiators)
- **Equity as an objective function**, not a compliance checkbox — fairness is *built into* the index, then toggled off for the commercial view.
- **Explainability** — every desert score decomposes into human-readable reasons.
- **A real Malaysia gap** — high-rise residents can't charge at home, so residential/condo POIs are weighted heavily; national policy lists criteria but no tool computes them at hex level.
- **Honesty about limits** — validated results, stated assumptions, and a refusal to fake a revenue number no honest model could produce.

---

## Quick "tricky question" defences (from the project's own risk notes)

- **"Isn't 79% coverage fine?"** — At a fair 500 m threshold, KL reaches 33% but Klang only 5.2%; "79% at 2 km" hides the equity gap. Klang is worst-served at *every* distance.
- **"Aren't the CDI weights arbitrary?"** — No: an objective entropy method independently lands on ~0.5/0.5, and the deserts survive (70–96% overlap) even when the weights are swung hard.
- **"Why does a recommended site sit in a low-CDI hex?"** — The CDI *diagnoses* the problem; the optimiser *prescribes* the best serving position. Different questions, correct behaviour.
- **"Why does the operator CDI recall real stations poorly?"** — By design. Its gap term steers *away* from served areas; a desert index that re-found existing stations would be useless.
- **"Your station snapshot is out of date."** — The pipeline is the product, the snapshot is the demo; it re-runs on fresh data. Live Google/PlugShare checks show the equity gap only *widens* with newer data.
- **"Can you predict the revenue?"** — No, and neither can anyone honestly — the utilisation data isn't public (the data-availability paradox). We forecast adoption and map need, and give an *indicative* scenario tool for the commercial case.
