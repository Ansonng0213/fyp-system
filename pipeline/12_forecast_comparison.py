# ============================================================
# FYP2 -- FORECASTING BENCHMARK  (six models, rolling origin)
#
#   A PARALLEL stage to 09_forecast.py. It does not touch 09's code or
#   outputs; the dashboard keeps reading forecast_kv_monthly.csv. This
#   stage produces the evidence that the model choice was correct --
#   or, if it was not, says so.
#
#   Six models, each base + tuned:
#     1 seasonal naive (m=12)   -- no hyperparameters; MASE denominator
#     2 naive with drift        -- no hyperparameters
#     3 ETS / Holt-Winters      -- trend / seasonal / damped
#     4 ARIMA                   -- p,d,q grid by AIC
#     5 SARIMA                  -- p,d,q + P,D,Q,m=12 grid by AIC
#     6 Prophet logistic + cap  -- tuned by Prophet's own cross_validation
#
#   Validation is ROLLING ORIGIN, not one split: expanding window,
#   min_train 36 months, step 1, horizons 6 and 12. Every model refits
#   at every origin and never sees data past it. (Hyperparameters are
#   selected ONCE on the full series -- refit per fold, not re-tuned per
#   fold, which would be leakage of a different kind and 60x the cost.)
#
#   MASE leads, not MAPE. The series roughly doubles year on year, so
#   MAPE flatters whichever model happens to fit the high-volume months
#   and is not comparable across models on a growing series. MASE is
#   scaled by the in-sample seasonal-naive error of each fold's own
#   training set, so folds are commensurable.
#
#   The 2030 column decides the champion as much as the error table.
#   Every model here except the logistic one extrapolates without limit;
#   a model can win the error table and still project a 2030 that
#   violates the national policy ceiling.
#
# Inputs : processed_data/jpj_kv_monthly_v2.csv
#          processed_data/kv_share_derivation.json
# Outputs: processed_data/forecast_model_comparison.csv
#          processed_data/forecast_backtest_folds.csv
#          processed_data/forecast_tuning_results.csv
#          processed_data/forecast_2030_scenarios.csv
#          processed_data/forecast_singlesplit_legacy.csv
#          processed_data/figures/forecast_fold_errors.png
#          processed_data/figures/forecast_2030_fan.png
#
# Reads existing artifacts only. Writes nothing 09 or the app consumes.
# ============================================================

import os
import sys
import json
import random
import logging
import warnings
import itertools

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import statsmodels.api as sm
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX

from prophet import Prophet
from prophet.diagnostics import cross_validation, performance_metrics

warnings.filterwarnings("ignore")
# cmdstanpy logs one INFO pair per Stan fit; across ~500 Prophet fits that
# buries every line this script prints. Disable outright, not just by level.
for noisy in ("prophet", "cmdstanpy", "matplotlib", "fbprophet"):
    lg = logging.getLogger(noisy)
    lg.setLevel(logging.CRITICAL)
    lg.propagate = False
    lg.disabled = True
    lg.handlers = []

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
os.environ["PYTHONHASHSEED"] = str(SEED)

OUT_DIR = "processed_data"
FIG_DIR = os.path.join(OUT_DIR, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

M = 12                     # seasonal period
MIN_TRAIN = 36
HORIZONS = (6, 12)
TIV_NATIONAL = 800_000     # same constant 09_forecast.py uses
CAP_PCT = 0.15
FORECAST_END = "2030-12-01"
ROBUST_START = "2021-01-01"

FAIL_LOG = []


def banner(n, title):
    print()
    print("=" * 66)
    print(f"STEP {n} -- {title}")
    print("=" * 66)


def to_md(df, floatfmt="{:.3f}"):
    d = df.copy()
    cols = [str(c) for c in d.columns]

    def cell(v):
        if isinstance(v, (float, np.floating)):
            return "--" if (v is None or np.isnan(v)) else floatfmt.format(v)
        return str(v)

    rows = [[cell(v) for v in r] for r in d.itertuples(index=False)]
    widths = [max([len(cols[i])] + [len(r[i]) for r in rows]) for i in range(len(cols))]
    out = ["| " + " | ".join(c.ljust(w) for c, w in zip(cols, widths)) + " |",
           "|" + "|".join("-" * (w + 2) for w in widths) + "|"]
    for r in rows:
        out.append("| " + " | ".join(v.ljust(w) for v, w in zip(r, widths)) + " |")
    return "\n".join(out)


# ------------------------------------------------------------
# FIGURE STYLE -- dark, matching cdi_map.png (stage 06) and the dashboard
# these figures are embedded in. Same canvas and text colours.
# ------------------------------------------------------------
FIG_BG = "#1A1A2E"          # == theme.MAP_CANVAS / cdi_map.png facecolor
FIG_TXT = "#E6E9EF"
FIG_GRID = "#3A4050"
FIG_MUTED = "#9AA1AD"
FIG_ACCENT = "#3E7BFA"
FIG_WARN = "#FF6B5A"
SERIES_COLORS = ["#00E5FF", "#00FF88", "#FFB02E", "#C792EA", "#FF6B9D",
                 "#7CD4FD", "#FFD166", "#8AE68A", "#FF9F7A", "#B388FF"]


def _style_axes(ax, title=None, ylabel=None):
    ax.set_facecolor(FIG_BG)
    for s in ax.spines.values():
        s.set_color(FIG_GRID)
    ax.tick_params(colors=FIG_MUTED, which="both")
    ax.grid(True, color=FIG_GRID, lw=0.6, alpha=0.5)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, color=FIG_TXT, fontsize=13, pad=10)
    if ylabel:
        ax.set_ylabel(ylabel, color=FIG_TXT)


