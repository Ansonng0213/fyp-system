# ============================================================
# FYP2 — DEMAND FORECAST PIPELINE  (Problem 12)
#
#   1. FORECAST KV monthly EV registrations to Dec 2030.
#      Primary: Prophet LOGISTIC growth — the cap comes from
#      POLICY, not curve-fitting: LCMB targets xEV = 15% of TIV
#      by 2030. TIV ~800k/yr national -> 15% -> 120k EV/yr
#      -> x 62.9% KV share / 12 -> cap ~6,290/month (central).
#      Accelerated scenario: 30% TIV -> cap ~12,580/month.
#      Comparison: ARIMA(1,1,1) on log-series (IR deliverable).
#   2. BACKTEST: train <=Dec 2024, test Jan-Dec 2025, report MAPE.
#      2025 doubled 2024 — a deliberately hard test, reported honestly.
#   3. FLOW -> STOCK: cumulative registrations = EVs on the road
#      (scrappage ~0 for a <6-yr-old fleet; documented assumption).
#   4. CHARGER GAP 2030: stock / EVs-per-port (10/15/20 band),
#      allocated to districts by population weights ->
#      required vs current ports = THE gap table.
#
# Data note: the Dec-2025 spike (~8.1k national) reflects the
# CBU import-duty exemption deadline pull-forward; treated as a
# one-off month, discussed in interpretation.
#
# Inputs : processed_data/jpj_kv_monthly_v2.csv
#          processed_data/district_allocation_weights_v2.csv
#          processed_data/ev_stations_kv_clean_v2.csv
# Outputs: processed_data/forecast_kv_monthly.csv
#          processed_data/charger_gap_2030.csv
#          processed_data/forecast_chart.png
# ============================================================

import os
import json
import logging
import numpy as np
import pandas as pd

logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

OUT_DIR = "processed_data"
TIV_NATIONAL = 800_000          # ~annual national vehicle market

# KV_SHARE is READ from the stage-03 derivation, never hardcoded, so a fresh
# data pull cannot silently desynchronise this constant from the audit trail.
#
# It is rounded to 3 dp, which is what this figure has always been: the
# derivation records 0.6286 and every published result was produced with 0.629.
# Using the unrounded value would move CAP_POLICY from 6,290.0 to 6,286.0/month
# and shift the 2030 forecast, the port requirement and the district gaps --
# i.e. it would change numbers already in the report. If you ever WANT the
# unrounded value, drop the round() deliberately and regenerate the downstream
# figures, don't let it happen as a side effect of this refactor.
_KV_SHARE_ROUND_DP = 3
with open(os.path.join(OUT_DIR, "kv_share_derivation.json"), encoding="utf-8") as _fh:
    _KV_SHARE_RAW = float(json.load(_fh)["kv_share_central_data_driven"])
KV_SHARE = round(_KV_SHARE_RAW, _KV_SHARE_ROUND_DP)     # data-driven (P3)
if abs(_KV_SHARE_RAW - KV_SHARE) > 0.5 * 10 ** -_KV_SHARE_ROUND_DP:
    raise SystemExit(
        f"KV share in kv_share_derivation.json ({_KV_SHARE_RAW}) no longer rounds "
        f"to the published {KV_SHARE}. Regenerate the forecast deliberately.")
print(f"KV share: {_KV_SHARE_RAW} from kv_share_derivation.json "
      f"-> {KV_SHARE} used (published value)")
CAP_POLICY = TIV_NATIONAL * 0.15 * KV_SHARE / 12     # 15% xEV target
CAP_ACCEL  = TIV_NATIONAL * 0.30 * KV_SHARE / 12     # accelerated scenario
HORIZON_END = "2030-12-01"
EV_PER_PORT = [10, 15, 20]      # planning band; 15 = central

# ------------------------------------------------------------
# STEP 1 — Load series
# ------------------------------------------------------------
print("=" * 60)
print("STEP 1 — Loading KV demand series")
print("=" * 60)

kv = pd.read_csv(os.path.join(OUT_DIR, "jpj_kv_monthly_v2.csv"), parse_dates=["month"])
df = kv[["month", "kv_central"]].rename(columns={"month": "ds", "kv_central": "y"})
print(f"  Months: {len(df)} ({df['ds'].min():%Y-%m} -> {df['ds'].max():%Y-%m}, 2026 partial)")
print(f"  Policy cap (15% TIV): {CAP_POLICY:,.0f}/month | accelerated (30%): {CAP_ACCEL:,.0f}/month")
print(f"  Latest 3 months avg: {df['y'].tail(3).mean():,.0f}/month")

