# Dashboard review — deployed app walkthrough

Reviewed: 2026-08-24, live at
`https://ansonng0213-fyp-system-apphome-nftqpp.streamlit.app/`
Browser: Chrome, viewport 1536×639 CSS px (dark theme).
Every page walked: Home (cover), Overview, CDI Map, Sites, Forecast, WhatIf,
Trust, Investment. Interactive controls exercised: Government/Operator toggle,
population-weight slider, map layer checkboxes, hex click, site-row selection,
desert-zones expander, forecast scenario toggle.

Findings are grouped by severity. Nothing here has been changed in the repo.

---

## A. Real defects (fix these first)

### A1. CDI Explorer — the "Inspect a hex" dropdown is empty and non-functional
The selectbox contains exactly ONE option: the placeholder
`— none (hover the map, or pick a hex) —`. Typing "Klang" returns "No results".
It also never syncs: clicking a hex on the map correctly opens the Hex Inspector
panel, but the dropdown stays on "none".

Its label is misleading too — "hover the map" does not populate it; hovering
only shows the map tooltip.

Fix: either populate it (e.g. the top-N hexes by CDI, labelled
`Klang · CDI 100 · 24,010 residents`) and two-way-bind it to the map click, or
delete the control and change the caption to "Click any hex on the map".

### A2. Sites — desert-zone "Zone type" mislabels the smallest zones
In the Desert zones (DBSCAN) table, the classifier looks like
`mean CDI >= 60 -> severity (high CDI), else scale (large population)`
with no population test at all. Result:

| Zone | District | Population | Mean CDI | Label shown |
|---|---|---|---|---|
| 4 | Klang | 32,857 | 47.6 | scale (large population) |
| 3 | Klang | 45,915 | 55.8 | scale (large population) |

Zone 4 is the SMALLEST of the eight zones by population and is labelled
"large population". Add the population-rank half of the rule (POLISH.md item 4
specified it) or introduce a third neutral label such as "moderate".

### A3. Forecast — two different numbers for the same figure on one page
- The blue callout at the top: "needs **~24,819 public ports** … a gap of **~23,952**"
- The KPI cards immediately below: **24,818 ports**, gap **23,951**

Off by one — precomputed headline vs live recompute rounding. Make the callout
read from the same computation as the cards (or round both the same way).

### A4. Thousand separators are inconsistent, sometimes side by side
- Sites table "People newly covered": `129556`, `82423`, `172796`
- The Site scorecard right next to it: `129,556`
- Forecast district table: `103976`, `6932` — while its own bar chart labels say `5,492`
- Desert zones table Population: `287046`
- Trust capacity table: `966,200` (correct)

Apply one number-format helper across every dataframe/table.

### A5. Trust — the coverage-radius curve has no legend
Three lines (grey, blue, orange) and no key. The caption names KL and Klang but
the reader cannot tell which line is which. This chart carries the equity
argument, so it needs a legend or direct end-of-line labels.

### A6. Forecast — y-axis title is clipped
The vertical axis label renders as "egistrations / month" — the leading "R" is
cut off by the chart container. Add left margin/padding to the figure.

### A7. Desert-zone IDs are raw cluster labels
The Zone column shows `0, 6, 2, 5, 7, 1, 3, 4` — unordered DBSCAN cluster ids
starting at 0. Renumber 1..8 in the displayed rank order (keep the raw id in the
CSV if you need traceability).

---

## B. Interpretability risks (a marker or examiner will ask about these)

### B1. Operator view DOUBLES the deserts, with no explanation
Switching Government → Operator (i.e. turning equity weighting OFF):
- Severe desert hexes: **38 → 75**
- People in severe zones: **756,330 → 1,532,231**

It is mathematically correct (dropping the equity multiplier lowers the max, and
CDI is renormalised by the max), but on screen it reads as "removing the equity
lens makes the equity problem worse", which looks backwards. Add one line of
caption on the toggle explaining that CDI is renormalised within each lens, so
counts are not comparable across lenses — only rankings are.

### B2. The sliders can produce numbers that contradict your own headline
Setting Population weight to 1.00 gives **2,462,322 people in severe zones** —
3.3× the 756,330 headline on the cover screen. There is no "reset to validated
defaults" button and nothing on the page states which settings produce the
reported figures.

Add a **Reset to validated defaults** button plus a note: "Headline figures use
Government lens, population 0.50 / activity 0.50."

### B3. What-If — the before/after maps look identical
With a station dropped on the worst Klang desert hex:
- Before and After maps are visually indistinguishable
- "SEVERE HEXES (CDI ≥ 50)" tile reads **0**, caption "38 → 38"
- "MEAN CDI CHANGE · 5 KM" = **−0.4**

So the flagship simulator's headline output is "nothing changed", even though
the same pin reports 95,482 people newly covered and RM 3 per person covered.
That undercuts the whole recommendation story.

Suggested fix: replace (or supplement) the twin maps with a single **Δ-CDI
difference map** on a diverging scale, so the change is actually visible; and
lead the tile row with the coverage/cost metrics that DO move, demoting the
severe-hex-count tile.

### B4. What-If — the new station is drawn on the "Before" map
The green pin and its 2 km ring appear on both panels. The caption explains it,
but showing your hypothetical station on the "before" state is conceptually
confusing. Consider a hollow/ghost marker on Before.

