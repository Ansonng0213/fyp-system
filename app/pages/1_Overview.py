"""Executive Overview — the landing page.

Orients a planner/operator in ~10 seconds and shows the whole arc: problem →
solution → evidence → method → trust → explore. Overview template (DESIGN.md
§2b). Every figure is computed by arithmetic on the stored artifacts (never the
pipeline), so nothing can drift from the CSVs in processed_data/.
"""
import os

import plotly.graph_objects as go
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


# --------------------------------------------------- metrics (arithmetic on artifacts)
@st.cache_data(show_spinner=False)
def headline_metrics() -> dict:
    hx = data.load_cdi()
    stn = data.load_stations()
    cap = data.load_capacity()
    gap = data.load_charger_gap()

    sev = hx[hx["cdi"] >= 50]
    inh = hx[hx["pop_est"] > 0].copy()
    inh["cov_pop"] = inh["pop_est"].where(inh["nearest_station_km"] <= 2.0, 0.0)
    g = inh.groupby("district").agg(cov=("cov_pop", "sum"), pop=("pop_est", "sum"))
    cov_pct = 100 * g["cov"] / g["pop"]
    kv_cov = 100 * inh["cov_pop"].sum() / inh["pop_est"].sum()
    counts = data.public_operational(stn).groupby("district").size()
    per100k = (counts / cap.set_index("district")["population"] * 1e5).dropna()

    return {
        "severe_pop": float(sev["pop_est"].sum()),
        "klang_sev": float(sev.loc[sev["district"] == "Klang", "pop_est"].sum()),
        "klang_cov": float(cov_pct["Klang"]), "kl_cov": float(cov_pct["WP Kuala Lumpur"]),
        "kv_cov": float(kv_cov),
        "disparity": float(per100k.max() / per100k.min()),
        "klang_p100": float(per100k["Klang"]), "sepang_p100": float(per100k["Sepang"]),
        "port_gap": float(gap["port_gap"].sum()),
        "required": float(gap["required_ports_2030"].sum()),
        "current": float(gap["current_ports"].sum()),
    }


@st.cache_data(show_spinner=False)
def solution_metrics() -> dict:
    """The solution headline: what the 20 recommended sites achieve."""
    hx = data.load_cdi()
    rec = data.load_recommended_sites()
    total = hx["pop_est"].sum()
    inh = hx[hx["pop_est"] > 0]
    base = inh.loc[inh["nearest_station_km"] <= 2.0, "pop_est"].sum()
    newly = rec["pop_newly_covered"].sum()
    return {"n": int(len(rec)), "newly": float(newly),
            "before": 100 * base / total, "after": 100 * (base + newly) / total}


@st.cache_data(show_spinner=False)
def coverage_by_district() -> dict:
    """2 km population coverage per district + KV average (for the bar chart)."""
    hx = data.load_cdi()
    inh = hx[hx["pop_est"] > 0].copy()
    inh["cov_pop"] = inh["pop_est"].where(inh["nearest_station_km"] <= 2.0, 0.0)
    g = inh.groupby("district").agg(cov=("cov_pop", "sum"), pop=("pop_est", "sum"))
    pct = (100 * g["cov"] / g["pop"]).sort_values()          # worst first
    kv = 100 * inh["cov_pop"].sum() / inh["pop_est"].sum()
    return {"districts": list(pct.index), "pct": [float(v) for v in pct], "kv": float(kv)}


try:
    m = headline_metrics()
    sm = solution_metrics()
    cov = coverage_by_district()
except Exception as exc:  # missing/renamed artifact -> explain, don't crash
    st.error(f"Could not load analytics artifacts from processed_data/ ({exc}). "
             "Run `python run_pipeline.py` from the repo root to regenerate them.")
    st.stop()

# ----------------------------------------------------------------- KPI strip
ui.kpi_row([
    {"label": "People in severe charging deserts", "value": theme.fmt_int(m["severe_pop"]),
     "context": f"CDI ≥ 50 hexes · {theme.fmt_int(m['klang_sev'])} in Klang alone"},
    {"label": "Klang vs KL coverage — 2 km",
     "value": f"{theme.fmt_pct(m['klang_cov'])} vs {theme.fmt_pct(m['kl_cov'])}",
     "context": f"population within 2 km of a public charger · KV overall {theme.fmt_pct(m['kv_cov'])}"},
    {"label": "Per-capita access disparity", "value": theme.fmt_mult(m["disparity"]),
     "context": f"worst-to-best · Klang {m['klang_p100']:.2f} vs Sepang {m['sepang_p100']:.2f} "
                "public stations / 100k"},
    {"label": "Projected 2030 port gap", "value": f"~{theme.fmt_int(m['port_gap'])} ports",
     "context": f"{theme.fmt_int(m['required'])} required vs {theme.fmt_int(m['current'])} today · "
                "~2.5× the national 10,000 target"},
])

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

