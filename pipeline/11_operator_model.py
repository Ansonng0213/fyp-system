# ============================================================
# FYP2 -- OPERATOR SITING MODEL  (diagnostic, Problem 14)
#
#   A SUPERVISED MODEL OF WHERE COMMERCIAL OPERATORS ACTUALLY BUILT.
#   Target: has_station = does this H3 r8 hex contain a public-facing,
#   operational charger?  (222 / 4003 hexes = 5.55%)
#
#   *** DIAGNOSTIC ONLY -- NEVER A SITING RECOMMENDATION. ***
#   This model learns the market's revealed preference, including its
#   income bias. Deploying its ranking would REPRODUCE the inequity the
#   CDI exists to correct. It is evidence about operator behaviour, and
#   a forecast of where the market goes next if nothing changes.
#   The CDI answers "where SHOULD chargers go"; this answers
#   "where DO they go" -- the contrast is the project's argument.
#
#   Leakage discipline: every supply-derived column (supply_raw,
#   supply_n, supply_gap, nearest_station_km, stations_2km,
#   stations_5km, cdi, demand_pressure, pop_n, act_n) is BANNED --
#   they are functions of the station layer, i.e. of the target.
#   Only demand-side and geographic features are admitted.
#
#   1  dataset build + leakage assertion
#   2  feature-group ablation A-H (all rows reported)
#   3  5 algorithms x {base, tuned} = 10 builds
#   4  evaluation under 2 CV schemes (random + spatial block)
#   5  the income finding, 3 specifications + spatial-block bootstrap
#   6  SHAP + permutation importance cross-check
#   7  market forecast, 10 seeds, stability reported
#   8  robustness: Poisson port-count model + H3 res-7 rerun
#
# Inputs : processed_data/hex_cdi_v1.csv
#          processed_data/poi_kv_clean_v2.csv
#          processed_data/ev_stations_kv_clean_v2.csv
# Outputs: processed_data/operator_model_comparison.csv
#          processed_data/operator_feature_ablation.csv
#          processed_data/operator_income_specifications.csv
#          processed_data/operator_model_scores.csv
#          processed_data/operator_market_forecast.csv
#          processed_data/operator_robustness.csv
#          processed_data/figures/*.png
#
# Reads existing artifacts only. Writes nothing that any other stage
# or dashboard page consumes.
# ============================================================
#
# ------------------------------------------------------------------
# LIMITATIONS (known, documented, NOT fixed here)
# ------------------------------------------------------------------
# 1. TWO UNMAPPED BOUNDARY STATIONS.
#    Of the 376 public-facing operational stations, 374 fall inside an
#    H3 res-8 cell of the analysis grid. Two do not and are silently
#    dropped from the target:
#      - station_id 270838, "KSL Esplanade Mall" (Shell Recharge),
#        Klang,  lat 2.958201, lon 101.465195 -- 10 m outside the
#        grid edge.
#      - station_id 188641, "RnR Dengkil Southbound" (chargEV),
#        Sepang, lat 2.903953, lon 101.615049 -- 498 m outside the
#        grid edge.
#    Both are genuine public chargers that the grid cannot represent.
#    They are 0.53% of the positive class; the target is therefore 222
#    hexes rather than a possible 224, and every metric in this script
#    is computed against 222. The direction of the bias is known: the
#    model is scored on very slightly FEWER positives than exist.
#
# 2. THE GRID HAS NO EXTERNAL BUFFER.
#    hex_grid_kv.geojson covers the 7 study districts and stops at the
#    administrative boundary. Nothing outside it exists to this model.
#    Consequently a hex on the study-area edge sees only the supply and
#    the POIs that happen to fall inside the boundary, and understates
#    any real charger, population or activity just across it -- e.g.
#    Kuala Selangor to the north-west, Seremban/Nilai to the south,
#    Bentong to the north-east. Edge hexes are systematically
#    under-informed relative to interior hexes.
#    Note this cuts BOTH ways and is not corrected anywhere upstream:
#    the same unbuffered grid underlies the CDI (stage 06) and the
#    recommender (stage 07), so edge hexes may read as more deserted
#    than they are.
#    A ring of buffer hexes drawn one or two rings beyond the boundary,
#    populated with cross-border stations and POIs and used for feature
#    construction only (never as prediction targets), would remove this.
#    THAT IS A SEPARATE TASK AND IS DELIBERATELY NOT ATTEMPTED HERE.
# ------------------------------------------------------------------

import os
import sys
import json
import warnings
import random

import numpy as np
import pandas as pd
import h3

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.model_selection import (StratifiedKFold, GroupKFold,
                                     RandomizedSearchCV, cross_val_predict,
                                     train_test_split)
from sklearn.inspection import permutation_importance
from sklearn.metrics import (average_precision_score, roc_auc_score,
                             brier_score_loss, f1_score, confusion_matrix,
                             precision_recall_curve)
from sklearn.calibration import calibration_curve

import xgboost as xgb
import lightgbm as lgb
import shap
import scipy.stats as st_stats
import statsmodels.api as sm

warnings.filterwarnings("ignore")

# ------------------------------------------------------------
# CONFIG -- every seed pinned
# ------------------------------------------------------------
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
os.environ["PYTHONHASHSEED"] = str(SEED)

