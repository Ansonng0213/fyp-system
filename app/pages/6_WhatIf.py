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
IS_KLANG = (base["district"].to_numpy() == "Klang")
POP_TOTAL = float(POP.sum())
POP_KLANG = float(POP[IS_KLANG].sum())
WORST = INHABITED.iloc[0]                               # highest-CDI (worst-desert) hex
SITE1 = rec.iloc[0]                                     # optimizer's #1 build location

# The market's next 20. operator_market_forecast.csv is a DISTRICT-level summary
# with no coordinates, so it cannot name sites; operator_model_scores.csv holds
# the per-hex out-of-fold probabilities that produced that summary and is the
# only artifact that can. DIAGNOSTIC — a prediction of commercial behaviour.
_scores = data.load_operator_scores()
if len(_scores):
    MARKET = (_scores[_scores["has_station"] == 0]
              .nlargest(20, "oof_proba_randomCV")
              .reset_index(drop=True))
else:
    MARKET = pd.DataFrame()


def _hav(latp, lonp):
    la, lo = np.radians(LAT), np.radians(LON)
    pa, po = np.radians(latp), np.radians(lonp)
    return 2 * 6371.0 * np.arcsin(np.sqrt(np.sin((pa - la) / 2) ** 2 +
                                          np.cos(la) * np.cos(pa) * np.sin((po - lo) / 2) ** 2))


def _newly_for(latp, lonp):
    d = _hav(latp, lonp)
    return float(POP[(d <= 2.0) & ~BEFORE_COV].sum())


@st.cache_data(show_spinner=False)
def compute_scenario(coords: tuple, w_pop: float, equity_on: bool) -> dict:
    """Every number this page shows, for an arbitrary set of station coordinates.

    Identical arithmetic to the original inline block — factored out only so the
    preset scenarios and the comparison table are computed the same way as the
    live pins and cannot drift apart. No CDI formula changed: the frozen
    denominator from cdi_scale.json is still the only thing CDI divides by.
    """
    n = len(base)
    sum_decay = np.zeros(n)
    dmin = np.full(n, np.inf)
    dmin_prev = np.full(n, np.inf)
    for j, (latp, lonp) in enumerate(coords):
        d = _hav(latp, lonp)
        sum_decay += np.exp(-d / DECAY_KM)
        dmin = np.minimum(dmin, d)
        if j < len(coords) - 1:
            dmin_prev = np.minimum(dmin_prev, d)

    new_supply_n = np.clip(SUPPLY_RAW + sum_decay, 0, P99_CAP) / P99_CAP if P99_CAP > 0 else 0
    new_gap = 1.0 - new_supply_n
    dem = cdi_lib.demand_pressure(base, w_pop, equity_on).to_numpy()
    peak = cdi_lib.cdi_scale()
    before_cdi = (100.0 * dem * SUPPLY_GAP / peak) if peak > 0 else dem * 0
    after_cdi = (100.0 * dem * new_gap / peak) if peak > 0 else dem * 0

    catchment = dmin <= 2.0
    newly = catchment & ~BEFORE_COV
    people_newly = float(POP[newly].sum())
    catch_pop = float(POP[catchment].sum())
    cov_after = BEFORE_COV | catchment
    m5 = dmin <= 5.0
    return {
        "before_cdi": before_cdi, "after_cdi": after_cdi,
        "delta_cdi": after_cdi - before_cdi,
        "people_newly": people_newly, "catch_pop": catch_pop,
        "marginal": people_newly - float(POP[(dmin_prev <= 2.0) & ~BEFORE_COV].sum()),
        "sev_b": int((before_cdi >= 50).sum()), "sev_a": int((after_cdi >= 50).sum()),
        "mean_cdi_change": float(after_cdi[m5].mean() - before_cdi[m5].mean()) if m5.any() else 0.0,
        "pct_gap_closed": (100.0 * people_newly / catch_pop) if catch_pop > 0 else 0.0,
        "equity_pct": (100.0 * POP[newly & BELOW_MEDIAN].sum() / people_newly) if people_newly > 0 else 0.0,
        "coverage_kv": 100.0 * POP[cov_after].sum() / POP_TOTAL,
        "coverage_klang": 100.0 * POP[cov_after & IS_KLANG].sum() / POP_KLANG,
        "n_sites": len(coords),
    }


