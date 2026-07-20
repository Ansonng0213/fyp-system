# ============================================================
# FYP2 — POI ACTIVITY PIPELINE (Problem 7 fix)
# Fixes two POI issues and produces the CDI's demand-activity layer:
#
#   1. DEDUP: OSM often tags one real place twice (node + building
#      outline). Named POIs with the same normalized name within
#      ~150 m are collapsed to one record ("Unknown" names exempt —
#      they are legitimately distinct unnamed features).
#   2. DWELL-TIME WEIGHTS: a 7-Eleven is not Mid Valley. Each
#      category gets a charging-opportunity weight based on typical
#      parking dwell time (literature: Andrenacci 2016; Pagany 2019).
#      Weights live in ONE config dict -> stakeholder-configurable,
#      sensitivity-testable (not hidden magic numbers).
#   3. OUTPUT: per-hex weighted activity score on the 4,003-hex
#      master grid + per-category counts (for CDI + dashboard).
#
# Inputs : processed_data/poi_kv_clean.csv
#          processed_data/hex_population_v1.csv   (the master grid)
# Outputs: processed_data/poi_kv_clean_v2.csv
#          processed_data/hex_activity_v1.csv
#          processed_data/audit_poi_dedup.csv
#          processed_data/hex_activity_map.png
# ============================================================

import os
import re
import pandas as pd
import h3

OUT_DIR = "processed_data"
H3_RES = 8          # analysis grid
DEDUP_RES = 10      # ~70 m hex edge -> same-name within same/adjacent r10 cell = dup

# --- Dwell-time charging-opportunity weights (0-1), config-driven ---
# Rationale: weight ~ typical parked duration & public-charging relevance.
# work/residential ~ 8h+ sessions (residential = high-rise w/o home charging,
# the Malaysian condo segment); shopping/entertainment ~ 2-3h; transport
# includes park-and-ride & car parks (prime charging venues); food ~ 1h.
DWELL_WEIGHTS = {
    "work":          1.0,
    "residential":   1.0,
    "shopping":      0.7,
    "entertainment": 0.7,
    "transport":     0.6,
    "education":     0.5,
    "healthcare":    0.5,
    "food_drink":    0.5,
    "exercise":      0.4,
    "community":     0.4,
    "other":         0.2,
}

# ------------------------------------------------------------
# STEP 1 — Load POIs + normalize names
# ------------------------------------------------------------
print("=" * 60)
print("STEP 1 — Loading POIs")
print("=" * 60)

poi = pd.read_csv(os.path.join(OUT_DIR, "poi_kv_clean.csv"))
n0 = len(poi)
print(f"  POIs loaded: {n0:,}")

def norm_name(s):
    s = re.sub(r"[^a-z0-9 ]", " ", str(s).lower())
    return " ".join(s.split())

poi["name_norm"] = poi["name"].map(norm_name)
named = poi["name_norm"].ne("unknown") & poi["name_norm"].ne("")
print(f"  Named POIs (dedup-eligible): {named.sum():,} | unnamed kept as-is: {(~named).sum():,}")

# ------------------------------------------------------------
# STEP 2 — Same-name proximity dedup (node vs building double-tag)
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 2 — Deduplicating double-tagged POIs")
print("=" * 60)

poi["cell_fine"] = [h3.latlng_to_cell(la, lo, DEDUP_RES)
                    for la, lo in zip(poi["latitude"], poi["longitude"])]

# Two same-named POIs are duplicates if their fine cells are identical or adjacent.
# Efficient approximation: also compare on the PARENT cell (res 9) — same name
# in the same ~350 m parent almost always = one real place double-tagged.
poi["cell_parent"] = [h3.cell_to_parent(c, DEDUP_RES - 1) for c in poi["cell_fine"]]

dup_mask = named & poi.duplicated(subset=["name_norm", "category", "cell_parent"], keep="first")
audit = poi.loc[dup_mask, ["name", "category", "district", "latitude", "longitude"]]
audit.to_csv(os.path.join(OUT_DIR, "audit_poi_dedup.csv"), index=False)
poi_v2 = poi[~dup_mask].drop(columns=["name_norm", "cell_fine", "cell_parent"]).copy()