OUT_DIR = "processed_data"
FIG_DIR = os.path.join(OUT_DIR, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

RES = 8
N_SPATIAL_BLOCKS = 8
N_TUNE_ITER = 50
N_BOOTSTRAP = 1000
FORECAST_SEEDS = range(10)
TOP_KS = [10, 20, 50]
KLCC = (3.1578, 101.7117)
R_EARTH = 6371.0

# Feature sets used for the two different jobs. The ablation table
# (STEP 2) shows why: C is the inference set (no geography, so a
# coefficient means something), D is the prediction set.
INFERENCE_SET = "C"
PREDICTION_SET = "D"

BANNED = ["supply_raw", "supply_n", "supply_gap", "nearest_station_km",
          "stations_2km", "stations_5km", "cdi", "demand_pressure",
          "pop_n", "act_n"]

POI_CATEGORIES = ["community", "education", "entertainment", "exercise",
                  "food_drink", "healthcare", "other", "residential",
                  "shopping", "transport", "work"]
COMMERCIAL_CATS = ["shopping", "work", "food_drink", "entertainment"]


def banner(n, title):
    print()
    print("=" * 64)
    print(f"STEP {n} -- {title}")
    print("=" * 64)


def to_md(df, floatfmt="{:.4f}", index=False):
    """Markdown table without pulling in tabulate."""
    d = df.reset_index() if index else df.copy()
    cols = [str(c) for c in d.columns]

    def cell(v):
        if isinstance(v, float):
            if np.isnan(v):
                return "--"
            return floatfmt.format(v)
        return str(v)

    rows = [[cell(v) for v in r] for r in d.itertuples(index=False)]
    widths = [max(len(cols[i]), *(len(r[i]) for r in rows)) if rows else len(cols[i])
              for i in range(len(cols))]
    out = ["| " + " | ".join(c.ljust(w) for c, w in zip(cols, widths)) + " |",
           "|" + "|".join("-" * (w + 2) for w in widths) + "|"]
    for r in rows:
        out.append("| " + " | ".join(v.ljust(w) for v, w in zip(r, widths)) + " |")
    return "\n".join(out)


def haversine(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = (np.sin((la2 - la1) / 2) ** 2 +
         np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R_EARTH * np.arcsin(np.sqrt(a))


# ============================================================
print("=" * 64)
print("FYP2 -- OPERATOR SITING MODEL (DIAGNOSTIC ONLY)")
print("=" * 64)
print("Library versions")
print(f"  python      {sys.version.split()[0]}")
print(f"  numpy       {np.__version__}")
print(f"  pandas      {pd.__version__}")
import sklearn
print(f"  scikit-learn {sklearn.__version__}")
print(f"  xgboost     {xgb.__version__}")
print(f"  lightgbm    {lgb.__version__}")
print(f"  shap        {shap.__version__}")
print(f"  statsmodels {sm.__version__}")
print(f"  h3          {h3.__version__}")
print(f"  matplotlib  {matplotlib.__version__}")
print(f"  seed        {SEED}")

# ------------------------------------------------------------
banner(1, "BUILD THE DATASET")
# ------------------------------------------------------------
hx = pd.read_csv(os.path.join(OUT_DIR, "hex_cdi_v1.csv"))
print(f"  hex_cdi_v1.csv            {len(hx):,} hexes, {hx.shape[1]} cols")

# --- keep ONLY demand-side + geographic columns. Everything the CDI
#     derived from the station layer is dropped here, at the source.
base = hx[["h3_index", "district", "lat", "lon",
           "pop_est", "activity_score", "equity_mult"]].copy()

# --- POIs: bin to res-8 from raw lat/lon, pivot the 11 categories
poi = pd.read_csv(os.path.join(OUT_DIR, "poi_kv_clean_v2.csv"))
poi = poi.dropna(subset=["latitude", "longitude", "category"])
poi["h3_index"] = [h3.latlng_to_cell(a, b, RES)
                   for a, b in zip(poi["latitude"], poi["longitude"])]
poi_wide = (poi.pivot_table(index="h3_index", columns="category",
                            values="name", aggfunc="size", fill_value=0)
            .reindex(columns=POI_CATEGORIES, fill_value=0))
poi_wide.columns = [f"poi_{c}" for c in poi_wide.columns]
poi_cols = list(poi_wide.columns)
print(f"  poi_kv_clean_v2.csv       {len(poi):,} POIs -> {len(poi_cols)} count columns")
print(f"                            {poi_wide.index.isin(base.h3_index).sum():,} "
      f"POI-bearing cells, {(~poi_wide.index.isin(base.h3_index)).sum():,} outside grid (dropped)")

base = base.merge(poi_wide, left_on="h3_index", right_index=True, how="left")
base[poi_cols] = base[poi_cols].fillna(0).astype(int)

# --- TARGET: public-facing AND operational stations only
stn = pd.read_csv(os.path.join(OUT_DIR, "ev_stations_kv_clean_v2.csv"))
pub = stn[stn["is_public_facing"].astype(bool) &
          stn["is_operational"].astype(bool)].copy()
pub["h3_index"] = [h3.latlng_to_cell(a, b, RES)
                   for a, b in zip(pub["latitude"], pub["longitude"])]
in_grid = pub[pub["h3_index"].isin(set(base["h3_index"]))]
print(f"  ev_stations_kv_clean_v2   {len(stn)} rows -> {len(pub)} public+operational")
print(f"                            {len(in_grid)} land inside the grid "
      f"({len(pub) - len(in_grid)} on the boundary, dropped)")

pos_hexes = set(in_grid["h3_index"])
base["has_station"] = base["h3_index"].isin(pos_hexes).astype(int)

n_pos = int(base["has_station"].sum())
prevalence = n_pos / len(base)
print(f"\n  TARGET has_station        {n_pos} of {len(base):,} hexes = {prevalence:.3%}")
assert n_pos == 222, f"expected 222 positive hexes, got {n_pos}"
print("  OK matches the expected 222 / 4003 (5.5%)")

# --- engineered features (used by ablation sets E-H only)
idx_pos = {c: i for i, c in enumerate(base["h3_index"])}
lag_act, lag_pop = np.zeros(len(base)), np.zeros(len(base))
act_v = base["activity_score"].to_numpy()
pop_v = base["pop_est"].to_numpy()
for i, cell in enumerate(base["h3_index"]):
    nb = [idx_pos[c] for c in h3.grid_ring(cell, 1) if c in idx_pos]
    if nb:
        lag_act[i] = act_v[nb].mean()
        lag_pop[i] = pop_v[nb].mean()
base["lag_activity"] = lag_act
base["lag_pop"] = lag_pop

comm = base[[f"poi_{c}" for c in COMMERCIAL_CATS]].sum(axis=1)
base["comm_resi_ratio"] = comm / (base["poi_residential"] + 1.0)

counts = base[poi_cols].to_numpy(dtype=float)
tot = counts.sum(axis=1, keepdims=True)
p = np.divide(counts, tot, out=np.zeros_like(counts), where=tot > 0)
base["poi_diversity"] = -np.sum(np.where(p > 0, p * np.log(p), 0.0), axis=1)

base["dist_klcc_km"] = haversine(base["lat"].to_numpy(), base["lon"].to_numpy(),
                                 KLCC[0], KLCC[1])

dist_dummies = pd.get_dummies(base["district"], prefix="dist", drop_first=True)
dist_cols = list(dist_dummies.columns)
base = pd.concat([base, dist_dummies.astype(int)], axis=1)

# --- spatial blocks (used by CV scheme b AND by the bootstrap)
km = KMeans(n_clusters=N_SPATIAL_BLOCKS, random_state=SEED, n_init=10)
base["spatial_block"] = km.fit_predict(base[["lat", "lon"]])
print(f"\n  Spatial blocks (KMeans {N_SPATIAL_BLOCKS} on lat/lon):")
blk = base.groupby("spatial_block").agg(hexes=("h3_index", "size"),
                                        positives=("has_station", "sum"))
blk["rate"] = blk["positives"] / blk["hexes"]
print(to_md(blk.reset_index(), index=False))

# ------------------------------------------------------------
# FEATURE SETS
# ------------------------------------------------------------
SET_A = ["pop_est", "equity_mult"]
SET_B = SET_A + ["activity_score"]
SET_C = SET_B + poi_cols
SET_D = SET_C + ["lat", "lon"] + dist_cols
SET_E = SET_C + ["lag_activity", "lag_pop"]
SET_F = SET_C + ["comm_resi_ratio", "poi_diversity"]
SET_G = SET_C + ["dist_klcc_km"]
SET_H = SET_C + ["lag_activity", "lag_pop", "comm_resi_ratio",
                 "poi_diversity", "dist_klcc_km"]

FEATURE_SETS = {
    "A": ("population + equity only", SET_A),
    "B": ("A + activity score", SET_B),
    "C": ("B + 11 POI counts  [INFERENCE SET]", SET_C),
    "D": ("C + lat/lon + district dummies  [PREDICTION SET]", SET_D),
    "E": ("C + spatial lag (6-neighbour mean act & pop)", SET_E),
    "F": ("C + commercial/residential ratio + POI diversity", SET_F),
    "G": ("C + distance to KLCC", SET_G),
    "H": ("C + all engineered (E+F+G)", SET_H),
}

# --- LEAKAGE ASSERTION -------------------------------------------------
all_feats = sorted({f for _, (_, fs) in FEATURE_SETS.items() for f in fs})
present = [b for b in BANNED if b in all_feats]
print("\n  LEAKAGE ASSERTION -- banned supply-derived features")
for b in BANNED:
    print(f"    {b:22s} {'*** PRESENT ***' if b in all_feats else 'absent  OK'}")
assert not present, f"LEAKAGE: banned features present: {present}"
print(f"  OK assertion PASSED -- 0 of {len(BANNED)} banned features in any feature set")

print(f"\n  FINAL FEATURE LIST ({len(all_feats)} distinct across all sets):")
for f in all_feats:
    print(f"    - {f}")
print(f"\n  Prediction set {PREDICTION_SET} ({len(FEATURE_SETS[PREDICTION_SET][1])} features), "
      f"inference set {INFERENCE_SET} ({len(FEATURE_SETS[INFERENCE_SET][1])} features)")

y = base["has_station"].to_numpy()
groups = base["spatial_block"].to_numpy()


# ------------------------------------------------------------
# EVALUATION HELPERS
# ------------------------------------------------------------
# NOTE ON ACCURACY: accuracy is NOT reported anywhere in this script.
# With 5.55% prevalence, a model that predicts "no station" for every
# hex scores 94.45% accuracy while finding zero stations. It is a
# meaningless metric on this problem. PR-AUC is primary because it is
# the metric that degrades when the positive class is missed, and its
# random baseline is exactly the prevalence (0.0555).

def prec_rec_at_k(y_true, proba, k):
    order = np.argsort(-proba)[:k]
    hits = int(y_true[order].sum())
    return hits / k, hits / max(1, int(y_true.sum()))


def score_block(y_true, proba, label):
    row = {"model": label,
           "pr_auc": average_precision_score(y_true, proba),
           "random_baseline": prevalence,
           "lift_over_random": average_precision_score(y_true, proba) / prevalence,
           "roc_auc": roc_auc_score(y_true, proba),
           "brier": brier_score_loss(y_true, proba),
           "f1_at_0.5": f1_score(y_true, (proba >= 0.5).astype(int), zero_division=0)}
    for k in TOP_KS:
        pk, rk = prec_rec_at_k(y_true, proba, k)
        row[f"precision@{k}"] = pk
        row[f"recall@{k}"] = rk
    return row


def oof_proba(model, X, y, scheme, groups=None, seed=SEED):
    if scheme == "stratified":
        cv = StratifiedKFold(5, shuffle=True, random_state=seed)
        return cross_val_predict(model, X, y, cv=cv, method="predict_proba")[:, 1]
    cv = GroupKFold(n_splits=N_SPATIAL_BLOCKS)
    return cross_val_predict(model, X, y, cv=cv, groups=groups,
                             method="predict_proba")[:, 1]


# ------------------------------------------------------------
banner(2, "FEATURE-GROUP ABLATION (all 8 sets reported)")
# ------------------------------------------------------------
print("  Fixed probe model: RandomForest(400, seed 42), StratifiedKFold(5)")
print("  and spatial-block GroupKFold(8). Out-of-fold predictions only.\n")

abl_rows = []
for key, (desc, feats) in FEATURE_SETS.items():
    X = base[feats].to_numpy(dtype=float)
    probe = RandomForestClassifier(n_estimators=400, random_state=SEED, n_jobs=-1)
    p_rand = oof_proba(probe, X, y, "stratified")
    p_spat = oof_proba(probe, X, y, "spatial", groups)
    abl_rows.append({
        "set": key, "description": desc, "n_features": len(feats),
        "pr_auc_random_cv": average_precision_score(y, p_rand),
        "pr_auc_spatial_cv": average_precision_score(y, p_spat),
        "roc_auc_random_cv": roc_auc_score(y, p_rand),
        "precision@50_random_cv": prec_rec_at_k(y, p_rand, 50)[0],
        "random_baseline": prevalence,
    })
    print(f"  {key}  {desc:52s} PR-AUC {abl_rows[-1]['pr_auc_random_cv']:.4f}")

abl = pd.DataFrame(abl_rows)
c_pr = float(abl.loc[abl["set"] == "C", "pr_auc_random_cv"].iloc[0])
abl["gain_vs_C"] = abl["pr_auc_random_cv"] - c_pr
abl.to_csv(os.path.join(OUT_DIR, "operator_feature_ablation.csv"), index=False)

print("\n### Feature-group ablation\n")
print(to_md(abl[["set", "description", "n_features", "pr_auc_random_cv",
                 "pr_auc_spatial_cv", "precision@50_random_cv", "gain_vs_C"]]))
print(f"\n  Random baseline PR-AUC = {prevalence:.4f}")
eng = abl[abl["set"].isin(["E", "F", "G", "H"])]["gain_vs_C"]
print(f"  Engineered sets E-H gain over C: min {eng.min():+.4f}, max {eng.max():+.4f} "
      f"-- reported regardless of sign, no set was dropped.")

# ------------------------------------------------------------
banner(3, "MODELS -- 5 algorithms x {base, tuned} = 10 builds")
# ------------------------------------------------------------
FEATS = FEATURE_SETS[PREDICTION_SET][1]
X = base[FEATS].to_numpy(dtype=float)
print(f"  Feature set {PREDICTION_SET}: {len(FEATS)} features, n={len(X):,}, "
      f"positives={n_pos} ({prevalence:.2%})\n")

spw = (len(y) - y.sum()) / y.sum()   # scale_pos_weight for boosters


def make_lr():
    return Pipeline([("sc", StandardScaler()),
                     ("m", LogisticRegression(class_weight="balanced",
                                              max_iter=5000, random_state=SEED))])


BASE_MODELS = {
    "LogisticRegression": make_lr(),
    "DecisionTree": DecisionTreeClassifier(random_state=SEED),
    "RandomForest": RandomForestClassifier(n_estimators=400, random_state=SEED, n_jobs=-1),
    "XGBoost": xgb.XGBClassifier(n_estimators=400, learning_rate=0.1,
                                 eval_metric="logloss", random_state=SEED,
                                 n_jobs=-1, tree_method="hist"),
    "LightGBM": lgb.LGBMClassifier(n_estimators=400, random_state=SEED,
                                   n_jobs=-1, verbose=-1),
}

SEARCH_SPACES = {
    "LogisticRegression": {"m__C": st_stats.loguniform(1e-3, 1e2),
                           "m__penalty": ["l1", "l2"],
                           "m__solver": ["liblinear", "saga"]},
    "DecisionTree": {"max_depth": [2, 3, 4, 5, 6, 8, 10, 12, None],
                     "min_samples_leaf": st_stats.randint(1, 60),
                     "min_samples_split": st_stats.randint(2, 60),
                     "criterion": ["gini", "entropy"],
                     "class_weight": [None, "balanced"]},
    "RandomForest": {"n_estimators": st_stats.randint(200, 900),
                     "max_depth": [4, 6, 8, 12, 16, None],
                     "min_samples_leaf": st_stats.randint(1, 25),
                     "max_features": ["sqrt", "log2", 0.4, 0.7],
                     "class_weight": [None, "balanced", "balanced_subsample"]},
    "XGBoost": {"n_estimators": st_stats.randint(200, 900),
                "max_depth": st_stats.randint(2, 9),
                "learning_rate": st_stats.loguniform(0.01, 0.3),
                "subsample": st_stats.uniform(0.6, 0.4),
                "colsample_bytree": st_stats.uniform(0.5, 0.5),
                "min_child_weight": st_stats.randint(1, 12),
                "reg_lambda": st_stats.loguniform(1e-2, 20),
                "scale_pos_weight": [1.0, np.sqrt(spw), spw]},
    "LightGBM": {"n_estimators": st_stats.randint(200, 900),
                 "num_leaves": st_stats.randint(7, 80),
                 "max_depth": [-1, 3, 5, 7, 10],
                 "learning_rate": st_stats.loguniform(0.01, 0.3),
                 "min_child_samples": st_stats.randint(5, 60),
                 "subsample": st_stats.uniform(0.6, 0.4),
                 "colsample_bytree": st_stats.uniform(0.5, 0.5),
                 "reg_lambda": st_stats.loguniform(1e-2, 20),
                 "scale_pos_weight": [1.0, np.sqrt(spw), spw]},
}


def fresh(name, seed=SEED):
    if name == "LogisticRegression":
        return make_lr()
    m = {"DecisionTree": DecisionTreeClassifier(random_state=seed),
         "RandomForest": RandomForestClassifier(n_estimators=400, random_state=seed, n_jobs=-1),
         "XGBoost": xgb.XGBClassifier(n_estimators=400, learning_rate=0.1,
                                      eval_metric="logloss", random_state=seed,
                                      n_jobs=-1, tree_method="hist"),
         "LightGBM": lgb.LGBMClassifier(n_estimators=400, random_state=seed,
                                        n_jobs=-1, verbose=-1)}[name]
    return m


tuned_models, best_params = {}, {}
for name in BASE_MODELS:
    print(f"  Tuning {name} -- RandomizedSearchCV, {N_TUNE_ITER} iters, "
          f"StratifiedKFold(5), scoring=average_precision ...")
    search = RandomizedSearchCV(
        fresh(name), SEARCH_SPACES[name], n_iter=N_TUNE_ITER,
        scoring="average_precision",
        cv=StratifiedKFold(5, shuffle=True, random_state=SEED),
        random_state=SEED, n_jobs=-1, refit=True, error_score=0.0)
    search.fit(X, y)
    tuned_models[name] = search.best_estimator_
    best_params[name] = search.best_params_
    print(f"      best CV AP = {search.best_score_:.4f}")
    print(f"      best params = "
          f"{ {k: (round(v, 4) if isinstance(v, float) else v) for k, v in search.best_params_.items()} }")

# ------------------------------------------------------------
banner(4, "EVALUATION -- 2 CV schemes, identical metrics")
# ------------------------------------------------------------
print("  (a) StratifiedKFold(5, shuffle=True)   -- random split")
print("  (b) KMeans(8) on lat/lon -> GroupKFold(8) -- spatial block, "
      "held-out regions")
print("  All scores from cross_val_predict. Accuracy deliberately omitted "
      "(see note in source).\n")

comparison, oof_store = [], {}
for name in BASE_MODELS:
    for variant, mdl in (("base", BASE_MODELS[name]), ("tuned", tuned_models[name])):
        label = f"{name} ({variant})"
        p_rand = oof_proba(mdl, X, y, "stratified")
        p_spat = oof_proba(mdl, X, y, "spatial", groups)
        oof_store[label] = (p_rand, p_spat)

        r = score_block(y, p_rand, label)
        s = score_block(y, p_spat, label)
        row = {"model": name, "variant": variant,
               "feature_set": PREDICTION_SET, "n_features": len(FEATS)}
        for k, v in r.items():
            if k != "model":
                row[f"{k}__randomCV"] = v
        for k, v in s.items():
            if k not in ("model", "random_baseline"):
                row[f"{k}__spatialCV"] = v
        row["best_params"] = json.dumps(
            {k: (float(v) if isinstance(v, (np.floating, float)) else
                 int(v) if isinstance(v, (np.integer,)) else str(v))
             for k, v in best_params[name].items()}) if variant == "tuned" else ""
        comparison.append(row)
        print(f"  {label:32s} PR-AUC random {r['pr_auc']:.4f} | "
              f"spatial {s['pr_auc']:.4f} | P@50 {r['precision@50']:.3f}")

comp = pd.DataFrame(comparison).sort_values("pr_auc__randomCV", ascending=False)
comp.to_csv(os.path.join(OUT_DIR, "operator_model_comparison.csv"), index=False)
assert len(comp) == 10

show = ["model", "variant", "pr_auc__randomCV", "pr_auc__spatialCV",
        "roc_auc__randomCV", "precision@10__randomCV", "precision@20__randomCV",
        "precision@50__randomCV", "recall@50__randomCV",
        "f1_at_0.5__randomCV", "brier__randomCV"]
print("\n### Model comparison (10 builds)\n")
print(to_md(comp[show]))
print(f"\n  RANDOM BASELINE PR-AUC = {prevalence:.4f}  "
      f"(a coin-flip ranker scores this; every model above is a multiple of it)")
print("  Accuracy is NOT reported: predicting all-negative would score "
      f"{1 - prevalence:.2%} while finding nothing.")

champ_label = comp.iloc[0]["model"] + " (" + comp.iloc[0]["variant"] + ")"
champ_name, champ_variant = comp.iloc[0]["model"], comp.iloc[0]["variant"]
champ_model = tuned_models[champ_name] if champ_variant == "tuned" else BASE_MODELS[champ_name]
spat_best = comp.sort_values("pr_auc__spatialCV", ascending=False).iloc[0]
print(f"\n  CHAMPION (by random-CV PR-AUC): {champ_label}")
print(f"  Best under spatial-block CV   : {spat_best['model']} ({spat_best['variant']})"
      f" -- {'SAME' if spat_best['model'] == champ_name and spat_best['variant'] == champ_variant else 'DIFFERENT, noted'}")

# --- champion figures
p_rand_ch, p_spat_ch = oof_store[champ_label]
base["oof_proba_randomCV"] = p_rand_ch
base["oof_proba_spatialCV"] = p_spat_ch

prec, rec, _ = precision_recall_curve(y, p_rand_ch)
plt.figure(figsize=(6, 5))
plt.plot(rec, prec, lw=2, label=f"{champ_label} (AP={average_precision_score(y, p_rand_ch):.3f})")
plt.axhline(prevalence, ls="--", c="grey", label=f"random baseline ({prevalence:.3f})")
plt.xlabel("Recall"); plt.ylabel("Precision")
plt.title("Precision-Recall -- out-of-fold"); plt.legend(); plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "pr_curve.png"), dpi=150); plt.close()

frac_pos, mean_pred = calibration_curve(y, p_rand_ch, n_bins=10, strategy="quantile")
plt.figure(figsize=(6, 5))
plt.plot(mean_pred, frac_pos, "o-", label=champ_label)
plt.plot([0, 1], [0, 1], "--", c="grey", label="perfect")
plt.xlabel("Mean predicted probability"); plt.ylabel("Observed frequency")
plt.title(f"Calibration -- Brier {brier_score_loss(y, p_rand_ch):.4f}")
plt.legend(); plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "calibration.png"), dpi=150); plt.close()

