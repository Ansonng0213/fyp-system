# FYP PROJECT MEMORY — Ng Cheng Xin (TP071136)

**Title:** Developing Geospatial Optimization and Demand Forecasting Model for Equitable EV Charging Infrastructure
**Programme:** APD3F2601CS(DA) — B.Sc. (Hons) CS, Data Analytics, Asia Pacific University
**Supervisor:** Ms. Tan Li June | **2nd Marker:** Ms. Farhana Illiani Binti Hassan
**Status:** IR (Interim Report) submitted. FYP2 = modeling + system build phase.
**Study area:** Greater Klang Valley — 7 districts: WP Kuala Lumpur, WP Putrajaya, Petaling, Hulu Langat, Gombak, Klang, Sepang

---

## 1. Core Idea

EV chargers in KV are deployed by commercial ROI logic → concentrated in rich commercial districts → "charging deserts" in M40/B40 residential suburbs. Project builds a proxy-based (no charging-transaction data needed), equity-weighted geospatial optimization pipeline:

1. **Map** existing infrastructure gaps (multi-source fused station data)
2. **Forecast** EV registration demand to 2030 (Prophet vs ARIMA on JPJ time series)
3. **Optimize** new station placement (K-Means + DBSCAN on H3 hex-aggregated **Charging Desert Index (CDI)** — original composite metric weighting POI dwell-time demand, population, income equity, and existing coverage)
4. **Deliver** interactive geospatial dashboard for urban planners / CPOs

Methodology: CRISP-DM. SDG 10 + SDG 11 alignment. Key refs: Ermagun & Tian 2024, Hsu & Fingerman 2021, Roy & Law 2022, Pagany et al. 2019, Erbaş et al. 2018, Andrenacci et al. 2016.

---

## 2. Data Inventory

### Raw (`raw_data/`)
| File | Rows | Notes |
|---|---|---|
| cars_2020..2026.csv (7 files) | 4,578,675 total | JPJ registrations, cols: date_reg, type, maker, model, colour, fuel, state. 2026 partial (→ Mar 2026) |
| hh_income_district.csv | 318 | DOSM, 2019 & 2022, mean+median income |
| population_district.csv | 319,200 | DOSM, 2020–2024, by sex/age/ethnicity |
| KV_Demand_Proxies.csv | ~108,831 | OSM POIs via OSMnx, 11 categories |
| KV_Existing_EV_Stations.csv | 340 | OCM (288) + OSM (52) merged |
| KV_EV_Stations_OSM_only.csv | 52 | OSM-only stations |
| KV_EV_Google_MicroGrid.csv | ~460 | Google Places, 1.5km micro-grid sweep |
| KV_EV_Google_Validation.csv | 225 | Google validation run |
| KV_EV_Missing_Stations.csv | 111 | Google stations >threshold from fused set (has nearest_ours_m) |
| KV_Master_Fused_EV_Stations_FullDetails.csv | 545 | Final fused OCM+OSM+Google |

### Processed (`processed_data/`)
| File | Rows | Key facts |
|---|---|---|
| jpj_kv_ev_clean.csv | 60,063 | KV EV registrations 2020-01→2026-03. By year: 45 / 178 / 2,078 / 8,481 / 13,288 / 27,280 / 8,713(partial). State: KL 44,946, Selangor 15,116, Putrajaya 1 |
| income_kv_clean.csv | 7 | 2022 median: Klang lowest RM8,203; Sepang highest RM12,608 |
| population_kv_clean.csv | 7 | 2023: Petaling 2,334,700 max; Putrajaya 118,800 min |
| poi_kv_clean.csv | 108,785 | shopping 35,910 / work 30,527 / residential 15,913 = 75.8%. KL 41,256 POIs, Putrajaya 783 |
| ev_stations_kv_clean.csv | 535 | KL 326 (60.9%) / Hulu Langat 50 / Petaling 49 / Sepang 45 / Putrajaya 34 / Gombak 17 / Klang 14. Source: OCM 278, Google 205, OSM 52 |

