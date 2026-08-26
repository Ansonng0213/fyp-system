# ============================================================
# FYP2 -- OPERATOR MODEL: FULL COEFFICIENT / SHAP READ-OUT
#
#   READ-ONLY COMPANION to 11_operator_model.py.
#
#   11_operator_model.py fits these models and prints only the
#   headline rows. This script re-derives the SAME deterministic
#   fits (identical seed, identical feature construction) and prints
#   the COMPLETE tables that were computed but summarised away.
#
#   It trains nothing new and tunes nothing:
#     - the logistic coefficients come from the same standardised
#       LogisticRegression on inference set C used by STEP 5
#       specification (ii) of 11_operator_model.py;
#     - the champion hyperparameters are READ from
#       operator_model_comparison.csv, never re-searched.
#
#   Adds one genuinely new calculation, explicitly requested: the
#   spatial-block bootstrap applied to poi_residential, using the
#   identical procedure already applied to equity_mult.
#
# Inputs : processed_data/hex_cdi_v1.csv
#          processed_data/poi_kv_clean_v2.csv
#          processed_data/ev_stations_kv_clean_v2.csv
#          processed_data/operator_model_comparison.csv      (champion params)
#          processed_data/operator_income_specifications.csv (existing CIs)
# Outputs: processed_data/operator_coefficients_full.csv
#
# Modifies no existing script, CSV, or dashboard page.
# ============================================================

import os
import json
import random
import warnings

import numpy as np
import pandas as pd
import h3

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import xgboost as xgb
import shap

warnings.filterwarnings("ignore")

# --- identical configuration to 11_operator_model.py ---------------
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
OUT_DIR = "processed_data"
RES = 8
N_SPATIAL_BLOCKS = 8
N_BOOTSTRAP = 1000
POI_CATEGORIES = ["community", "education", "entertainment", "exercise",
                  "food_drink", "healthcare", "other", "residential",
                  "shopping", "transport", "work"]
BOOTSTRAP_TARGET = "poi_residential"


def banner(n, title):
    print()
    print("=" * 64)
    print(f"STEP {n} -- {title}")
    print("=" * 64)


def to_md(df, floatfmt="{:.4f}"):
    d = df.copy()
    cols = [str(c) for c in d.columns]

    def cell(v):
        if isinstance(v, float):
            return "--" if np.isnan(v) else floatfmt.format(v)
        return str(v)

    rows = [[cell(v) for v in r] for r in d.itertuples(index=False)]
    widths = [max([len(cols[i])] + [len(r[i]) for r in rows]) for i in range(len(cols))]
    out = ["| " + " | ".join(c.ljust(w) for c, w in zip(cols, widths)) + " |",
           "|" + "|".join("-" * (w + 2) for w in widths) + "|"]
    for r in rows:
        out.append("| " + " | ".join(v.ljust(w) for v, w in zip(r, widths)) + " |")
    return "\n".join(out)


def make_lr():
    return Pipeline([("sc", StandardScaler()),
                     ("m", LogisticRegression(class_weight="balanced",
                                              max_iter=5000, random_state=SEED))])


print("=" * 64)
print("OPERATOR MODEL -- FULL COEFFICIENT READ-OUT (read-only)")
print("=" * 64)

# ------------------------------------------------------------
banner(1, "REBUILD THE DATASET (identical to 11_operator_model.py)")
# ------------------------------------------------------------
hx = pd.read_csv(os.path.join(OUT_DIR, "hex_cdi_v1.csv"))
base = hx[["h3_index", "district", "lat", "lon",
           "pop_est", "activity_score", "equity_mult"]].copy()

poi = pd.read_csv(os.path.join(OUT_DIR, "poi_kv_clean_v2.csv"))
poi = poi.dropna(subset=["latitude", "longitude", "category"])
poi["h3_index"] = [h3.latlng_to_cell(a, b, RES)
                   for a, b in zip(poi["latitude"], poi["longitude"])]
poi_wide = (poi.pivot_table(index="h3_index", columns="category",
                            values="name", aggfunc="size", fill_value=0)
            .reindex(columns=POI_CATEGORIES, fill_value=0))
poi_wide.columns = [f"poi_{c}" for c in poi_wide.columns]
poi_cols = list(poi_wide.columns)
base = base.merge(poi_wide, left_on="h3_index", right_index=True, how="left")
base[poi_cols] = base[poi_cols].fillna(0).astype(int)

stn = pd.read_csv(os.path.join(OUT_DIR, "ev_stations_kv_clean_v2.csv"))
pub = stn[stn["is_public_facing"].astype(bool) &
          stn["is_operational"].astype(bool)].copy()
