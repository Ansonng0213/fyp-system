# ============================================================
# FYP2 — VALIDATION PIPELINE  (Problem 11)
#
#   A. HOLDOUT RECALL: hide 20% of real public stations (10 random
#      trials). Do our demand layers predict where they are?
#        predictors tested per trial:
#          pop_only      = pop_n                     (naive baseline)
#          demand_blend  = 0.5*pop_n + 0.5*act_n     (our demand layer)
#          operator_cdi  = demand_blend * gap(80%)   (forward-looking)
#        metric: recall@k% = share of hidden stations whose hex is in
#        the top-k% of hexes ranked by the predictor.
#        chance level for uniform-random placement = k%.
#   B. COVERAGE-RADIUS CURVE: population within r km of public
#      charging for r in 0.25..5.0 (overall + Klang vs KL contrast).
#   C. CAPACITY ADEQUACY: people/port and EVs/port, KV + district.
#   D. OPERATOR CROSS-CHECK TEMPLATE: 8 sample zones (4 KL core,
#      4 desert) prefilled with our counts, columns for manual
#      JomCharge / Gentari / ChargEV counts.
#
# Inputs : processed_data/hex_cdi_v1.csv
#          processed_data/ev_stations_kv_clean_v2.csv
#          processed_data/jpj_kv_monthly_v2.csv
# Outputs: processed_data/validation_holdout_results.csv
#          processed_data/coverage_radius_curve.csv (+ .png)
#          processed_data/capacity_adequacy.csv
#          processed_data/operator_crosscheck_template.csv
# ============================================================

import os
import numpy as np
import pandas as pd
import h3

OUT_DIR = "processed_data"
SEEDS = range(10)
HOLDOUT_FRAC = 0.20
TOP_KS = [0.05, 0.10, 0.20]
DECAY_KM = 1.5
R_EARTH = 6371.0
rng_global = np.random.default_rng(2026)

def haversine_matrix(lat1, lon1, lat2, lon2):
    la1, lo1 = np.radians(lat1)[:, None], np.radians(lon1)[:, None]
    la2, lo2 = np.radians(lat2)[None, :], np.radians(lon2)[None, :]
    a = (np.sin((la2 - la1) / 2) ** 2 +
         np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2)
    return (2 * R_EARTH * np.arcsin(np.sqrt(a))).astype(np.float32)

def norm01(x):
    cap = np.quantile(x, 0.99)
    return np.clip(x, None, cap) / cap if cap > 0 else x * 0

# ------------------------------------------------------------
# STEP 1 — Load
# ------------------------------------------------------------
print("=" * 60)
print("STEP 1 — Loading")
print("=" * 60)

hx = pd.read_csv(os.path.join(OUT_DIR, "hex_cdi_v1.csv"))
st = pd.read_csv(os.path.join(OUT_DIR, "ev_stations_kv_clean_v2.csv"))
pub = st[st["is_public_facing"] & st["is_operational"]].reset_index(drop=True)
pub["h3_index"] = [h3.latlng_to_cell(la, lo, 8)
                   for la, lo in zip(pub["latitude"], pub["longitude"])]
n_hex = len(hx)
hex_pos = {c: i for i, c in enumerate(hx["h3_index"])}
print(f"  Hexes: {n_hex:,} | public operational stations: {len(pub)}")

D_all = haversine_matrix(hx["lat"].to_numpy(), hx["lon"].to_numpy(),
                         pub["latitude"].to_numpy(), pub["longitude"].to_numpy())

pop_n = hx["pop_n"].to_numpy()
act_n = hx["act_n"].to_numpy()
demand_blend = 0.5 * pop_n + 0.5 * act_n

# ------------------------------------------------------------
# STEP 2 — Holdout recall experiment
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print(f"STEP 2 — Holdout recall ({len(SEEDS)} trials, hide {HOLDOUT_FRAC:.0%})")
print("=" * 60)

rows = []
n_hold = int(round(len(pub) * HOLDOUT_FRAC))
for seed in SEEDS:
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(pub))
    hold, keep = idx[:n_hold], idx[n_hold:]

    gap = 1 - norm01(np.exp(-D_all[:, keep] / DECAY_KM).sum(axis=1))
    predictors = {"pop_only": pop_n,
                  "demand_blend": demand_blend,
                  "operator_cdi": demand_blend * gap}

    hidden_hex_ids = pub.loc[hold, "h3_index"]
    hidden_rows = np.array([hex_pos[c] for c in hidden_hex_ids if c in hex_pos])

    for pname, score in predictors.items():
        order = np.argsort(-score)
        rank_of = np.empty(n_hex, dtype=int)
        rank_of[order] = np.arange(n_hex)
        for k in TOP_KS:
            cutoff = int(n_hex * k)
            recall = (rank_of[hidden_rows] < cutoff).mean()
            rows.append({"seed": seed, "predictor": pname,
                         "top_k_pct": int(k * 100), "recall": recall})

res = pd.DataFrame(rows)
summary = (res.groupby(["predictor", "top_k_pct"])["recall"]
           .agg(["mean", "std"]).round(3).reset_index())
summary["chance"] = summary["top_k_pct"] / 100
summary["lift_vs_chance"] = (summary["mean"] / summary["chance"]).round(1)
print(summary.to_string(index=False))
res.to_csv(os.path.join(OUT_DIR, "validation_holdout_results.csv"), index=False)