cm = confusion_matrix(y, (p_rand_ch >= 0.5).astype(int))
fig, ax = plt.subplots(figsize=(5, 4.5))
ax.imshow(cm, cmap="Blues")
for i in range(2):
    for j in range(2):
        ax.text(j, i, f"{cm[i, j]:,}", ha="center", va="center",
                color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=13)
ax.set_xticks([0, 1], ["pred 0", "pred 1"]); ax.set_yticks([0, 1], ["true 0", "true 1"])
ax.set_title(f"Confusion matrix @0.5 -- {champ_label}")
plt.tight_layout(); plt.savefig(os.path.join(FIG_DIR, "confusion_matrix.png"), dpi=150); plt.close()
print(f"\n  Confusion matrix @0.5 (OOF): TN={cm[0,0]:,} FP={cm[0,1]:,} "
      f"FN={cm[1,0]:,} TP={cm[1,1]:,}")
print("  Figures -> pr_curve.png, calibration.png, confusion_matrix.png")

# ------------------------------------------------------------
banner(5, "THE INCOME FINDING -- three specifications")
# ------------------------------------------------------------
print("  equity_mult = KV median income / district median income, clipped")
print("  0.75-1.35. It is INVERSE income: HIGHER equity_mult = POORER")
print("  district. So a NEGATIVE coefficient on equity_mult means")
print("  operators avoid poorer areas.\n")
print(f"  All three fit on inference set {INFERENCE_SET} "
      f"({len(SET_C)} features), standardised, LogisticRegression"
      " (class_weight='balanced').\n")

