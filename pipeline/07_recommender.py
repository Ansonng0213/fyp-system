# ============================================================
# FYP2 — SITE RECOMMENDATION ENGINE  (Problem 10)
#
#   1. GREEDY MAXIMAL-COVERAGE (Church & ReVelle 1974):
#      "covered" = a public charger within 2 km. Each round places
#      one site at the candidate hex covering the most demand-
#      weighted, currently-uncovered population. 20 rounds.
#      Candidates = hexes with real activity (a charger needs a
#      host venue). Existing 376 public stations pre-cover the map.
#   2. K-MEANS COMPARISON (IR deliverable): demand-weighted k=20
#      cluster centers snapped to candidate hexes -> coverage
#      compared head-to-head against greedy.
#   3. DBSCAN DESERT ZONES (IR deliverable, correct job): groups
#      contiguous high-CDI hexes into named desert zones.
#   4. EQUITY IMPACT: population within 2 km of public charging,
#      before vs after, overall + per district.
#
# Inputs : processed_data/hex_cdi_v1.csv
#          processed_data/ev_stations_kv_clean_v2.csv
#          processed_data/kv_districts_dosm.geojson (map)
# Outputs: processed_data/recommended_sites_v1.csv
#          processed_data/desert_zones_v1.csv
#          processed_data/recommendation_map.png
# ============================================================

import os
import numpy as np
import pandas as pd

OUT_DIR = "processed_data"
N_SITES = 20
COVER_KM = 2.0
CDI_ZONE_MIN = 40        # hexes at/above this join desert zones
R_EARTH = 6371.0

def haversine_matrix(lat1, lon1, lat2, lon2):
    la1, lo1 = np.radians(lat1)[:, None], np.radians(lon1)[:, None]
    la2, lo2 = np.radians(lat2)[None, :], np.radians(lon2)[None, :]
    a = (np.sin((la2 - la1) / 2) ** 2 +
         np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2)
    return (2 * R_EARTH * np.arcsin(np.sqrt(a))).astype(np.float32)

# ------------------------------------------------------------
# STEP 1 — Load + initial coverage state
# ------------------------------------------------------------
print("=" * 60)
print("STEP 1 — Loading + initial coverage")
print("=" * 60)

hx = pd.read_csv(os.path.join(OUT_DIR, "hex_cdi_v1.csv"))
st = pd.read_csv(os.path.join(OUT_DIR, "ev_stations_kv_clean_v2.csv"))
st = st[st["is_public_facing"] & st["is_operational"]]

hx["covered"] = hx["nearest_station_km"] <= COVER_KM
total_pop = hx["pop_est"].sum()
pop_cov0 = hx.loc[hx["covered"], "pop_est"].sum()
print(f"  Hexes: {len(hx):,} | existing public stations: {len(st)}")
print(f"  BEFORE: {pop_cov0:,.0f} of {total_pop:,.0f} people within {COVER_KM:.0f} km "
      f"of public charging = {pop_cov0/total_pop*100:.1f}%")

cand = hx[hx["activity_score"] > 0].reset_index(drop=True)      # needs a host venue
print(f"  Candidate hexes (activity > 0): {len(cand):,}")

D = haversine_matrix(cand["lat"].to_numpy(), cand["lon"].to_numpy(),
                     hx["lat"].to_numpy(), hx["lon"].to_numpy())   # (cand, all)
within = D <= COVER_KM

# ------------------------------------------------------------
# STEP 2 — Greedy maximal coverage
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print(f"STEP 2 — Greedy placement of {N_SITES} sites")
print("=" * 60)

demand = hx["demand_pressure"].to_numpy()
pop = hx["pop_est"].to_numpy()
uncovered = ~hx["covered"].to_numpy()
chosen, rows = [], []

for rank in range(1, N_SITES + 1):
    gains = (within & uncovered[None, :]) @ demand
    gains[chosen] = -1
    best = int(np.argmax(gains))
    newly = within[best] & uncovered
    r = cand.loc[best]
    rows.append({
        "rank": rank, "h3_index": r["h3_index"], "district": r["district"],
        "lat": round(r["lat"], 5), "lon": round(r["lon"], 5),
        "cdi": round(r["cdi"], 1),
        "pop_newly_covered": int(pop[newly].sum()),
        "demand_gain": round(float(demand[newly].sum()), 2),
        "nearest_existing_km": r["nearest_station_km"],
        "hex_pop": int(r["pop_est"]), "hex_activity": round(r["activity_score"], 0),
    })
    uncovered = uncovered & ~within[best]
    chosen.append(best)
    cum = total_pop - pop[uncovered & ~hx["covered"].to_numpy()].sum()

rec = pd.DataFrame(rows)
pop_cov1 = pop_cov0 + rec["pop_newly_covered"].sum()
print(rec[["rank", "district", "cdi", "pop_newly_covered", "nearest_existing_km"]]
      .head(10).to_string(index=False))
print(f"\n  AFTER {N_SITES} sites: {pop_cov1:,.0f} people covered = "
      f"{pop_cov1/total_pop*100:.1f}%  (+{(pop_cov1-pop_cov0)/total_pop*100:.1f} pts, "
      f"+{pop_cov1-pop_cov0:,.0f} people)")