# ------------------------------------------------------------
# STEP 3 — Coverage-radius curve
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 3 — Coverage-radius curve")
print("=" * 60)

radii = np.arange(0.25, 5.01, 0.25)
total_pop = hx["pop_est"].sum()
curve = []
for r in radii:
    m = hx["nearest_station_km"] <= r
    row = {"radius_km": r,
           "kv_pct": hx.loc[m, "pop_est"].sum() / total_pop * 100}
    for d in ["Klang", "WP Kuala Lumpur"]:
        g = hx[hx["district"] == d]
        row[f"{d.split()[-1].lower()}_pct"] = (
            g.loc[g["nearest_station_km"] <= r, "pop_est"].sum()
            / g["pop_est"].sum() * 100)
    curve.append(row)
curve = pd.DataFrame(curve).round(1)
curve.to_csv(os.path.join(OUT_DIR, "coverage_radius_curve.csv"), index=False)
print(curve[curve["radius_km"].isin([0.5, 1.0, 2.0, 3.0, 5.0])].to_string(index=False))

# ------------------------------------------------------------
# STEP 4 — Capacity adequacy
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 4 — Capacity adequacy")
print("=" * 60)

kv_series = pd.read_csv(os.path.join(OUT_DIR, "jpj_kv_monthly_v2.csv"))
ev_stock = kv_series["kv_central"].sum()
ports_d = pub.groupby("district")["total_ports"].sum()
pop_d = hx.groupby("district")["pop_est"].sum()
cap = pd.DataFrame({"public_ports": ports_d, "population": pop_d.round(0)})
cap["people_per_port"] = (cap["population"] / cap["public_ports"]).round(0)
cap = cap.sort_values("people_per_port", ascending=False)
total_ports = int(pub["total_ports"].sum())
print(cap.to_string())
print(f"\n  KV total: {total_ports} ports | {total_pop/total_ports:,.0f} people/port | "
      f"{ev_stock/total_ports:.0f} EVs/port (guideline ~10-20)")
print(f"  Robustness: even at 2x true ports -> {ev_stock/(2*total_ports):.0f} EVs/port (still above guideline)")
cap.to_csv(os.path.join(OUT_DIR, "capacity_adequacy.csv"))

# ------------------------------------------------------------
# STEP 5 — Operator cross-check template (manual task for user)
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 5 — Operator cross-check template")
print("=" * 60)

kl_zones = (hx[hx["district"] == "WP Kuala Lumpur"]
            .nlargest(4, "activity_score")[["h3_index", "district", "lat", "lon"]])
desert_zones = (hx[hx["district"].isin(["Klang", "Gombak", "Hulu Langat"])]
                .nlargest(4, "cdi")[["h3_index", "district", "lat", "lon"]])
zones = pd.concat([kl_zones.assign(zone_type="served_KL"),
                   desert_zones.assign(zone_type="desert")]).reset_index(drop=True)

Dz = haversine_matrix(zones["lat"].to_numpy(), zones["lon"].to_numpy(),
                      pub["latitude"].to_numpy(), pub["longitude"].to_numpy())
zones["our_public_stations_2km"] = (Dz <= 2.0).sum(axis=1)
for col in ["jomcharge_count", "gentari_count", "chargev_count", "other_count", "notes"]:
    zones[col] = ""
zones["maps_link"] = ("https://www.google.com/maps/@" +
                      zones["lat"].round(5).astype(str) + "," +
                      zones["lon"].round(5).astype(str) + ",14z")
zones.to_csv(os.path.join(OUT_DIR, "operator_crosscheck_template.csv"), index=False)
print(zones[["zone_type", "district", "lat", "lon", "our_public_stations_2km"]]
      .to_string(index=False))
print("\n  TO DO (manual, ~1 hour): open each zone in the JomCharge, Gentari and")
print("  ChargEV apps/maps, count stations within ~2 km of the center point, fill")
print("  the columns. Result = estimated recall of our dataset, served vs desert.")

# ------------------------------------------------------------
# STEP 6 — Coverage curve chart
# ------------------------------------------------------------
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(curve["radius_km"], curve["kv_pct"], lw=2.4, color="#1f77b4",
            label="Klang Valley overall")
    ax.plot(curve["radius_km"], curve["lumpur_pct"], lw=1.8, color="#2ca02c",
            ls="--", label="WP Kuala Lumpur")
    ax.plot(curve["radius_km"], curve["klang_pct"], lw=1.8, color="#d62728",
            ls="--", label="Klang")
    ax.axvline(2.0, color="#888", lw=0.8, ls=":")
    ax.text(2.05, 8, "2 km (analysis threshold)", fontsize=8, color="#666")
    ax.set_xlabel("Distance to nearest public charger (km)")
    ax.set_ylabel("% of population covered")
    ax.set_title("Charging Access — Coverage vs Distance Threshold")
    ax.set_ylim(0, 102)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "coverage_curve.png"), dpi=150)
    print(f"\n  Chart saved -> coverage_curve.png")
except ImportError:
    pass

print("  Saved -> validation_holdout_results.csv, coverage_radius_curve.csv,")
print("           capacity_adequacy.csv, operator_crosscheck_template.csv")
