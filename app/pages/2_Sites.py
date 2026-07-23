"""Page 2 — Recommendations.

Where to build next, and what each site is worth. Map-first (DESIGN.md §2a):
CDI backdrop + numbered green site markers + red desert-zone outlines + optional
cyan stations, a site-count slider driving the map/table/KPIs/coverage so the
user sees marginal value, a sortable site table that opens a CPO-ready scorecard,
a cumulative-coverage curve and a before→after coverage chart. Reuses the shared
map/border/station/color helpers; reads only processed_data/.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from lib import data, mapping, theme, ui

st.set_page_config(page_title="Recommendations", layout="wide")
theme.inject_base_css()

TABLE_KEY = "site_table"
_SHOW_LABELS = True   # rank-number TextLayer on the site markers

# ------------------------------------------------------------------ load (cached)
rec = data.load_recommended_sites().sort_values("rank").reset_index(drop=True)
zones = data.load_desert_zones().sort_values("population", ascending=False).reset_index(drop=True)
hx = data.load_cdi()
stations = data.load_stations()
districts_geo = data.load_districts()
kv_outline = data.load_kv_outline()
kv_mask = data.load_kv_mask()

TOTAL_POP = float(hx["pop_est"].sum())
BASE_COV = float(hx.loc[hx["nearest_station_km"] <= 2.0, "pop_est"].sum())
BEFORE_PCT = 100 * BASE_COV / TOTAL_POP


@st.cache_data(show_spinner=False)
def cumulative_series():
    r = data.load_recommended_sites().sort_values("rank")
    ys = [0.0] + [float(v) for v in r["pop_newly_covered"].cumsum()]
    xs = list(range(0, len(r) + 1))
    return xs, ys


@st.cache_data(show_spinner=False)
def coverage_before_after(n: int):
    """Per-district 2 km coverage before, and after the top-n sites (a hex is
    covered if its centroid is within 2 km of an existing public station OR a
    selected site). Sorted worst-first by 'before'."""
    h = data.load_cdi()
    sites = data.load_recommended_sites().sort_values("rank").head(n)
    R = 6371.0
    hlat = np.radians(h["lat"].to_numpy())[:, None]
    hlon = np.radians(h["lon"].to_numpy())[:, None]
    slat = np.radians(sites["lat"].to_numpy())[None, :]
    slon = np.radians(sites["lon"].to_numpy())[None, :]
    d = 2 * R * np.arcsin(np.sqrt(np.sin((slat - hlat) / 2) ** 2 +
                                  np.cos(hlat) * np.cos(slat) * np.sin((slon - hlon) / 2) ** 2))
    near_site = d.min(axis=1) if n > 0 else np.full(len(h), np.inf)
    t = h.copy()
    t["cov_before"] = t["nearest_station_km"] <= 2.0
    t["cov_after"] = t["cov_before"] | (near_site <= 2.0)
    g = t.groupby("district").apply(
        lambda x: pd.Series({
            "before": 100 * x.loc[x["cov_before"], "pop_est"].sum() / x["pop_est"].sum(),
            "after": 100 * x.loc[x["cov_after"], "pop_est"].sum() / x["pop_est"].sum(),
        }), include_groups=False).sort_values("before")
    return list(g.index), [float(v) for v in g["before"]], [float(v) for v in g["after"]]


# ------------------------------------------------------------------ sidebar controls
with st.sidebar:
    st.markdown("<div class='ctl-title'>Sites to build</div>", unsafe_allow_html=True)
    n_sites = st.slider("Number of sites", 1, len(rec), len(rec),
                        help="Show the top-N ranked sites — drag down to see the marginal value of each.")
    st.caption("Sites are ranked by how many new people they bring within 2 km (greedy maximal coverage).")
    st.divider()

    st.markdown("<div class='ctl-title'>Map layers</div>", unsafe_allow_html=True)
    show_cdi = st.checkbox("CDI heat backdrop", value=True)
    show_sites = st.checkbox("Recommended sites", value=True)
    show_zones = st.checkbox("Desert zones", value=True)
    show_public = st.checkbox("Public stations", value=False)
    st.markdown(
        "<div class='lyr-legend'>"
        "<div class='lyr-item'><span class='dot' style='background:#00FF88'></span>Recommended site</div>"
        "<div class='lyr-item'><span class='dot' style='background:transparent;border:1.5px solid #FF3B30'></span>Desert zone</div>"
        "<div class='lyr-item'><span class='dot' style='background:#00E5FF'></span>Public station</div>"
        "</div>",
        unsafe_allow_html=True,
    )

shown = rec.head(n_sites).copy()

# ------------------------------------------------ selected site (from table, prev run)
sel_state = st.session_state.get(TABLE_KEY)
sel_pos = None
try:
    rows = (sel_state.get("selection") if hasattr(sel_state, "get") else None) or {}
    rows = rows.get("rows") if hasattr(rows, "get") else None
    if rows:
        sel_pos = rows[0]
except Exception:
    sel_pos = None

selected = None
if sel_pos is not None and sel_pos < len(shown):
    selected = shown.iloc[sel_pos]      # table is sorted by rank, same order as `shown`

# ------------------------------------------------------------------ reactive metrics
newly = float(shown["pop_newly_covered"].sum())
after_pct = 100 * (BASE_COV + newly) / TOTAL_POP

# ------------------------------------------------------------------ build map layers
layers = mapping.mask_layer(kv_mask)

if show_cdi:
    bg = hx[["h3_index"]].copy()
    bg["fill_color"] = [theme.cdi_to_rgb(v, alpha=150) for v in hx["cdi"]]
    layers.append(pdk.Layer(
        "H3HexagonLayer", id="cdi_bg", data=bg, get_hexagon="h3_index",
        get_fill_color="fill_color", pickable=False, stroked=False, extruded=False, opacity=0.55,
    ))

layers += mapping.border_layers(districts_geo, kv_outline)

if show_zones and len(zones):
    zd = zones.copy()
    zd["radius_m"] = np.sqrt(zd["hexes"] * 0.737 / np.pi) * 1000        # ~footprint of the cluster
    zd["tip"] = [f"Desert zone · {z.district}\n{int(z.hexes)} hexes · {z.population:,.0f} people · "
                 f"mean CDI {z.mean_cdi:.0f}" for z in zd.itertuples()]
    layers.append(pdk.Layer(
        "ScatterplotLayer", id="zones", data=zd[["lon", "lat", "radius_m", "tip"]],
        get_position="[lon, lat]", get_radius="radius_m",
        filled=True, get_fill_color=theme.DESERT_OUTLINE + [26],
        stroked=True, get_line_color=theme.DESERT_OUTLINE + [220], line_width_min_pixels=1.5,
        pickable=True, parameters={"depthTest": False},
    ))

if show_public:
    layers += mapping.station_layers(stations, show_public=True, show_private=False)

if show_sites and len(shown):
    sd = shown.copy()
    sd["rank_str"] = sd["rank"].astype(str)
    sd["tip"] = [f"Site #{int(s.rank)} · {s.district}\nCDI {s.cdi:.0f} · "
                 f"+{s.pop_newly_covered:,.0f} people covered\nnearest existing {s.nearest_existing_km:.1f} km"
                 for s in sd.itertuples()]
    # marker + number both at z=0 with depthTest off, so the label stays centred
    # on the marker at every zoom (no elevation parallax)
    layers.append(pdk.Layer(
        "ScatterplotLayer", id="sites", data=sd[["lon", "lat", "tip"]],
        get_position="[lon, lat]", get_fill_color=theme.RECOMMENDED + [235],
        get_radius=260, radius_min_pixels=9, radius_max_pixels=16,
        stroked=True, get_line_color=[6, 8, 16, 235], line_width_min_pixels=1, pickable=True,
        parameters={"depthTest": False},
    ))
    if _SHOW_LABELS:
        layers.append(pdk.Layer(
            "TextLayer", id="site_labels", data=sd[["lon", "lat", "rank_str"]],
            get_position="[lon, lat]", get_text="rank_str", get_size=14,
            get_color=[8, 10, 16], pickable=False, parameters={"depthTest": False},
        ))

if selected is not None:
    hl = pd.DataFrame([{"lon": float(selected["lon"]), "lat": float(selected["lat"])}])
    layers.append(pdk.Layer(
        "ScatterplotLayer", id="site_hl", data=hl, get_position="[lon, lat]",
        get_fill_color=[0, 0, 0, 0], stroked=True, get_line_color=[255, 255, 255, 255],
        line_width_min_pixels=2.5, get_radius=360, radius_min_pixels=14, radius_max_pixels=22,
        pickable=False, parameters={"depthTest": False},
    ))

view_state = pdk.ViewState(latitude=float(hx["lat"].mean()), longitude=float(hx["lon"].mean()),
                           zoom=9.1, pitch=0, bearing=0)
tooltip = {
    "html": "{tip}",
    "style": {"backgroundColor": theme.SURFACE, "color": theme.TEXT, "fontSize": "12px",
              "border": f"1px solid {theme.BORDER}", "borderRadius": "6px",
              "padding": "6px 8px", "maxWidth": "290px", "whiteSpace": "pre-line",
              "lineHeight": "1.4"},
}
deck = pdk.Deck(layers=layers, initial_view_state=view_state,
                map_provider="carto", map_style=pdk.map_styles.CARTO_DARK, tooltip=tooltip)

# ------------------------------------------------------------------ header + KPIs
st.markdown(
    "<div class='page-title'>Recommendations</div>"
    "<div class='page-sub'>Where to build next, ranked by people brought within 2 km of public "
    "charging · greedy maximal coverage</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='leg-wrap' style='max-width:360px'><div class='leg-label'>CDI backdrop</div>"
    "<div class='leg-bar'></div><div class='leg-scale'><span>0</span><span>50</span><span>100</span></div></div>",
    unsafe_allow_html=True,
)
st.markdown("<hr>", unsafe_allow_html=True)

ui.kpi_row([
    {"label": "People newly covered", "value": theme.fmt_int(newly),
     "context": f"within 2 km of a new site · top {n_sites} of {len(rec)} sites"},
    {"label": "Coverage before → after", "value": f"{theme.fmt_pct(BEFORE_PCT)} → {theme.fmt_pct(after_pct)}",
     "context": f"KV population within 2 km of public charging · +{after_pct - BEFORE_PCT:.1f} pts"},
    {"label": "Sites shown", "value": f"{n_sites} of {len(rec)}",
     "context": "drag the slider to see each site's marginal value"},
])

st.write("")

st.info("**Why some sites sit in low-CDI hexes — this is intended, not a bug.** The Charging Desert "
        "Index shows *where* underserved people are; the optimizer picks the best *position* to serve "
        "them. A 2 km catchment placed at the edge of a desert pocket can cover the whole pocket, even "
        "if the host hex itself already has a charger nearby.")

st.pydeck_chart(deck, use_container_width=True, height=560)

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ------------------------------------------------------------------ table + scorecard
tbl_col, card_col = st.columns([0.6, 0.4], gap="large")

with tbl_col:
    ui.section_header("Recommended sites")
    table_df = shown[["rank", "district", "cdi", "pop_newly_covered", "nearest_existing_km"]]
    st.dataframe(
        table_df, key=TABLE_KEY, on_select="rerun", selection_mode="single-row",
        hide_index=True, use_container_width=True, height=430,
        column_config={
            "rank": st.column_config.NumberColumn("Rank", width="small"),
            "district": st.column_config.TextColumn("District"),
            "cdi": st.column_config.NumberColumn("CDI", format="%.0f", width="small"),
            "pop_newly_covered": st.column_config.NumberColumn("People newly covered", format="%d"),
            "nearest_existing_km": st.column_config.NumberColumn("Nearest existing (km)", format="%.1f"),
        },
    )
    st.caption("Click a row to open its scorecard and highlight it on the map. Click a column header to sort.")

with card_col:
    ui.section_header("Site scorecard")
    if selected is None:
        st.markdown("<div class='insp-panel'><div class='insp-h'>No site selected</div>"
                    "<div class='insp-sub'>Click a row in the table to open a site's full scorecard.</div>"
                    "</div>", unsafe_allow_html=True)
    else:
        r = selected
        rows = [
            ("District", r["district"]),
            ("Location", f"{r['lat']:.5f}, {r['lon']:.5f}"),
            ("Host-hex CDI", f"{r['cdi']:.0f}"),
            ("Host-hex population", f"{r['hex_pop']:,.0f}"),
            ("Host-hex activity", f"{r['hex_activity']:.0f}"),
            ("People newly covered", f"{r['pop_newly_covered']:,.0f}"),
            ("Demand gain (weighted)", f"{r['demand_gain']:.2f}"),
            ("Nearest existing station", f"{r['nearest_existing_km']:.1f} km"),
        ]
        rows_html = "".join(f"<div class='insp-row'><span>{k}</span><b>{v}</b></div>" for k, v in rows)
        maps_url = f"https://www.google.com/maps/@{r['lat']:.5f},{r['lon']:.5f},15z"
        st.markdown(
            "<div class='insp-panel'><div class='insp-h'>Recommended site</div>"
            f"<div class='insp-cdi'>#{int(r['rank'])}</div>"
            f"<div class='insp-sub'>{r['district']}</div>"
            f"<div class='insp-reason'>Brings <b>{r['pop_newly_covered']:,.0f} people</b> within 2 km "
            f"of public charging · nearest existing station {r['nearest_existing_km']:.1f} km away.</div>"
            f"{rows_html}"
            f"<a class='insp-link' href='{maps_url}' target='_blank'>Open in Google Maps ↗</a></div>",
            unsafe_allow_html=True,
        )

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ------------------------------------------------------------------ coverage charts
ui.section_header("Marginal value & coverage")
curve_col, ba_col = st.columns(2, gap="large")

with curve_col:
    xs, ys = cumulative_series()
    figc = go.Figure()
    figc.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines", line=dict(color=theme.ACCENT, width=2.5),
        hovertemplate="%{x} sites → %{y:,.0f} people newly covered<extra></extra>"))
    figc.add_trace(go.Scatter(
        x=[n_sites], y=[ys[n_sites]], mode="markers",
        marker=dict(color=theme.ACCENT, size=12, line=dict(color="#FFFFFF", width=2)),
        hovertemplate=f"{n_sites} sites → %{{y:,.0f}} newly covered<extra></extra>"))
    figc.update_layout(
        height=320, margin=dict(l=6, r=16, t=34, b=6), showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=theme.TEXT_MUTED, size=12),
        title=dict(text="Cumulative people newly covered", font=dict(color=theme.TEXT, size=13.5), x=0),
        xaxis=dict(title="Number of sites", showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                   zeroline=False, dtick=5),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", zeroline=False,
                   tickformat=",", rangemode="tozero"),
    )
    st.plotly_chart(figc, use_container_width=True, config={"displayModeBar": False})

with ba_col:
    d_names, before, after = coverage_before_after(n_sites)
    figb = go.Figure()
    figb.add_bar(y=d_names, x=before, orientation="h", name="Before",
                 marker=dict(color=theme.TEXT_FAINT, cornerradius=3),
                 hovertemplate="%{y} before: %{x:.1f}%<extra></extra>")
    figb.add_bar(y=d_names, x=after, orientation="h", name="After",
                 marker=dict(color=theme.ACCENT, cornerradius=3),
                 hovertemplate="%{y} after: %{x:.1f}%<extra></extra>")
    figb.update_layout(
        barmode="group", height=320, margin=dict(l=6, r=14, t=34, b=6),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=theme.TEXT_MUTED, size=12), bargap=0.32, bargroupgap=0.08,
        title=dict(text="2 km coverage before → after, by district",
                   font=dict(color=theme.TEXT, size=13.5), x=0),
        legend=dict(orientation="h", y=1.14, x=1, xanchor="right", font=dict(size=11)),
        xaxis=dict(range=[0, 108], showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                   ticksuffix="%", zeroline=False),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(figb, use_container_width=True, config={"displayModeBar": False})

st.caption(f"Coverage recomputed for the {n_sites} sites shown. Headline at 20 sites: "
           "Klang 47.2% → 83.7%.")

st.write("")

# ------------------------------------------------------------------ desert zones
ui.section_header("Desert zones (DBSCAN)")
with st.expander(f"{len(zones)} contiguous desert zones — two distinct types", expanded=False):
    st.caption("Two desert types are visible: **Petaling's** zones are largest by population (moderate "
               "severity), while **Klang's** zones are the most severe (highest mean CDI).")
    zt = zones[["zone", "district", "hexes", "population", "mean_cdi"]].copy()
    st.dataframe(
        zt, hide_index=True, use_container_width=True,
        column_config={
            "zone": st.column_config.NumberColumn("Zone", width="small"),
            "district": st.column_config.TextColumn("District"),
            "hexes": st.column_config.NumberColumn("Hexes", width="small"),
            "population": st.column_config.NumberColumn("Population", format="%d"),
            "mean_cdi": st.column_config.NumberColumn("Mean CDI", format="%.1f"),
        },
    )

st.markdown(
    "<div class='site-footer'>Ng Cheng Xin · TP071136 · Asia Pacific University · FYP 2026 · "
    "Sites: greedy maximal coverage · Zones: DBSCAN on CDI ≥ 40.</div>",
    unsafe_allow_html=True,
)
