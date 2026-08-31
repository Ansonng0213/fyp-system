"""Page 5 — Validation & Data.

The credibility page: why believe any of this? Holdout recall, forecast backtest,
weight-sensitivity, coverage-vs-radius, a second (capacity) validation lens, honest
limitations with mitigations, full data provenance, a methods summary, and the
operator cross-check (auto-populates when the template is filled). Reads only
processed_data/ artifacts.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import data, theme, ui

st.set_page_config(page_title="Validation & Data", layout="wide")
theme.inject_base_css()

# ------------------------------------------------------------------ load
val = data.load_validation()
cov = data.load_coverage_curve()
cap = data.load_capacity().sort_values("people_per_port", ascending=False)
fc = data.load_forecast()
oc = data.load_operator_crosscheck()

EV_STOCK = float(fc.loc[fc["actual"].notna(), "actual"].sum())      # ≈ 61,568 today
PORTS = int(cap["public_ports"].sum())                              # 867
EVS_PER_PORT = EV_STOCK / PORTS                                     # ≈ 71

# --- stage 12, the rolling-origin benchmark -------------------------------
# This panel used to hold three hardcoded single-split MAPE figures and claim
# Prophet "cut ARIMA's error by more than half". Stage 12 superseded that: on
# 980 rolling-origin folds ARIMA tuned beats Prophet base at h=6 and ETS base
# wins both horizons. The panel now reads the benchmark instead of asserting a
# result. The legacy single-split figures live on the Forecast page, which is
# also where the log1p-vs-log discrepancy on the ARIMA row is documented.
try:
    fcomp = data.load_forecast_comparison()
    f2030 = data.load_forecast_2030_scenarios()
    HAVE_S12 = len(fcomp) > 0
except Exception:
    fcomp = f2030 = pd.DataFrame()
    HAVE_S12 = False

if HAVE_S12:
    _full = fcomp[fcomp["series"] == "full_2020_2026"]
    S12_FAMILIES = int(_full["model"].nunique())
    S12_FOLDS = int(fcomp["folds"].sum())
    S12_H = sorted(int(h) for h in _full["h"].unique())
    S12_BEST = {h: _full[_full["h"] == h].sort_values("MASE_mean").iloc[0] for h in S12_H}
    S12_RANK = {}
    for _h in S12_H:
        _o = _full[_full["h"] == _h].sort_values("MASE_mean").reset_index(drop=True)
        _i = _o.index[(_o["model"] == "ProphetLogistic") & (_o["variant"] == "base")]
        S12_RANK[_h] = (int(_i[0]) + 1, len(_o)) if len(_i) else (None, len(_o))
    S12_CEIL = float(f2030["policy_ceiling_monthly"].iloc[0])
    _prow = f2030[(f2030["model"] == "ProphetLogistic") & (f2030["variant"] == "base")].iloc[0]
    S12_TREND = float(_prow["trend_dec_2030"])
    _sarr = f2030[f2030["model"] == "SARIMA"]["peak_over_ceiling_ratio"]
    S12_SAR_LO, S12_SAR_HI = float(_sarr.min()), float(_sarr.max())

ENTROPY = (0.47, 0.53)
OVERLAP = [("Pop-heavy · 0.7 / 0.3", 70), ("Activity-heavy · 0.3 / 0.7", 70),
           ("Entropy weights", 96), ("Equity off (Operator)", 82)]

# ------------------------------------------------------------------ 1 · framing
st.markdown(
    "<div class='page-title'>Validation & Data</div>"
    "<div class='page-sub'>Why you can believe the numbers</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='solution-band'><div class='solution-body'>Every figure in this system is "
    "<b>validated</b>, <b>sensitivity-tested</b>, and <b>traceable to its source</b>. This page "
    "shows how.</div></div>",
    unsafe_allow_html=True,
)
st.write("")

# ------------------------------------------------------------------ 2 · holdout + backtest
ui.section_header("Does the demand layer predict where stations went?")
g = val.groupby(["predictor", "top_k_pct"])["recall"].mean().unstack()
lbl = {"demand_blend": "Demand blend (CDI demand)", "pop_only": "Population only",
       "operator_cdi": "Operator CDI (with gap term)"}
ho = pd.DataFrame([{
    "Predictor": lbl[k], "Top 5%": f"{g.loc[k, 5] * 100:.1f}%",
    "Top 10%": f"{g.loc[k, 10] * 100:.1f}%", "Top 20%": f"{g.loc[k, 20] * 100:.1f}%",
    "Lift @10%": f"{g.loc[k, 10] / 0.10:.1f}×",
} for k in ["demand_blend", "pop_only", "operator_cdi"]])
# Rolling-origin leaderboard at the shorter horizon. Deliberately shows the top
# five INCLUDING the retained model wherever it falls -- Prophet base sits fifth,
# and a panel that hid that would be making the same mistake this rewrite fixes.
if HAVE_S12:
    _h0 = S12_H[0]
    _lead = (_full[_full["h"] == _h0].sort_values("MASE_mean")
             .head(5).reset_index(drop=True))
    bt = pd.DataFrame([{
        "Model": f"{r['model']} ({r['variant']})",
        "MASE": f"{r['MASE_mean']:.3f}",
        "MAPE %": f"{r['MAPE_mean']:.1f}",
        "Retained": "✓" if (r["model"] == "ProphetLogistic"
                                 and r["variant"] == "base") else "",
    } for _, r in _lead.iterrows()])
else:
    bt = pd.DataFrame()

# two equal-height panels (bottoms aligned): header, HTML table, footer explanation
_left = ui.panel(
    "Hold-out recall — hide 20% of real stations, can the demand layer find them?",
    ui.html_table(ho, num_cols=["Top 5%", "Top 10%", "Top 20%", "Lift @10%"]),
    # ATTRIBUTION: 5.3x belongs to the DEMAND LAYER (population + activity, no
    # supply gap, no equity), NOT to the CDI. The full Operator CDI scores 2.7x.
    # Do not reintroduce any clause crediting the 5.3x to the CDI.
    "The <b>demand layer</b> — population and activity only, with no supply-gap term and no "
    "equity weighting — puts held-out real stations in its top 10% of hexes at "
    "<span class='tick'>5.3× chance</span>. Population alone reaches only 4.5×, so the activity "
    "layer adds real signal. The full <b>Operator CDI scores 2.7×, deliberately lower</b>: its "
    "supply-gap term demotes areas that already have chargers, and this test rewards predicting "
    "where operators <i>did</i> build. A desert index that simply re-found existing stations "
    "would be useless.")
# WAS: "it cut ARIMA's error by more than half (17.6% vs 37.5%)" off a single
# 2025 split. Superseded -- see the note at the top of this file.
if HAVE_S12:
    _b = S12_BEST[S12_H[0]]
    _rk = " · ".join(f"h={h}: <b>{S12_RANK[h][0]} of {S12_RANK[h][1]}</b>"
                     for h in S12_H if S12_RANK[h][0])
    _right = ui.panel(
        f"Forecast model selection — {S12_FAMILIES} families, "
        f"{S12_FOLDS:,} rolling-origin folds (top {len(bt)} at h={S12_H[0]})",
        ui.html_table(bt, num_cols=["MASE", "MAPE %"]),
        f"Prophet logistic is <b>not</b> the accuracy winner — {_b['model']} "
        f"{_b['variant']} has the lowest MASE at both horizons ("
        + ", ".join(f"{S12_BEST[h]['MASE_mean']:.3f} at h={h}" for h in S12_H)
        + f"), and Prophet base ranks {_rk}. It is retained because its trend is "
        "the only one that <b>saturates by construction</b> — "
        f"<span class='tick'>{S12_TREND:,.0f}/month</span> by Dec 2030 against the "
        f"<b>{S12_CEIL:,.0f}</b> policy ceiling, where SARIMA extrapolates to "
        f"<b>{S12_SAR_LO:.0f}–{S12_SAR_HI:.0f}×</b> it. A five-year policy "
        "projection needs a bounded functional form, not the lowest six-month "
        "error. The superseded single-split MAPE figures are kept on the "
        "Forecast page as a legacy comparison.")
else:
    _right = ui.panel(
        "Forecast model selection",
        "<div class='trust-strip'>Benchmark artifacts not found — run "
        "<code>python pipeline/12_forecast_comparison.py</code>.</div>", "")
st.markdown(f"<div class='card-row'>{_left}{_right}</div>", unsafe_allow_html=True)

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ------------------------------------------------------------------ 3 · sensitivity
ui.section_header("Aren't the CDI weights arbitrary?")
c_ent, c_rob = st.columns([0.42, 0.58], gap="large")
with c_ent:
    # matching .panel-h header (same line as the chart's header) so the two
    # top-aligned columns start level
    st.markdown(
        "<div class='panel-h'>Entropy weighting agrees with the blend</div>"
        "<div class='trust-strip'>Entropy weighting — letting the data suggest the blend — "
        f"independently proposes <b>population {ENTROPY[0]:.2f} / activity {ENTROPY[1]:.2f}</b>, "
        "essentially the chosen <b>0.50 / 0.50</b>. The objective method agrees with the choice.</div>",
        unsafe_allow_html=True,
    )
with c_rob:
    st.markdown("<div class='panel-h'>Deserts are stable under weight swings</div>",
                unsafe_allow_html=True)
    ov = pd.DataFrame(OVERLAP, columns=["Weight scenario", "pct"])
    fig_ov = go.Figure(go.Bar(
        x=ov["pct"], y=ov["Weight scenario"], orientation="h",
        marker=dict(color=theme.ACCENT, cornerradius=4),
        text=[f"{p}%" for p in ov["pct"]], textposition="outside", cliponaxis=False,
        textfont=dict(color=theme.TEXT, size=12),
        hovertemplate="%{y}: %{x}% of top-50 deserts unchanged<extra></extra>",
    ))
    # title moved to the caption below; small top margin so the plot sits right
    # under its .panel-h header, level with the left column's header
    fig_ov.update_layout(
        height=196, margin=dict(l=6, r=40, t=6, b=6), showlegend=False, bargap=0.3,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=theme.TEXT_MUTED, size=12),
        xaxis=dict(range=[0, 108], ticksuffix="%", showgrid=True,
                   gridcolor="rgba(255,255,255,0.06)", zeroline=False),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_ov, use_container_width=True, config={"displayModeBar": False})
st.caption("Top-50 desert overlap vs baseline under weight perturbations. The deserts are stable, not "
           "artifacts of the weights — the worst areas persist even when the blend is swung hard or "
           "equity is switched off.")

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ------------------------------------------------------------------ 4 · coverage vs radius
ui.section_header("Isn't 79% coverage fine?")
radii = [float(x) for x in cov["radius_km"]]
radius = st.select_slider("Coverage radius (km)", options=radii, value=0.5)
row = cov[cov["radius_km"] == radius].iloc[0]
r1, r2, r3 = st.columns(3, gap="medium")
r1.markdown(f"<div class='page-sub'>KV overall<br><b style='color:{theme.TEXT};font-size:1.3rem'>"
            f"{row['kv_pct']:.1f}%</b></div>", unsafe_allow_html=True)
r2.markdown(f"<div class='page-sub'>Klang (worst)<br><b style='color:{theme.TEXT};font-size:1.3rem'>"
            f"{row['klang_pct']:.1f}%</b></div>", unsafe_allow_html=True)
r3.markdown(f"<div class='page-sub'>Kuala Lumpur<br><b style='color:{theme.TEXT};font-size:1.3rem'>"
            f"{row['lumpur_pct']:.1f}%</b></div>", unsafe_allow_html=True)

fig_cov = go.Figure()
for col, name, color in [("lumpur_pct", "Kuala Lumpur", "#8B93A7"),
                         ("kv_pct", "KV overall", theme.ACCENT),
                         ("klang_pct", "Klang", "#E8833A")]:
    fig_cov.add_trace(go.Scatter(x=cov["radius_km"], y=cov[col], mode="lines", name=name,
                                 line=dict(color=color, width=2.5),
                                 hovertemplate="%{x} km: %{y:.1f}%<extra>" + name + "</extra>"))
fig_cov.add_vline(x=radius, line=dict(color=theme.TEXT_FAINT, width=1, dash="dash"))
# Direct end-of-line labels. This chart carries the equity argument and had
# three unlabelled lines (review item A5): the legend was configured but the
# 10px top margin left it nowhere to render. Labelling each line at its end
# removes the lookup entirely; the legend is kept, with room, as a fallback.
_x_end = float(cov["radius_km"].max())
for col, name, color in [("lumpur_pct", "Kuala Lumpur", "#8B93A7"),
                         ("kv_pct", "KV overall", theme.ACCENT),
                         ("klang_pct", "Klang", "#E8833A")]:
    fig_cov.add_annotation(
        x=_x_end, y=float(cov[cov["radius_km"] == _x_end][col].iloc[0]),
        text=f" {name}", showarrow=False, xanchor="left", yanchor="middle",
        font=dict(color=color, size=11.5),
    )
fig_cov.update_layout(
    height=340, margin=dict(l=12, r=110, t=44, b=6), hovermode="x unified",
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=theme.TEXT_MUTED, size=12),
    legend=dict(orientation="h", y=1.16, x=1, xanchor="right", font=dict(size=11)),
    xaxis=dict(title="Distance to nearest public station (km)", showgrid=False,
               zeroline=False, automargin=True),
    yaxis=dict(title="Population covered", ticksuffix="%", showgrid=True, automargin=True,
               gridcolor="rgba(255,255,255,0.06)", zeroline=False, range=[0, 105]),
)
st.plotly_chart(fig_cov, use_container_width=True, config={"displayModeBar": False})
st.caption("Coverage depends heavily on the threshold. At **500 m**, KL reaches **33.4%** but Klang only "
           "**5.2%** — and Klang is the worst-served district at *every* distance. \"79% at 2 km\" hides "
           "the equity gap.")

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ------------------------------------------------------------------ 5 · capacity cross-validation
ui.section_header("A second, independent lens: capacity per port")
c_tab, c_note = st.columns([0.55, 0.45], gap="large")
with c_tab:
    ct = cap.rename(columns={"district": "District", "public_ports": "Public ports",
                             "population": "Population", "people_per_port": "People / port"}).copy()
    ct["Population"] = ct["Population"].map(lambda v: f"{v:,.0f}")
    ct["People / port"] = ct["People / port"].map(lambda v: f"{v:,.0f}")
    st.markdown(
        ui.html_table(ct[["District", "Public ports", "Population", "People / port"]],
                      num_cols=["Public ports", "Population", "People / port"]),
        unsafe_allow_html=True,
    )
with c_note:
    st.markdown(
        f"<div class='trust-strip'>KV averages <span class='tick'>{EVS_PER_PORT:.0f} EVs per public "
        f"port</span> — far above the <b>10–20 per-port</b> service guideline. Even under a <b>2× "
        f"station undercount</b> it is ~{EV_STOCK / (PORTS * 2):.0f}, still above the guideline.<br><br>"
        "Crucially, <b>two independent methods agree</b>: distance-coverage (Section 4) and "
        "capacity-per-port both rank <b>Klang and Gombak</b> the worst-served. Agreement across "
        "unrelated measures is what makes the desert finding robust.</div>",
        unsafe_allow_html=True,
    )

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ------------------------------------------------------------------ 6 · limitations
ui.section_header("Known limitations — stated honestly")
st.markdown(
    "<div class='trust-strip'>"
    # MEASURED, not hedged. This used to read "some populated hexes read low
    # (e.g. parts of Puchong)", which understated a bias big enough for a marker
    # to find independently. The figures are from the sensitivity analysis
    # recorded in CLAUDE.md trap 21; the direction is the part that matters.
    "<b>OSM POI under-tagging — the largest data limitation in this study.</b> "
    "The dasymetric step at <code>04_hex_population.py:110-112</code> gives a hex weight 0 "
    "unless it holds at least one residential POI or three POIs of any kind, so an unmapped "
    "hex is assigned <i>exactly zero</i> people. Petaling is worst affected: it carries "
    "<b>4.7 POIs per 1,000 residents against Kuala Lumpur's 20.6</b>, so the gate discards "
    "<b>76% of its land area</b> — only 24% retained — and packs 2.33M people into 102 km² at "
    "roughly <b>4.2× the district's true density</b>. <b>USJ and Puchong carry zero mapped POIs "
    "across about 14 km² each</b> and are absent from the population surface entirely. "
    "<i>Mitigation:</i> allocation preserves official DOSM district totals <b>exactly</b>, so "
    "re-weighting one district cannot move another's population. <b>Klang's headline figures are "
    "invariant</b> — its 47.2% 2 km coverage and its 8 of the 20 recommended sites are identical "
    "under both counterfactuals tested (no gate with POI weighting, and uniform weighting). "
    "Most importantly the bias runs <b>against</b> the thesis: under-tagging packs people into "
    "the well-served hexes, so correcting it would <i>raise</i> measured inequality — "
    "<b>Gini 0.497 → 0.53–0.61</b> and KV-wide 2 km coverage <b>79.3% → 62–75%</b>. "
    "The published figures are therefore <b>conservative</b>, not flattering.<br><br>"
    "<b>Station / port undercount</b> — a snapshot may miss stations, especially port counts. "
    "<i>Mitigation:</i> conclusions hold under a 2× undercount; the bias makes deserts look "
    "<i>conservative</i>, not exaggerated.<br><br>"
    "<b>Income at district, not hex, level</b> — <i>Mitigation:</i> used only as a bounded equity "
    "multiplier (×0.75–1.35), never fabricated to hex precision.<br><br>"
    "<b>Uniform EVs-per-port ratio across districts</b> — condo-heavy areas likely need more. "
    "<i>Mitigation:</i> flagged as a future refinement; sensitivity band shown (10–20 EVs/port).<br><br>"
    "<b>Rakan Niaga dealer-registration geography</b> — 74% of records are dealer-labelled. "
    "<i>Mitigation:</i> a national-anchored method never uses dealer state labels; the KV share "
    "(<b>62.9%</b>, sensitivity 55–70%) is data-derived and converges with the IR's 60% assumption."
    "</div>",
    unsafe_allow_html=True,
)

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ------------------------------------------------------------------ 7 · provenance
ui.section_header("Data provenance")
prov = pd.DataFrame([
    ["EV registrations", "JPJ (Road Transport Dept)", "2020-01 → 2026-03 (partial)", "97,951 nat’l",
     "Dealer 'Rakan Niaga' geography unreliable", "National-anchored; KV share 62.9% data-derived"],
    ["Population", "DOSM", "2023", "7 districts",
     "District-level only", "Dasymetric to H3 res-8; district totals preserved exactly"],
    ["Household income", "DOSM", "2022 (median)", "7 districts",
     "District-level only", "Used only as a bounded equity multiplier"],
    ["District boundaries", "DOSM (administrative_2)", "official", "7 polygons",
     "Bounding-box misassignment (v1)", "Polygon spatial-join reassignment (v2)"],
    ["Points of interest", "OpenStreetMap (OSMnx)", "Apr 2026 pull", "108,785",
     "Tag completeness varies sharply by district — Petaling 4.7 POIs/1k residents vs KL 20.6",
     "Dwell-time weighted; 538 double-tags de-duplicated; direction of the bias measured "
     "(see limitations) and it runs against the thesis"],
    ["Charging stations", "OpenChargeMap + OSM + Google Places", "Apr 2026", "535 (376 public+op)",
     "Snapshot; possible undercount", "Multi-source fusion, 0 residual duplicates"],
], columns=["Dataset", "Source", "Date / coverage", "Rows", "Known limitation", "Mitigation"])
st.markdown(ui.html_table(prov), unsafe_allow_html=True)

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ------------------------------------------------------------------ 8 · methods
ui.section_header("How it was built")
st.markdown(
    "<div class='trust-strip'><b>CRISP-DM</b> workflow · official <b>DOSM polygon</b> district "
    "assignment · multi-source <b>station fusion</b> (OpenChargeMap + OSM + Google) with 120 m + "
    "name dedup · <b>dasymetric H3 res-8</b> population (district totals preserved) · "
    "<b>dwell-time-weighted</b> POI activity · <b>equity-weighted</b> Charging Desert Index · "
    "<b>greedy maximal-coverage</b> site selection (vs K-Means baseline) · <b>Prophet logistic</b> "
    "forecast with a policy-derived cap.</div>",
    unsafe_allow_html=True,
)

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ------------------------------------------------------------------ 9 · live cross-check (PlugShare)
ui.section_header("Live cross-check — our snapshot vs PlugShare")
desert = oc[oc["zone_type"] == "desert"].copy()
ps_filled = ("plugshare_public_count" in oc.columns
             and desert["plugshare_public_count"].notna().any())

if ps_filled:
    d = desert.copy()
    d["Location (lat, lon)"] = (d["lat"].astype(float).round(4).astype(str) + ", "
                                + d["lon"].astype(float).round(4).astype(str))
    show = d[["Location (lat, lon)", "our_public_stations_2km",
              "plugshare_public_count", "maps_link"]].rename(columns={
        "our_public_stations_2km": "Our snapshot ≤2 km",
        "plugshare_public_count": "PlugShare live ≤2 km", "maps_link": "Map"})
    tbl = ui.html_table(show, num_cols=["Our snapshot ≤2 km", "PlugShare live ≤2 km"],
                        link_cols=["Map"])
    # one .stack so intro box → table → reading box → caption keep a uniform gap
    st.markdown(
        "<div class='stack'>"
        "<div class='trust-strip'>The four worst Klang desert hexes were <b>manually verified against "
        "live PlugShare</b> (public + operational only — restricted-access and coming-soon stations "
        "filtered out). The check <b>refines</b> the desert finding rather than overturning it: public "
        "charging in Klang <b>does exist, but it clusters at commercial nodes</b> — Aeon Mall Bukit Tinggi, "
        "GM Klang Wholesale City, the Klang town centre and highway hotels — while the surrounding "
        "<b>residential neighbourhoods stay empty</b>. In three of the four hexes the chargers sit "
        "0.5–1.8 km away at that commercial fringe; the residential cores themselves have none. The one "
        "exception, the Port Klang core, is <b>genuinely empty</b> — ~4 km to the nearest charger.</div>"
        f"{tbl}"
        "<div class='trust-strip'><b>The defensible reading:</b> charging follows "
        "<b>commercial-ROI siting, not residential need</b> — precisely this project's thesis, now "
        "evidenced directly on the map. Our snapshot counts operational public stations at data-collection "
        "time (Apr 2026); PlugShare is live, and the gap is mostly recent commercial-venue build-out. The "
        "district-level equity gaps above (2 km coverage, per-port capacity, 500 m coverage) are unaffected "
        "and still hold.</div>"
        "<div class='stack-cap'>Manual verification, Aug 2026 · public + operational PlugShare listings, "
        "restricted-access and coming-soon excluded · counts are rough per-zone tallies within 2 km.</div>"
        "</div>",
        unsafe_allow_html=True,
    )
else:
    show = oc[["zone_type", "district", "our_public_stations_2km", "maps_link"]].rename(columns={
        "zone_type": "Zone type", "district": "District",
        "our_public_stations_2km": "Our stations ≤2 km", "maps_link": "Map"})
    tbl = ui.html_table(show, num_cols=["Our stations ≤2 km"], link_cols=["Map"])
    st.markdown(
        "<div class='stack'>"
        "<div class='trust-strip'>Live cross-check against PlugShare — <b>pending manual "
        "verification</b>. The 8 seed zones (4 served-KL, 4 Klang-desert) carry our own counts in "
        "<code>operator_crosscheck_template.csv</code>; fill the "
        "<code>plugshare_public_count</code> column and this section presents the comparison.</div>"
        f"{tbl}</div>",
        unsafe_allow_html=True,
    )

st.markdown(
    "<div class='site-footer'>Ng Cheng Xin · TP071136 · Asia Pacific University · FYP 2026 · "
    "Validation: hold-out recall · forecast backtest · weight sensitivity · capacity cross-validation · "
    "operator cross-check.</div>",
    unsafe_allow_html=True,
)