**Headline desert evidence (v2 — official-boundary corrected; USE THESE, not v1 raw share):**
- ⚠ REPORTING CONVENTION: lead with **coverage** and **per-100k** metrics, NOT raw station-share. The old v1 "KL holds 60.9% of stations" is SUPERSEDED — after the polygon-sjoin district fix KL has 294/535 stations (55.0%) and 189/376 public+operational (50.3%), a weaker/less-defensible framing.
- Defensible equity headlines: **2km population coverage — Klang 47.2% vs KL 98.0%** (KV overall 79.3%; full ladder: Klang 47.2 / Gombak 58.5 / Sepang 64.2 / Hulu Langat 78.1 / Petaling 89.4 / Putrajaya 95.3 / KL 98.0). **Per-100k public+operational stations — 7.4× worst-to-best disparity** (Klang 1.68 vs Sepang 12.38; KL 9.42). Verified against ev_stations_kv_clean_v2.csv + hex_cdi_v1.csv on 2026-07-21.

---

## 3. Pipeline Scripts

| Script | Role |
|---|---|
| collect_ev_stations.py | OCM bounding-box pull → polygon filter → sjoin district labels (⚠ hardcoded OCM API key) |
| supplement_ev_stations.py | OSM charging_station pull, 50m dedup vs OCM, merge |
| validate_ev_google.py | (misnamed) Google Places micro-grid extractor, 1.5km circles (⚠ hardcoded Google API key) |
| fuse_datasets.py | Google vs OCM/OSM 100m dedup → 545-row master fuse |
| traffic.py | OSMnx POI extraction, 11-category mapping, district sjoin |
| preprocessing.ipynb | All 5 dataset cleaning flows (mirrors report §3.4.1) + EDA charts |

Key preprocessing decisions already made:
- JPJ: filter fuel='electric' (97,951) → **Rakan Niaga fix**: 74% of EV records are dealer-registered with no real state; 60% of them sampled (seed 42) and redistributed to KV using genuine-KV proportional weights (74.7% KL / 25.3% Sel / 0.006% Putrajaya) → 60,063 final
- Stations: Google's 205 missing districts filled via **hardcoded lat/lon bounding boxes** (Sepang box lat max extended 2.90→3.00); total_ports & max_power_kw median-imputed; 10 OCM exact-coordinate duplicate pairs dropped (545→535)
- Income ref year 2022; population ref year 2023 (×1000 unit conversion); "Ulu Langat"→"Hulu Langat" standardized everywhere
- POI: 9 sparse OSM tag columns dropped; 46 "Outside KV" rows removed

---

## 3.5 ✅ FYP2 PROGRESS LOG

**IR report is FROZEN — all fixes happen in data/code only. Frame changes as "detected & corrected during FYP2 data validation" (CRISP-DM iteration).**

**[SOLVED] Problems 1+2 — corrected station pipeline (`fix_stations_p1_p2.py` → `ev_stations_kv_clean_v2.csv`):**
- District assignment now via polygon sjoin on **official DOSM administrative_2_district.geojson** (dosm-malaysia/data-open GitHub — same agency as income/pop data, citable). Saved as `kv_districts_dosm.geojson`. 2 edge stations recovered via nearest-within-2km.
- **v1→v2 district shifts:** KL 326→294 (−32) | Putrajaya 34→**11** (−23, Cyberjaya/Bangi returned to rightful districts) | Klang 14→**22** (+8) | Petaling 49→69 (+20) | Hulu Langat 50→67 (+17) | Gombak 17→21 (+4) | Sepang 45→51 (+6). Even 7 OCM/OSM labels flipped under official boundaries (audit_district_changes.csv).
- **Access classification restored:** Public 151 | Public-assumed (Google) 205 | **Private (restricted) 161** (101 in KL!) | Unknown 28. `is_public_facing` + `is_operational` flags added; 6 CLOSED_TEMPORARILY harmonized & flagged.
- **Honest imputation:** total_ports median-filled with `ports_imputed` flag (91 rows); max_power_kw left NaN with `power_known` flag (257 unknown) — no more fabricated 22 kW values.
- Second-pass fuzzy dedup (120m + name similarity): **0 residual duplicates** → validates original fusion quality (report this positively).
- **New headline desert metric (public-facing operational stations per 100k pop):** Klang **1.68** (worst) | Gombak 1.86 | Petaling 2.48 | Hulu Langat 2.81 | Putrajaya 7.58 | KL 9.42 | Sepang 12.38 (KLIA effect — motivates hex-level CDI over district averages). **7.4× worst-to-best disparity; KL:Klang = 5.6×.** Story sharper than v1 and now defensible.