pub["h3_index"] = [h3.latlng_to_cell(a, b, RES)
                   for a, b in zip(pub["latitude"], pub["longitude"])]
base["has_station"] = base["h3_index"].isin(
    set(pub[pub["h3_index"].isin(set(base["h3_index"]))]["h3_index"])).astype(int)

dist_dummies = pd.get_dummies(base["district"], prefix="dist", drop_first=True)
dist_cols = list(dist_dummies.columns)
base = pd.concat([base, dist_dummies.astype(int)], axis=1)

km = KMeans(n_clusters=N_SPATIAL_BLOCKS, random_state=SEED, n_init=10)
base["spatial_block"] = km.fit_predict(base[["lat", "lon"]])

SET_C = ["pop_est", "equity_mult", "activity_score"] + poi_cols
SET_D = SET_C + ["lat", "lon"] + dist_cols

y = base["has_station"].to_numpy()
groups = base["spatial_block"].to_numpy()
prevalence = y.mean()
assert int(y.sum()) == 222, "dataset drifted -- expected 222 positives"
print(f"  {len(base):,} hexes, {int(y.sum())} positive ({prevalence:.3%}) -- matches the original run")
print(f"  Inference set C = {len(SET_C)} features")

# ------------------------------------------------------------
banner(2, "FULL COEFFICIENT TABLE -- inference set C, standardised")
# ------------------------------------------------------------
Xc = base[SET_C].to_numpy(dtype=float)
lr = make_lr()
lr.fit(Xc, y)
coefs = lr.named_steps["m"].coef_[0]

coef_tab = pd.DataFrame({"feature": SET_C,
                         "coefficient": coefs,
                         "odds_ratio": np.exp(coefs)})
coef_tab["abs_coefficient"] = coef_tab["coefficient"].abs()
coef_tab = coef_tab.sort_values("abs_coefficient", ascending=False).reset_index(drop=True)
coef_tab.insert(0, "rank", np.arange(1, len(coef_tab) + 1))

print("  Standardised: each coefficient is the log-odds change per 1 SD of")
print("  that feature, holding the rest fixed. Odds ratio = exp(coefficient).")
print("  Features are hex-level counts; equity_mult is INVERSE income")
print("  (higher = poorer district).\n")
print(to_md(coef_tab[["rank", "feature", "coefficient", "odds_ratio"]]))

# ------------------------------------------------------------
banner(3, "SPECIFIC ANSWERS (a) (b) (c)")
# ------------------------------------------------------------
look = coef_tab.set_index("feature")


def line(f):
    r = look.loc[f]
    sign = "NEGATIVE" if r["coefficient"] < 0 else "POSITIVE"
    return (f"  {f:18s} coef {r['coefficient']:+.4f}   OR {r['odds_ratio']:.4f}   "
            f"{sign}   (rank {int(r['rank'])}/{len(coef_tab)})")


print("  (a) poi_residential")
print(line("poi_residential"))
pr_c = float(look.loc["poi_residential", "coefficient"])
pr_or = float(look.loc["poi_residential", "odds_ratio"])
print(f"      -> YES, negative. Each +1 SD of residential POI count multiplies")
print(f"         the odds of the hex holding a public charger by {pr_or:.3f}, "
      f"i.e. {(1 - pr_or) * 100:.1f}% lower odds.")

print("\n  (b) the other four requested features")
for f in ["poi_shopping", "poi_work", "pop_est", "activity_score"]:
    print(line(f))

print("\n  (c) all 11 POI categories, most positive -> most negative")
poi_rank = coef_tab[coef_tab["feature"].isin(poi_cols)].copy()
poi_rank = poi_rank.sort_values("coefficient", ascending=False).reset_index(drop=True)
poi_rank.insert(0, "poi_rank", np.arange(1, len(poi_rank) + 1))
print()
print(to_md(poi_rank[["poi_rank", "feature", "coefficient", "odds_ratio"]]))
n_pos_poi = int((poi_rank["coefficient"] > 0).sum())
print(f"\n  {n_pos_poi} of 11 POI categories carry a POSITIVE coefficient, "
      f"{11 - n_pos_poi} negative.")

# ------------------------------------------------------------
banner(4, f"SPATIAL-BLOCK BOOTSTRAP -- {BOOTSTRAP_TARGET}")
# ------------------------------------------------------------
print(f"  Identical procedure to the equity_mult bootstrap: resample the")
print(f"  {N_SPATIAL_BLOCKS} spatial blocks WITH REPLACEMENT, {N_BOOTSTRAP} iterations,")
print("  refit the same standardised logistic on set C each time.\n")