---

## C. Naming and navigation

### C1. Three different names for the same page
| Sidebar | Overview card | Page H1 |
|---|---|---|
| CDI Map | CDI Explorer | CDI Explorer |
| Sites | Recommendations | Recommendations |
| Forecast | Demand Forecast | Demand Forecast |
| **WhatIf** | What-If Simulator | What-If Simulator |
| Trust | Validation & Data | Validation & Data |
| Investment | Investment Scenario | Investment Scenario Calculator |

The sidebar is showing raw filenames — **"WhatIf" with no space** is the most
visible symptom. Set explicit sidebar labels (rename the page files, or use
`st.Page` / `st.navigation` with `title=`) so all three columns match.

### C2. Browser tab titles are inconsistent
Home = "Charging Desert Index — Greater Klang Valley", Overview = "KV EV
Charging Intelligence", the rest = the page name. Pick one pattern, e.g.
`CDI Explorer · KV EV Charging Intelligence`.

---

## D. Layout and legibility

### D1. The cover screen does not fit on one screen
Content height is ~1,861 px against a 639 px viewport — nearly 3 screens. The
KPI row is cut in half at the fold and **"Enter Dashboard" is about 1.5 screens
down**, so a first-time viewer sees a title and no way forward. Compress the
hero (smaller title block, KPI row and button above the fold) and move the hero
map below as the scroll reward.

### D2. The cover's hero CDI map is dimmed to near-illegibility
The same `cdi_map.png` renders crisp on Overview (white title, bright colorbar)
but on Home it is faded — the colorbar title, its tick labels and the
"Public stations" legend nearly vanish into the background. If the dimming is a
deliberate backdrop effect, commit to it (heavier blur / lower opacity, no
readable labels expected); if not, drop the dimming. This is POLISH.md item 1
territory and it is currently the worst dark-on-dark spot in the app.

### D3. Overview — "Explore the system" card grid is unbalanced
Pages 1–5 sit in a 5-across row, then Page 6 is a full-width orphan card.
A 3 × 2 grid would read much better.

### D4. The static CDI map has a lot of dead space and no district names
The PNG is letterboxed with large empty areas, and it carries no district
labels — so a reader cannot tell which blob is Klang. Since "Klang is the desert
capital" is the headline, annotate the district names on the figure and crop
tighter.

### D5. Sidebar district multiselect is clipped
At 639 px viewport height the last chip (**WP Putrajaya**) is cut in half at the
bottom of the sidebar and cannot be scrolled fully into view. Consider collapsing
the multiselect into a compact summary ("All 7 districts") that expands.

### D6. CDI Explorer — colour legend is far from the map
The "CHARGING DESERT INDEX" gradient bar sits at the very top of the page,
separated from the map by the KPI cards and the inspect control. Move it beside
or directly above the map.

### D7. Interactive maps extend well past the study area
The pydeck view includes Seremban, Kuala Pilah, Titi and Karak — a lot of empty
basemap. Fit the initial view to the KV bounds.

### D8. Overview coverage-gap bars are all one colour
All seven district bars are the same blue. Colouring the four below the KV
average (Klang, Gombak, Sepang, Hulu Langat) differently would make the equity
gap read instantly.

---

## E. Operational note for the viva

The deployed app cold-starts slowly (~15 s from a sleeping container) and the
"CONNECTING" badge appeared once mid-session when the websocket dropped. Open
and warm the app several minutes before any live demo, and have
`streamlit run app/Home.py` ready locally as a fallback.

---

## F. What is working well (do not change these)

- **Hex tooltip reason strings** are exactly the explainability differentiator:
  "Klang · CDI 64 · 15,820 residents · activity 188 · ×1.24 equity ·
  nearest charger 1.1 km · 6 within 5 km".
- **Hex Inspector panel** — full component breakdown plus an "Open in Google
  Maps" link. Excellent for a demo.
- **Instant recompute** — the Operator toggle and weight slider update the whole
  page with no perceptible lag. The stored-components trick works.
- **"Why some sites sit in low-CDI hexes — this is intended, not a bug"**
  callout on Sites pre-empts the single most likely viva attack.
- **Site scorecard** with a plain-English lead sentence ("Brings 129,556 people
  within 2 km of public charging · nearest existing station 3.8 km away").
- **Trust page is the strongest page in the app** — the objection-as-heading
  structure ("Does the index predict reality?", "Aren't the CDI weights
  arbitrary?", "Isn't 79% coverage fine?"), the deliberately-lower Operator-CDI
  recall explanation, "Known limitations — stated honestly", the data-provenance
  table, and the PlugShare live cross-check with the refined
  commercial-clustering framing (not the old zero-stations claim).
- **Investment page disclaimers** — the orange "INDICATIVE SCENARIO — NOT A
  REVENUE PREDICTION" banner plus "Read this before trusting any number above"
  handle the project's riskiest claim honestly and visibly.
- **What-If sidebar controls** — drop-on-worst-desert-hex, Clear all, compare
  with top recommended site, side-by-side / single map toggle.
- POLISH.md item 4 (desert-zone "Zone type" column) is **already built** — it
  just needs the classification rule fixed per A2.
