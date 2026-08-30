"""Page 1 — CDI Explorer.

Map-first explorer (DESIGN.md §2a): slim sidebar controls, a full-height inferno
CDI map as the hero, and a right-hand inspector that appears on selection. The
persona toggle and weight slider recompute CDI live from stored components
(app/lib/cdi.py) — pure arithmetic, no pipeline. Reason strings are the product's
explainability: available on hover (guaranteed) and in the inspector.

Selection: clicking a hex on the map focuses it and opens the inspector panel.
(An "Inspect a hex" selectbox used to sit above the map; it never populated and
never synced with the map, so it was removed -- review item A1.)
"""
import pandas as pd
import pydeck as pdk
import streamlit as st

from lib import cdi as cdi_lib
from lib import data, mapping, theme, ui

st.set_page_config(page_title="CDI Explorer", layout="wide")
theme.inject_base_css()

MAP_KEY = "cdi_map"

# ------------------------------------------------------------------ load (cached)
base = data.load_cdi()
stations = data.load_stations()
districts_geo = data.load_districts()
kv_outline = data.load_kv_outline()
kv_mask = data.load_kv_mask()
ALL_DISTRICTS = sorted(base["district"].unique())


# ----------------------------------------- native map-click (bonus selection path)
def clicked_hex() -> str | None:
    """Read the hex clicked on the previous render from the chart's selection
    state. Fully defensive: any shape mismatch just yields None (hover + the
    selector remain the guaranteed paths)."""
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


clicked = clicked_hex()

def _reset_defaults() -> None:
    """Restore the validated baseline configuration the headline figures use."""
    st.session_state["persona"] = "Government"
    st.session_state["w_pop"] = 0.5