@st.cache_data(show_spinner=False)
def recommended_benchmarks(cost_per_station: int) -> dict:
    """Mean per-site cost-per-person and catchment-gap-closed across the 20
    recommended sites, so a user can judge whether their own placement is good."""
    costs, gaps = [], []
    for r in rec.itertuples():
        d = _hav(float(r.lat), float(r.lon))
        cat = d <= 2.0
        newly_pop = float(POP[cat & ~BEFORE_COV].sum())
        catch = float(POP[cat].sum())
        if newly_pop > 0:
            costs.append(cost_per_station / newly_pop)
        if catch > 0:
            gaps.append(100.0 * newly_pop / catch)
    return {"cost": float(np.mean(costs)) if costs else None,
            "gap": float(np.mean(gaps)) if gaps else None}


def _change_to_rgb(delta: float, max_abs: float) -> list:
    """Sequential ramp for the Change map: no change -> strong improvement.

    Deliberately NOT the 0-100 CDI ramp. A real improvement here is 2-3 CDI
    points; on a 0-100 scale that is 2% of the range and is invisible, which is
    exactly why this page used to read as 'nothing happened'. Scaling to the
    largest change actually on the map makes the effect legible.
    """
    if max_abs <= 0:
        return [40, 46, 60, 60]
    t = min(1.0, abs(delta) / max_abs) ** 0.65      # gamma lifts small changes
    base_rgb, hot = (32, 38, 52), theme.RECOMMENDED
    rgb = [int(base_rgb[i] + (hot[i] - base_rgb[i]) * t) for i in range(3)]
    return rgb + [int(45 + 195 * t)]


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


# --- preset scenarios. The MAX_PINS cap governs MANUAL placement only; a preset
#     loads its whole set (20 sites) deliberately.
def _load_equity_preset():
    st.session_state.pins = [
        {"lat": float(r.lat), "lon": float(r.lon),
         "label": f"Recommended #{int(r.rank)} · {r.district}"}
        for r in rec.itertuples()]
    st.session_state.mode = "equity_preset"
    st.session_state.presets_run = st.session_state.get("presets_run", set()) | {"equity"}


def _load_market_preset():
    st.session_state.pins = [
        {"lat": float(r.lat), "lon": float(r.lon),
         "label": f"Market #{i} · {r.district}"}
        for i, r in enumerate(MARKET.itertuples(), 1)]
    st.session_state.mode = "market_preset"
    st.session_state.presets_run = st.session_state.get("presets_run", set()) | {"market"}


def _reset_defaults() -> None:
    """Restore the validated baseline configuration the headline figures use."""
    st.session_state["wi_persona"] = "Government"
    st.session_state["wi_w_pop"] = 0.5


# ------------------------------------------------------------------ sidebar controls
with st.sidebar:
    st.markdown("<div class='ctl-title'>View</div>", unsafe_allow_html=True)
    persona = st.segmented_control("Persona", ["Government", "Operator"], default="Government",
                                   label_visibility="collapsed", key="wi_persona") or "Government"
    st.caption("**Government** weights equity · **Operator** ranks pure market demand.")
    st.divider()
    w_pop = st.slider("Population weight", 0.0, 1.0, 0.5, 0.05, key="wi_w_pop",
                      help="Activity weight = 1 − population weight")
    st.caption(f"Demand blend: population {w_pop:.2f} · activity {1 - w_pop:.2f}")
    st.button("Reset to validated defaults", on_click=_reset_defaults,
              use_container_width=True,
              help="Government lens, population 0.50 / activity 0.50")
    st.caption("Headline figures use the Government lens with population 0.50 / "
               "activity 0.50. CDI is scaled against the validated baseline, so "
               "values remain comparable across settings.")
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

    st.markdown("<div class='ctl-title'>Preset scenarios</div>", unsafe_allow_html=True)
    st.button("Load the 20 recommended sites", use_container_width=True,
              on_click=_load_equity_preset,
              help="Equity-weighted greedy maximal-coverage plan (stage 07)")
    if len(MARKET):
        st.button("Load the market's next 20", use_container_width=True,
                  on_click=_load_market_preset,
                  help="Predicted commercial build-out (stage 11) — a forecast of "
                       "operator behaviour, NOT a recommendation")
        st.caption("Presets load all 20 sites; the 5-station cap applies to manual "
                   "placement only.")
    else:
        st.caption("Presets: run `python pipeline/11_operator_model.py` to enable "
                   "the market-forecast comparison.")
    st.divider()

    cost_per_station = st.number_input("Cost per station (RM)", min_value=0, value=300_000, step=50_000,
                                       key="wi_cost")
    st.divider()

    st.markdown("<div class='ctl-title'>Maps</div>", unsafe_allow_html=True)
    # "Change" is the default: it is the only view on which a 2-3 point CDI
    # improvement is actually visible.
    map_layout = st.segmented_control("Map layout", ["Change", "Side by side", "Single"],
                                      default="Change", label_visibility="collapsed",
                                      key="wi_layout") or "Change"
    map_view = "After"
    if map_layout == "Single":
        map_view = st.segmented_control("Map view", ["After", "Before"], default="After",
                                        key="wi_view") or "After"