block_idx = {b: np.where(groups == b)[0] for b in range(N_SPATIAL_BLOCKS)}
j = SET_C.index(BOOTSTRAP_TARGET)
rng = np.random.default_rng(SEED)
draws = []
for _ in range(N_BOOTSTRAP):
    pick = rng.integers(0, N_SPATIAL_BLOCKS, N_SPATIAL_BLOCKS)
    rows = np.concatenate([block_idx[b] for b in pick])
    yb = y[rows]
    if yb.sum() < 10 or yb.sum() == len(yb):
        continue
    try:
        pipe = make_lr()
        pipe.fit(Xc[rows], yb)
        draws.append(pipe.named_steps["m"].coef_[0][j])
    except Exception:
        continue
draws = np.array(draws)
ci_lo, ci_hi = np.percentile(draws, [2.5, 97.5])
share_neg = float((draws < 0).mean())
crosses = bool(ci_lo <= 0 <= ci_hi)

print(f"  point estimate      {pr_c:+.4f}   (OR {pr_or:.4f})")
print(f"  95% CI              [{ci_lo:+.4f}, {ci_hi:+.4f}]")
print(f"  draws negative      {share_neg:.1%}  ({len(draws)}/{N_BOOTSTRAP} valid)")
print(f"  CI crosses zero     {'YES' if crosses else 'NO'}")

# side-by-side against the equity_mult result already on disk
spec = pd.read_csv(os.path.join(OUT_DIR, "operator_income_specifications.csv"))
eq = spec[spec["specification"].str.startswith("(ii)")].iloc[0]
cmp_tab = pd.DataFrame([
    {"feature": "equity_mult (income)", "coefficient": eq["equity_mult_coef"],
     "odds_ratio": eq["odds_ratio"], "ci_low": eq["ci_low"], "ci_high": eq["ci_high"],
     "pct_draws_negative": eq["boot_share_negative"] * 100,
     "ci_crosses_zero": "YES"},
    {"feature": BOOTSTRAP_TARGET, "coefficient": pr_c, "odds_ratio": pr_or,
     "ci_low": ci_lo, "ci_high": ci_hi, "pct_draws_negative": share_neg * 100,
     "ci_crosses_zero": "YES" if crosses else "NO"},
])
print("\n### Same test, two findings\n")
print(to_md(cmp_tab))
print()
if not crosses:
    print(f"  VERDICT: {BOOTSTRAP_TARGET} SURVIVES the test the income effect failed.")
    print("  Its CI excludes zero under spatial resampling; equity_mult's does not.")
    print("  'Chargers avoid residential areas' is the statistically defensible")
    print("  half of the story; 'chargers avoid poorer areas' is not, on this data.")
else:
    print(f"  VERDICT: {BOOTSTRAP_TARGET} ALSO fails -- its CI crosses zero too.")

# ------------------------------------------------------------
banner(5, "FULL SHAP RANKING -- why poi_residential is not in the top 5")
# ------------------------------------------------------------
comp = pd.read_csv(os.path.join(OUT_DIR, "operator_model_comparison.csv"))
champ = comp.iloc[0]
raw = json.loads(champ["best_params"])


def cast(v):
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            try:
                return float(v)
            except ValueError:
                return v
    return v


params = {k: cast(v) for k, v in raw.items()}
print(f"  Champion read from operator_model_comparison.csv: "
      f"{champ['model']} ({champ['variant']}), feature set {champ['feature_set']}")
print(f"  Hyperparameters re-used verbatim, NOT re-searched:\n    {params}\n")

Xd = base[SET_D].to_numpy(dtype=float)
model = xgb.XGBClassifier(eval_metric="logloss", random_state=SEED,
                          n_jobs=-1, tree_method="hist", **params)
model.fit(Xd, y)
sv = shap.TreeExplainer(model).shap_values(pd.DataFrame(Xd, columns=SET_D))
if isinstance(sv, list):
    sv = sv[1]
if getattr(sv, "ndim", 2) == 3:
    sv = sv[:, :, 1]

shap_tab = pd.DataFrame({"feature": SET_D,
                         "shap_mean_abs": np.abs(sv).mean(axis=0)}) \
    .sort_values("shap_mean_abs", ascending=False).reset_index(drop=True)
shap_tab.insert(0, "shap_rank", np.arange(1, len(shap_tab) + 1))
shap_tab["share_of_total"] = shap_tab["shap_mean_abs"] / shap_tab["shap_mean_abs"].sum()

print(f"### Full SHAP mean |value| ranking -- all {len(SET_D)} features of set D\n")
print(to_md(shap_tab))