# ----------------------------------------------------------------- solution callout
st.markdown(
    "<div class='solution-band'><div class='solution-lead'>The opportunity</div>"
    f"<div class='solution-body'>{sm['n']} optimally placed sites would bring "
    f"<b>{theme.fmt_int(sm['newly'])} more people</b> within 2 km of public charging — "
    f"lifting Klang Valley coverage from <b>{theme.fmt_pct(sm['before'])}</b> to "
    f"<b>{theme.fmt_pct(sm['after'])}</b>.</div></div>",
    unsafe_allow_html=True,
)

st.write("")

# ----------------------------------------------------------------- coverage chart
ui.section_header("Coverage gap by district")
fig = go.Figure(go.Bar(
    x=cov["pct"], y=cov["districts"], orientation="h",
    marker=dict(color="#3E7BFA", cornerradius=4),
    text=[f"{v:.1f}%" for v in cov["pct"]], textposition="outside", cliponaxis=False,
    textfont=dict(color=theme.TEXT, size=12),
    hovertemplate="%{y}: %{x:.1f}% within 2 km<extra></extra>",
))
fig.add_vline(x=cov["kv"], line=dict(color=theme.TEXT_MUTED, width=1, dash="dash"))
fig.add_annotation(x=cov["kv"], y=1.05, yref="paper", text=f"KV avg {cov['kv']:.1f}%",
                   showarrow=False, xanchor="center",
                   font=dict(color=theme.TEXT_MUTED, size=11))
fig.update_layout(
    height=300, margin=dict(l=6, r=44, t=30, b=6), bargap=0.38, showlegend=False,
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=theme.TEXT_MUTED, size=12),
    xaxis=dict(range=[0, 108], showgrid=True, gridcolor="rgba(255,255,255,0.06)",
               ticksuffix="%", zeroline=False),
    yaxis=dict(autorange="reversed"),
)
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
st.caption("Population within 2 km of a public + operational charger. Worst-served districts first.")

st.write("")

# ----------------------------------------------------------------- how it works
ui.section_header("How it works")
ui.steps_row([
    ("1", "Fuse multi-source data",
     "JPJ registrations, DOSM census, OSM points of interest and three charger sources into one base."),
    ("2", "Score every hex with the CDI",
     "Rate each cell for demand, equity and existing supply — the Charging Desert Index."),
    ("3", "Forecast demand to 2030",
     "Project EV growth per district and the public-charger ports each area will need."),
    ("4", "Recommend sites by maximal coverage",
     "Place sites that bring the most underserved people within 2 km."),
])

st.write("")

# ----------------------------------------------------------------- validation trust strip
st.markdown(
    "<div class='trust-strip'><b>Validated:</b> demand layer recovers held-out real stations at "
    "<span class='tick'>5.3× chance</span> · forecast backtest "
    "<span class='tick'>17.6% MAPE</span> (vs ARIMA 37.5%) · district population totals "
    "preserved exactly.</div>",
    unsafe_allow_html=True,
)

st.write("")

# ----------------------------------------------------------------- navigation
ui.section_header("Explore the system")
# Seven cards in a 4 + 3 grid. A single row of seven would wrap to
# five-plus-orphan (.card-row is flex with a 190px min-width), which is the
# imbalance recorded as item D3 in docs/DASHBOARD_REVIEW_2026-08-24.md.
ui.nav_row([
    {"index": "PAGE 1", "title": "CDI Explorer", "href": "CDI_Map",
     "desc": "Interactive desert map with a Government / Operator lens, weight sliders and per-hex reason strings."},
    {"index": "PAGE 2", "title": "Recommendations", "href": "Sites",
     "desc": "20 optimal new sites by maximal coverage — scorecards, desert zones and a coverage-gain curve."},
    {"index": "PAGE 3", "title": "Market Logic", "href": "Market_Logic",
     "desc": "Diagnostic — what actually drives commercial siting, and where the market builds next. Not a recommendation."},
    {"index": "PAGE 4", "title": "Demand Forecast", "href": "Forecast",
     "desc": "EV demand to 2030 (Prophet vs ARIMA) and the district-level public-port gap."},
])
st.write("")
ui.nav_row([
    {"index": "PAGE 5", "title": "What-If Simulator", "href": "WhatIf",
     "desc": "Drop a hypothetical station and watch coverage, gaps and CDI update live."},
    {"index": "PAGE 6", "title": "Validation & Data", "href": "Trust",
     "desc": "Holdout recall, coverage curves, capacity adequacy and full data provenance."},
    {"index": "PAGE 7", "title": "Investment Scenario", "href": "Investment",
     "desc": "Operator lens — stress-test the indicative commercial case for a candidate site."},
])

st.write("")

# ----------------------------------------------------------------- footer
st.markdown(
    "<div class='site-footer'>Ng Cheng Xin · TP071136 · Asia Pacific University · FYP 2026 · "
    "Data: JPJ, DOSM, OpenStreetMap, OpenChargeMap, Google Places.</div>",
    unsafe_allow_html=True,
)