**[SOLVED] Problems 3+4 — national-anchored demand series (`fix_demand_p3.py`):**
- Dealer 'Rakan Niaga' state labels (72,502 records, 74%) are **never consulted**. National monthly series is exact: 97,951 EVs, 74 months, 2020-01→2026-03 (2026 partial). Annual: 71 / 257 / 3,129 / 13,301 / 21,789 / 44,813 / 14,591.
- **KV share = 62.9% data-driven**: genuine records (25,449) in KV states = KL 12,378 + Selangor 4,183×0.865 (KV-5 pop factor) + Putrajaya 1 → 62.9%. Converges with IR's cited 60% assumption → convergent validity. Sensitivity band 55%/70%.
- KV totals 2020–26Mar: central 61,568 | low 53,873 | high 68,566. **v1 total was 60,063 — within 2.5% of v2 central** → v1's TOTAL was fine; its SPATIAL split was the broken part (v1 KL share 74.8% vs population-based 24.0%, income-adjusted 24.4%).
- **District allocation weights v2** (primary=population 2023, sensitivity=pop×relative median income 2022): Petaling 27.9/26.7 | KL 24.0/24.4 | Hulu Langat 17.5/19.5 | Klang 13.6/11.1 | Gombak 11.6/11.7 | Sepang 4.1/5.1 | Putrajaya 1.4/1.4. Problem 4 solved by design: district forecast = KV forecast × weights.
- Outputs: jpj_national_monthly.csv, jpj_kv_monthly_v2.csv (low/central/high), district_allocation_weights_v2.csv, kv_share_derivation.json (audit), ev_demand_series_v2.png (chart).

**[SOLVED] Problem 5 — dasymetric hex population (`fix_hexpop_p5.py`):**
- H3 res-8 grid built from DOSM polygons: **4,003 hexes** (Hulu Langat 994, Klang 728, Gombak 726, Sepang 633, Petaling 584, KL 280, Putrajaya 58). Hex→district by cell containment.
- Two-class dasymetric: inhabited = ≥1 residential POI OR ≥3 total POIs → **1,585 inhabited (40%)**; weights = res_poi+1 (Laplace), winsorized at district p99; hex_pop = district_pop × weight/Σ. **District totals preserved exactly (verified all 7 OK)**.
- Inhabited hex stats: median 2,120, mean 5,274, max 98,119 (dense KL high-rise hex — documented estimate; log-dampened weights available as sensitivity if challenged). 38/15,913 residential POIs fell outside grid edges (fine).
- Outputs: hex_population_v1.csv, **hex_grid_kv.geojson (THE master analysis grid for CDI + dashboard)**, hex_population_map.png (choropleth sanity check — expected KV urban structure confirmed).
- Documented limitations: OSM residential completeness bias; income stays district-level (copied as equity attribute only). User must `pip install h3` locally.

