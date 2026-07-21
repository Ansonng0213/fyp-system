# DESIGN.md — Dashboard design standards (binding for every page)

This file governs the *look, feel, and interaction* of the Streamlit system.
Read it before building any page and follow it exactly. It sits alongside the
architecture rules in `CLAUDE.md` (read-only artifact pattern, instant CDI
arithmetic) and the page specs in `PLAN.md`. Where a page spec and this file
both apply, this file wins on visual/interaction questions.

**One-line intent:** a calm, credible, data-forward geospatial
decision-intelligence tool — CARTO / Kepler.gl class — that a city planner or a
charging operator would trust in a meeting. It must never look like a student demo.

---

## 1. Audience & tone
- **Users:** urban planners (government / equity mandate) and EV charging
  operators / CPOs (commercial mandate). Both are professionals making
  high-stakes siting decisions.
- **Reference feel:** CARTO, Kepler.gl, Uber-style geospatial analytics —
  dark canvas, the *data* carries the color, chrome stays quiet.
- **Voice:** precise, evidence-led, no hype. Every claim is backed by a number
  the user can trace to `processed_data/`. No emoji in headings, no exclamation
  marks in copy, no "amazing/powerful" marketing words.

## 2. Layout system
Global: `st.set_page_config(layout="wide")`. Reclaim vertical space by trimming
Streamlit's default top padding via injected CSS (`.block-container` padding).
Design target resolution: **1366×768** must be fully usable with no horizontal
scroll and no clipped panels.

### 2a. Explorer template (Pages 1, 2, 4 — map-first)
```
┌──────────────┬───────────────────────────────┬──────────────────┐
│ CONTROL PANEL│            MAP (hero)          │  INSPECTOR       │
│ (left, slim) │        full-height pydeck      │  (right, appears │
│              │                                │   on selection)  │
│ • Persona    │                                │                  │
│ • Weights    │                                │  reason-string   │
│ • Layers     │                                │  + detail rows   │
│ • Filters    │                                │                  │
└──────────────┴───────────────────────────────┴──────────────────┘
```
- **Left control panel = `st.sidebar`** (slim, collapsible). Order top→bottom:
  persona toggle (first, prominent) → weight slider → layer checklist →
  district filter.
- **Map = main area**, full-height (pydeck `height ≈ 720`). This is the hero;
  it must dominate the screen.
- **Right inspector** appears only when something is selected. Implement by
  switching the main columns from `[1]` (map full width) to
  `[0.72, 0.28]` (map + inspector) when a selection exists. When nothing is
  selected the inspector area shows a one-line hint, not empty space.

### 2b. Overview template (Home — narrative, not a map tool)
Vertical flow, centered, generous whitespace, sidebar collapsed:
KPI strip (4 cards in a row) → hero visual → one-paragraph narrative →
navigation cards. No live controls; this page orients, it doesn't analyse.

### 2c. Spacing & hierarchy
- One idea per band; separate bands with whitespace, not rules/boxes.
- Max ~3 levels of visual hierarchy per screen (title → section → detail).
- Never crowd controls; a slim panel with air beats a dense one.

## 3. Color system (semantic — reserved, never reused)
UI **chrome is monochrome** (grays + white); **color belongs to the data on the
map**. This is the CARTO/Kepler discipline and it keeps the map legend
unambiguous. A semantic color below is used for that meaning and *nothing else*.

### 3a. Map data semantics (reserved)
| Meaning | Color | Hex | RGB (pydeck) | Notes |
|---|---|---|---|---|
| CDI heat | inferno ramp | `#000004`→`#420A68`→`#932667`→`#DD513A`→`#FCA50A`→`#FCFFA4` | see ramp below | dark→amber→yellow; **do not draw CDI==0 hexes** (transparent), matching the pipeline map |
| Public stations | cyan | `#00E5FF` | `[0,229,255]` | dots |
| Private / restricted stations | muted gray | `#7A828E` | `[122,130,142]` | dots, lower alpha — visibly secondary |
| Recommended sites | green | `#00FF88` | `[0,255,136]` | numbered markers |
| Desert-zone outline | red | `#FF3B30` | `[255,59,48]` | outline only / low-alpha fill |
| District border | white, thin | `#FFFFFF` | `[255,255,255]` (~70% α) | 1 px hairline |
| Map canvas base | dark | `#1A1A2E` | — | matches `cdi_map.png` facecolor for a consistent hero + live look |

**Inferno CDI ramp** (normalize CDI 0–100 → 0–1, interpolate; put this in
`app/lib/theme.py` as `cdi_to_rgb(v)`):
`0.0 (0,0,4) · 0.2 (66,10,104) · 0.4 (147,38,103) · 0.6 (221,81,58) · 0.8 (252,165,10) · 1.0 (252,255,164)`.

### 3b. UI chrome (non-map)
| Token | Hex | Use |
|---|---|---|
| `bg` | `#0E1117` | app base (Streamlit dark) |
| `surface` | `#1A1F2B` | cards, inspector, panels |
| `surface-2` | `#262B38` | hover / elevated / active fill |
| `border` | `#2A303C` | hairlines between cards |
| `text` | `#E6E9EF` | primary text, KPI values |
| `text-muted` | `#9AA1AD` | labels, context lines |
| `text-faint` | `#6B7280` | captions, hints |
| `accent` | `#3E7BFA` | **UI affordances only** — active toggle, links, focus. A blue deliberately *outside* the map palette so it can never be mistaken for a data color |

