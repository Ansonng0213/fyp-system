# POLISH.md — deferred visual-polish & finishing backlog

Items to do LATER, during a dedicated final polish pass — **not** while building
functional pages. Each page is built for correctness first; cosmetics are swept
here at the end so the whole system gets one consistent visual finish.

---

## 1. Hero map legibility (cdi_map.png) + dark-on-dark sweep
**Problem:** on the Executive Overview, the hero image `processed_data/cdi_map.png`
reads poorly — the colorbar/legend text and the low-CDI hexes are too dark against
the near-black canvas (`facecolor="#1a1a2e"`), so the bottom half of the ramp and
the legend labels are hard to see.

**Fix (during final polish):**
- Regenerate the map from `pipeline/06_build_cdi.py` with:
  - a **lighter canvas floor** (raise the figure/axes facecolor above `#1a1a2e`,
    or add a subtle mid-tone panel behind the hexes) so low-CDI inferno values
    separate from the background;
  - **brighter legend/colorbar text** (white or near-white tick labels + label,
    higher contrast) — currently dark grey on dark.
- Re-run stage 06 to overwrite `cdi_map.png`; the Overview reads it automatically.
- Keep the inferno ramp and all data semantics unchanged (DESIGN.md §3) — this is
  a contrast/legibility fix only.

**Also (end-of-project):** sweep **every page** for dark-on-dark legibility —
map legends, captions, muted text, axis labels, tooltip contrast — at 1366×768
in the dark theme. Anything that disappears against the background gets lifted.

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
