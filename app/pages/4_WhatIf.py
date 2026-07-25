"""Page 4 — What-If Simulator.

Place up to 5 hypothetical stations and see the COMBINED impact recomputed live,
entirely from stored components (CLAUDE.md §2) — no pipeline calls, fully
vectorized over the 4,003 hexes. Adds each station's distance-decayed supply,
renormalizes with the SAME p99 cap as the pipeline supply_n, recomputes gap + CDI
under the current persona/weights, and reports coverage / severity / CDI / gap /
cost / equity deltas. Reuses the shared map/border/color helpers.
"""
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

from lib import cdi as cdi_lib
from lib import data, mapping, theme, ui

st.set_page_config(page_title="What-If Simulator", layout="wide")
theme.inject_base_css()

MAP_KEY = "whatif_map"
NONE = "__none__"
DECAY_KM = 1.5
MAX_PINS = 5

# ------------------------------------------------------------------ load (cached)
base = data.load_cdi()
rec = data.load_recommended_sites().sort_values("rank").reset_index(drop=True)
districts_geo = data.load_districts()
kv_outline = data.load_kv_outline()
kv_mask = data.load_kv_mask()

BY_H3 = base.set_index("h3_index")
INHABITED = base[base["pop_est"] > 0].sort_values("cdi", ascending=False)
TOP_HEXES = INHABITED.head(250)
P99_CAP = float(base["supply_raw"].quantile(0.99))

LAT = base["lat"].to_numpy(); LON = base["lon"].to_numpy()
POP = base["pop_est"].to_numpy()
SUPPLY_RAW = base["supply_raw"].to_numpy()
SUPPLY_GAP = base["supply_gap"].to_numpy()
BEFORE_COV = base["nearest_station_km"].to_numpy() <= 2.0
BELOW_MEDIAN = base["equity_mult"].to_numpy() > 1.0     # district income < KV median
WORST = INHABITED.iloc[0]                               # highest-CDI (worst-desert) hex
SITE1 = rec.iloc[0]                                     # optimizer's #1 build location


def _hav(latp, lonp):
    la, lo = np.radians(LAT), np.radians(LON)
    pa, po = np.radians(latp), np.radians(lonp)
    return 2 * 6371.0 * np.arcsin(np.sqrt(np.sin((pa - la) / 2) ** 2 +
                                          np.cos(la) * np.cos(pa) * np.sin((po - lo) / 2) ** 2))


def _newly_for(latp, lonp):
    d = _hav(latp, lonp)
    return float(POP[(d <= 2.0) & ~BEFORE_COV].sum())


# ------------------------------------------------------------ pin/mode state
if "pins" not in st.session_state:
    st.session_state.pins = [{"lat": float(WORST.lat), "lon": float(WORST.lon),
                              "label": f"{WORST.district} · worst-desert hex"}]
    st.session_state.mode = "picked"


def _add_pin(lat, lon, label):
    if st.session_state.mode == "optimizer":       # leaving optimizer view → start your own set
        st.session_state.pins = []
        st.session_state.mode = "picked"
    if len(st.session_state.pins) < MAX_PINS:
        st.session_state.pins.append({"lat": lat, "lon": lon, "label": label})


def _clicked_h3():
    state = st.session_state.get(MAP_KEY)
    if state is None:
        return None
    try:
        sel = state.get("selection") if hasattr(state, "get") else getattr(state, "selection", None)
        objs = sel.get("objects") if hasattr(sel, "get") else getattr(sel, "objects", None)
        for rows in (objs or {}).values():
            if rows:
                return rows[0].get("h3_index")
    except Exception:
        return None
    return None


clicked = _clicked_h3()
if clicked and clicked != st.session_state.get("_last_click") and clicked in BY_H3.index:
    st.session_state["_last_click"] = clicked
    r = BY_H3.loc[clicked]
    _add_pin(float(r.lat), float(r.lon), f"{r.district} · clicked hex")


def _add_from_selector():
    h3 = st.session_state.get("wi_hex")
    if h3 and h3 != NONE and h3 in BY_H3.index:
        r = BY_H3.loc[h3]
        _add_pin(float(r.lat), float(r.lon), f"{r.district} · picked hex")
    st.session_state.wi_hex = NONE


# on_click callbacks (NOT st.rerun) so widgets rendered later in the sidebar —
# the Map-layout / cost controls — always render and keep their state
def _remove_pin(i):
    if 0 <= i < len(st.session_state.pins):
        st.session_state.pins.pop(i)