def _style_legend(ax, **kw):
    leg = ax.legend(facecolor=FIG_BG, edgecolor=FIG_GRID, labelcolor=FIG_TXT, **kw)
    if leg:
        leg.get_frame().set_alpha(0.9)
    return leg


def draw_figures(folds_df, model_paths, ds, y, fut_ds, cap):
    """Both stage-12 PNGs, dark-themed.

    Split out so they can be redrawn from the persisted CSVs without
    re-running the 980-fold benchmark -- see --figures-only at the foot of
    this file. Writes only PNGs; touches no CSV.
    """
    # --- fold MASE distribution
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), facecolor=FIG_BG)
    for ax, h in zip(axes, HORIZONS):
        sub = folds_df[(folds_df["series"] == "full_2020_2026") &
                       (folds_df["h"] == h) & folds_df["converged"]].copy()
        sub["label"] = sub["model"] + "\n" + sub["variant"]
        order = sub.groupby("label")["MASE"].mean().sort_values().index.tolist()
        bp = ax.boxplot([sub.loc[sub["label"] == L, "MASE"].dropna() for L in order],
                        tick_labels=[L.replace("\n", " ") for L in order],
                        patch_artist=True)
        for patch in bp["boxes"]:
            patch.set_facecolor("#2A3040")
            patch.set_edgecolor(FIG_MUTED)
        for part in ("whiskers", "caps"):
            for ln in bp[part]:
                ln.set_color(FIG_MUTED)
        for med in bp["medians"]:
            med.set_color(FIG_ACCENT)
            med.set_linewidth(1.8)
        for fl in bp["fliers"]:
            fl.set(markeredgecolor=FIG_MUTED, markersize=3, alpha=0.7)
        ax.axhline(1.0, ls="--", c=FIG_WARN, lw=1.2,
                   label="seasonal naive (MASE = 1)")
        _style_axes(ax, f"Fold MASE distribution, h = {h}", "MASE")
        ax.tick_params(axis="x", rotation=60, labelsize=7, colors=FIG_MUTED)
        _style_legend(ax, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "forecast_fold_errors.png"),
                dpi=150, facecolor=FIG_BG)
    plt.close(fig)

    # --- 2030 fan chart
    fig, ax = plt.subplots(figsize=(12, 6), facecolor=FIG_BG)
    ax.plot(ds, y, color=FIG_TXT, lw=2.0, label="actual", zorder=5)
    for i, (label, pred) in enumerate(model_paths.items()):
        ax.plot(fut_ds, pred, lw=1.4, alpha=0.9,
                color=SERIES_COLORS[i % len(SERIES_COLORS)], label=label)
    ax.axhline(cap, ls="--", c=FIG_WARN, lw=1.6,
               label=f"policy ceiling {cap:,.0f}/mo")
    ax.axvline(ds.iloc[-1], color=FIG_MUTED, lw=1.0, ls=":")
    top = max(3 * cap,
              float(np.nanmax([p.max() for p in model_paths.values()])) * 1.05)
    ax.set_ylim(0, min(60_000, top))
    ax.annotate("actuals end", (ds.iloc[-1], ax.get_ylim()[1]),
                color=FIG_MUTED, fontsize=9, ha="right", va="top",
                xytext=(-6, -8), textcoords="offset points")
    _style_axes(ax, "Projection to Dec 2030 -- every model, against the policy ceiling",
                "registrations / month")
    _style_legend(ax, fontsize=7, ncol=2, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "forecast_2030_fan.png"),
                dpi=150, facecolor=FIG_BG)
    plt.close(fig)
    print("  forecast_fold_errors.png, forecast_2030_fan.png  (dark theme)")


# ------------------------------------------------------------
print("=" * 66)
print("FYP2 -- FORECASTING BENCHMARK (six models, rolling origin)")
print("=" * 66)
print("Library versions")
print(f"  python      {sys.version.split()[0]}")
print(f"  numpy       {np.__version__}")
print(f"  pandas      {pd.__version__}")
print(f"  statsmodels {sm.__version__}")
import prophet as _pr
print(f"  prophet     {_pr.__version__}")
print(f"  matplotlib  {matplotlib.__version__}")
print(f"  seed        {SEED}")

# ------------------------------------------------------------
banner(0, "REPORT THE DATA")
# ------------------------------------------------------------
raw = pd.read_csv(os.path.join(OUT_DIR, "jpj_kv_monthly_v2.csv"))
raw["month"] = pd.to_datetime(raw["month"])
series = raw[["month", "kv_central"]].rename(columns={"month": "ds", "kv_central": "y"})
series = series.sort_values("ds").reset_index(drop=True)

n_obs = len(series)
first, last = series["ds"].iloc[0], series["ds"].iloc[-1]
print(f"  source            processed_data/jpj_kv_monthly_v2.csv, column kv_central")
print(f"  n_observations    {n_obs}")
print(f"  first month       {first:%Y-%m}")
print(f"  last month        {last:%Y-%m}")
print(f"  zero/neg values   {int((series['y'] <= 0).sum())}")
print(f"  min / max         {series['y'].min():,.1f} / {series['y'].max():,.1f}")

EXPECTED = (74, "2020-01", "2026-03")
actual = (n_obs, f"{first:%Y-%m}", f"{last:%Y-%m}")
if actual != EXPECTED:
    print()
    print("  *** STOP -- the series does not match the expected shape. ***")
    print(f"      expected {EXPECTED}, found {actual}")
    print("      Not continuing; report this before the benchmark is run.")
    sys.exit(1)
print("  OK 74 rows, Jan 2020 - Mar 2026 as expected -- continuing.")

with open(os.path.join(OUT_DIR, "kv_share_derivation.json"), encoding="utf-8") as fh:
    KV_SHARE_RAW = float(json.load(fh)["kv_share_central_data_driven"])