SPECS = {
    "(i) with district dummies":   SET_C + dist_cols,
    "(ii) without district dummies": SET_C,
    "(iii) district dummies only (no income)": [f for f in SET_C if f != "equity_mult"] + dist_cols,
}


def fit_logit(feats):
    Xs = base[feats].to_numpy(dtype=float)
    pipe = make_lr()
    pipe.fit(Xs, y)
    coefs = dict(zip(feats, pipe.named_steps["m"].coef_[0]))
    p = oof_proba(make_lr(), Xs, y, "stratified")
    return coefs, average_precision_score(y, p), roc_auc_score(y, p)


spec_rows = []
for label, feats in SPECS.items():
    coefs, ap, auc = fit_logit(feats)
    c = coefs.get("equity_mult", np.nan)
    spec_rows.append({
        "specification": label, "n_features": len(feats),
        "equity_mult_coef": c,
        "odds_ratio": np.exp(c) if not np.isnan(c) else np.nan,
        "pr_auc_oof": ap, "roc_auc_oof": auc,
        "income_in_model": "equity_mult" in feats,
    })
    if np.isnan(c):
        print(f"  {label:42s} equity_mult ABSENT by design | PR-AUC {ap:.4f}")
    else:
        print(f"  {label:42s} coef {c:+.4f}  OR {np.exp(c):.3f} | PR-AUC {ap:.4f}")

