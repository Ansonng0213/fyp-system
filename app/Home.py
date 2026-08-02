"""Cover / landing screen — the entry point of the app.

The first screen a visitor sees before the dashboard: project title, author,
a one-line hook, three headline stats (computed live from processed_data/ so they
never drift), and a single call to action. Minimal and striking (DESIGN.md dark
style). The Executive Overview and the five tool pages live in app/pages/ and are
reached via the "Enter Dashboard" button (and the sidebar).
"""
import base64
import os

import streamlit as st

from lib import data, theme

st.set_page_config(page_title="Charging Desert Index — Greater Klang Valley",
                   layout="wide", initial_sidebar_state="collapsed")
theme.inject_base_css()

# Official FYP title (FYP_PROJECT_MEMORY.md). "Charging Desert Index" is the
# system's name, used as the eyebrow brand above the registered title.
TITLE = ("Developing Geospatial Optimization and Demand Forecasting Model "
         "for Equitable EV Charging Infrastructure")


@st.cache_data(show_spinner=False)
def cover_stats() -> tuple[float, float, float]:
    """The project's punchline in three numbers, read from the artifacts."""
    hx = data.load_cdi()
    stn = data.load_stations()
    cap = data.load_capacity()
    gap = data.load_charger_gap()
    severe = float(hx.loc[hx["cdi"] >= 50, "pop_est"].sum())
    counts = data.public_operational(stn).groupby("district").size()
    per100k = (counts / cap.set_index("district")["population"] * 1e5).dropna()
    disparity = float(per100k.max() / per100k.min())
    port_gap = float(gap["port_gap"].sum())
    return severe, disparity, port_gap


def _hero_data_uri() -> str | None:
    """cdi_map.png as an inline data URI (dimmed hero) — None if not built yet."""
    p = os.path.join(str(data.DATA_DIR), "cdi_map.png")
    if not os.path.exists(p):
        return None
    with open(p, "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")


try:
    severe, disparity, port_gap = cover_stats()
    stats_html = (
        f"<div class='cover-stat'><div class='cover-stat-v'>{theme.fmt_int(severe)}</div>"
        "<div class='cover-stat-l'>people in severe charging deserts</div></div>"
        f"<div class='cover-stat'><div class='cover-stat-v'>{theme.fmt_mult(disparity)}</div>"
        "<div class='cover-stat-l'>access gap between best- and worst-served districts</div></div>"
        f"<div class='cover-stat'><div class='cover-stat-v'>~{theme.fmt_int(port_gap)} ports</div>"
        "<div class='cover-stat-l'>public charge points needed by 2030</div></div>"
    )
except Exception:  # artifacts missing → cover still renders, just without the strip
    stats_html = ""

hero = _hero_data_uri()
hero_html = (f"<div class='cover-hero'><img src='{hero}' alt='Charging Desert Index map'/></div>"
             if hero else "")

st.markdown(
    "<div class='cover'>"
    "<div class='cover-eyebrow'>Charging Desert Index</div>"
    f"<div class='cover-title'>{TITLE}</div>"
    "<div class='cover-author'>Ng Cheng Xin · TP071136 · Asia Pacific University · "
    "Final Year Project 2026</div>"
    "<div class='cover-hook'>Where do the next EV chargers belong — and who is being left "
    "behind? A data-driven answer for the Greater Klang Valley.</div>"
    f"<div class='cover-stats'>{stats_html}</div>"
    "</div>",
    unsafe_allow_html=True,
)

# the single call to action — st.page_link routes reliably (styled as a button)
st.page_link("pages/1_Overview.py", label="Enter Dashboard  →")

st.markdown(
    "<div class='cover'>"
    f"{hero_html}"
    "<div class='cover-foot'>Data sources: JPJ · DOSM · OpenStreetMap · OpenChargeMap · "
    "Google Places &nbsp;·&nbsp; Supervised by Ms. Tan Li June</div>"
    "</div>",
    unsafe_allow_html=True,
)
