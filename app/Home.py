"""Executive Overview — the landing page.

Orients a planner/operator in ~10 seconds, then routes them into the tool.
Overview template (DESIGN.md §2b): KPI strip -> hero visual -> narrative ->
navigation cards; no live controls. The four headline figures are computed by
arithmetic on the stored artifacts (never the pipeline), so they can never drift
from the CSVs in processed_data/.
"""
import os

import streamlit as st

from lib import data, theme, ui

st.set_page_config(page_title="KV EV Charging Intelligence",
                   layout="wide", initial_sidebar_state="collapsed")
theme.inject_base_css()

# ----------------------------------------------------------------- header
st.markdown(
    "<div class='page-title'>EV Charging Intelligence — Greater Klang Valley</div>"
    "<div class='page-sub'>Equity-weighted geospatial decision intelligence for EV "
    "charging placement · 7 districts · H3 res-8 grid</div>",
    unsafe_allow_html=True,
)
st.markdown("<hr>", unsafe_allow_html=True)


# --------------------------------------------------- headline metrics (arithmetic)
@st.cache_data(show_spinner=False)
def headline_metrics() -> dict:
    """Derive the four Overview figures from stored artifacts only. This is
    arithmetic on already-computed columns (the allowed exception in CLAUDE.md
    §2), not a pipeline recomputation — it guarantees the Overview matches the
    data files exactly."""
    hx = data.load_cdi()
    stn = data.load_stations()
    cap = data.load_capacity()
    gap = data.load_charger_gap()

    # 1) people living in severe-desert hexes (CDI >= 50)
    sev = hx[hx["cdi"] >= 50]
    severe_pop = float(sev["pop_est"].sum())
    klang_sev = float(sev.loc[sev["district"] == "Klang", "pop_est"].sum())

    # 2) population within 2 km of a public charger, by district + KV overall
    inh = hx[hx["pop_est"] > 0].copy()
    inh["cov_pop"] = inh["pop_est"].where(inh["nearest_station_km"] <= 2.0, 0.0)
    g = inh.groupby("district").agg(cov=("cov_pop", "sum"), pop=("pop_est", "sum"))
    cov_pct = 100 * g["cov"] / g["pop"]
    kv_cov = 100 * inh["cov_pop"].sum() / inh["pop_est"].sum()

    # 3) public+operational stations per 100k residents -> worst-to-best disparity
    counts = data.public_operational(stn).groupby("district").size()
    pop = cap.set_index("district")["population"]
    per100k = (counts / pop * 1e5).dropna()

    return {
        "severe_pop": severe_pop,
        "klang_sev": klang_sev,
        "klang_cov": float(cov_pct["Klang"]),
        "kl_cov": float(cov_pct["WP Kuala Lumpur"]),
        "kv_cov": float(kv_cov),
        "disparity": float(per100k.max() / per100k.min()),
        "klang_p100": float(per100k["Klang"]),
        "sepang_p100": float(per100k["Sepang"]),
        "port_gap": float(gap["port_gap"].sum()),
        "required": float(gap["required_ports_2030"].sum()),
        "current": float(gap["current_ports"].sum()),
    }


try:
    m = headline_metrics()
except Exception as exc:  # missing/renamed artifact -> explain, don't crash
    st.error(f"Could not load analytics artifacts from processed_data/ ({exc}). "
             "Run `python run_pipeline.py` from the repo root to regenerate them.")
    st.stop()

# ----------------------------------------------------------------- KPI strip
c1, c2, c3, c4 = st.columns(4, gap="medium")
ui.kpi_card(
    c1, "People in severe charging deserts",
    theme.fmt_int(m["severe_pop"]),
    f"CDI ≥ 50 hexes · {theme.fmt_int(m['klang_sev'])} in Klang alone",
)
ui.kpi_card(
    c2, "Klang vs KL coverage — 2 km",
    f"{theme.fmt_pct(m['klang_cov'])} vs {theme.fmt_pct(m['kl_cov'])}",
    f"population within 2 km of a public charger · KV overall {theme.fmt_pct(m['kv_cov'])}",
)
ui.kpi_card(
    c3, "Per-capita access disparity",
    theme.fmt_mult(m["disparity"]),
    f"worst-to-best · Klang {m['klang_p100']:.2f} vs Sepang {m['sepang_p100']:.2f} "
    "public stations / 100k",
)
ui.kpi_card(
    c4, "Projected 2030 port gap",
    f"~{theme.fmt_int(m['port_gap'])} ports",
    f"{theme.fmt_int(m['required'])} required vs {theme.fmt_int(m['current'])} today · "
    "~2.5× the national 10,000 target",
)

st.write("")

# ----------------------------------------------------------------- hero visual
hero = os.path.join(str(data.DATA_DIR), "cdi_map.png")
if os.path.exists(hero):
    _, mid, _ = st.columns([1, 8, 1])
    mid.image(
        hero, use_container_width=True,
        caption="Charging Desert Index — Greater Klang Valley (H3 res 8). "
                "Brighter = higher desert severity; cyan dots = public stations.",
    )
else:
    st.info("cdi_map.png not found — run `python pipeline/06_build_cdi.py` to regenerate the map.")

st.write("")

# ----------------------------------------------------------------- narrative
ui.section_header("Why this exists")
st.markdown(
    "<div class='narrative'>Charging infrastructure in the Greater Klang Valley is deployed on "
    "commercial return-on-investment logic, which concentrates chargers in central, higher-income "
    "Kuala Lumpur while lower-income and residential suburbs are left behind. KL holds about half of "
    "all public stations; <b>Klang</b> — with over a million residents — reaches barely a third of "
    "KL's per-capita access. This system measures that gap hex by hex with an equity-weighted "
    "<b>Charging Desert Index</b>, forecasts EV demand to 2030, and recommends where new stations "
    "would serve the most underserved people first.</div>",
    unsafe_allow_html=True,
)

st.write("")

# ----------------------------------------------------------------- navigation
ui.section_header("Explore the system")
pages = [
    ("PAGE 1", "CDI Explorer",
     "Interactive desert map with a Government / Operator lens, weight sliders and per-hex reason strings."),
    ("PAGE 2", "Recommendations",
     "20 optimal new sites by maximal coverage — scorecards, desert zones and a coverage-gain curve."),
    ("PAGE 3", "Demand Forecast",
     "EV demand to 2030 (Prophet vs ARIMA) and the district-level public-port gap."),
    ("PAGE 4", "What-If Simulator",
     "Drop a hypothetical station and watch coverage, gaps and CDI update live."),
    ("PAGE 5", "Validation & Data",
     "Holdout recall, coverage curves, capacity adequacy and full data provenance."),
]
nav_cols = st.columns(len(pages), gap="medium")
for col, (idx, title, desc) in zip(nav_cols, pages):
    ui.nav_card(col, idx, title, desc)
st.caption("Navigation activates page by page as each is built — you're viewing the first (Home).")