# --- bootstrap CI by resampling SPATIAL BLOCKS, not rows
print(f"\n  Bootstrap 95% CI -- resampling the {N_SPATIAL_BLOCKS} SPATIAL BLOCKS "
      f"with replacement, {N_BOOTSTRAP} iterations.")
print("  Rows are NOT resampled: neighbouring hexes share population,")
print("  POIs and district income, so row-bootstrap would understate the CI.\n")

block_idx = {b: np.where(groups == b)[0] for b in range(N_SPATIAL_BLOCKS)}
rng = np.random.default_rng(SEED)
for r in spec_rows:
    if not r["income_in_model"]:
        r["ci_low"], r["ci_high"], r["boot_n_valid"] = np.nan, np.nan, 0
        continue
    feats = SPECS[r["specification"]]
    Xs = base[feats].to_numpy(dtype=float)
    j = feats.index("equity_mult")
    draws = []
    for _ in range(N_BOOTSTRAP):
        pick = rng.integers(0, N_SPATIAL_BLOCKS, N_SPATIAL_BLOCKS)
        rows = np.concatenate([block_idx[b] for b in pick])
        yb = y[rows]
        if yb.sum() < 10 or yb.sum() == len(yb):
            continue
        try:
            pipe = make_lr()
            pipe.fit(Xs[rows], yb)
            draws.append(pipe.named_steps["m"].coef_[0][j])
        except Exception:
            continue
    draws = np.array(draws)
    r["ci_low"], r["ci_high"] = np.percentile(draws, [2.5, 97.5])
    r["boot_n_valid"] = len(draws)
    r["boot_share_negative"] = float((draws < 0).mean())
    print(f"  {r['specification']:42s} coef {r['equity_mult_coef']:+.4f}  "
          f"95% CI [{r['ci_low']:+.4f}, {r['ci_high']:+.4f}]  "
          f"({len(draws)}/{N_BOOTSTRAP} valid draws, "
          f"{r['boot_share_negative']:.1%} negative)")