def _clear_pins():
    st.session_state.pins = []
    st.session_state.mode = "picked"


def _compare():
    st.session_state.mode = "optimizer"
    st.session_state.pins = [{"lat": float(SITE1.lat), "lon": float(SITE1.lon),
                              "label": f"Recommended site #1 · {SITE1.district}"}]


# ------------------------------------------------------------------ sidebar controls
with st.sidebar:
    st.markdown("<div class='ctl-title'>View</div>", unsafe_allow_html=True)
    persona = st.segmented_control("Persona", ["Government", "Operator"], default="Government",
                                   label_visibility="collapsed", key="wi_persona") or "Government"
    st.caption("**Government** weights equity · **Operator** ranks pure market demand.")
    st.divider()
    w_pop = st.slider("Population weight", 0.0, 1.0, 0.5, 0.05,
                      help="Activity weight = 1 − population weight")
    st.caption(f"Demand blend: population {w_pop:.2f} · activity {1 - w_pop:.2f}")
    st.divider()

    st.markdown(f"<div class='ctl-title'>Place stations · up to {MAX_PINS}</div>", unsafe_allow_html=True)
    opts = [NONE] + TOP_HEXES["h3_index"].tolist()
    labels = {r.h3_index: f"#{i} · {r.district} · CDI {r.cdi:.0f} · {r.lat:.4f},{r.lon:.4f}"
              for i, r in enumerate(TOP_HEXES.itertuples(), 1)}
    st.selectbox("Drop station on a worst-desert hex (highest CDI)", opts, key="wi_hex",
                 on_change=_add_from_selector,
                 format_func=lambda h: "— pick a hex —" if h == NONE else labels.get(h, h))
    st.caption("…or click any hex on the map.")

    pins = st.session_state.pins
    if pins:
        for i, p in enumerate(pins):
            c1, c2 = st.columns([0.84, 0.16])
            c1.caption(f"{i + 1}. {p['label']}")
            c2.button("✕", key=f"rm{i}", help="remove", on_click=_remove_pin, args=(i,))
        st.button("Clear all", use_container_width=True, on_click=_clear_pins)
    else:
        st.caption("No stations placed yet.")

    st.button("Compare with top recommended site", use_container_width=True, on_click=_compare)
    st.divider()

    cost_per_station = st.number_input("Cost per station (RM)", min_value=0, value=300_000, step=50_000,
                                       key="wi_cost")
    st.divider()

    st.markdown("<div class='ctl-title'>Maps</div>", unsafe_allow_html=True)
    map_layout = st.segmented_control("Map layout", ["Side by side", "Single"], default="Side by side",
                                      label_visibility="collapsed", key="wi_layout") or "Side by side"
    map_view = "After"
    if map_layout == "Single":
        map_view = st.segmented_control("Map view", ["After", "Before"], default="After",
                                        key="wi_view") or "After"

equity_on = persona == "Government"
pins = st.session_state.pins

# ------------------------------------------------------------------ header
st.markdown(
    "<div class='page-title'>What-If Simulator</div>"
    "<div class='page-sub'>Place up to 5 hypothetical stations and watch coverage, severity, CDI, "
    "cost and equity recompute live from stored components</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='leg-wrap' style='max-width:360px'><div class='leg-label'>Charging Desert Index</div>"
    "<div class='leg-bar'></div><div class='leg-scale'><span>0</span><span>50</span><span>100</span></div></div>",
    unsafe_allow_html=True,
)
st.markdown("<hr>", unsafe_allow_html=True)

if not pins:
    st.info("No stations placed. Pick a worst-desert hex, click the map, or compare with the optimizer.")
    st.stop()

# ------------------------------------------------------ live recompute (vectorized)
sum_decay = np.zeros(len(base)); dmin = np.full(len(base), np.inf); dmin_prev = np.full(len(base), np.inf)
for j, p in enumerate(pins):
    d = _hav(p["lat"], p["lon"])
    sum_decay += np.exp(-d / DECAY_KM)
    dmin = np.minimum(dmin, d)
    if j < len(pins) - 1:
        dmin_prev = np.minimum(dmin_prev, d)