# ------------------------------------------------------------
# STEP 2 — Backtest: train <=2024, test 2025
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 2 — Backtest (train <=Dec 2024, test Jan-Dec 2025)")
print("=" * 60)

from prophet import Prophet
from statsmodels.tsa.arima.model import ARIMA

train = df[df["ds"] <= "2024-12-01"].copy()
test = df[(df["ds"] >= "2025-01-01") & (df["ds"] <= "2025-12-01")].copy()

def fit_prophet(data, cap, periods, growth="logistic"):
    d = data.copy()
    d["cap"], d["floor"] = cap, 0.0
    m = Prophet(growth=growth, yearly_seasonality=True,
                weekly_seasonality=False, daily_seasonality=False)
    m.fit(d)
    fut = m.make_future_dataframe(periods=periods, freq="MS")
    fut["cap"], fut["floor"] = cap, 0.0
    return m, m.predict(fut)

def mape(actual, pred):
    return float(np.mean(np.abs((actual - pred) / actual)) * 100)

results = {}

_, fc = fit_prophet(train, CAP_POLICY, 12)
pred = fc.set_index("ds").loc[test["ds"], "yhat"].to_numpy()
results["Prophet logistic (policy cap)"] = mape(test["y"].to_numpy(), np.maximum(pred, 0))

_, fc_lin = fit_prophet(train, CAP_POLICY, 12, growth="linear")
pred_lin = fc_lin.set_index("ds").loc[test["ds"], "yhat"].to_numpy()
results["Prophet linear (no cap)"] = mape(test["y"].to_numpy(), np.maximum(pred_lin, 0))

ar = ARIMA(np.log1p(train["y"]), order=(1, 1, 1)).fit()
pred_ar = np.expm1(ar.forecast(steps=12).to_numpy())
results["ARIMA(1,1,1) on log"] = mape(test["y"].to_numpy(), pred_ar)

print("  MAPE on held-out 2025 (a hard test: 2025 doubled 2024):")
for k, v in sorted(results.items(), key=lambda x: x[1]):
    print(f"    {k:32s}: {v:5.1f}%")

# ------------------------------------------------------------
# STEP 3 — Full-data forecast to Dec 2030 (both cap scenarios)
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 3 — Forecast to Dec 2030")
print("=" * 60)

n_ahead = (2030 - df["ds"].max().year) * 12 + (12 - df["ds"].max().month)
_, fc_pol = fit_prophet(df, CAP_POLICY, n_ahead)
_, fc_acc = fit_prophet(df, CAP_ACCEL, n_ahead)

out = fc_pol[["ds", "yhat", "yhat_lower", "yhat_upper"]].rename(
    columns={"yhat": "policy_cap", "yhat_lower": "policy_lo", "yhat_upper": "policy_hi"})
out["accel_cap"] = fc_acc["yhat"]
out = out.merge(df, on="ds", how="left").rename(columns={"y": "actual"})
for c in ["policy_cap", "policy_lo", "policy_hi", "accel_cap"]:
    out[c] = out[c].clip(lower=0)
out.to_csv(os.path.join(OUT_DIR, "forecast_kv_monthly.csv"), index=False)

ann = (out.assign(year=out["ds"].dt.year)
       .groupby("year")[["policy_cap", "accel_cap"]].sum().round(0).astype(int))
print("  Forecast annual KV registrations (policy vs accelerated cap):")
print(ann.loc[2026:2030].to_string())

# ------------------------------------------------------------
# STEP 4 — Flow -> stock -> charger gap 2030
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 4 — EV stock and 2030 charger gap")
print("=" * 60)

hist_stock = df["y"].sum()
fut = out[out["actual"].isna()]
stock_2030_pol = hist_stock + fut["policy_cap"].sum()
stock_2030_acc = hist_stock + fut["accel_cap"].sum()
print(f"  KV EV stock today (cumulative): {hist_stock:,.0f}")
print(f"  KV EV stock end-2030 — policy: {stock_2030_pol:,.0f} | accelerated: {stock_2030_acc:,.0f}")

