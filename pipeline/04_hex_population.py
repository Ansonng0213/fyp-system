# ============================================================
# FYP2 — HEX-LEVEL POPULATION PIPELINE (Problem 5 fix)
# District population (7 values) -> H3 res-8 hexagons (~0.74 km2)
# via TWO-CLASS DASYMETRIC MAPPING:
#
#   1. Build the H3 r8 hex grid for the 7 study districts from
#      the official DOSM polygons (hex -> district by hex center).
#   2. Evidence layer: residential POIs per hex (+ total POIs).
#   3. Classify hexes: INHABITED if >=1 residential POI or >=3
#      POIs of any kind; else uninhabited (weight 0).
#   4. Weight inhabited hexes: residential_count + 1 (Laplace
#      smoothing), winsorized at the district 99th percentile.
#   5. Allocate: hex_pop = district_pop * weight / sum(weights).
#      District totals are preserved EXACTLY by construction.
#
# Income stays district-level (7 values are too coarse to fake
# hex precision) — copied to hexes as an equity attribute only.
#
# Inputs : processed_data/kv_districts_dosm.geojson
#          processed_data/poi_kv_clean.csv
#          processed_data/population_kv_clean.csv
#          processed_data/income_kv_clean.csv
# Outputs: processed_data/hex_population_v1.csv
#          processed_data/hex_grid_kv.geojson
#          processed_data/hex_population_map.png
# ============================================================

import os
import json
import pandas as pd
import geopandas as gpd
import h3
from shapely.geometry import Polygon

OUT_DIR = "processed_data"
H3_RES = 8

# ------------------------------------------------------------
# STEP 1 — Hex grid from official district polygons
# ------------------------------------------------------------
print("=" * 60)
print(f"STEP 1 — Building H3 res-{H3_RES} grid from DOSM polygons")
print("=" * 60)

kv = gpd.read_file(os.path.join(OUT_DIR, "kv_districts_dosm.geojson"))
dist_col = "district_canon" if "district_canon" in kv.columns else "district"

def polygon_to_cells_compat(geom, res):
    """Cover a shapely (Multi)Polygon with H3 cells (works on h3 v3 & v4)."""
    cells = set()
    geoms = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for g in geoms:
        try:                                   # h3 v4: accepts __geo_interface__
            cells |= set(h3.geo_to_cells(g, res))
        except AttributeError:                 # older APIs
            outer = [(lat, lng) for lng, lat in g.exterior.coords]
            holes = [[(lat, lng) for lng, lat in r.coords] for r in g.interiors]
            try:                               # h3 v4 manual
                cells |= set(h3.polygon_to_cells(h3.LatLngPoly(outer, *holes), res))
            except AttributeError:             # h3 v3
                gj = {"type": "Polygon",
                      "coordinates": [[[lat, lng] for lat, lng in outer]] +
                                     [[[lat, lng] for lat, lng in h] for h in holes]}
                cells |= set(h3.polyfill(gj, res))
    return cells

rows = []
for _, d in kv.iterrows():
    for cell in polygon_to_cells_compat(d.geometry, H3_RES):
        rows.append({"h3_index": cell, "district": d[dist_col]})
hexes = pd.DataFrame(rows).drop_duplicates("h3_index")
print(f"  Hexes generated: {len(hexes):,}")
print(hexes["district"].value_counts().to_string())

# ------------------------------------------------------------
# STEP 2 — Evidence layer: POIs per hex
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 2 — Residential evidence per hex")
print("=" * 60)

poi = pd.read_csv(os.path.join(OUT_DIR, "poi_kv_clean.csv"),
                  usecols=["latitude", "longitude", "category"])
poi["h3_index"] = [h3.latlng_to_cell(la, lo, H3_RES)
                   for la, lo in zip(poi["latitude"], poi["longitude"])]

res_counts = (poi[poi["category"] == "residential"]
              .groupby("h3_index").size().rename("res_poi"))
all_counts = poi.groupby("h3_index").size().rename("total_poi")

hexes = (hexes.merge(res_counts, on="h3_index", how="left")
              .merge(all_counts, on="h3_index", how="left")
              .fillna({"res_poi": 0, "total_poi": 0}))