**[SOLVED] Problem 7 — POI dedup + dwell-time activity (`fix_poi_p7.py`):**
- Same-name+category dedup within ~350m (res-9 parent cell): **538 double-tags removed** (0.5%; residential 121, shopping 120 top — the node+building pattern). Unnamed "Unknown" POIs (79,688) exempt. Audit: audit_poi_dedup.csv.
- **Dwell-time weights (config dict, stakeholder-adjustable):** work 1.0, residential 1.0 (condo/no-home-charging segment), shopping 0.7, entertainment 0.7, transport 0.6, education/healthcare/food 0.5, exercise/community 0.4, other 0.2. Grounded in dwell-time lit (Andrenacci 2016, Pagany 2019).
- **hex_activity_v1.csv = master grid + per-category counts + activity_score.** 1,827 hexes active (vs 1,585 inhabited — commercial-only hexes exist, correct). Median 11.7, max 902.9; top-5 all KL core (KLCC/Bukit Bintang pattern confirmed on map). 280 POIs fell off grid edges.
- **ALL DATA FIXES NOW DONE (P1-P5, P7-P8, P13 pending user's key revocation). CDI ingredients ready: pop_est (P5) + activity_score (P7) + district_income + stations v2.**

**Strategic decisions from business-value discussion (user's questions):**
- Station data freshness fear → mitigations locked into roadmap: MEVnet official benchmark table (5,839 points national Mar 2026), operator-list cross-check sample (JomCharge/Gentari/ChargEV), fresh re-pull near submission, provenance table. "The pipeline is the product, the snapshot is the demo."
- Revenue modeling: NOT in IR scope (objectives = deserts, forecast, optimize, dashboard). Full revenue PREDICTION impossible (no utilization data — the paradox). BUT "Investment Scenario Calculator" is buildable & honest: user-adjustable assumptions (sessions/day, kWh/session, tariff RM/kWh, CapEx) → indicative breakeven. Label as scenario tool, never prediction. Dashboard bonus module.
- CPO persona wants: ranked sites WITH reasons (explainability), catchment stats, competitor distance, scenario testing, portfolio-under-budget optimization, PDF scorecards, validation metrics for trust.
- Gov persona wants: equity gap quantification (Gini before/after), underserved population counts, district progress vs 10k target, subsidy targeting, MEVnet-complementary positioning.

**Market research conclusions (Jul 2026):**
- Global category real & maturing: "EV charging site selection & planning platforms" (CB Insights) — geospatial+mobility+grid data → demand forecast, site comparison, ROI prediction. Players: EVpin (data consolidation per address: registrations, traffic, competitors, zoning, grid; utilization scoring), Kevala/EVlogic (grid capacity focus), Driivz-style factors (dwell compatibility, competitive gaps, own-network benchmarking). Industry shifting "from rapid expansion toward strategic deployment."
- Commercial ROI/utilization prediction rests on PROPRIETARY session data moats → user's decision to DROP revenue modeling is validated; scope = adoption forecast + reason-coded desert identification + recommendations.
- Our differentiators: (1) equity as objective function not compliance checkbox, (2) explainability ("desert because of reasons X/Y/Z" decomposition), (3) Malaysia gap — MEVnet lists socioeconomic siting criteria but no tool computes them → "MEVnet lists the criteria; we compute them." (4) Optional grid nod: OSM substation feasibility flag layer.
- Workflow decision: design/strategy stays in chat (memory file = bridge); Claude Code in terminal recommended for FYP2 build phase (Streamlit repo) — save CLAUDE.md in repo pointing to FYP_PROJECT_MEMORY.md.

**[BUILT] CDI v1 (`build_cdi.py` → hex_cdi_v1.csv, cdi_map.png):**
- Formula implemented as designed: CDI = 100×norm(DemandPressure × SupplyGap); DemandPressure = (0.5·pop_n + 0.5·act_n)×equity_mult (income-inverse, clipped 0.75–1.35); Supply = Σ exp(−d/1.5km) over 376 public+operational stations, p99-winsorized min-max norms.
- **Entropy weighting validation: data-suggested blend = 0.47/0.53 vs our 0.5/0.5** → objective method independently confirms the choice; 96% top-50 overlap.
- **Sensitivity: top-50 desert overlap = 70% (pop-heavy), 70% (activity-heavy), 96% (entropy), 82% (equity OFF)** → deserts are real, not weight artifacts. Built-in marker defense.
- Equity multipliers: Klang 1.241, Petaling 1.058, Putrajaya 1.012, Gombak 1.000, KL 0.995, HL 0.908, Sepang 0.807.
- **HEADLINE RESULTS:** Klang = desert capital: 26 severe hexes (CDI≥50), **439,123 people in severe desert zones**; #1 desert CDI=100 at central Klang (3.01168,101.42758), ~24k residents. Petaling highest mean CDI (20.3) incl. 70k-resident Kota Damansara hex (CDI 67). Semenyih classic outer desert (CDI 67, 4.9km to charger). **203 inhabited hexes have ZERO stations within 5km.** Median nearest public station 4.16km.
- Nuance to defend: some top Klang hexes have a charger 0.7–1.4km away but still score high — supply_n is RELATIVE access (9 stations/5km for 21k people vs KL's 100+); per-capita framing if challenged.
- Reason strings work natively: "CDI 100: 24,010 residents, activity 386, ×1.24 equity, nearest charger 2.0km."

**[BUILT] Site Recommender (`build_recommender.py` → recommended_sites_v1.csv, desert_zones_v1.csv, recommendation_map.png):**
- Greedy maximal coverage (Church & ReVelle 1974), coverage = public charger ≤2km, candidates = activity>0 hexes (1,827), seeded by 376 existing stations. Needs scikit-learn (`pip install scikit-learn`).
- **HEADLINE: baseline coverage 79.3% (6.62M/8.36M people ≤2km). 20 optimal sites → 91.8% (+1,052,353 people).** Klang baseline **47.2%** (the desert thesis in one number) → 83.7% after its 8 sites. Sites by district: Klang 8, Gombak 5, Petaling 3, HL 2, KL 2, Sepang/Putrajaya 0.
- **Greedy vs K-Means (same 20-site budget): 1,052,353 vs 760,341 people (K-Means = 72%)** → empirical justification for coverage framing; K-Means = IR deliverable used as comparison baseline.
- **DBSCAN desert zones (CDI≥40, eps 1.6km):** 87 desert hexes → 8 contiguous zones + 36 isolated. Two desert types: Petaling zones biggest by population (287k, 236k, 147k; moderate severity ~42-52 CDI) vs Klang zones highest severity (mean CDI 66.6, 69.1). Zone table in desert_zones_v1.csv.
- **CRITICAL NUANCE (viva risk):** recommended sites can sit in LOW-CDI hexes (site #1 CDI 5.6, #7 CDI 0.2) — CORRECT behavior: CDI finds problem areas, optimizer finds best SERVING positions (a 2km circle placed at a pocket's edge covers the whole pocket; the host hex itself may already be covered). CDI = diagnosis, optimizer = prescription; they answer different questions.
- Sepang/Putrajaya correctly receive 0 sites (already covered / low demand density).

**[BUILT] Validation (`validate_cdi.py`):**
- **HOLDOUT RECALL (10 trials, 20% hidden): demand_blend top-10% hexes contain 53.4% of hidden real stations = 5.3× chance; top-20% → 75.2% (3.8×).** Beats pop_only (44.6%@10%) → activity layer adds +9pts real signal, justifying POI work.
- **CRITICAL INTERPRETATION (viva-sensitive): operator_cdi (demand×gap) recall is LOWER (27.1%@10%) BY DESIGN** — gap term down-ranks already-served hexes. Two-part validation: (1) demand layers validated against where market built (5.3× lift); (2) gap term confirmed to redirect away from served areas. If CDI had high recall on existing stations it would be useless (would re-recommend existing sites). demand_blend = "where stations went"; CDI = "where next ones should go."
- **Coverage curve per district (report figure coverage_curve.png):** at 500m Klang 5.2% vs KL 33.4%; at 1km Klang 20.7% vs KL 64.2%.
- Capacity table official: KL holds 463/867 ports (53%); Gombak 26,839 & Klang 25,200 people/port vs Sepang 3,533. KV 71 EVs/port; 2× robustness → 36 (still above ~10-20 guideline).
- **USER MANUAL TASK (~1hr): operator_crosscheck_template.csv** — 8 zones (4 KL served, 4 Klang desert) with maps links + our prefilled counts (KL zones: 12/16/3/10 stations ≤2km; Klang desert zones: 0/1/0/0). Fill JomCharge/Gentari/ChargEV counts from their apps → external recall estimate + desert confirmation.
- Note: K-Means results vary slightly across sklearn versions (user 68% vs sandbox 72% of greedy) — cite "~70%", pin versions in requirements.txt. Greedy fully deterministic & reproduced.

**[BUILT] Forecast (`build_forecast.py` → forecast_kv_monthly.csv, charger_gap_2030.csv, forecast_chart.png). Needs `pip install prophet statsmodels`. ("Importing plotly failed" message = harmless.)**
- **BACKTEST (train≤2024, test 2025 — a year that doubled): Prophet logistic w/ policy cap MAPE 17.6% vs Prophet linear 28.5% vs ARIMA(1,1,1)-log 37.5%.** A-priori design choice (logistic, cap from policy) empirically confirmed — 40% lower error than ARIMA. IR's Prophet-vs-ARIMA deliverable done.
- Caps from POLICY not curve-fit: 15% TIV (≈800k/yr national) × 62.9% KV /12 = 6,290/mo central; 30% accelerated = 12,580/mo. Dec-2025 spike = CBU duty-exemption pull-forward (one-off, documented).
- Annual KV forecast (policy): 2026 45.4k → 2030 74.2k/yr (approaching cap, correct logistic bend). **KV EV stock: 61,568 today → 372,266 (policy) / 552,775 (accelerated) by end-2030.**
- **CHARGER GAP 2030 (15 EVs/port, population allocation): KV needs 24,819 public ports vs 867 counted → gap ≈ 23,952.** Sensitivity 18.6k–37.2k (10–20 EVs/port); robust to 2× undercount (gap still 23,085). District gaps: Petaling 6,814, KL 5,492 (capacity gap despite 98% distance-coverage!), HL 4,249, Klang 3,322, Gombak 2,833, Sepang 911, Putrajaya 331. **Headline: KV alone needs ~2.5× the entire national 10k target.** KL = capacity-only problem; Klang = access AND capacity — ties whole narrative.
- Documented assumptions: population-allocation presumes mass-market democratization by 2030 (income-adj variant available); public-port ratio uniform across districts (condo-heavy areas need more — future refinement via residential mix); scrappage ≈ 0.

**[VALIDATION — SECONDARY] Google Places live coverage cross-check (`pipeline/00_collectors/google_coverage_check.py` → `google_coverage_raw.csv`, `google_vs_ours_by_district.csv`, run 2026-08-01):**
- Independent live Google Places (New) sweep, adaptive quadtree (219 API calls, hard-capped 700). **Google returns 564 public+operational stations in KV vs our 376.** BUT the surplus is NOT spread evenly — **+113 Petaling (171 vs 58) and +56 KL (245 vs 189) alone = ~90% of the gap**, while the deserts stayed essentially flat: **Klang +4 (23 vs 19), Gombak −4 (14 vs 18 — the ONLY district where Google finds FEWER than us).**
- **INTERPRETATION (thesis-supporting):** the new public chargers are piling into the already-served affluent commercial districts (Petaling/KL) while deserts barely move → under fuller/live data the **equity gap WIDENS, not narrows.** The "chargers chase commercial ROI" mechanism is visibly still operating. Reinforces the desert narrative rather than threatening it.
- Main driver of the raw 564-vs-376 difference is **snapshot-vs-live timing** (our v2 = earlier-2026 collection; Google = live Aug 2026; Gentari/ChargEV fast buildout since). Consistent with "the pipeline is the product, the snapshot is the demo." Petaling names sampled are genuine public networks (ChargEV/Gentari/Tesla/Shell/JomCharge), not private chargers slipping through.
- **CAVEATS (state in viva):** (1) Google exposes NO access-type field — public/private not reliably separable (only 1 name-flagged private; heuristic weak), so 564 is a soft, likely slight OVER-count of truly-public. (2) 2 dense ~1km cells in KL core still hit the 20-result cap → **KL 245 is a FLOOR (undercount), which only strengthens the widening-gap point.** (3) SECONDARY check only — our fuse already includes Google Places, so this partly checks against one of our own sources; the **manual PlugShare per-zone check is the stronger validation** (shows access type directly). `ev_stations_kv_clean_v2.csv` NOT modified (read-only comparison).

**ANALYTICS PHASE COMPLETE — all 13 active problems closed.** Remaining: user tasks (operator cross-check hour; API key revocation STILL unconfirmed), repo reorganization (pipeline/ app/ structure, requirements.txt pinned, CLAUDE.md), then Streamlit dashboard build in Claude Code (5 pages mapped to artifacts; toggles = arithmetic on stored components).

---

## 4. ⚠ AUDIT FINDINGS (issues Claude verified directly in the data — fix in FYP2)

1. **SECURITY: two live API keys hardcoded** in collect_ev_stations.py (OCM) and validate_ev_google.py (Google). Revoke/regenerate both, move to .env before any submission/GitHub push.
2. **Bounding-box district misassignment is real and material.** Boxes overlap and first-match wins:
   - Putrajaya box (2.85–3.05, 101.65–101.80) swallows Cyberjaya/Dengkil/Bangi edges → Putrajaya shows 34 stations (31 from Google) vs ~3 genuine per own Ch.2 text. Sepang/Hulu Langat undercounted.
   - KL box (101.55–101.75) overlaps Petaling box (101.40–101.60): audit found 10 Google stations in the 101.55–101.60 strip auto-labeled KL (Sungai Buloh/Kota Damansara areas are Petaling/Gombak). KL's 326 is inflated.
   - **Fix:** re-run district assignment with proper polygon sjoin (geocode_to_gdf polygons already used elsewhere in the codebase, or JUPEM/geoBoundaries shapefiles). Present before/after as robustness improvement.
3. **Report internal inconsistency:** Ch.2 cites KL 201 / Klang 5 / Gombak 16 / Putrajaya 3 stations (old OCM-only snapshot); Ch.3 + actual data say KL 326 / Klang 14 / Gombak 17 / Putrajaya 34. Also "545 distinct" (Ch.2) vs 535 post-dedup. Reconcile all numbers in final report.
4. **Rakan Niaga redistribution is circular:** weights derived from genuine registrations are themselves dealer/corporate-biased toward KL (75/25 KL:Selangor is implausible vs population 2.0M:6.2M). Putrajaya=1 record. Forecast will over-allocate KL. Fix via exogenous weights (population / car-ownership) + sensitivity analysis (50/60/70% scenarios), or forecast at KV-aggregate level and allocate spatially via CDI.
5. **JPJ has NO district column** — only state. "District-level forecasting" claim needs explicit disaggregation method (state forecast → district allocation via population/POI/CDI weights). Say this explicitly or markers will catch it.
6. **District-level population/income (7 values) is too coarse for hex-level CDI** — every hex in a district inherits identical values → blocky index. Fix: dasymetric distribution of district population across hexes weighted by residential building/POI density (or WorldPop 100m raster).
7. Minor: objectives say "next 10 years to 2030" (it's ~4); dedup thresholds inconsistent (50m OSM vs 100m Google — justify); report says data "as at mid-2024" but collection was Apr 2026; maker/model dropped from JPJ (kept in raw — could enable premium-vs-mass EV equity analysis).

---

## 5. FYP2 BUILD PLAN (agreed direction)

**Correctness first:** polygon sjoin re-assignment → regenerate ev_stations_kv_clean; Rakan Niaga sensitivity; reconcile report numbers; secure keys.

**CDI formalization:** explicit formula, per-hex (H3 res 8): demand (POI weighted by dwell-time category weights + population dasymetric) × equity multiplier (inverse income) − supply (existing ports/power within radius, distance-decayed). Normalize 0–100. Justify weights (entropy weighting / AHP / sensitivity ablation — NOT arbitrary).

**Accessibility rigor (big grade lever):** 2SFCA (two-step floating catchment area) accessibility score per hex; Gini/Lorenz of access vs income before/after recommendations → quantified equity impact.

**Forecast:** Prophet w/ logistic growth cap (cap from 15% TIV penetration policy target) vs ARIMA; backtest train≤2024 / test 2025, report MAPE; convert EV stock → charger need via EV-per-charger ratio benchmarks → district-level charger gap by 2030 (concrete number output).

**Optimization:** clustering (K-Means CDI-weighted, DBSCAN) PLUS coverage framing (greedy maximal-coverage on top-CDI hexes) → ranked recommended sites with per-site scorecard (demand, equity, nearest existing station, coverage gain).

**Validation (novel for FYP):** hold out 20% of existing stations → does high-CDI recover them (recall@k)? Cross-check recommendations vs announced Gentari/TNB/ChargEV expansion sites.

**System:** Streamlit dashboard (upgrade from static Folium HTML): layers = CDI heatmap, desert zones, existing stations, recommended sites, forecast slider 2026→2030, district drill-down, site scorecards. Export static Folium HTML as backup deliverable.

**Business framing:** CPO site-selection intelligence (de-risk RM1.5–2M/site CapEx); gov MEVnet targeting for 10,000-charger national goal; Malaysia-specific angle: high-rise residents can't home-charge → weight apartment/condo POIs heavily in CDI.

---

## 6. Environment

Python 3.11, VS Code + Jupyter, `fyp_env` venv, Windows 11. Libraries: pandas, geopandas, osmnx, h3-py, scikit-learn, folium, matplotlib/seaborn, prophet, statsmodels, requests. Local paths: `C:\Users\anson\OneDrive\Desktop\FYP_Data\{raw_data,processed_data}`. Hardware: i5-12500, 16GB DDR5, RTX 3050.

**[2026-07-19] MIGRATION COMPLETE:** fyp_system folder assembled by Claude (cleanup per audit: cache/dupes/.vscode removed, v1 comparison files retained, poi_kv_clean.csv retained as stage-05 input). API keys surgically removed from collectors (env-based via .env; repo greps clean — old keys still need revocation by user). Full pipeline 02→09 verified end-to-end in the assembled folder (~30s, all headline numbers reproduced). Next: user smoke-tests Streamlit stub, git init + first commit, then Claude Code Page 1 per PLAN.md.