st = pd.read_csv(os.path.join(OUT_DIR, "ev_stations_kv_clean_v2.csv"))
pub = st[st["is_public_facing"] & st["is_operational"]]
cur_ports = pub.groupby("district")["total_ports"].sum()

w = pd.read_csv(os.path.join(OUT_DIR, "district_allocation_weights_v2.csv"))
gap = w[["district", "weight_population"]].copy()
for label, stock in [("policy", stock_2030_pol), ("accel", stock_2030_acc)]:
    gap[f"ev_2030_{label}"] = (gap["weight_population"] * stock).round(0).astype(int)
gap["required_ports_2030"] = (gap["ev_2030_policy"] / 15).round(0).astype(int)  # central ratio
gap = gap.merge(cur_ports.rename("current_ports"), left_on="district",
                right_index=True, how="left").fillna({"current_ports": 0})
gap["current_ports"] = gap["current_ports"].astype(int)
gap["port_gap"] = gap["required_ports_2030"] - gap["current_ports"]
gap = gap.sort_values("port_gap", ascending=False)

print(f"\n  CHARGER GAP TABLE (policy scenario, 15 EVs/port, population allocation):")
print(gap[["district", "ev_2030_policy", "required_ports_2030",
           "current_ports", "port_gap"]].to_string(index=False))

tot_req = gap["required_ports_2030"].sum()
print(f"\n  KV total required 2030: {tot_req:,} ports | counted today: {int(gap['current_ports'].sum())}"
      f" | gap: {int(gap['port_gap'].sum()):,}")
print(f"  Sensitivity band (10-20 EVs/port): "
      f"{stock_2030_pol/20:,.0f} - {stock_2030_pol/10:,.0f} ports required")
print(f"  Undercount robustness: even if true current ports are 2x counted "
      f"({int(2*gap['current_ports'].sum())}), the gap remains "
      f"{int(tot_req - 2*gap['current_ports'].sum()):,} ports")
gap.to_csv(os.path.join(OUT_DIR, "charger_gap_2030.csv"), index=False)

# ------------------------------------------------------------
# STEP 5 — Chart
# ------------------------------------------------------------
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(11, 8.5),
                             gridspec_kw={"height_ratios": [3, 2]})
    ax = axes[0]
    ax.plot(df["ds"], df["y"], color="#333", lw=1.6, label="Actual (v2 KV series)")
    f = out[out["ds"] > df["ds"].max()]
    ax.fill_between(f["ds"], f["policy_lo"], f["policy_hi"], color="#1f77b4", alpha=0.15)
    ax.plot(f["ds"], f["policy_cap"], color="#1f77b4", lw=2.2,
            label="Forecast — policy cap (15% TIV)")
    ax.plot(f["ds"], f["accel_cap"], color="#d62728", lw=1.6, ls="--",
            label="Forecast — accelerated (30% TIV)")
    ax.axhline(CAP_POLICY, color="#1f77b4", lw=0.8, ls=":")
    ax.axhline(CAP_ACCEL, color="#d62728", lw=0.8, ls=":")
    ax.set_title("KV Monthly EV Registrations — history and logistic forecast to 2030")
    ax.set_ylabel("Registrations / month")
    ax.legend(frameon=False, fontsize=9)

    ax2 = axes[1]
    full = pd.concat([df.rename(columns={"y": "policy_cap"})[["ds", "policy_cap"]]
                      .assign(accel_cap=lambda d: d["policy_cap"]), f[["ds", "policy_cap", "accel_cap"]]])
    ax2.plot(full["ds"], full["policy_cap"].cumsum(), color="#1f77b4", lw=2.2,
             label="EV stock — policy")
    ax2.plot(full["ds"], full["accel_cap"].cumsum(), color="#d62728", lw=1.6, ls="--",
             label="EV stock — accelerated")
    ax2.axvline(df["ds"].max(), color="#888", lw=0.8, ls=":")
    ax2.set_title("Cumulative KV EV stock (drives charger requirement)")
    ax2.set_ylabel("EVs on the road")
    ax2.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "forecast_chart.png"), dpi=150)
    print(f"\n  Chart saved -> forecast_chart.png")
except ImportError:
    pass

print("  Saved -> forecast_kv_monthly.csv, charger_gap_2030.csv")