hexes[["res_poi", "total_poi"]] = hexes[["res_poi", "total_poi"]].astype(int)
print(f"  Residential POIs mapped: {int(hexes['res_poi'].sum()):,}")
print(f"  Hexes with >=1 residential POI: {(hexes['res_poi'] > 0).sum():,}")

# ------------------------------------------------------------
# STEP 3 — Inhabited classification + smoothed weights
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 3 — Two-class dasymetric weights")
print("=" * 60)

hexes["inhabited"] = (hexes["res_poi"] >= 1) | (hexes["total_poi"] >= 3)
hexes["weight"] = 0.0
hexes.loc[hexes["inhabited"], "weight"] = hexes.loc[hexes["inhabited"], "res_poi"] + 1.0

# Winsorize per district at p99 so one mega-condo hex can't absorb a district
cap = hexes.groupby("district")["weight"].transform(lambda s: s.quantile(0.99))
hexes["weight"] = hexes["weight"].clip(upper=cap)

n_inh = int(hexes["inhabited"].sum())
print(f"  Inhabited hexes: {n_inh:,} / {len(hexes):,} ({n_inh/len(hexes)*100:.0f}%)")
print(f"  Uninhabited (forest/plantation/water/industrial-empty): {len(hexes)-n_inh:,}")

# ------------------------------------------------------------
# STEP 4 — Allocate district populations to hexes
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 4 — Population allocation")
print("=" * 60)

pop = pd.read_csv(os.path.join(OUT_DIR, "population_kv_clean.csv"))
inc = pd.read_csv(os.path.join(OUT_DIR, "income_kv_clean.csv"))
hexes = (hexes.merge(pop[["district", "population"]], on="district")
              .merge(inc[["district", "income_median"]], on="district"))

wsum = hexes.groupby("district")["weight"].transform("sum")
hexes["pop_est"] = hexes["population"] * hexes["weight"] / wsum
hexes = hexes.rename(columns={"population": "district_population",
                              "income_median": "district_income_median"})

check = hexes.groupby("district")["pop_est"].sum().round(0).astype(int)
target = pop.set_index("district")["population"]
print("  District-total preservation check (must match exactly):")
for d in check.index:
    ok = "OK " if int(check[d]) == int(target[d]) else "FAIL"
    print(f"    [{ok}] {d}: allocated {check[d]:,} vs actual {target[d]:,}")

print(f"\n  Hex population stats (inhabited hexes):")
print(hexes.loc[hexes['inhabited'], 'pop_est'].describe().round(0).to_string())

# ------------------------------------------------------------
# STEP 5 — Save outputs + sanity-check map
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 5 — Saving")
print("=" * 60)

out_cols = ["h3_index", "district", "res_poi", "total_poi", "inhabited",
            "weight", "pop_est", "district_population", "district_income_median"]
hexes[out_cols].to_csv(os.path.join(OUT_DIR, "hex_population_v1.csv"), index=False)

def cell_polygon(cell):
    try:
        b = h3.cell_to_boundary(cell)          # v4: ((lat,lng),...)
    except AttributeError:
        b = h3.h3_to_geo_boundary(cell)        # v3
    return Polygon([(lng, lat) for lat, lng in b])

hex_gdf = gpd.GeoDataFrame(hexes[out_cols],
                           geometry=[cell_polygon(c) for c in hexes["h3_index"]],
                           crs="EPSG:4326")
hex_gdf.to_file(os.path.join(OUT_DIR, "hex_grid_kv.geojson"), driver="GeoJSON")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    fig, ax = plt.subplots(figsize=(11, 10))
    plot = hex_gdf[hex_gdf["pop_est"] > 0]
    plot.plot(column="pop_est", cmap="viridis", ax=ax,
              norm=LogNorm(vmin=max(plot["pop_est"].min(), 10),
                           vmax=plot["pop_est"].max()),
              legend=True, legend_kwds={"label": "Estimated population per hex (log scale)",
                                        "shrink": 0.6})
    kv.boundary.plot(ax=ax, color="white", linewidth=1.0)
    ax.set_title(f"Dasymetric Population — H3 res {H3_RES} (district totals preserved exactly)")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "hex_population_map.png"), dpi=150,
                facecolor="#1a1a2e")
    print("  Map saved -> hex_population_map.png")
except ImportError:
    print("  (matplotlib missing — map skipped)")

print(f"  Saved -> hex_population_v1.csv ({len(hexes):,} hexes), hex_grid_kv.geojson")
