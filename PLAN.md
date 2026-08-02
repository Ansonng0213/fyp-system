# PLAN.md — Dashboard build spec (Streamlit)

Build the pages in this order. One page per session-chunk: build, run,
let the user verify in the browser, commit, move on.

Global: `st.set_page_config(layout="wide")`. Shared cached loaders in
`app/lib/data.py` (`@st.cache_data` on every CSV/GeoJSON read). Maps via
pydeck `H3HexagonLayer` (hex_cdi_v1.csv has `h3_index`) — no geometry
conversion needed. Consistent dark map style. All artifact reads from
`processed_data/`. **Follow `DESIGN.md` for all visual/interaction standards
(layout templates, semantic colors, KPI/inspector components, quality bar).**

---

## Home — Executive Overview  (app/Home.py)
The landing page: orient a planner/operator in 10 seconds, then route them.
Overview template from DESIGN.md §2b (vertical flow, sidebar collapsed, no live
controls). Government (equity-on) framing for the headline numbers.

- **KPI strip — 4 cards** (DESIGN.md KPI-card component; label + unit + context):
  1. **People in severe charging deserts** — `756,330 people` ·
     context "CDI ≥ 50 hexes · 439,123 in Klang alone".
  2. **Coverage gap (2 km)** — `Klang 47.2% vs KL 98.0%` ·
     context "population within 2 km of a public charger · KV overall 79.3%".
  3. **Per-capita access disparity** — `7.4×` worst-to-best ·
     context "Klang 1.68 vs Sepang 12.38 public+operational stations / 100k".
  4. **Projected 2030 port gap** — `~23,952 ports` ·
     context "24,819 required vs 867 today · ~2.5× the national 10,000 target".
  (All four are static, verified figures from `hex_cdi_v1.csv` /
  `ev_stations_kv_clean_v2.csv` / `charger_gap_2030.csv` — do not recompute.)
- **Hero visual:** `processed_data/cdi_map.png` full-width (`st.image`), caption
  "Charging Desert Index — Greater Klang Valley (H3 res 8)".
- **Narrative — one paragraph:** the thesis in plain language — chargers follow
  commercial ROI, so they cluster in KL while residential/lower-income suburbs
  (Klang worst) become charging deserts; this system maps the gap, forecasts
  2030 demand, and recommends equity-weighted sites.
- **Navigation cards:** one card per page (CDI Explorer, Recommendations,
  Forecast, What-If, Validation & Data) — title + one-line description,
  `st.page_link` to each. This is the primary way into the tool.

---

## Page 1 — CDI Explorer  (app/pages/1_CDI_Map.py)
Data: hex_cdi_v1.csv, kv_districts_dosm.geojson, ev_stations_kv_clean_v2.csv
- pydeck H3HexagonLayer colored by CDI (0-100, inferno-like scale),
  district outlines, toggleable public-station dots.
- Sidebar:
  * View toggle: **Government** (equity ON) / **Operator** (equity OFF)
  * Weight slider w_pop (0-1, default 0.5); w_act = 1 - w_pop
  * Recompute CDI live from stored components (formula in CLAUDE.md §2)
  * District filter multiselect
- Click/hover a hex -> reason panel: "CDI {x}: {pop} residents, activity
  {a}, equity x{e}, nearest charger {d} km, {n} stations within 5 km."
- KPI row: severe hexes (CDI>=50), population in severe zones, median
  nearest-charger km — all reactive to the toggle.

## Page 2 — Recommendations  (app/pages/2_Sites.py)
Data: recommended_sites_v1.csv, desert_zones_v1.csv, hex_cdi_v1.csv
- Map: CDI backdrop + numbered site markers + desert-zone outlines.
- Site table (rank, district, pop_newly_covered, nearest_existing_km).
- Click a site -> scorecard card: all fields + "covers {n} newly served
  people" + Google Maps link.
- Coverage before/after bar per district (data: recompute from
  hex_cdi_v1 nearest_station_km <= 2 vs the covered_after logic, or
  precompute a small CSV in pipeline/07 if simpler).
- Slider "number of sites (1-20)" -> cumulative coverage curve.

## Page 3 — Demand Forecast  (app/pages/3_Forecast.py)
Data: forecast_kv_monthly.csv, charger_gap_2030.csv
- Line chart: actual + policy & accelerated forecasts + uncertainty band
  (plotly). Cap lines annotated "15% / 30% TIV policy targets".
- Year slider 2026-2030 -> EV stock number + required ports at that year
  (linear interp of cumulative forecast; ratio selector 10/15/20 EVs/port).
- District gap table (charger_gap_2030.csv) with bar chart.
- Callout: "KV alone needs ~2.5x the national 10,000-charger target."

## Page 4 — What-If Simulator  (app/pages/4_WhatIf.py)
Data: hex_cdi_v1.csv
- User clicks map (or picks district + enters lat/lon) to place a
  hypothetical station.
- Live recompute: for each hex, new_supply_raw = supply_raw +
  exp(-haversine(hex, pin)/1.5); renormalize with the SAME p99 cap
  (store the cap value: p99 of original supply_raw — compute once in the
  loader); new gap, new CDI; delta metrics:
  * people newly within 2 km (nearest_station_km vs distance to pin)
  * severe-hex count change, mean CDI change in 5 km radius
- Show before/after side-by-side mini-maps + delta KPI cards.

## Page 5 — Validation & Data  (app/pages/5_Trust.py)
Data: validation_holdout_results.csv, coverage_radius_curve.csv,
capacity_adequacy.csv, operator_crosscheck_template.csv (+ filled version
if present), audit_* files
- Holdout recall table + explanation paragraph (demand layer 5.3x chance;
  gap term redirects by design).
- Coverage-vs-radius interactive chart with radius slider.
- Capacity adequacy table.
- Data provenance table (hardcode from FYP_PROJECT_MEMORY.md: source,
  date, rows, limitation, mitigation per dataset).
- If operator_crosscheck has filled columns, compute and show recall.

## ✅ Page 6 — Investment Scenario Calculator  (app/pages/7_Investment.py) — BUILT
Operator/commercial lens. Sidebar: optional site anchor (one of the 20 recommended
sites → shows catchment pop + CDI), then assumptions — ports, sessions/port/day,
kWh/session, tariff & energy cost RM/kWh, CapEx/port, monthly opex.
Output (all labelled "indicative"): monthly energy & gross margin, net after opex,
simple payback, break-even sessions/day, and a payback-vs-utilization sensitivity
chart (the 15%–35% utilization cliff). Amber "INDICATIVE — user assumptions, not a
revenue prediction" banner + honest caveat panel (data-availability paradox). No
model/revenue claims. Ties back to the CDI equity lens.

---

## Definition of done (per page)
Runs with `streamlit run app/Home.py` from repo root; no pipeline
recomputation; loads < 2 s after cache warm; user confirmed in browser;
committed.