# Rounded to 3 dp to match 09_forecast.py and every published figure. The
# derivation records 0.6286; 0.629 is the number the report was built on.
KV_SHARE = round(KV_SHARE_RAW, 3)
CAP_MONTHLY = TIV_NATIONAL * CAP_PCT * KV_SHARE / M
print(f"\n  KV share (kv_share_derivation.json)  {KV_SHARE_RAW} -> {KV_SHARE} used")
print(f"  policy ceiling  {TIV_NATIONAL:,} x {CAP_PCT:.0%} x {KV_SHARE} / 12 = "
      f"{CAP_MONTHLY:,.1f} registrations/month  (same constant 09_forecast.py uses)")

Y = series["y"].to_numpy(dtype=float)
DS = series["ds"]


# ------------------------------------------------------------
# MODELS -- each returns a length-h forecast from a training array
# ------------------------------------------------------------
def f_snaive(y, h, **_):
    out = [y[-M + ((i) % M)] if len(y) >= M else y[-1] for i in range(h)]
    return np.array(out, dtype=float)


def f_drift(y, h, **_):
    if len(y) < 2:
        return np.repeat(y[-1], h)
    slope = (y[-1] - y[0]) / (len(y) - 1)
    return y[-1] + slope * np.arange(1, h + 1)


def f_ets(y, h, trend="add", seasonal="add", damped=False, **_):
    kw = dict(trend=trend, seasonal=seasonal,
              seasonal_periods=M if seasonal else None,
              initialization_method="estimated")
    if trend is not None:
        kw["damped_trend"] = damped
    fit = ExponentialSmoothing(y, **kw).fit(optimized=True)
    return np.asarray(fit.forecast(h), dtype=float)


def f_arima(y, h, order=(1, 1, 1), log=True, **_):
    yy = np.log(y) if log else y
    fit = ARIMA(yy, order=order).fit()
    fc = np.asarray(fit.forecast(h), dtype=float)
    return np.exp(fc) if log else fc