# ------------------------------------------------------------------ sidebar controls
with st.sidebar:
    st.markdown("<div class='ctl-title'>View</div>", unsafe_allow_html=True)
    persona = st.segmented_control(
        "Persona", ["Government", "Operator"], default="Government",
        label_visibility="collapsed", key="persona",
    ) or "Government"
    st.caption("**Government** weights equity for underserved areas · "
               "**Operator** ranks pure market demand.")
    st.divider()

    w_pop = st.slider("Population weight", 0.0, 1.0, 0.5, 0.05, key="w_pop",
                      help="Activity weight = 1 − population weight")
    st.caption(f"Demand blend: population {w_pop:.2f} · activity {1 - w_pop:.2f}")
    st.button("Reset to validated defaults", on_click=_reset_defaults,
              use_container_width=True,
              help="Government lens, population 0.50 / activity 0.50")
    st.caption("Headline figures use the Government lens with population 0.50 / "
               "activity 0.50. CDI is scaled against the validated baseline, so "
               "values remain comparable across settings.")
    st.divider()

    st.markdown("<div class='ctl-title'>Map layers</div>", unsafe_allow_html=True)
    show_public = st.checkbox("Public stations", value=True)
    show_private = st.checkbox("Private / restricted", value=False)
    show_borders = st.checkbox("District borders", value=True)
    show_market = st.checkbox(
        "Market interest (predicted)", value=False,
        help="Replaces the CDI colouring with the operator model's predicted "
             "probability that a hex holds a public charger. Diagnostic: this is "
             "commercial INTEREST, not need.")
    st.markdown(
        "<div class='lyr-legend'>"
        "<div class='lyr-item'><span class='dot' style='background:#00E5FF'></span>Public stations</div>"
        "<div class='lyr-item'><span class='dot' style='background:#7A828E'></span>Private / restricted</div>"
        "<div class='lyr-item'><span class='line-swatch'></span>District border</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    sel_districts = st.multiselect("Districts", ALL_DISTRICTS, default=ALL_DISTRICTS)

equity_on = persona == "Government"

# ------------------------------------------------------- recompute CDI, then filter
df = base.copy()
df["cdi_live"] = cdi_lib.recompute_cdi(df, w_pop=w_pop, equity_on=equity_on)

if not sel_districts:
    st.markdown("<div class='page-title'>CDI Explorer</div>", unsafe_allow_html=True)
    st.info("Select at least one district in the sidebar to display the map.")
    st.stop()

view = df[df["district"].isin(sel_districts)].copy()


def reason_of(r, eq_on: bool) -> str:
    parts = [f"CDI {r.cdi_live:.0f}", f"{r.pop_est:,.0f} residents", f"activity {r.activity_score:.0f}"]
    if eq_on:
        parts.append(f"×{r.equity_mult:.2f} equity")
    parts += [f"nearest charger {r.nearest_station_km:.1f} km", f"{int(r.stations_5km)} within 5 km"]
    return " · ".join(parts)


view["reason"] = [reason_of(r, equity_on) for r in view.itertuples()]

# --- optional market-interest layer (stage 11, DIAGNOSTIC) -------------------
# Predicted probability that a hex holds a public charger, i.e. commercial
# INTEREST. Deliberately a different colour ramp from the CDI so the two are
# never read as the same quantity: need is the inferno ramp, interest is amber.
MARKET_MAX = 0.0
if show_market:
    _sc = data.load_operator_scores()
    if len(_sc):
        view = view.merge(_sc[["h3_index", "oof_proba_randomCV"]],
                          on="h3_index", how="left")
        view["market_p"] = view["oof_proba_randomCV"].fillna(0.0)
        MARKET_MAX = float(view["market_p"].max())
    else:
        show_market = False


def market_rgb(p: float, pmax: float) -> list:
    if pmax <= 0:
        return [40, 46, 60, 60]
    t = min(1.0, max(0.0, p / pmax)) ** 0.6
    lo, hi = (28, 32, 44), (255, 176, 46)          # slate -> amber
    return [int(lo[i] + (hi[i] - lo[i]) * t) for i in range(3)] + [int(45 + 195 * t)]


if show_market:
    view["fill_color"] = [market_rgb(p, MARKET_MAX) for p in view["market_p"]]
    view["tip"] = [f"{d}\nPredicted market interest {p:.1%}\n(CDI {c:.0f} — need, for contrast)"
                   for d, p, c in zip(view["district"], view["market_p"], view["cdi_live"])]
else:
    CDI_MAX = float(view["cdi_live"].max())
    view["fill_color"] = [theme.cdi_to_rgb(v, over_max=CDI_MAX) for v in view["cdi_live"]]
    view["tip"] = [f"{d}\n{rs}" for d, rs in zip(view["district"], view["reason"])]

# ------------------------------------------------------------------ header + legend
st.markdown(
    "<div class='page-title'>CDI Explorer</div>"
    "<div class='page-sub'>Charging Desert Index by hex · brighter = more underserved · "
    "recomputed live from stored components</div>",
    unsafe_allow_html=True,
)
if show_market:
    st.markdown(
        "<div class='leg-wrap' style='max-width:420px'>"
        "<div class='leg-label'>Predicted market interest — NOT need</div>"
        "<div class='leg-bar' style='background:linear-gradient(90deg,#1C202C,#FFB02E)'></div>"
        f"<div class='leg-scale'><span>0%</span><span>{MARKET_MAX / 2:.0%}</span>"
        f"<span>{MARKET_MAX:.0%}</span></div></div>",
        unsafe_allow_html=True,
    )
    st.warning(
        "**Diagnostic layer.** This is the operator model's predicted probability "
        "that a hex holds a public charger — where the commercial market is "
        "drawn, not where charging is needed. It is shown for contrast with the "
        "Charging Desert Index, and must not be used to select sites. "
        "See the Market Logic page.",
        icon="⚠️",
    )
else:
    ui.cdi_legend(float(view["cdi_live"].max()))
st.markdown("<hr>", unsafe_allow_html=True)

# ------------------------------------------------------------------ KPI row (reactive)
inh_view = view[view["pop_est"] > 0]
severe = view[view["cdi_live"] >= 50]
median_near = view["nearest_station_km"].median() if len(view) else 0.0
ui.kpi_row([
    {"label": "Severe desert hexes", "value": theme.fmt_int((view["cdi_live"] >= 50).sum()),
     "context": f"{persona} view · CDI ≥ 50 · of {theme.fmt_int(len(inh_view))} inhabited in view"},
    {"label": "People in severe zones", "value": theme.fmt_int(severe["pop_est"].sum()),
     "context": f"CDI ≥ 50 · demand blend pop {w_pop:.2f} / act {1 - w_pop:.2f}"},
    {"label": "Median nearest charger", "value": theme.fmt_km(median_near),
     "context": "all hexes in view · public + operational stations"},
])

st.write("")

# ------------------------------------------------------------ hex selection
# The map click IS the selection. There used to be an "Inspect a hex"
# selectbox here; it shipped with only its placeholder option, returned
# nothing when typed into, and never synced with a map click, so it was a
# dead control (review item A1). Removed rather than repaired -- clicking the
# hex is the better interaction and it already worked.
view_ids = set(view["h3_index"])
selected_h3 = clicked if clicked in view_ids else None
selected_row = view.loc[view["h3_index"] == selected_h3].iloc[0] if selected_h3 else None
st.caption("Click any hex on the map to inspect it. Hover for its reason string.")

# ------------------------------------------------------------------ build map layers
# mask first (dims everything outside KV), then hexes, borders, highlight, stations
layers = mapping.mask_layer(kv_mask)
layers.append(
    pdk.Layer(
        "H3HexagonLayer", id="cdi_layer",
        data=view[["h3_index", "fill_color", "tip"]],
        get_hexagon="h3_index", get_fill_color="fill_color",
        pickable=True, auto_highlight=True, stroked=False, extruded=False, opacity=0.85,
    )
)
if show_borders:
    layers += mapping.border_layers(districts_geo, kv_outline)
if selected_row is not None:
    layers.append(pdk.Layer(
        "H3HexagonLayer", id="highlight",
        data=pd.DataFrame([{"h3_index": selected_row["h3_index"]}]),
        get_hexagon="h3_index", get_fill_color=[62, 123, 250, 55],
        stroked=True, get_line_color=[255, 255, 255, 230], line_width_min_pixels=2,
        pickable=False, extruded=False,
    ))
# stations rendered last so they sit on top → their tooltip takes priority
layers += mapping.station_layers(
    stations[stations["district"].isin(sel_districts)],
    show_public=show_public, show_private=show_private,
)

view_state = pdk.ViewState(
    latitude=float(view["lat"].mean()), longitude=float(view["lon"].mean()),
    zoom=9.1 if len(sel_districts) > 2 else 10.3, pitch=0, bearing=0,
)
# tip values are PLAIN TEXT (no <b>/<br/> tags), so no pydeck version can render
# tags literally; line breaks come from \n + white-space:pre-line, not <br/>
tooltip = {
    "html": "{tip}",
    "style": {"backgroundColor": theme.SURFACE, "color": theme.TEXT, "fontSize": "12px",
              "border": f"1px solid {theme.BORDER}", "borderRadius": "6px",
              "padding": "6px 8px", "maxWidth": "290px", "whiteSpace": "pre-line",
              "lineHeight": "1.4"},
}
deck = pdk.Deck(
    layers=layers, initial_view_state=view_state,
    map_provider="carto", map_style=pdk.map_styles.CARTO_DARK, tooltip=tooltip,
)

# ------------------------------------------------------------------ map + inspector
if selected_row is not None:
    map_col, insp_col = st.columns([0.72, 0.28], gap="large")
else:
    map_col, insp_col = st.container(), None

with map_col:
    st.pydeck_chart(deck, use_container_width=True, height=620,
                    selection_mode="single-object", on_select="rerun", key=MAP_KEY)

if insp_col is not None:
    r = selected_row
    detail = [
        ("District", r["district"]),
        ("Population (est.)", f"{r['pop_est']:,.0f}"),
        ("Activity score", f"{r['activity_score']:.0f}"),
        ("Equity multiplier", f"×{r['equity_mult']:.2f}" + ("" if equity_on else " (off — Operator)")),
        ("Nearest public charger", f"{r['nearest_station_km']:.1f} km"),
        ("Stations within 2 km", f"{int(r['stations_2km'])}"),
        ("Stations within 5 km", f"{int(r['stations_5km'])}"),
        ("Location", f"{r['lat']:.5f}, {r['lon']:.5f}"),
    ]
    reason_parts = [f"{r['pop_est']:,.0f} residents", f"activity {r['activity_score']:.0f}"]
    if equity_on:
        reason_parts.append(f"×{r['equity_mult']:.2f} equity")
    reason_parts += [f"nearest charger {r['nearest_station_km']:.1f} km",
                     f"{int(r['stations_5km'])} within 5 km"]
    rows_html = "".join(f"<div class='insp-row'><span>{k}</span><b>{v}</b></div>" for k, v in detail)
    maps_url = f"https://www.google.com/maps/@{r['lat']:.5f},{r['lon']:.5f},15z"
    warn = ("<div class='insp-warn'>⚠ Low OpenStreetMap coverage here — "
            "population/activity may be understated.</div>"
            if r["pop_est"] == 0 and r["activity_score"] == 0 else "")
    insp_col.markdown(
        "<div class='insp-panel'>"
        "<div class='insp-h'>Hex inspector</div>"
        f"<div class='insp-cdi'>CDI {r['cdi_live']:.0f}</div>"
        f"<div class='insp-sub'>{r['district']}</div>"
        f"<div class='insp-reason'>{' · '.join(reason_parts)}</div>"
        f"{rows_html}"
        f"<a class='insp-link' href='{maps_url}' target='_blank'>Open in Google Maps ↗</a>"
        f"{warn}"
        "</div>",
        unsafe_allow_html=True,
    )