new_supply_n = np.clip(SUPPLY_RAW + sum_decay, 0, P99_CAP) / P99_CAP if P99_CAP > 0 else 0
new_gap = 1.0 - new_supply_n
dem = cdi_lib.demand_pressure(base, w_pop, equity_on).to_numpy()
before_raw = dem * SUPPLY_GAP
after_raw = dem * new_gap
peak = before_raw.max()
before_cdi = (100.0 * before_raw / peak) if peak > 0 else before_raw * 0
after_cdi = (100.0 * after_raw / peak) if peak > 0 else after_raw * 0

catchment = dmin <= 2.0
newly = catchment & ~BEFORE_COV
people_newly = float(POP[newly].sum())
catch_pop = float(POP[catchment].sum())
marginal = people_newly - float(POP[(dmin_prev <= 2.0) & ~BEFORE_COV].sum())
sev_b, sev_a = int((before_cdi >= 50).sum()), int((after_cdi >= 50).sum())
d_severe = sev_a - sev_b
m5 = dmin <= 5.0
mean_cdi_change = float(after_cdi[m5].mean() - before_cdi[m5].mean()) if m5.any() else 0.0
pct_gap_closed = (100.0 * people_newly / catch_pop) if catch_pop > 0 else 0.0
total_cost = len(pins) * cost_per_station
cost_per_person = (total_cost / people_newly) if people_newly > 0 else None
equity_pct = (100.0 * POP[newly & BELOW_MEDIAN].sum() / people_newly) if people_newly > 0 else 0.0


def _signed_int(n):
    return f"{n:+d}" if n != 0 else "0"


# ------------------------------------------------------------------ mode label + note
mode_label = ("Optimizer recommendation" if st.session_state.mode == "optimizer"
              else f"Your picked hex{'es' if len(pins) != 1 else ''} · {len(pins)} of {MAX_PINS}")
st.markdown(
    f"<div class='page-sub' style='margin-bottom:8px'><b style='color:{theme.TEXT}'>{mode_label}</b> · "
    f"<b style='color:{theme.TEXT}'>{persona}</b> lens</div>",
    unsafe_allow_html=True,
)
if st.session_state.mode == "optimizer":
    w_n, s_n = _newly_for(WORST.lat, WORST.lon), _newly_for(SITE1.lat, SITE1.lon)
    st.markdown(
        f"<div class='trust-strip'>Worst-desert hex covers <b>{w_n:,.0f} people</b> · the optimizer's "
        f"recommended site covers <span class='tick'>{s_n:,.0f}</span> — "
        f"<b>+{s_n - w_n:,.0f} more</b>, from a lower-CDI location. "
        "The worst desert is not the best place to build.</div>",
        unsafe_allow_html=True,
    )
    st.write("")

# ------------------------------------------------------------------ KPI rows
ui.kpi_row([
    {"label": "People newly within 2 km", "value": theme.fmt_int(people_newly),
     "context": "gained public-charging access from these stations"},
    {"label": "Population in 2 km catchment", "value": theme.fmt_int(catch_pop),
     "context": "total reachable market within 2 km"},
    {"label": "Catchment gap closed", "value": theme.fmt_pct(pct_gap_closed),
     "context": "share of the catchment that gains new coverage"},
    {"label": "Marginal gain · last station", "value": theme.fmt_int(marginal),
     "context": "people the most-recent pin adds beyond the others"},
])
st.write("")
ui.kpi_row([
    {"label": "Severe hexes (CDI ≥ 50)", "value": _signed_int(d_severe),
     "context": f"{sev_b} → {sev_a} · negative is better"},
    {"label": "Mean CDI change · 5 km", "value": f"{mean_cdi_change:+.1f}",
     "context": "average CDI shift within 5 km · lower is better"},
    {"label": "Cost per person covered", "value": (f"RM {cost_per_person:,.0f}" if cost_per_person else "n/a"),
     "context": f"{len(pins)} × RM{cost_per_station:,.0f} ÷ people newly covered · indicative planning figure"},
    {"label": "Equity · below-median income", "value": theme.fmt_pct(equity_pct),
     "context": "of newly-covered people in below-KV-median-income districts"},
])

st.write("")
st.write("")

