"""Cached artifact loaders — the ONLY place the app touches the filesystem.

Architecture rule (CLAUDE.md #1): the app READS files written by pipeline/ into
processed_data/ and never recomputes pipeline logic. Every read here is wrapped
in @st.cache_data so a warm page loads in well under a second (DESIGN.md §8).

Paths resolve relative to the repo root via __file__, so loaders work no matter
what the current working directory is (app/lib -> app -> repo root).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

# app/lib/data.py -> parents[0]=lib, [1]=app, [2]=repo root
DATA_DIR = Path(__file__).resolve().parents[2] / "processed_data"

_BOOL_COLS = ("is_operational", "is_public_facing", "is_free",
              "ports_imputed", "power_known")


def _csv(name: str, **kw) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / name, **kw)


# ------------------------------------------------------------------ core layers
@st.cache_data(show_spinner=False)
def load_cdi() -> pd.DataFrame:
    """Per-hex Charging Desert Index + stored components (pop_n, act_n,
    equity_mult, supply_n, nearest_station_km ...). The app's core layer;
    CDI is re-mixed from these columns for the persona/weight controls."""
    return _csv("hex_cdi_v1.csv")


@st.cache_data(show_spinner=False)
def load_stations() -> pd.DataFrame:
    """Fused EV stations (v2, official-boundary corrected). Coerces the flag
    columns to real booleans so `is_public_facing & is_operational` is safe."""
    df = _csv("ev_stations_kv_clean_v2.csv")
    for c in _BOOL_COLS:
        if c in df.columns and df[c].dtype != bool:
            df[c] = df[c].astype(str).str.strip().str.lower().isin(("true", "1"))
    return df


def public_operational(stations: pd.DataFrame) -> pd.DataFrame:
    """Supply-side subset used by the CDI: public-facing AND operational.
    Cheap filter, not a pipeline step — the single definition, reused everywhere."""
    return stations[stations["is_public_facing"] & stations["is_operational"]]


@st.cache_data(show_spinner=False)
def load_districts() -> dict:
    """DOSM district polygons as a GeoJSON dict (properties: district_canon,
    state_canon; geometry MultiPolygon) — for pydeck outlines / district filter."""
    with open(DATA_DIR / "kv_districts_dosm.geojson", "r", encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------ page-2: recommend
@st.cache_data(show_spinner=False)
def load_recommended_sites() -> pd.DataFrame:
    """20 greedy maximal-coverage sites (rank, district, lat, lon, cdi,
    pop_newly_covered, demand_gain, nearest_existing_km ...)."""
    return _csv("recommended_sites_v1.csv")


@st.cache_data(show_spinner=False)
def load_desert_zones() -> pd.DataFrame:
    """DBSCAN-clustered desert zones (zone, hexes, population, district,
    mean_cdi, lat, lon)."""
    return _csv("desert_zones_v1.csv")


# -------------------------------------------------------------- page-3: forecast
@st.cache_data(show_spinner=False)
def load_forecast() -> pd.DataFrame:
    """Monthly KV EV-stock forecast (ds, policy_cap, policy_lo/hi, accel_cap,
    actual). `ds` parsed to datetime for plotting."""
    return _csv("forecast_kv_monthly.csv", parse_dates=["ds"])


@st.cache_data(show_spinner=False)
def load_charger_gap() -> pd.DataFrame:
    """2030 district port gap (district, weight_population, ev_2030_policy/accel,
    required_ports_2030, current_ports, port_gap)."""
    return _csv("charger_gap_2030.csv")


# ------------------------------------------------------------- page-5: validation
@st.cache_data(show_spinner=False)
def load_validation() -> pd.DataFrame:
    """Holdout recall trials (seed, predictor, top_k_pct, recall)."""
    return _csv("validation_holdout_results.csv")


@st.cache_data(show_spinner=False)
def load_coverage_curve() -> pd.DataFrame:
    """Coverage vs radius (radius_km, kv_pct, klang_pct, lumpur_pct)."""
    return _csv("coverage_radius_curve.csv")


@st.cache_data(show_spinner=False)
def load_capacity() -> pd.DataFrame:
    """Per-district capacity adequacy (district, public_ports, population,
    people_per_port)."""
    return _csv("capacity_adequacy.csv")


@st.cache_data(show_spinner=False)
def load_operator_crosscheck() -> pd.DataFrame:
    """Operator cross-check template/results (may have empty count columns until
    the user fills JomCharge/Gentari/ChargEV counts)."""
    return _csv("operator_crosscheck_template.csv")
