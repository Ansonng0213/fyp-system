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
def load_operator_scores() -> pd.DataFrame:
    """Per-hex out-of-fold probability that a hex holds a public charger, from
    pipeline/11_operator_model.py (DIAGNOSTIC — a model of where the market
    builds, never a recommendation).

    Note for callers: operator_market_forecast.csv is a DISTRICT-level summary
    and carries no coordinates, so it cannot yield individual sites. This
    per-hex file is the only artifact that can. Returns an empty frame if
    stage 11 has not been run, so the app degrades instead of crashing.
    """
    path = DATA_DIR / "operator_model_scores.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def load_operator_coefficients() -> pd.DataFrame:
    """Full standardised logistic coefficients + SHAP ranks + spatial-block
    bootstrap CIs, from pipeline/11b_operator_coefficients.py."""
    return _csv("operator_coefficients_full.csv")


@st.cache_data(show_spinner=False)
def load_operator_model_comparison() -> pd.DataFrame:
    """Ten model builds (5 algorithms x base/tuned) under both CV schemes."""
    return _csv("operator_model_comparison.csv")


@st.cache_data(show_spinner=False)
def load_operator_ablation() -> pd.DataFrame:
    """Feature-group ablation A-H, all rows including the engineered sets."""
    return _csv("operator_feature_ablation.csv")


@st.cache_data(show_spinner=False)
def load_operator_market_forecast() -> pd.DataFrame:
    """District breakdown of the predicted next-20 build-out, 10-seed
    mean/std. DIAGNOSTIC -- a forecast of commercial behaviour."""
    return _csv("operator_market_forecast.csv")


@st.cache_data(show_spinner=False)
def load_operator_income_specs() -> pd.DataFrame:
    """The three income specifications and their bootstrap CIs (stage 11)."""
    return _csv("operator_income_specifications.csv")


@st.cache_data(show_spinner=False)
def load_operator_robustness() -> pd.DataFrame:
    """Poisson port-count model and the H3 res-7 rerun (stage 11)."""
    return _csv("operator_robustness.csv")


@st.cache_data(show_spinner=False)
def load_forecast_comparison() -> pd.DataFrame:
    """Rolling-origin model comparison from pipeline/12_forecast_comparison.py."""
    return _csv("forecast_model_comparison.csv")


@st.cache_data(show_spinner=False)
def load_forecast_2030_scenarios() -> pd.DataFrame:
    """Per-model 2030 endpoint and plausibility verdict (stage 12)."""
    return _csv("forecast_2030_scenarios.csv")


@st.cache_data(show_spinner=False)
def load_cdi_scale() -> float:
    """The frozen CDI denominator written by pipeline/06_build_cdi.py.

    CDI = 100 * (demand_pressure * supply_gap) / cdi_scale. Every lens and
    weight setting divides by this ONE number, so a CDI of 60 means the same
    absolute thing in the Government lens, the Operator lens and at any slider
    position. Normalizing each configuration against its own maximum (what the
    app used to do) made the Operator lens look like it had twice as many
    deserts, purely because dropping the equity multiplier shrinks the maximum.

    Falls back to the baseline value if the artifact is missing, so an old
    checkout still renders rather than crashing.
    """
    path = DATA_DIR / "cdi_scale.json"
    if not path.exists():
        return 1.1370670015477882
    with open(path, "r", encoding="utf-8") as fh:
        return float(json.load(fh)["cdi_scale"])


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


@st.cache_data(show_spinner=False)
def load_kv_outline() -> dict | None:
    """Dissolved outer KV boundary (single feature) for the thin boundary line.
    Produced by pipeline/make_kv_outline.py; returns None if not generated yet."""
    path = DATA_DIR / "kv_outline.geojson"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


@st.cache_data(show_spinner=False)
def load_kv_mask() -> dict | None:
    """Big box with the KV outline cut out (a hole), for the dim-outside overlay
    that makes the study area pop. Produced by pipeline/make_kv_outline.py."""
    path = DATA_DIR / "kv_mask.geojson"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as fh:
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