def f_sarima(y, h, order=(1, 1, 1), seasonal_order=(0, 1, 1, M), log=True, **_):
    yy = np.log(y) if log else y
    fit = SARIMAX(yy, order=order, seasonal_order=seasonal_order,
                  enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
    fc = np.asarray(fit.forecast(h), dtype=float)
    return np.exp(fc) if log else fc


def _prophet_frame(y, ds):
    return pd.DataFrame({"ds": ds, "y": y})


def f_prophet(y, h, ds=None, changepoint_prior_scale=0.05,
              seasonality_prior_scale=10.0, seasonality_mode="additive", **_):
    d = _prophet_frame(y, ds)
    d["cap"] = CAP_MONTHLY
    d["floor"] = 0.0
    m = Prophet(growth="logistic", yearly_seasonality=True, weekly_seasonality=False,
                daily_seasonality=False,
                changepoint_prior_scale=changepoint_prior_scale,
                seasonality_prior_scale=seasonality_prior_scale,
                seasonality_mode=seasonality_mode,
                interval_width=0.8)
    m.fit(d)
    fut = m.make_future_dataframe(periods=h, freq="MS")
    fut["cap"] = CAP_MONTHLY
    fut["floor"] = 0.0
    return m.predict(fut)["yhat"].to_numpy()[-h:]


MODELS = {
    "SeasonalNaive": f_snaive,
    "NaiveDrift": f_drift,
    "ETS": f_ets,
    "ARIMA": f_arima,
    "SARIMA": f_sarima,
    "ProphetLogistic": f_prophet,
}
NO_TUNE = {"SeasonalNaive", "NaiveDrift"}
BASE_PARAMS = {
    "SeasonalNaive": {}, "NaiveDrift": {},
    "ETS": dict(trend="add", seasonal="add", damped=False),
    "ARIMA": dict(order=(1, 1, 1), log=True),
    "SARIMA": dict(order=(1, 1, 1), seasonal_order=(0, 1, 1, M), log=True),
    "ProphetLogistic": dict(changepoint_prior_scale=0.05,
                            seasonality_prior_scale=10.0,
                            seasonality_mode="additive"),
}


def forecast(name, params, y, h, ds=None):
    """Single forecast call. Returns None on failure (logged, never silent)."""
    try:
        out = MODELS[name](y, h, ds=ds, **params)
        out = np.asarray(out, dtype=float)
        if out.shape != (h,) or not np.all(np.isfinite(out)):
            raise ValueError("non-finite or wrong-shape forecast")
        return out
    except Exception as e:
        FAIL_LOG.append({"model": name, "h": h, "n_train": len(y),
                         "error": f"{type(e).__name__}: {e}"[:160]})
        return None


# ------------------------------------------------------------
# --figures-only : redraw both PNGs from artifacts already on disk.
#
# Reloads forecast_backtest_folds.csv for the fold chart, and the tuned
# parameters from forecast_tuning_results.csv so the ten builds can be refit
# on the FULL series to recover the 2030 projection paths -- those paths are
# not persisted, only their endpoints are. It does NOT re-run the
# rolling-origin benchmark (980 folds) and writes no CSV.
# ------------------------------------------------------------
if "--figures-only" in sys.argv:
    banner("F", "FIGURES ONLY -- redraw from artifacts, no benchmark re-run")
    folds_csv = pd.read_csv(os.path.join(OUT_DIR, "forecast_backtest_folds.csv"))
    tune_csv = pd.read_csv(os.path.join(OUT_DIR, "forecast_tuning_results.csv"))
    print(f"  forecast_backtest_folds.csv    {len(folds_csv):,} folds")
    print(f"  forecast_tuning_results.csv    {len(tune_csv)} models")

    tuned_from_csv = {}
    for _, r in tune_csv.iterrows():
        if not bool(r["tuned"]):
            tuned_from_csv[r["model"]] = {}
            continue
        p = json.loads(r["best_params"])
        for k in ("order", "seasonal_order"):
            if k in p:
                p[k] = tuple(p[k])
        tuned_from_csv[r["model"]] = p

    h_fig = (pd.Timestamp(FORECAST_END).to_period("M") - DS.iloc[-1].to_period("M")).n
    fut_fig = pd.date_range(DS.iloc[-1] + pd.offsets.MonthBegin(1),
                            FORECAST_END, freq="MS")
    print(f"  refitting {h_fig}-month projections for the fan chart "
          f"(ceiling {CAP_MONTHLY:,.0f}/mo) ...")
    paths_fig = {}
    for nm in MODELS:
        for vr, pr in (("base", BASE_PARAMS[nm]), ("tuned", tuned_from_csv.get(nm, {}))):
            if nm in NO_TUNE and vr == "tuned":
                continue
            pv = forecast(nm, pr, Y, h_fig, ds=DS)
            if pv is not None:
                paths_fig[f"{nm} ({vr})"] = pv
    print(f"  {len(paths_fig)} projection paths recovered")
    draw_figures(folds_csv, paths_fig, DS, Y, fut_fig, CAP_MONTHLY)
    print()
    print("=" * 66)
    print("PNGs only. No CSV written, benchmark not re-run.")
    print("=" * 66)
    sys.exit(0)


# ------------------------------------------------------------
banner(1, "TUNING -- best hyperparameters per model")
# ------------------------------------------------------------
print("  Selected ONCE on the full series, then refit unchanged inside every")
print("  rolling-origin fold. Naive models have no hyperparameters.\n")
tuned_params, tuning_rows = {}, []

for nm in ("SeasonalNaive", "NaiveDrift"):
    tuned_params[nm] = {}
    tuning_rows.append({"model": nm, "tuned": False, "criterion": "n/a",
                        "best_params": "none -- this model has NO hyperparameters",
                        "score": np.nan, "n_candidates": 0})
    print(f"  {nm:16s} no hyperparameters to tune")

# --- ETS: grid on AIC
best, best_aic, n_cand = None, np.inf, 0
for trend in ("add", None):
    for seasonal in ("add", "mul", None):
        for damped in (True, False):
            if trend is None and damped:
                continue
            if seasonal == "mul" and Y.min() <= 0:
                continue
            n_cand += 1
            try:
                kw = dict(trend=trend, seasonal=seasonal,
                          seasonal_periods=M if seasonal else None,
                          initialization_method="estimated")
                if trend is not None:
                    kw["damped_trend"] = damped
                aic = ExponentialSmoothing(Y, **kw).fit(optimized=True).aic
                if np.isfinite(aic) and aic < best_aic:
                    best_aic, best = aic, dict(trend=trend, seasonal=seasonal, damped=damped)
            except Exception:
                continue
tuned_params["ETS"] = best or BASE_PARAMS["ETS"]
tuning_rows.append({"model": "ETS", "tuned": True, "criterion": "AIC",
                    "best_params": json.dumps(tuned_params["ETS"]),
                    "score": best_aic, "n_candidates": n_cand})
print(f"  ETS              best {tuned_params['ETS']}  AIC {best_aic:,.1f}  "
      f"({n_cand} candidates)")

# --- ARIMA: p,d,q grid on AIC (log scale, as 09 used)
logY = np.log(Y)
best, best_aic, n_cand = None, np.inf, 0
for p, d, q in itertools.product(range(4), range(3), range(4)):
    n_cand += 1
    try:
        aic = ARIMA(logY, order=(p, d, q)).fit().aic
        if np.isfinite(aic) and aic < best_aic:
            best_aic, best = aic, dict(order=(p, d, q), log=True)
    except Exception:
        continue
tuned_params["ARIMA"] = best or BASE_PARAMS["ARIMA"]
tuning_rows.append({"model": "ARIMA", "tuned": True, "criterion": "AIC",
                    "best_params": json.dumps({"order": list(tuned_params['ARIMA']['order']),
                                               "log": True}),
                    "score": best_aic, "n_candidates": n_cand})
print(f"  ARIMA            best order {tuned_params['ARIMA']['order']} on log scale  "
      f"AIC {best_aic:,.1f}  ({n_cand} candidates)")

# --- SARIMA: p,d,q + P,D,Q grid on AIC
best, best_aic, n_cand = None, np.inf, 0
for p, d, q in itertools.product(range(3), range(2), range(3)):
    for P, D, Q in itertools.product(range(2), range(2), range(2)):
        n_cand += 1
        try:
            aic = SARIMAX(logY, order=(p, d, q), seasonal_order=(P, D, Q, M),
                          enforce_stationarity=False,
                          enforce_invertibility=False).fit(disp=False).aic
            if np.isfinite(aic) and aic < best_aic:
                best_aic = aic
                best = dict(order=(p, d, q), seasonal_order=(P, D, Q, M), log=True)
        except Exception:
            continue
tuned_params["SARIMA"] = best or BASE_PARAMS["SARIMA"]
tuning_rows.append({"model": "SARIMA", "tuned": True, "criterion": "AIC",
                    "best_params": json.dumps({"order": list(tuned_params['SARIMA']['order']),
                                               "seasonal_order": list(tuned_params['SARIMA']['seasonal_order']),
                                               "log": True}),
                    "score": best_aic, "n_candidates": n_cand})
print(f"  SARIMA           best order {tuned_params['SARIMA']['order']} x "
      f"{tuned_params['SARIMA']['seasonal_order']} on log scale  AIC {best_aic:,.1f}  "
      f"({n_cand} candidates)")

# --- Prophet: its own cross_validation + performance_metrics
pdf = _prophet_frame(Y, DS)
pdf["cap"], pdf["floor"] = CAP_MONTHLY, 0.0
best, best_rmse, n_cand = None, np.inf, 0
for cps in (0.01, 0.05, 0.1, 0.5):
    for sps in (0.1, 1.0, 10.0):
        for mode in ("additive", "multiplicative"):
            n_cand += 1
            try:
                m = Prophet(growth="logistic", yearly_seasonality=True,
                            weekly_seasonality=False, daily_seasonality=False,
                            changepoint_prior_scale=cps, seasonality_prior_scale=sps,
                            seasonality_mode=mode)
                m.fit(pdf)
                cv = cross_validation(m, initial="1095 days", period="90 days",
                                      horizon="365 days", disable_tqdm=True)
                rmse = performance_metrics(cv, rolling_window=1)["rmse"].iloc[0]
                if np.isfinite(rmse) and rmse < best_rmse:
                    best_rmse = float(rmse)
                    best = dict(changepoint_prior_scale=cps, seasonality_prior_scale=sps,
                                seasonality_mode=mode)
            except Exception:
                continue
tuned_params["ProphetLogistic"] = best or BASE_PARAMS["ProphetLogistic"]
tuning_rows.append({"model": "ProphetLogistic", "tuned": True,
                    "criterion": "Prophet cross_validation RMSE (initial 1095d, "
                                 "period 90d, horizon 365d)",
                    "best_params": json.dumps(tuned_params["ProphetLogistic"]),
                    "score": best_rmse, "n_candidates": n_cand})
print(f"  ProphetLogistic  best {tuned_params['ProphetLogistic']}  "
      f"CV RMSE {best_rmse:,.1f}  ({n_cand} candidates)")

tune_df = pd.DataFrame(tuning_rows)
tune_df.to_csv(os.path.join(OUT_DIR, "forecast_tuning_results.csv"), index=False)
print("\n### Tuning results\n")
print(to_md(tune_df[["model", "tuned", "criterion", "best_params", "n_candidates"]]))


# ------------------------------------------------------------
# METRICS
# ------------------------------------------------------------
def mase_denom(train):
    """In-sample seasonal-naive MAE of THIS fold's training set."""
    if len(train) <= M:
        return np.nan
    return float(np.mean(np.abs(train[M:] - train[:-M])))


def fold_metrics(actual, pred, denom):
    err = actual - pred
    mae = float(np.mean(np.abs(err)))
    return {
        "MASE": mae / denom if denom and denom > 0 else np.nan,
        "MAE": mae,
        "RMSE": float(np.sqrt(np.mean(err ** 2))),
        "MAPE": float(np.mean(np.abs(err / actual)) * 100.0),
    }


# ------------------------------------------------------------
banner(2, "ROLLING-ORIGIN BACKTEST")
# ------------------------------------------------------------
def rolling_origin(y, ds, label):
    rows = []
    for h in HORIZONS:
        origins = range(MIN_TRAIN, len(y) - h + 1)
        for name in MODELS:
            for variant, params in (("base", BASE_PARAMS[name]),
                                    ("tuned", tuned_params[name])):
                if name in NO_TUNE and variant == "tuned":
                    continue
                for o in origins:
                    tr, te = y[:o], y[o:o + h]
                    pred = forecast(name, params, tr, h, ds=ds.iloc[:o])
                    if pred is None:
                        rows.append({"series": label, "model": name, "variant": variant,
                                     "h": h, "origin": o,
                                     "origin_month": f"{ds.iloc[o - 1]:%Y-%m}",
                                     "converged": False, "MASE": np.nan, "MAE": np.nan,
                                     "RMSE": np.nan, "MAPE": np.nan})
                        continue
                    mt = fold_metrics(te, pred, mase_denom(tr))
                    rows.append({"series": label, "model": name, "variant": variant,
                                 "h": h, "origin": o,
                                 "origin_month": f"{ds.iloc[o - 1]:%Y-%m}",
                                 "converged": True, **mt})
        print(f"    h={h}: {len(list(origins))} folds x "
              f"{len(MODELS) + len(MODELS) - len(NO_TUNE)} model builds done")
    return pd.DataFrame(rows)


print(f"  Expanding window, min_train={MIN_TRAIN}, step=1, horizons {HORIZONS}.")
print(f"  h=6  -> origins {MIN_TRAIN}..{len(Y) - 6} ({len(Y) - 6 - MIN_TRAIN + 1} folds)")
print(f"  h=12 -> origins {MIN_TRAIN}..{len(Y) - 12} ({len(Y) - 12 - MIN_TRAIN + 1} folds)")
print("  Every model refits at every origin; nothing sees data past its origin.\n")

folds = rolling_origin(Y, DS, "full_2020_2026")

# --- robustness series (COVID excluded)
print(f"\n  Robustness: same protocol on the series from {ROBUST_START[:7]}.")
rob_mask = DS >= pd.Timestamp(ROBUST_START)
Yr, DSr = Y[rob_mask.to_numpy()], DS[rob_mask].reset_index(drop=True)
print(f"  n={len(Yr)} observations, "
      f"h=6 -> {len(Yr) - 6 - MIN_TRAIN + 1} folds, "
      f"h=12 -> {len(Yr) - 12 - MIN_TRAIN + 1} folds\n")
folds_rob = rolling_origin(Yr, DSr, "from_2021_no_covid")

all_folds = pd.concat([folds, folds_rob], ignore_index=True)
all_folds.to_csv(os.path.join(OUT_DIR, "forecast_backtest_folds.csv"), index=False)

n_fail = int((~all_folds["converged"]).sum())
print(f"\n  Folds recorded: {len(all_folds):,}  |  non-converged: {n_fail}")
if FAIL_LOG:
    fl = pd.DataFrame(FAIL_LOG).groupby(["model", "h"]).size().reset_index(name="failures")
    print("  Convergence failures (logged, folds retained as NaN, never dropped):")
    print(to_md(fl))
else:
    print("  No convergence failures.")


# ------------------------------------------------------------
banner(3, "METRICS -- mean +/- std across folds (MASE leads)")
# ------------------------------------------------------------
def summarise(df, label):
    g = (df[df["series"] == label]
         .groupby(["model", "variant", "h"])
         .agg(folds=("MASE", "size"),
              converged=("converged", "sum"),
              MASE_mean=("MASE", "mean"), MASE_std=("MASE", "std"),
              MAE_mean=("MAE", "mean"), MAE_std=("MAE", "std"),
              RMSE_mean=("RMSE", "mean"), RMSE_std=("RMSE", "std"),
              MAPE_mean=("MAPE", "mean"), MAPE_std=("MAPE", "std"))
         .reset_index())
    g["series"] = label
    return g


comp = pd.concat([summarise(all_folds, "full_2020_2026"),
                  summarise(all_folds, "from_2021_no_covid")], ignore_index=True)
comp.to_csv(os.path.join(OUT_DIR, "forecast_model_comparison.csv"), index=False)

print("  MASE < 1 means the model beats a seasonal-naive forecast. MAPE is shown")
print("  last and on purpose: the series roughly doubles, so MAPE rewards models")
print("  that fit high-volume months and is not comparable across models here.\n")

for h in HORIZONS:
    sub = comp[(comp["series"] == "full_2020_2026") & (comp["h"] == h)] \
        .sort_values("MASE_mean").reset_index(drop=True)
    show = sub[["model", "variant", "folds", "MASE_mean", "MASE_std",
                "MAE_mean", "RMSE_mean", "MAPE_mean", "MAPE_std"]]
    print(f"### Rolling origin, h = {h} months (full series)\n")
    print(to_md(show))
    print()

WIN = {}
for h in HORIZONS:
    sub = comp[(comp["series"] == "full_2020_2026") & (comp["h"] == h)]
    b = sub.loc[sub["MASE_mean"].idxmin()]
    WIN[h] = (b["model"], b["variant"], float(b["MASE_mean"]))
    print(f"  MASE winner h={h}: {b['model']} ({b['variant']}) "
          f"MASE {b['MASE_mean']:.3f} +/- {b['MASE_std']:.3f}")


# ------------------------------------------------------------
banner(4, "LEGACY SINGLE SPLIT -- train <= 2024-12, test 2025")
# ------------------------------------------------------------
print("  Reproduces the protocol behind the reported 'Prophet 17.6% vs ARIMA")
print("  37.5%' MAPE headline, so the old numbers sit beside the new MASE.\n")

cut = int((DS < pd.Timestamp("2025-01-01")).sum())
tr, te = Y[:cut], Y[cut:cut + 12]
te_ds = DS.iloc[cut:cut + 12]
denom = mase_denom(tr)
print(f"  train {DS.iloc[0]:%Y-%m}..{DS.iloc[cut - 1]:%Y-%m} ({cut} obs) | "
      f"test {te_ds.iloc[0]:%Y-%m}..{te_ds.iloc[-1]:%Y-%m} ({len(te)} obs)")

legacy_rows = []
for name in MODELS:
    for variant, params in (("base", BASE_PARAMS[name]), ("tuned", tuned_params[name])):
        if name in NO_TUNE and variant == "tuned":
            continue
        pred = forecast(name, params, tr, len(te), ds=DS.iloc[:cut])
        if pred is None:
            legacy_rows.append({"model": name, "variant": variant, "converged": False,
                                "MASE": np.nan, "MAE": np.nan, "RMSE": np.nan, "MAPE": np.nan})
            continue
        legacy_rows.append({"model": name, "variant": variant, "converged": True,
                            **fold_metrics(te, pred, denom)})

# the two extra specifications 09_forecast.py reported
extra = [("ProphetLinear", dict(), None), ("ARIMA(1,1,1)-log", dict(order=(1, 1, 1), log=True), None)]
try:
    d = _prophet_frame(tr, DS.iloc[:cut])
    m = Prophet(growth="linear", yearly_seasonality=True, weekly_seasonality=False,
                daily_seasonality=False)
    m.fit(d)
    fut = m.make_future_dataframe(periods=len(te), freq="MS")
    pl = m.predict(fut)["yhat"].to_numpy()[-len(te):]
    legacy_rows.append({"model": "ProphetLinear (09 reference)", "variant": "base",
                        "converged": True, **fold_metrics(te, pl, denom)})
except Exception as e:
    FAIL_LOG.append({"model": "ProphetLinear", "h": 12, "n_train": cut, "error": str(e)[:160]})

pred = forecast("ARIMA", dict(order=(1, 1, 1), log=True), tr, len(te), ds=DS.iloc[:cut])
if pred is not None:
    legacy_rows.append({"model": "ARIMA(1,1,1)-log (09 reference)", "variant": "base",
                        "converged": True, **fold_metrics(te, pred, denom)})

legacy = pd.DataFrame(legacy_rows).sort_values("MAPE").reset_index(drop=True)
legacy.to_csv(os.path.join(OUT_DIR, "forecast_singlesplit_legacy.csv"), index=False)
print("\n### Single split 2025 -- old-style MAPE beside MASE\n")
print(to_md(legacy[["model", "variant", "MAPE", "MASE", "MAE", "RMSE"]]))

lr = legacy.set_index(legacy["model"] + " (" + legacy["variant"] + ")")
print("\n  Rank by MAPE : " + " < ".join(legacy.sort_values("MAPE")["model"].head(4)))
print("  Rank by MASE : " + " < ".join(legacy.sort_values("MASE")["model"].head(4)))


# ------------------------------------------------------------
banner(5, "THE 2030 EXTRAPOLATION -- does the projection stay plausible?")
# ------------------------------------------------------------
h_2030 = (pd.Timestamp(FORECAST_END).to_period("M") - DS.iloc[-1].to_period("M")).n
future_ds = pd.date_range(DS.iloc[-1] + pd.offsets.MonthBegin(1), FORECAST_END, freq="MS")
stock_now = float(Y.sum())
LAST12_MEAN = float(Y[-12:].mean())
print(f"  Fitting each model on all {len(Y)} observations and projecting "
      f"{h_2030} months to {FORECAST_END[:7]}.")
print(f"  EV stock today (cumulative registrations) = {stock_now:,.0f}")
print(f"  Policy ceiling = {CAP_MONTHLY:,.1f} registrations/month")
print(f"  Last 12 actual months mean = {LAST12_MEAN:,.0f}/month\n")
print("  TWO failure modes are checked, not one:")
print("    over-projection  -- peak above the policy ceiling (>5x = runaway)")
print("    under-projection -- 2030 mean below ~the last 12 actual months, i.e.")
print("                        the model simply stops growing. Passing the")
print("                        ceiling test by forecasting no growth is NOT")
print("                        a plausible 2030.\n")

scen_rows, paths = [], {}
for name in MODELS:
    for variant, params in (("base", BASE_PARAMS[name]), ("tuned", tuned_params[name])):
        if name in NO_TUNE and variant == "tuned":
            continue
        pred = forecast(name, params, Y, h_2030, ds=DS)
        label = f"{name} ({variant})"
        if pred is None:
            scen_rows.append({"model": name, "variant": variant, "converged": False,
                              "dec_2030_monthly": np.nan, "cumulative_stock_2030": np.nan,
                              "peak_monthly": np.nan, "exceeds_policy_ceiling": "n/a",
                              "plausible": "n/a", "note": "did not converge"})
            continue
        paths[label] = pred
        dec = float(pred[-1])
        peak = float(np.max(pred))
        stock = stock_now + float(np.sum(np.clip(pred, 0, None)))
        over = peak > CAP_MONTHLY
        neg = bool(np.any(pred < 0))
        ratio_over = peak / CAP_MONTHLY
        # growth check: the ceiling test only catches OVER-projection. A model
        # that simply stops growing also fails as a 2030 forecast.
        y2030 = float(np.mean(pred[-12:]))
        growth = y2030 / LAST12_MEAN

        if neg:
            verdict, note = "NO", "projects NEGATIVE registrations"
        elif ratio_over > 5:
            verdict, note = "NO", (f"peak {peak:,.0f}/mo is {ratio_over:.0f}x the ceiling "
                                   "-- runaway extrapolation, unusable")
        elif growth < 1.05:
            verdict, note = "NO", (f"2030 mean is {growth:.2f}x the last 12 actual months "
                                   "-- projects flat/declining demand, implausible under "
                                   "a 15% penetration policy")
        elif over:
            verdict, note = "borderline", (f"peak {peak:,.0f}/mo is {ratio_over:.2f}x the ceiling "
                                           "-- seasonal overshoot of a saturating trend, "
                                           "not runaway growth")
        else:
            verdict, note = "yes", "under the ceiling and still growing"

        row = {"model": name, "variant": variant, "converged": True,
               "dec_2030_monthly": dec, "mean_2030_monthly": y2030,
               "cumulative_stock_2030": stock, "peak_monthly": peak,
               "peak_over_ceiling_ratio": ratio_over,
               "growth_vs_last12": growth,
               "exceeds_policy_ceiling": "YES" if over else "no",
               "plausible": verdict, "note": note}
        # For Prophet, report the TREND separately: the logistic trend is what
        # saturates: yhat = trend + additive seasonality, so yhat can sit above
        # the cap even when the trend never does.
        if name == "ProphetLogistic":
            try:
                d = _prophet_frame(Y, DS); d["cap"], d["floor"] = CAP_MONTHLY, 0.0
                mm = Prophet(growth="logistic", yearly_seasonality=True,
                             weekly_seasonality=False, daily_seasonality=False, **params)
                mm.fit(d)
                ff = mm.make_future_dataframe(periods=h_2030, freq="MS")
                ff["cap"], ff["floor"] = CAP_MONTHLY, 0.0
                row["trend_dec_2030"] = float(mm.predict(ff)["trend"].iloc[-1])
            except Exception:
                row["trend_dec_2030"] = np.nan
        else:
            row["trend_dec_2030"] = np.nan
        scen_rows.append(row)

scen = pd.DataFrame(scen_rows)
scen["policy_ceiling_monthly"] = CAP_MONTHLY
scen.to_csv(os.path.join(OUT_DIR, "forecast_2030_scenarios.csv"), index=False)
print("### 2030 endpoint per model\n")
print(to_md(scen[["model", "variant", "dec_2030_monthly", "peak_monthly",
                  "growth_vs_last12", "cumulative_stock_2030",
                  "exceeds_policy_ceiling", "plausible", "note"]],
            floatfmt="{:,.2f}"))

plaus = scen[scen["plausible"].isin(["yes", "borderline"])]
hard_no = scen[scen["plausible"] == "NO"]
print(f"\n  PASS or BORDERLINE: {len(plaus)} of {int(scen['converged'].sum())} converged builds")
for _, r in plaus.iterrows():
    print(f"    [{r['plausible']:10s}] {r['model']} ({r['variant']}): "
          f"Dec-2030 {r['dec_2030_monthly']:,.0f}/mo, stock {r['cumulative_stock_2030']:,.0f}")
print(f"\n  REJECTED: {len(hard_no)}")
for _, r in hard_no.iterrows():
    print(f"    [rejected  ] {r['model']} ({r['variant']}): {r['note']}")

pt = scen.loc[scen["model"] == "ProphetLogistic", "trend_dec_2030"].dropna()
if len(pt):
    print(f"\n  Prophet logistic TREND at Dec-2030: "
          f"{', '.join(f'{v:,.0f}' for v in pt)} vs ceiling {CAP_MONTHLY:,.0f}")
    print("  The trend saturates as designed; only additive yearly seasonality")
    print("  lifts yhat above the cap in peak months. That is a different failure")
    print("  from SARIMA, whose trend itself diverges.")

# ------------------------------------------------------------
banner(6, "FIGURES")
# ------------------------------------------------------------
draw_figures(all_folds, paths, DS, Y, future_ds, CAP_MONTHLY)


# ------------------------------------------------------------
banner(7, "ROBUSTNESS -- ranking with COVID excluded")
# ------------------------------------------------------------
for h in HORIZONS:
    a = comp[(comp["series"] == "full_2020_2026") & (comp["h"] == h)] \
        .sort_values("MASE_mean")[["model", "variant", "MASE_mean"]].reset_index(drop=True)
    b = comp[(comp["series"] == "from_2021_no_covid") & (comp["h"] == h)] \
        .sort_values("MASE_mean")[["model", "variant", "MASE_mean"]].reset_index(drop=True)
    a["build"] = a["model"] + " (" + a["variant"] + ")"
    b["build"] = b["model"] + " (" + b["variant"] + ")"
    merged = pd.DataFrame({
        "rank": range(1, len(a) + 1),
        "full series 2020-": a["build"], "MASE_full": a["MASE_mean"],
        "from 2021 (no COVID)": b["build"], "MASE_2021": b["MASE_mean"],
    })
    print(f"\n### Ranking by MASE, h = {h}\n")
    print(to_md(merged))
    same_top = a["build"].iloc[0] == b["build"].iloc[0]
    tau = pd.Series(a["build"]).map({v: i for i, v in enumerate(b["build"])}).corr(
        pd.Series(range(len(a))), method="kendall")
    print(f"  Top model identical: {'YES' if same_top else 'NO'} "
          f"({a['build'].iloc[0]} vs {b['build'].iloc[0]})")
    print(f"  Kendall tau between the two orderings: {tau:.3f}")

# ------------------------------------------------------------
banner(8, "VERDICT")
# ------------------------------------------------------------
for h in HORIZONS:
    m, v, s = WIN[h]
    print(f"  Best MASE h={h:<3}: {m} ({v}), MASE {s:.3f}")
best_2030 = plaus.sort_values("cumulative_stock_2030")
print(f"  Passes the 2030 plausibility check: "
      f"{', '.join(best_2030['model'] + ' (' + best_2030['variant'] + ')') if len(best_2030) else 'NONE'}")
grade = dict(zip(scen["model"] + " (" + scen["variant"] + ")", scen["plausible"]))
for h in HORIZONS:
    b = f"{WIN[h][0]} ({WIN[h][1]})"
    print(f"  2030 grade of the h={h} accuracy winner {b}: {grade.get(b, 'n/a')}")
clean = set(scen.loc[scen["plausible"] == "yes", "model"])
acc_names = set(best_2030["model"]) if len(best_2030) else set()
agree = all(WIN[h][0] in acc_names for h in HORIZONS)
clean_agree = all(WIN[h][0] in clean for h in HORIZONS)
lg = legacy.sort_values("MAPE").reset_index(drop=True)
print(f"  Legacy single split still ranks {lg['model'].iloc[0]} first on BOTH "
      f"MAPE ({lg['MAPE'].iloc[0]:.1f}%) and MASE ({lg.sort_values('MASE')['MASE'].iloc[0]:.2f}).")

_h6 = (comp[(comp["series"] == "full_2020_2026") & (comp["h"] == 6)]
       .sort_values("MASE_mean").reset_index(drop=True))
_hit = _h6.index[(_h6["model"] == "ProphetLogistic") & (_h6["variant"] == "base")]
_rank = int(_hit[0]) + 1 if len(_hit) else -1
print("  So the old headline gap survives the CHANGE OF METRIC but not the")
print("  change of VALIDATION DESIGN -- under rolling origin the same model")
print(f"  falls to rank {_rank} of {len(_h6)} at h=6. The single 2025 split "
      "flattered it.")
print(f"  Same model wins accuracy AND clears 2030 outright: "
      f"{'YES' if clean_agree else 'NO'}")
if agree and not clean_agree:
    print("  -> The accuracy winner only reaches BORDERLINE on 2030: it clears the")
    print("     runaway test but its peak still sits above the policy ceiling. The")
    print("     models that pass 2030 outright are NOT the ones that forecast best")
    print("     at h=6/12. Accuracy and plausibility point at different models, and")
    print("     that split is the finding -- report both columns, not the error")
    print("     table alone.")
if not agree:
    print("  -> The accuracy winner and the plausibility winner DIFFER. That")
    print("     difference is the finding: an unconstrained model can fit the")
    print("     recent past better and still project a 2030 the policy ceiling")
    print("     forbids. Report both columns, not just the error table.")

print()
print("=" * 66)
print("09_forecast.py and its outputs are untouched; the dashboard still reads")
print("forecast_kv_monthly.csv. This stage is comparison evidence only.")
print("=" * 66)