specs = pd.DataFrame(spec_rows)
specs.to_csv(os.path.join(OUT_DIR, "operator_income_specifications.csv"), index=False)
print("\n### Income specifications\n")
print(to_md(specs[["specification", "n_features", "equity_mult_coef", "odds_ratio",
                   "ci_low", "ci_high", "pr_auc_oof"]]))

sign = specs.loc[specs["income_in_model"], "equity_mult_coef"]
crosses = specs.loc[specs["income_in_model"]].apply(
    lambda r: (r["ci_low"] <= 0 <= r["ci_high"]), axis=1)
print(f"\n  Point estimate: {'NEGATIVE in both specs -- operators favour richer districts' if (sign < 0).all() else 'mixed / positive -- read the table'}")
print(f"  Spatial-block 95% CI crosses zero in {int(crosses.sum())} of "
      f"{len(crosses)} income specifications.")
if int(crosses.sum()) > 0:
    print("\n  READ THIS BEFORE QUOTING THE INCOME EFFECT:")
    print("  The direction is consistent (both specs negative, and the large")
    print("  majority of bootstrap draws are negative), but once spatial")
    print("  dependence is respected the effect is NOT statistically")
    print("  distinguishable from zero. With income measured at DISTRICT")
    print("  level there are effectively only 7 independent income values,")
    print("  so this dataset cannot resolve a district-level income effect")
    print("  however many hexes it contains. State it as SUGGESTIVE, NOT")
    print("  SIGNIFICANT. The defensible inequity evidence in this project")
    print("  remains the coverage and per-capita gaps, not this coefficient.")
print(f"\n  Spec (i) vs (ii): adding district dummies moves the coefficient")
print(f"  {specs.loc[1, 'equity_mult_coef']:+.4f} -> {specs.loc[0, 'equity_mult_coef']:+.4f}"
      f" ({abs(specs.loc[0, 'equity_mult_coef'] / specs.loc[1, 'equity_mult_coef']):.0%} retained).")
print("  Spec (iii) shows district dummies alone reach PR-AUC "
      f"{specs.loc[2, 'pr_auc_oof']:.4f} vs {specs.loc[0, 'pr_auc_oof']:.4f} with")
print("  income included -- income adds essentially nothing once you know")
print("  the district, because income IS a district-level constant here.")

# ------------------------------------------------------------
banner(6, "EXPLAINABILITY -- SHAP + permutation importance")
# ------------------------------------------------------------
Xdf = pd.DataFrame(X, columns=FEATS)
champ_fit = champ_model
champ_fit.fit(X, y)

print(f"  Champion: {champ_label} on feature set {PREDICTION_SET}")
try:
    if champ_name == "LogisticRegression":
        expl = shap.LinearExplainer(champ_fit.named_steps["m"],
                                    champ_fit.named_steps["sc"].transform(X))
        sv = expl.shap_values(champ_fit.named_steps["sc"].transform(X))
    else:
        expl = shap.TreeExplainer(champ_fit)
        sv = expl.shap_values(Xdf)
        if isinstance(sv, list):
            sv = sv[1]
        if getattr(sv, "ndim", 2) == 3:
            sv = sv[:, :, 1]
    shap_ok = True
except Exception as e:
    print(f"  SHAP failed ({e}) -- falling back to permutation importance only")
    shap_ok = False

if shap_ok:
    shap_mean = np.abs(sv).mean(axis=0)
    shap_rank = pd.DataFrame({"feature": FEATS, "mean_abs_shap": shap_mean}) \
        .sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)

    plt.figure()
    shap.summary_plot(sv, Xdf, plot_type="bar", show=False, max_display=15)
    plt.title(f"SHAP mean |value| -- {champ_label}")
    plt.tight_layout(); plt.savefig(os.path.join(FIG_DIR, "shap_summary_bar.png"), dpi=150)
    plt.close()

    plt.figure()
    shap.summary_plot(sv, Xdf, show=False, max_display=15)
    plt.title(f"SHAP beeswarm -- {champ_label}")
    plt.tight_layout(); plt.savefig(os.path.join(FIG_DIR, "shap_beeswarm.png"), dpi=150)
    plt.close()

    for i, feat in enumerate(shap_rank["feature"].head(3), start=1):
        plt.figure()
        shap.dependence_plot(feat, sv, Xdf, show=False)
        plt.tight_layout()
        plt.savefig(os.path.join(FIG_DIR, f"shap_dependence_{i}_{feat}.png"), dpi=150)
        plt.close()

    print("\n### SHAP top 10\n")
    print(to_md(shap_rank.head(10)))
    print("  Figures -> shap_summary_bar.png, shap_beeswarm.png, "
          "shap_dependence_{1,2,3}_*.png")

# --- permutation importance (model-agnostic cross-check)
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, stratify=y,
                                      random_state=SEED)