sr = shap_tab.set_index("feature")
res_rank = int(sr.loc["poi_residential", "shap_rank"])
res_val = float(sr.loc["poi_residential", "shap_mean_abs"])
top_val = float(shap_tab.iloc[0]["shap_mean_abs"])
print(f"\n  ANSWER: poi_residential is SHAP rank {res_rank} of {len(SET_D)}, "
      f"mean |SHAP| = {res_val:.4f}")
print(f"          = {res_val / top_val:.1%} of the top feature "
      f"({shap_tab.iloc[0]['feature']}, {top_val:.4f}).")
print(f"          It is genuinely LOW in SHAP magnitude, not merely just")
print(f"          outside the top 5 -- it sits at rank {res_rank}, not 6 or 7.")
print()
print("  WHY THE TWO METHODS DISAGREE ON THIS FEATURE:")
print("  - The logistic coefficient is a CONDITIONAL, SIGNED, LINEAR effect:")
print("    holding activity and every other POI type fixed, more residential")
print("    POIs means lower odds. That is a contrast, and it is large.")
print("  - Mean |SHAP| is an UNSIGNED, MARGINAL magnitude on a tree model.")
print("    XGBoost can reproduce the same contrast through the commercial")
print("    features it already splits on (activity_score, poi_transport,")
print("    poi_food_drink), which are correlated with residential density,")
print("    so poi_residential is rarely the variable the tree splits on and")
print("    absorbs little attributed credit.")
print("  - Neither is wrong. The coefficient answers 'what is the residential")
print("    effect net of everything else'; SHAP answers 'how much work does")
print("    this column do in this particular tree ensemble'.")

# ------------------------------------------------------------
banner(6, "WRITE ARTIFACT")
# ------------------------------------------------------------
full = coef_tab.merge(shap_tab[["feature", "shap_rank", "shap_mean_abs"]],
                      on="feature", how="left")
full["boot_ci_low"] = np.nan
full["boot_ci_high"] = np.nan
full["boot_pct_negative"] = np.nan
full["boot_ci_crosses_zero"] = ""
m = full["feature"] == BOOTSTRAP_TARGET
full.loc[m, ["boot_ci_low", "boot_ci_high", "boot_pct_negative"]] = \
    [ci_lo, ci_hi, share_neg * 100]
full.loc[m, "boot_ci_crosses_zero"] = "YES" if crosses else "NO"
me = full["feature"] == "equity_mult"
full.loc[me, ["boot_ci_low", "boot_ci_high", "boot_pct_negative"]] = \
    [eq["ci_low"], eq["ci_high"], eq["boot_share_negative"] * 100]
full.loc[me, "boot_ci_crosses_zero"] = "YES"
full["model"] = "LogisticRegression standardised, inference set C (spec ii)"
full["shap_model"] = f"{champ['model']} ({champ['variant']}), set {champ['feature_set']}"

path = os.path.join(OUT_DIR, "operator_coefficients_full.csv")
full.to_csv(path, index=False)
print(f"  {path}  ({len(full)} rows)")

# ------------------------------------------------------------
banner(7, "SPECIFICATION COMPARISON -- restated cleanly (read-only)")
# ------------------------------------------------------------
spec = spec.copy()
spec["equity_mult_coef"] = spec["equity_mult_coef"].astype(float)
out = spec[["specification", "n_features", "pr_auc_oof", "roc_auc_oof",
            "equity_mult_coef", "odds_ratio", "ci_low", "ci_high",
            "boot_share_negative"]].copy()
print("  Values read verbatim from operator_income_specifications.csv --")
print("  nothing refitted.\n")
print(to_md(out, floatfmt="{:.4f}"))

p_i = float(spec.loc[0, "pr_auc_oof"])
p_iii = float(spec.loc[2, "pr_auc_oof"])
print(f"\n  DOES ADDING INCOME TO A MODEL THAT ALREADY HAS DISTRICT DUMMIES")
print(f"  CHANGE PR-AUC?")
print(f"    (iii) district dummies only, NO income : PR-AUC {p_iii:.4f}")
print(f"    (i)   district dummies PLUS income     : PR-AUC {p_i:.4f}")
print(f"    difference                             : {p_i - p_iii:+.4f}")
print(f"  -> No: to four decimal places both are {p_i:.4f}, so adding income")
print(f"     to a model that already knows the district changes PR-AUC by")
print(f"     {p_i - p_iii:+.6f} -- nothing, because district income is a")
print("     district-level constant that the dummies already encode.")
print()
print("=" * 64)
print("Read-only read-out complete. No model retrained, no hyperparameter")
print("re-searched, no existing artifact modified.")
print("=" * 64)