print("\n  Sites by district:")
print(rec["district"].value_counts().to_string())

# Per-district before/after coverage
hx["covered_after"] = ~uncovered | hx["covered"]
per_d = (hx.groupby("district")
         .apply(lambda g: pd.Series({
             "before_%": g.loc[g["covered"], "pop_est"].sum() / g["pop_est"].sum() * 100,
             "after_%": g.loc[g["covered_after"], "pop_est"].sum() / g["pop_est"].sum() * 100}),
                include_groups=False)
         .round(1).sort_values("before_%"))
print("\n  Population within 2 km of public charging, by district:")
print(per_d.to_string())

# ------------------------------------------------------------
# STEP 3 — K-Means comparison (same budget of 20 sites)
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 3 — K-Means comparison")
print("=" * 60)

from sklearn.cluster import KMeans
u0 = ~hx["covered"].to_numpy()
pts = hx.loc[u0, ["lat", "lon"]].to_numpy()
w = hx.loc[u0, "demand_pressure"].to_numpy() + 1e-9
km = KMeans(n_clusters=N_SITES, random_state=42, n_init=10).fit(pts, sample_weight=w)

# snap centers to nearest candidate hex, then score coverage identically
Dc = haversine_matrix(km.cluster_centers_[:, 0], km.cluster_centers_[:, 1],
                      cand["lat"].to_numpy(), cand["lon"].to_numpy())
snap = np.unique(Dc.argmin(axis=1))
ucov = u0.copy()
for s in snap:
    ucov = ucov & ~within[s]
km_gain = pop[u0 & ~ucov].sum()
greedy_gain = rec["pop_newly_covered"].sum()
print(f"  Greedy coverage gain : {greedy_gain:,.0f} people")
print(f"  K-Means coverage gain: {km_gain:,.0f} people "
      f"({km_gain/greedy_gain*100:.0f}% of greedy, {len(snap)} unique sites)")
print("  -> greedy optimizes coverage directly; K-Means finds demand gravity centers.")

# ------------------------------------------------------------
# STEP 4 — DBSCAN desert zones
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print(f"STEP 4 — DBSCAN desert zones (CDI >= {CDI_ZONE_MIN})")
print("=" * 60)

from sklearn.cluster import DBSCAN
dz = hx[hx["cdi"] >= CDI_ZONE_MIN].reset_index(drop=True)
db = DBSCAN(eps=1.6 / R_EARTH, min_samples=3, metric="haversine").fit(
    np.radians(dz[["lat", "lon"]].to_numpy()))
dz["zone"] = db.labels_
zones = (dz[dz["zone"] >= 0].groupby("zone")
         .agg(hexes=("h3_index", "size"), population=("pop_est", "sum"),
              district=("district", lambda s: s.mode()[0]),
              mean_cdi=("cdi", "mean"),
              lat=("lat", "mean"), lon=("lon", "mean"))
         .sort_values("population", ascending=False).round(1))
print(f"  Desert hexes: {len(dz)} -> {len(zones)} contiguous zones "
      f"({(dz['zone'] == -1).sum()} isolated)")
print(zones.head(8).to_string())

# ------------------------------------------------------------
# STEP 5 — Save + map
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 5 — Saving")
print("=" * 60)

rec.to_csv(os.path.join(OUT_DIR, "recommended_sites_v1.csv"), index=False)
zones.reset_index().to_csv(os.path.join(OUT_DIR, "desert_zones_v1.csv"), index=False)

try:
    import geopandas as gpd
    import h3
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from shapely.geometry import Polygon

    def cell_polygon(cell):
        b = h3.cell_to_boundary(cell)
        return Polygon([(lng, lat) for lat, lng in b])

    gdf = gpd.GeoDataFrame(hx[["h3_index", "cdi"]],
                           geometry=[cell_polygon(c) for c in hx["h3_index"]],
                           crs="EPSG:4326")
    kv = gpd.read_file(os.path.join(OUT_DIR, "kv_districts_dosm.geojson"))
    fig, ax = plt.subplots(figsize=(11, 10))
    gdf[gdf["cdi"] > 0].plot(column="cdi", cmap="inferno", ax=ax, vmin=0, vmax=100)
    kv.boundary.plot(ax=ax, color="white", linewidth=1.0)
    ax.scatter(st["longitude"], st["latitude"], s=5, c="#00e5ff",
               alpha=0.7, linewidths=0, label="Existing public stations")
    ax.scatter(rec["lon"], rec["lat"], s=140, c="#00ff88", marker="*",
               edgecolors="black", linewidths=0.6, label=f"Recommended sites (top {N_SITES})")
    for _, r in rec.iterrows():
        ax.annotate(str(r["rank"]), (r["lon"], r["lat"]),
                    fontsize=6.5, ha="center", va="center", color="black")
    ax.legend(loc="lower left", frameon=False, labelcolor="white")
    ax.set_title("Recommended Charging Sites — Greedy Maximal Coverage over CDI")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "recommendation_map.png"), dpi=150,
                facecolor="#1a1a2e")
    print("  Map saved -> recommendation_map.png")
except ImportError:
    print("  (geopandas/matplotlib/h3 missing — map skipped)")

print("  Saved -> recommended_sites_v1.csv, desert_zones_v1.csv")