equity_on = persona == "Government"
pins = st.session_state.pins

# ------------------------------------------------------------------ header
st.markdown(
    "<div class='page-title'>What-If Simulator</div>"
    "<div class='page-sub'>Place hypothetical stations — up to 5 by hand, or load a 20-site preset — "
    "and watch coverage, severity, CDI, cost and equity recompute live from stored components</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='leg-wrap' style='max-width:360px'><div class='leg-label'>Charging Desert Index</div>"
    "<div class='leg-bar'></div><div class='leg-scale'><span>0</span><span>50</span><span>100</span></div></div>",
    unsafe_allow_html=True,
)
st.markdown("<hr>", unsafe_allow_html=True)

if not pins:
    st.info("No stations placed yet. Pick a worst-desert hex, click any hex on the map, or load a "
            "preset scenario from the sidebar to see the impact.")
    st.stop()

# ------------------------------------------------------ live recompute (vectorized)
# The SHARED frozen denominator (cdi_scale.json) is applied inside
# compute_scenario(); this page never normalizes against its own frame maximum.
COORDS = tuple((float(p["lat"]), float(p["lon"])) for p in pins)
S = compute_scenario(COORDS, w_pop, equity_on)

before_cdi, after_cdi, delta_cdi = S["before_cdi"], S["after_cdi"], S["delta_cdi"]
people_newly, catch_pop = S["people_newly"], S["catch_pop"]
marginal = S["marginal"]
sev_b, sev_a = S["sev_b"], S["sev_a"]
d_severe = sev_a - sev_b
mean_cdi_change = S["mean_cdi_change"]
pct_gap_closed = S["pct_gap_closed"]
equity_pct = S["equity_pct"]
total_cost = len(pins) * cost_per_station
cost_per_person = (total_cost / people_newly) if people_newly > 0 else None
BENCH = recommended_benchmarks(int(cost_per_station))


def _signed_int(n):
    return f"{n:+d}" if n != 0 else "0"


# ------------------------------------------------------------------ mode label + note
_MODE_LABELS = {
    "optimizer": "Optimizer recommendation",
    "equity_preset": f"Preset · the {len(rec)} recommended sites (equity siting)",
    "market_preset": f"Preset · the market's next {len(MARKET)} (predicted, not recommended)",
}
mode_label = _MODE_LABELS.get(
    st.session_state.mode,
    f"Your picked hex{'es' if len(pins) != 1 else ''} · {len(pins)} of {MAX_PINS}")
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
_gap_ctx = "share of the catchment that gains new coverage"
if BENCH["gap"] is not None:
    _gap_ctx += f" · average across recommended sites {BENCH['gap']:.1f}%"
_cost_ctx = f"{len(pins)} × RM{cost_per_station:,.0f} ÷ people newly covered · indicative"
if BENCH["cost"] is not None:
    _cost_ctx += f" · average across recommended sites RM {BENCH['cost']:,.0f}"