- **Deltas / good-bad in KPI context are typographic, not colored** — use `▲ / ▼`
  glyphs in `text-muted`, so the map's green (`#00FF88`) and red (`#FF3B30`)
  stay exclusive to their map meanings. If a card must signal direction with
  color, use `accent`, never the reserved map greens/reds. (Practically: build
  custom KPI cards, or `st.metric(..., delta_color="off")`.)
- **Accessibility:** inferno + cyan/green/red is distinguishable but not
  colorblind-proof — every colored map layer is *also* named in the layer
  checklist (swatch + label), so meaning never rests on hue alone.

## 4. Typography & numbers
- **No orphan numbers.** Every metric shows **label + unit + context** (a
  comparison, share, or delta). "756,330" alone is banned; "756,330 people ·
  CDI ≥ 50 · 439k in Klang" is correct.
- Thousand separators on every count/currency: `f"{v:,.0f}"` → `23,952`.
- Units are explicit and consistent: `km`, `%` (one decimal, `47.2%`),
  multipliers `×1.24` and `7.4×`, `ports`, `people`, `RM`.
- **Type scale** (via markdown/CSS in cards):
  - KPI value ≈ 2.2 rem / 700 · KPI label ≈ 0.78 rem / uppercase / letter-spaced / `text-muted`
  - KPI context ≈ 0.85 rem / `text-muted`
  - Section header ≈ 1.1 rem / 600 · Body ≈ 0.95 rem
- Numbers in reason-strings may use a tabular/mono feel for alignment, but keep
  it subtle.

## 5. Components (build once in `app/lib/ui.py`, reuse everywhere)
- **KPI card** — `value + label + context line`, on a `surface` card with a thin
  `border`. Example: value **`Klang 47.2% vs KL 98.0%`**, label
  `POPULATION WITHIN 2 KM OF A PUBLIC CHARGER`, context `KV overall 79.3%`.
- **Inspector panel — reason-string pattern** (the product's explainability in
  one line), middot `·` separated:
  `CDI 78: 22,000 residents · activity 240 · ×1.24 equity · nearest charger 4.1 km · 3 stations within 5 km`
  Then optional detail rows (district, stations within 2 km, coverage note).
  In **Operator** view the equity term is dropped (equity = 1.0) — show the
  string without `×.. equity`, don't show a misleading multiplier.
- **Layer toggles = a checklist** of `st.checkbox`, each prefixed with its
  semantic color swatch so the toggle doubles as the legend
  (▪ cyan Public · ▪ gray Private · ▪ green Recommended · ▪ red Desert zones).
- **Persona toggle (Government / Operator)** — **always top-left, always the
  first and most prominent control.** Use a segmented control / radio in a
  bordered container with a one-line caption of what changes: *"Government
  weights equity for underserved areas · Operator ranks pure market demand."*
  Flipping it recomputes CDI live from stored components (`CLAUDE.md` §2),
  and every reactive KPI/label updates with it.

## 6. Interaction standards
- **Hover → tooltip** carrying the reason-string (pydeck `tooltip`). Always
  available; this is the guaranteed explainability path.
- **Select → inspector** panel on the right. Selection mechanism is finalized
  when Page 1 is built: prefer native pydeck selection if the installed
  Streamlit supports it; otherwise a "focus" selector (pick a hex / site by
  rank or search) drives the inspector. Hover tooltip works regardless.
- **Every control must visibly change something** — no dead sliders/toggles.
- Transitions stay quick and quiet; no gratuitous animation.

## 7. Architecture ties (from CLAUDE.md — restated so design can't break them)
- App **only reads** `processed_data/`; it never recomputes pipeline logic.
- `@st.cache_data` on **every** CSV/GeoJSON read (shared loaders in
  `app/lib/data.py`).
- The only "computation" allowed in the app is the CDI **arithmetic on stored
  components** (`pop_n, act_n, equity_mult, supply_n`) for the persona toggle,
  weight slider, and radius/what-if — milliseconds, vectorized (`app/lib/cdi.py`).
- Suggested shared modules: `data.py` (loaders), `theme.py` (color tokens +
  `cdi_to_rgb` + CSS injector), `ui.py` (kpi_card, inspector, reason_string,
  persona_toggle, layer_checklist), `cdi.py` (pure recompute).

## 8. Quality bar — per-page checklist (all must pass before "done")
- [ ] Loads in **< 2 s** after cache warm; `@st.cache_data` on all file reads.
- [ ] Fully readable and unclipped at **1366×768**; no horizontal scroll.
- [ ] **Every control visibly changes** the map/KPIs; no orphan controls.
- [ ] **No orphan numbers** — label + unit + context on every metric.
- [ ] Semantic colors used only for their reserved meaning.
- [ ] **Empty states handled:** no selection (inspector hint), district filter
      that matches nothing, a persona/weight combo that greys a term, missing
      optional file (e.g. unfilled operator cross-check) — all degrade
      gracefully with a message, never a crash or blank void.
- [ ] Persona toggle top-left and prominent; map is the hero on explorer pages.
- [ ] User confirms it in the browser, then commit.

## 9. Quick Do / Don't
- **Do** let the map carry color; keep chrome gray. **Don't** color buttons/text
  with map semantics.
- **Do** give every number a unit and a comparison. **Don't** ship a bare figure.
- **Do** reuse `app/lib` components for consistency. **Don't** restyle a KPI card
  per page.
- **Do** recompute CDI by arithmetic on stored columns. **Don't** call any
  pipeline logic from the app.
- **Do** keep it quiet and credible. **Don't** make it look like a demo.