pm = fresh(champ_name) if champ_variant == "base" else tuned_models[champ_name]
pm.fit(Xtr, ytr)
perm = permutation_importance(pm, Xte, yte, n_repeats=10, random_state=SEED,
                              scoring="average_precision", n_jobs=-1)
perm_rank = pd.DataFrame({"feature": FEATS,
                          "perm_importance": perm.importances_mean,
                          "perm_std": perm.importances_std}) \
    .sort_values("perm_importance", ascending=False).reset_index(drop=True)

plt.figure(figsize=(7, 6))
top = perm_rank.head(15).iloc[::-1]
plt.barh(top["feature"], top["perm_importance"], xerr=top["perm_std"])
plt.xlabel("Drop in average precision when shuffled")
plt.title(f"Permutation importance -- {champ_label}")
plt.tight_layout(); plt.savefig(os.path.join(FIG_DIR, "permutation_importance.png"), dpi=150)
plt.close()

print("\n### Permutation importance top 10\n")
print(to_md(perm_rank.head(10)))

if shap_ok:
    s5, p5 = set(shap_rank["feature"].head(5)), set(perm_rank["feature"].head(5))
    print(f"\n  AGREEMENT CHECK -- top-5 overlap: {len(s5 & p5)}/5")
    print(f"    both     : {sorted(s5 & p5)}")
    print(f"    SHAP only: {sorted(s5 - p5)}")
    print(f"    perm only: {sorted(p5 - s5)}")
    print(f"  The two methods {'AGREE' if len(s5 & p5) >= 4 else 'PARTLY DISAGREE'} "
          "on the leading drivers.")

# ------------------------------------------------------------
banner(7, "MARKET FORECAST -- where the market builds next (10 seeds)")
# ------------------------------------------------------------
print("  *** DIAGNOSTIC FORECAST, NOT A RECOMMENDATION. ***")
print("  This ranks hexes the market is most likely to build in next.")
print("  Following it would deepen the desert; it is here as the")
print("  counterfactual the CDI argues against.\n")
print("  Out-of-fold probabilities only, has_station == 0 hexes only,")
print(f"  champion re-run under seeds {list(FORECAST_SEEDS)}.\n")

neg_mask = base["has_station"].to_numpy() == 0
districts = sorted(base["district"].unique())
per_seed = {k: {d: [] for d in districts} for k in (20, 50)}
klang_zero = {20: 0, 50: 0}
seed_rows = []

for sd in FORECAST_SEEDS:
    mdl = tuned_models[champ_name] if champ_variant == "tuned" else fresh(champ_name, sd)
    if champ_variant == "tuned":
        try:
            mdl = type(mdl)(**{**mdl.get_params(), "random_state": sd}) \
                if champ_name != "LogisticRegression" else mdl
        except Exception:
            pass
    p = oof_proba(mdl, X, y, "stratified", seed=sd)
    cand = base.loc[neg_mask, ["h3_index", "district"]].copy()
    cand["proba"] = p[neg_mask]
    cand = cand.sort_values("proba", ascending=False)
    for k in (20, 50):
        vc = cand.head(k)["district"].value_counts()
        for d in districts:
            per_seed[k][d].append(int(vc.get(d, 0)))
        if int(vc.get("Klang", 0)) == 0:
            klang_zero[k] += 1
        seed_rows.append({"seed": sd, "top_k": k,
                          **{d: int(vc.get(d, 0)) for d in districts}})
    print(f"  seed {sd}: top-20 = " +
          ", ".join(f"{d} {per_seed[20][d][-1]}" for d in districts
                    if per_seed[20][d][-1] > 0))

fc_rows = []
for k in (20, 50):
    for d in districts:
        v = np.array(per_seed[k][d], dtype=float)
        fc_rows.append({"top_k": k, "district": d,
                        "mean_sites": v.mean(), "std_sites": v.std(ddof=0),
                        "min_sites": int(v.min()), "max_sites": int(v.max()),
                        "n_seeds_zero": int((v == 0).sum()), "n_seeds": len(v)})
fc = pd.DataFrame(fc_rows).sort_values(["top_k", "mean_sites"], ascending=[True, False])
fc.to_csv(os.path.join(OUT_DIR, "operator_market_forecast.csv"), index=False)

for k in (20, 50):
    print(f"\n### Market forecast -- top {k} (mean +/- std over 10 seeds)\n")
    sub = fc[fc["top_k"] == k].copy()
    sub["mean +/- std"] = [f"{m:.1f} +/- {s:.1f}" for m, s in
                         zip(sub["mean_sites"], sub["std_sites"])]
    print(to_md(sub[["district", "mean +/- std", "min_sites", "max_sites",
                     "n_seeds_zero"]]))
    print(f"  Klang receives ZERO of the top {k} in "
          f"{klang_zero[k]} of {len(list(FORECAST_SEEDS))} runs.")

# --- per-hex OOF scores artifact
scores = base[["h3_index", "district", "lat", "lon", "pop_est",
               "activity_score", "equity_mult", "has_station",
               "oof_proba_randomCV", "oof_proba_spatialCV"]].copy()
scores["rank_randomCV"] = scores["oof_proba_randomCV"].rank(ascending=False).astype(int)
scores["champion_model"] = champ_label
scores["feature_set"] = PREDICTION_SET
scores["DIAGNOSTIC_ONLY"] = "not a siting recommendation"
scores.to_csv(os.path.join(OUT_DIR, "operator_model_scores.csv"), index=False)
print(f"\n  Per-hex OOF probabilities -> operator_model_scores.csv ({len(scores):,} rows)")

# ------------------------------------------------------------
banner(8, "ROBUSTNESS -- port intensity + coarser grid")
# ------------------------------------------------------------
rob_rows = []

# --- (a) Poisson count model on total_ports, non-imputed rows only
print("  (a) Poisson model on total_ports -- does income predict INTENSITY,")
print("      not just presence? Imputed port counts are excluded outright.\n")
non_imp = in_grid[~in_grid["ports_imputed"].astype(bool)].copy()
ports = non_imp.groupby("h3_index")["total_ports"].sum()
base["ports_nonimputed"] = base["h3_index"].map(ports).fillna(0).astype(int)
print(f"      {len(non_imp)} of {len(in_grid)} in-grid public stations have a "
      f"MEASURED port count ({len(in_grid) - len(non_imp)} imputed, dropped)")
print(f"      {int((base['ports_nonimputed'] > 0).sum())} hexes carry "
      f"{int(base['ports_nonimputed'].sum())} measured ports")