print(f"  Duplicates removed (same name+category within ~350 m): {dup_mask.sum():,}")
print(f"  POIs after dedup: {len(poi_v2):,}  ({dup_mask.sum()/n0*100:.1f}% were double-tags)")
print("  Removed by category:")
print(audit["category"].value_counts().to_string())

# ------------------------------------------------------------
# STEP 3 — Dwell-time weighted activity per hex
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 3 — Weighted activity on the master grid")
print("=" * 60)

poi_v2["h3_index"] = [h3.latlng_to_cell(la, lo, H3_RES)
                      for la, lo in zip(poi_v2["latitude"], poi_v2["longitude"])]
poi_v2["dwell_weight"] = poi_v2["category"].map(DWELL_WEIGHTS).fillna(0.2)

grid = pd.read_csv(os.path.join(OUT_DIR, "hex_population_v1.csv"))

cat_counts = (poi_v2.pivot_table(index="h3_index", columns="category",
                                 aggfunc="size", fill_value=0)
              .add_prefix("poi_"))
activity = poi_v2.groupby("h3_index")["dwell_weight"].sum().rename("activity_score")

hexes = (grid.merge(cat_counts, on="h3_index", how="left")
             .merge(activity, on="h3_index", how="left")
             .fillna(0))
poi_cols = [c for c in hexes.columns if c.startswith("poi_")]
hexes[poi_cols] = hexes[poi_cols].astype(int)

on_grid = int(hexes[poi_cols].to_numpy().sum())
print(f"  POIs landing on the 4,003-hex grid: {on_grid:,} "
      f"({len(poi_v2)-on_grid} fell outside grid edges)")
print(f"  Hexes with activity > 0: {(hexes['activity_score'] > 0).sum():,}")
print(f"\n  Activity score stats (hexes with activity):")
print(hexes.loc[hexes["activity_score"] > 0, "activity_score"].describe().round(1).to_string())
print(f"\n  Top-5 busiest hexes:")
top = hexes.nlargest(5, "activity_score")[["h3_index", "district", "activity_score",
                                           "poi_shopping", "poi_work", "pop_est"]]
print(top.to_string(index=False))

# ------------------------------------------------------------
# STEP 4 — Save + sanity map
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 4 — Saving")
print("=" * 60)

poi_v2.drop(columns=["h3_index", "dwell_weight"]).to_csv(
    os.path.join(OUT_DIR, "poi_kv_clean_v2.csv"), index=False)
hexes.to_csv(os.path.join(OUT_DIR, "hex_activity_v1.csv"), index=False)

try:
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    from shapely.geometry import Polygon

    def cell_polygon(cell):
        try:
            b = h3.cell_to_boundary(cell)
        except AttributeError:
            b = h3.h3_to_geo_boundary(cell)
        return Polygon([(lng, lat) for lat, lng in b])

    gdf = gpd.GeoDataFrame(hexes[["h3_index", "activity_score"]],
                           geometry=[cell_polygon(c) for c in hexes["h3_index"]],
                           crs="EPSG:4326")
    kv = gpd.read_file(os.path.join(OUT_DIR, "kv_districts_dosm.geojson"))
    fig, ax = plt.subplots(figsize=(11, 10))
    plot = gdf[gdf["activity_score"] > 0]
    plot.plot(column="activity_score", cmap="magma", ax=ax,
              norm=LogNorm(vmin=max(plot["activity_score"].min(), 1),
                           vmax=plot["activity_score"].max()),
              legend=True, legend_kwds={"label": "Dwell-weighted activity (log scale)",
                                        "shrink": 0.6})
    kv.boundary.plot(ax=ax, color="white", linewidth=1.0)
    ax.set_title("Dwell-Time Weighted POI Activity — H3 res 8")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "hex_activity_map.png"), dpi=150,
                facecolor="#1a1a2e")
    print("  Map saved -> hex_activity_map.png")
except ImportError:
    print("  (geopandas/matplotlib missing — map skipped)")

print(f"  Saved -> poi_kv_clean_v2.csv, hex_activity_v1.csv, audit_poi_dedup.csv")
