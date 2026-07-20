"""FYP Dashboard — entry point. Pages live in app/pages/ (see PLAN.md)."""
import pandas as pd
import streamlit as st

st.set_page_config(page_title="KV EV Charging Intelligence", layout="wide")
st.title("EV Charging Intelligence — Greater Klang Valley")
st.caption("Equity-weighted charging desert analysis, siting and demand forecasting")

@st.cache_data
def load_cdi():
    return pd.read_csv("processed_data/hex_cdi_v1.csv")

hx = load_cdi()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Hexes analyzed", f"{len(hx):,}")
c2.metric("Severe desert hexes (CDI≥50)", int((hx["cdi"] >= 50).sum()))
c3.metric("People in severe zones", f"{hx.loc[hx['cdi']>=50,'pop_est'].sum():,.0f}")
c4.metric("Median nearest charger", f"{hx['nearest_station_km'].median():.1f} km")

st.info("Skeleton stub — pages to be built per PLAN.md. Run from repo root: `streamlit run app/Home.py`")
st.dataframe(hx.nlargest(10, "cdi")[["district", "pop_est", "activity_score",
             "nearest_station_km", "cdi"]].round(1), use_container_width=True)