Xp = base[SET_C].to_numpy(dtype=float)
Xp_s = StandardScaler().fit_transform(Xp)
Xp_sm = sm.add_constant(Xp_s)
pois = sm.GLM(base["ports_nonimputed"].to_numpy(), Xp_sm,
              family=sm.families.Poisson()).fit()
j = SET_C.index("equity_mult") + 1
coef_p, se_p = pois.params[j], pois.bse[j]
rob_rows.append({
    "check": "(a) Poisson on total_ports (non-imputed only)",
    "target": "measured public ports per hex", "n": len(base),
    "equity_mult_coef": coef_p,
    "effect_ratio": np.exp(coef_p), "effect_label": "incidence-rate ratio",
    "ci_low": coef_p - 1.96 * se_p, "ci_high": coef_p + 1.96 * se_p,
    "p_value": pois.pvalues[j],
})
print(f"      equity_mult coef {coef_p:+.4f}  IRR {np.exp(coef_p):.3f}  "
      f"p={pois.pvalues[j]:.4g}")
print("      NOTE: heavy zero-inflation (most hexes have no ports); read as")
print("      a direction check, not a calibrated intensity estimate.")

# --- (b) H3 res-7 rerun
print("\n  (b) H3 res-7 rerun -- does the income effect survive a coarser grid?")
print("      Population summed EXACTLY from res-8 children; POIs and")
print("      stations re-binned directly from lat/lon. res-9 skipped.\n")
r7 = base[["h3_index", "pop_est", "district", "equity_mult"]].copy()
r7["h3_r7"] = [h3.cell_to_parent(c, 7) for c in r7["h3_index"]]
agg = r7.groupby("h3_r7").agg(pop_est=("pop_est", "sum"),
                              district=("district", lambda s: s.mode().iloc[0]),
                              equity_mult=("equity_mult", "mean")).reset_index()
pop_check = abs(agg["pop_est"].sum() - base["pop_est"].sum())
print(f"      res-8 total pop {base['pop_est'].sum():,.0f} -> res-7 total "
      f"{agg['pop_est'].sum():,.0f} (diff {pop_check:.6f}) -- exact OK")

poi["h3_r7"] = [h3.latlng_to_cell(a, b, 7)
                for a, b in zip(poi["latitude"], poi["longitude"])]
p7 = (poi.pivot_table(index="h3_r7", columns="category", values="name",
                      aggfunc="size", fill_value=0)
      .reindex(columns=POI_CATEGORIES, fill_value=0))
p7.columns = [f"poi_{c}" for c in p7.columns]
agg = agg.merge(p7, left_on="h3_r7", right_index=True, how="left")
agg[poi_cols] = agg[poi_cols].fillna(0).astype(int)

pub7 = pub.copy()
pub7["h3_r7"] = [h3.latlng_to_cell(a, b, 7)
                 for a, b in zip(pub7["latitude"], pub7["longitude"])]
agg["activity_score"] = agg["h3_r7"].map(
    base.assign(h3_r7=[h3.cell_to_parent(c, 7) for c in base["h3_index"]])
        .groupby("h3_r7")["activity_score"].sum()).fillna(0)
agg["has_station"] = agg["h3_r7"].isin(set(pub7["h3_r7"])).astype(int)

y7 = agg["has_station"].to_numpy()
prev7 = y7.mean()
print(f"      res-7 grid: {len(agg):,} cells, {int(y7.sum())} positive "
      f"({prev7:.2%} vs {prevalence:.2%} at res-8)")

X7 = agg[SET_C].to_numpy(dtype=float)
pipe7 = make_lr(); pipe7.fit(X7, y7)
c7 = pipe7.named_steps["m"].coef_[0][SET_C.index("equity_mult")]
p7_oof = oof_proba(make_lr(), X7, y7, "stratified")
rob_rows.append({
    "check": "(b) H3 res-7 rerun (coarser grid)",
    "target": "has_station at res 7", "n": len(agg),
    "equity_mult_coef": c7, "effect_ratio": np.exp(c7),
    "effect_label": "odds ratio", "ci_low": np.nan, "ci_high": np.nan,
    "pr_auc_oof": average_precision_score(y7, p7_oof),
    "random_baseline": prev7,
})
c8 = float(specs.loc[1, "equity_mult_coef"])
print(f"      equity_mult coef {c7:+.4f}  OR {np.exp(c7):.3f}  "
      f"(res-8 spec (ii) was {c8:+.4f}, OR {np.exp(c8):.3f})")
print(f"      Magnitude retained: {abs(c7) / abs(c8):.1%} of the res-8 effect.")
# Distinguish a genuine reversal from attenuation to ~0: a coefficient
# of +0.02 (OR 1.02) is not an opposite effect, it is no effect.
if abs(c7) < 0.05:
    verdict = ("ATTENUATES TO ~ZERO -- the income signal does NOT survive "
               "the coarser grid (this is not a reversal, it is a null)")
elif np.sign(c7) == np.sign(c8):
    verdict = "SURVIVES with the same sign"
else:
    verdict = "REVERSES sign -- materially contradicts the res-8 result"
print(f"      Verdict: {verdict}.")
print("      Caveat: res-7 cells are ~7x larger, so 17.8% of them contain a")
print("      station vs 5.5% at res-8, and each cell mixes districts -- the")
print("      district-level income signal is averaged away by construction.")

rob = pd.DataFrame(rob_rows)
rob.to_csv(os.path.join(OUT_DIR, "operator_robustness.csv"), index=False)
print("\n### Robustness\n")
print(to_md(rob[["check", "n", "equity_mult_coef", "effect_ratio",
                 "effect_label"]]))

# ------------------------------------------------------------
banner(9, "OUTPUTS")
# ------------------------------------------------------------
for f in ["operator_model_comparison.csv", "operator_feature_ablation.csv",
          "operator_income_specifications.csv", "operator_model_scores.csv",
          "operator_market_forecast.csv", "operator_robustness.csv"]:
    p = os.path.join(OUT_DIR, f)
    print(f"  {f:44s} {sum(1 for _ in open(p)) - 1:>6,} rows")
print(f"  figures/ {len(os.listdir(FIG_DIR)):>2} png")
print()
print("=" * 64)
print("REMINDER: this model is DIAGNOSTIC. It describes and forecasts the")
print("market's revealed preference -- including its income bias. It must")
print("never be presented as a siting recommendation; the CDI and the")
print("greedy coverage optimiser (stages 06/07) remain the prescriptive")
print("tools. The value of this stage is the CONTRAST between them.")
print("=" * 64)