ui.kpi_row([
    {"label": "People newly within 2 km", "value": theme.fmt_int(people_newly),
     "context": "gained public-charging access from these stations"},
    {"label": "Population in 2 km catchment", "value": theme.fmt_int(catch_pop),
     "context": "total reachable market within 2 km"},
    {"label": "Catchment gap closed", "value": theme.fmt_pct(pct_gap_closed),
     "context": _gap_ctx},
    {"label": "Equity · below-median income", "value": theme.fmt_pct(equity_pct),
     "context": "of newly-covered people in below-KV-median-income districts"},
])
st.write("")
ui.kpi_row([
    {"label": "Marginal gain · last station", "value": theme.fmt_int(marginal),
     "context": "people the most-recent pin adds beyond the others"},
    {"label": "Severe hexes (CDI ≥ 50)", "value": _signed_int(d_severe),
     "context": f"{sev_b} → {sev_a} · negative is better"},
    {"label": "Mean CDI change · 5 km", "value": f"{mean_cdi_change:+.1f}",
     "context": "average CDI shift within 5 km · lower is better"},
    {"label": "Cost per person covered", "value": (f"RM {cost_per_person:,.0f}" if cost_per_person else "n/a"),
     "context": _cost_ctx},
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
zoom = 10.5 if len(pins) == 1 else (9.4 if len(pins) <= MAX_PINS else 8.7)
pins_df = pd.DataFrame(pins)


def _dashed_rings(pin_list, radius_km=2.0, dashes=36):
    """2 km catchment drawn as a dashed circle — reads as proposed, not built."""
    rows = []
    for p in pin_list:
        dlat = radius_km / 111.32
        dlon = radius_km / (111.32 * max(0.2, np.cos(np.radians(p["lat"]))))
        for k in range(0, dashes, 2):
            a0, a1 = 2 * np.pi * k / dashes, 2 * np.pi * (k + 1) / dashes
            rows.append({"path": [[p["lon"] + dlon * np.cos(a),
                                   p["lat"] + dlat * np.sin(a)]
                                  for a in (a0, (a0 + a1) / 2, a1)]})
    return pd.DataFrame(rows)


GHOST_RINGS = _dashed_rings(pins)
tooltip = {"html": "{tip}", "style": {"backgroundColor": theme.SURFACE, "color": theme.TEXT,
           "fontSize": "12px", "border": f"1px solid {theme.BORDER}", "borderRadius": "6px",
           "padding": "6px 8px", "maxWidth": "290px", "whiteSpace": "pre-line", "lineHeight": "1.4"}}


def make_deck(values, height_zoom, kind="cdi", ghost=False, max_abs=0.0):
    mdf = base[["h3_index", "district", "pop_est"]].copy()
    if kind == "change":
        mdf["fill_color"] = [_change_to_rgb(v, max_abs) for v in values]
        mdf["tip"] = [f"{d}\nCDI change {v:+.2f} · {p:,.0f} residents"
                      for d, v, p in zip(mdf["district"], values, mdf["pop_est"])]
    else:
        mdf["fill_color"] = [theme.cdi_to_rgb(v) for v in values]
        mdf["tip"] = [f"{d}\nCDI {v:.0f} · {p:,.0f} residents"
                      for d, v, p in zip(mdf["district"], values, mdf["pop_est"])]
    layers = mapping.mask_layer(kv_mask)
    layers.append(pdk.Layer("H3HexagonLayer", id="cdi_hex",
                            data=mdf[["h3_index", "fill_color", "tip"]], get_hexagon="h3_index",
                            get_fill_color="fill_color", pickable=True, auto_highlight=True,
                            stroked=False, extruded=False, opacity=0.85))
    layers += mapping.border_layers(districts_geo, kv_outline)
    if ghost:
        # Proposed, not built: dashed catchment + hollow marker.
        layers.append(pdk.Layer("PathLayer", id="rings_ghost", data=GHOST_RINGS,
                                get_path="path", get_color=theme.ACCENT_RGB + [170],
                                width_min_pixels=1.4, pickable=False,
                                parameters={"depthTest": False}))
        layers.append(pdk.Layer("ScatterplotLayer", id="pins_ghost", data=pins_df,
                                get_position="[lon, lat]", filled=False, stroked=True,
                                get_radius=300, radius_min_pixels=9, radius_max_pixels=15,
                                get_line_color=theme.RECOMMENDED + [235],
                                line_width_min_pixels=2, pickable=False,
                                parameters={"depthTest": False}))
    else:
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


MAX_ABS = float(np.abs(delta_cdi).max())
CHANGE_RANGE = f"0 to −{MAX_ABS:.1f} CDI"

if map_layout == "Change":
    ui.section_header("Change · CDI after − before")
    st.markdown(
        "<div class='leg-wrap' style='max-width:360px'>"
        "<div class='leg-label'>CDI improvement</div>"
        "<div class='leg-bar' style='background:linear-gradient(90deg,#202634,#00FF88)'></div>"
        f"<div class='leg-scale'><span>0 (no change)</span><span>−{MAX_ABS:.1f} (most improved)</span></div>"
        "</div>", unsafe_allow_html=True)
    st.pydeck_chart(make_deck(delta_cdi, zoom, kind="change", max_abs=MAX_ABS),
                    use_container_width=True, height=520,
                    selection_mode="single-object", on_select="rerun", key=MAP_KEY)
    st.caption(f"Scaled to the largest change on this map — **{CHANGE_RANGE}** — not the 0–100 CDI ramp, "
               "on which a change this size would be invisible. Brighter green = bigger drop in desert "
               "severity. Click a hex to add a station.")
elif map_layout == "Side by side":
    cB, cA = st.columns(2, gap="medium")
    with cB:
        ui.section_header("Before")
        st.pydeck_chart(make_deck(before_cdi, zoom - 0.4, ghost=True), use_container_width=True, height=430)
    with cA:
        ui.section_header("After")
        st.pydeck_chart(make_deck(after_cdi, zoom - 0.4), use_container_width=True, height=430,
                        selection_mode="single-object", on_select="rerun", key=MAP_KEY)
    st.caption("Same colour scale and centre on both maps. On **Before** the stations are hollow with a "
               "dashed 2 km ring — they do not exist yet; on **After** they are solid. "
               "Click a hex on the After map to add a station.")
else:
    cdi_arr = after_cdi if map_view == "After" else before_cdi
    st.pydeck_chart(make_deck(cdi_arr, zoom, ghost=(map_view == "Before")),
                    use_container_width=True, height=520,
                    selection_mode="single-object", on_select="rerun", key=MAP_KEY)
    st.caption(f"Showing CDI **{map_view.lower()}** · "
               + ("hollow markers with dashed rings = proposed, not yet built. "
                  if map_view == "Before" else "green pins = your stations · blue rings = 2 km catchments. ")
               + "Click a hex to add a station; toggle the view in the sidebar.")

# ------------------------------------------------------------------ prose callout
_n = len(pins)
_station_word = "station" if _n == 1 else "stations"
_where = pins[0]["label"].split("·")[0].strip() if _n == 1 else "these locations"

_msg = (f"Putting {_n} {_station_word} at {_where} brings "
        f"**{people_newly:,.0f} people** within 2 km of public charging who did not have it before. "
        f"That is **{pct_gap_closed:.1f}%** of everyone living inside the 2 km catchment, and "
        f"**{equity_pct:.1f}%** of the people who gain access live in districts earning below the "
        f"Klang Valley median income.")

if MAX_ABS > 0:
    _msg += (f" Desert severity falls across the surrounding area — the most improved hex drops by "
             f"**{MAX_ABS:.1f} CDI points**, and the average within 5 km falls by "
             f"**{abs(mean_cdi_change):.1f}**.")

if d_severe == 0:
    _msg += (f" The count of severe hexes stays at {sev_b}. That does not mean nothing happened: a hex "
             "only leaves that list when it crosses back under CDI 50, and these hexes start far above "
             "it. The people reached and the severity drop above are the real effect; the severe count "
             "is a coarse threshold that moves last.")
elif d_severe < 0:
    _msg += (f" **{abs(d_severe)}** hex{'es' if abs(d_severe) != 1 else ''} also drop out of severe-desert "
             f"status entirely ({sev_b} → {sev_a}).")

st.success(_msg)

# ------------------------------------------------------------------ scenario comparison
_runs = st.session_state.get("presets_run", set())
if {"equity", "market"} <= _runs and len(MARKET):
    st.write("")
    ui.section_header("Equity siting vs the market's own forecast")
    eq_s = compute_scenario(tuple(zip(rec["lat"].astype(float), rec["lon"].astype(float))),
                            w_pop, equity_on)
    mk_s = compute_scenario(tuple(zip(MARKET["lat"].astype(float), MARKET["lon"].astype(float))),
                            w_pop, equity_on)
    cmp_df = pd.DataFrame({
        "": ["People newly covered", "Coverage · Klang Valley", "Coverage · Klang",
             "Newly covered in below-median districts"],
        "Equity siting (20 sites)": [
            f"{eq_s['people_newly']:,.0f}", f"{eq_s['coverage_kv']:.1f}%",
            f"{eq_s['coverage_klang']:.1f}%", f"{eq_s['equity_pct']:.1f}%"],
        "Market forecast (20 sites)": [
            f"{mk_s['people_newly']:,.0f}", f"{mk_s['coverage_kv']:.1f}%",
            f"{mk_s['coverage_klang']:.1f}%", f"{mk_s['equity_pct']:.1f}%"],
    })
    st.markdown(ui.html_table(cmp_df, num_cols=["Equity siting (20 sites)",
                                                "Market forecast (20 sites)"]),
                unsafe_allow_html=True)
    st.caption("**Equity siting** = the 20 sites this system recommends (greedy maximal coverage, "
               "stage 07). **Market forecast** = the 20 hexes a model trained on where operators have "
               "actually built predicts they will build next (stage 11) — a *prediction of commercial "
               "behaviour, not a recommendation*. Both start from the same "
               f"{100.0 * POP[BEFORE_COV].sum() / POP_TOTAL:.1f}% Klang Valley baseline coverage "
               f"({100.0 * POP[BEFORE_COV & IS_KLANG].sum() / POP_KLANG:.1f}% in Klang).")

st.caption("**Indicative catchment simulation** using the same exp(−distance / 1.5 km) decay as the CDI — "
           "it recomputes coverage and CDI from stored components, not utilization or revenue.")