with st.expander("How to read these", expanded=False):
    st.markdown(
        "- **People newly within 2 km** — gained access: people brought within 2 km of public charging who weren't before.\n"
        "- **Population in 2 km catchment** — the total reachable market: everyone within 2 km of your station(s).\n"
        "- **Catchment gap closed** — share of the catchment that gains *new* coverage (100% = pure desert, 0% = fully redundant).\n"
        "- **Marginal gain · last station** — people the most-recent pin adds beyond the earlier ones (exposes diminishing returns).\n"
        "- **Severe hexes (CDI ≥ 50)** — did any hex escape severe-desert status (a single station rarely moves this relative count).\n"
        "- **Mean CDI change · 5 km** — average nearby severity shift; lower means deserts eased.\n"
        "- **Cost per person covered** — indicative planning figure = total station cost ÷ people newly covered. *Not* a revenue or utilization prediction.\n"
        "- **Equity · below-median income** — share of newly-covered people in below-KV-median-income districts (Klang, Petaling, Putrajaya). "
        "It's coverage-based, so for a *fixed* pin it's the same under both lenses — the lens changes *where* you'd place."
    )

st.write("")

# ------------------------------------------------------------------ maps
c_lat = float(np.mean([p["lat"] for p in pins]))
c_lon = float(np.mean([p["lon"] for p in pins]))
zoom = 10.5 if len(pins) == 1 else 9.4
pins_df = pd.DataFrame(pins)
tooltip = {"html": "{tip}", "style": {"backgroundColor": theme.SURFACE, "color": theme.TEXT,
           "fontSize": "12px", "border": f"1px solid {theme.BORDER}", "borderRadius": "6px",
           "padding": "6px 8px", "maxWidth": "290px", "whiteSpace": "pre-line", "lineHeight": "1.4"}}


def make_deck(cdi_arr, height_zoom):
    mdf = base[["h3_index", "district", "pop_est"]].copy()
    mdf["fill_color"] = [theme.cdi_to_rgb(v) for v in cdi_arr]
    mdf["tip"] = [f"{d}\nCDI {v:.0f} · {p:,.0f} residents"
                  for d, v, p in zip(mdf["district"], cdi_arr, mdf["pop_est"])]
    layers = mapping.mask_layer(kv_mask)
    layers.append(pdk.Layer("H3HexagonLayer", id="cdi_hex",
                            data=mdf[["h3_index", "fill_color", "tip"]], get_hexagon="h3_index",
                            get_fill_color="fill_color", pickable=True, auto_highlight=True,
                            stroked=False, extruded=False, opacity=0.85))
    layers += mapping.border_layers(districts_geo, kv_outline)
    layers.append(pdk.Layer("ScatterplotLayer", id="rings", data=pins_df, get_position="[lon, lat]",
                            get_radius=2000, filled=False, stroked=True,
                            get_line_color=theme.ACCENT_RGB + [200], line_width_min_pixels=1.5,
                            pickable=False, parameters={"depthTest": False}))
    layers.append(pdk.Layer("ScatterplotLayer", id="pins", data=pins_df, get_position="[lon, lat]",
                            get_fill_color=theme.RECOMMENDED + [240], get_radius=300,
                            radius_min_pixels=9, radius_max_pixels=15, stroked=True,
                            get_line_color=[255, 255, 255, 255], line_width_min_pixels=2,
                            pickable=False, parameters={"depthTest": False}))
    return pdk.Deck(layers=layers,
                    initial_view_state=pdk.ViewState(latitude=c_lat, longitude=c_lon, zoom=height_zoom,
                                                     pitch=0, bearing=0),
                    map_provider="carto", map_style=pdk.map_styles.CARTO_DARK, tooltip=tooltip)


if map_layout == "Side by side":
    cB, cA = st.columns(2, gap="medium")
    with cB:
        ui.section_header("Before")
        st.pydeck_chart(make_deck(before_cdi, zoom - 0.4), use_container_width=True, height=430)
    with cA:
        ui.section_header("After")
        st.pydeck_chart(make_deck(after_cdi, zoom - 0.4), use_container_width=True, height=430,
                        selection_mode="single-object", on_select="rerun", key=MAP_KEY)
    st.caption("Same colour scale and centre on both maps. Green pins = your stations · blue rings = "
               "their 2 km catchments. Click a hex on the After map to add a station.")
else:
    cdi_arr = after_cdi if map_view == "After" else before_cdi
    st.pydeck_chart(make_deck(cdi_arr, zoom), use_container_width=True, height=520,
                    selection_mode="single-object", on_select="rerun", key=MAP_KEY)
    st.caption(f"Showing CDI **{map_view.lower()}** · green pins = your stations · blue rings = 2 km "
               "catchments. Click a hex to add a station; toggle the view in the sidebar.")

st.caption("**Indicative catchment simulation** using the same exp(−distance / 1.5 km) decay as the CDI — "
           "it recomputes coverage and CDI from stored components, not utilization or revenue.")
