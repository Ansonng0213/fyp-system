# POLISH.md — deferred visual-polish & finishing backlog

Items to do LATER, during a dedicated final polish pass — **not** while building
functional pages. Each page is built for correctness first; cosmetics are swept
here at the end so the whole system gets one consistent visual finish.

---

## 1. Dark-on-dark legibility sweep (end of project)
Sweep **every page** for dark-on-dark legibility — map legends, captions, muted
text, axis labels, tooltip contrast — at 1366×768 in the dark theme. Anything that
disappears against the background gets lifted.
*(The `cdi_map.png` hero title/colorbar have already been fixed to near-white
`#E6E9EF`.)*

---

## 2. Cover / landing screen (after all 5 functional pages exist)
Add a cover screen shown before the Executive Overview:
- Project title (large).
- **Ng Cheng Xin · TP071136 · APU**
- Full project title: *Developing Geospatial Optimization and Demand Forecasting
  Model for Equitable EV Charging Infrastructure*.
- One-line description of what the system does.
- An **"Enter Dashboard"** button that routes to the Executive Overview (Home).

Build only after Pages 1–5 are done, so routing targets all exist. Follow
DESIGN.md tone (calm, credible, not a student demo).

---

## 3. WorldPop population raster (deferred data enhancement)
Blend a **WorldPop 100 m population raster** into pipeline **stage 04** to fill
OSM-undertagged hexes — e.g. parts of Puchong currently show 0 residents despite
visible housing, because the dasymetric weights rely on OSM residential tags.
Using WorldPop as the population surface (or as a fallback where OSM residential
density is 0) would remove these false "empty" hexes.

Cost: requires **re-running stages 04→09** and **re-validating** all downstream
results (hex population, CDI, recommendations, forecasts, headline numbers).
Only do this if time allows — the current dasymetric estimate is documented and
defensible; this is an accuracy upgrade, not a correctness fix.

---

## 4. Desert-zones table: add a "zone type" column
On Page 2's desert-zones expander, add a **zone type** column distinguishing the
two desert types so it's explicit at a glance: **large-population** zones
(Petaling — high population, moderate CDI) vs **high-severity** zones (Klang —
highest mean CDI). Classify by a simple rule (e.g. mean CDI ≥ 60 → high-severity;
else large-population by population rank), or precompute the label in the pipeline
recommender step.
