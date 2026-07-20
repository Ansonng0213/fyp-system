# ============================================================
# FYP2 — CORRECTED EV STATION CLEANING PIPELINE (v2)
# Fixes Problem 1: bounding-box district misassignment
#   -> replaced with polygon spatial join on OFFICIAL DOSM
#      administrative district boundaries (same agency as the
#      income & population datasets -> consistent naming).
# Fixes Problem 2: public/private contamination
#   -> usage_type RETAINED, access_type derived,
#      [Restricted] condo chargers flagged, status harmonized,
#      honest imputation flags instead of silent median fills.
# Extra: second-pass fuzzy cross-source deduplication.
#
# Input : raw_data/KV_Master_Fused_EV_Stations_FullDetails.csv (545 rows)
# Output: processed_data/ev_stations_kv_clean_v2.csv
#         processed_data/kv_districts_dosm.geojson
#         processed_data/audit_district_changes.csv
#         processed_data/audit_dedup_pairs.csv
# ============================================================

import os
import re
import difflib
import requests
import pandas as pd
import geopandas as gpd

RAW_STATIONS = "raw_data/KV_Master_Fused_EV_Stations_FullDetails.csv"
OLD_CLEAN    = "processed_data/ev_stations_kv_clean.csv"   # v1, for before/after
OUT_DIR      = "processed_data"
DOSM_GEOJSON_URL = ("https://raw.githubusercontent.com/dosm-malaysia/"
                    "data-open/main/datasets/geodata/administrative_2_district.geojson")
DOSM_LOCAL   = os.path.join(OUT_DIR, "kv_districts_dosm.geojson")

STUDY = {  # DOSM name -> (canonical district, canonical state)
    "W.P. Kuala Lumpur": ("WP Kuala Lumpur", "W.P. Kuala Lumpur"),
    "W.P. Putrajaya":    ("WP Putrajaya",    "W.P. Putrajaya"),
    "Petaling":          ("Petaling",        "Selangor"),
    "Ulu Langat":        ("Hulu Langat",     "Selangor"),
    "Gombak":            ("Gombak",          "Selangor"),
    "Klang":             ("Klang",           "Selangor"),
    "Sepang":            ("Sepang",          "Selangor"),
}

# ------------------------------------------------------------
# STEP 1 — Official district polygons (download once, cache)
# ------------------------------------------------------------
print("=" * 60)
print("STEP 1 — Loading official DOSM district boundaries")
print("=" * 60)

if os.path.exists(DOSM_LOCAL):
    kv_gdf = gpd.read_file(DOSM_LOCAL)
    print(f"  Loaded cached: {DOSM_LOCAL}")
else:
    r = requests.get(DOSM_GEOJSON_URL, timeout=120)
    r.raise_for_status()
    tmp = "dosm_all_districts.geojson"
    with open(tmp, "wb") as f:
        f.write(r.content)
    all_gdf = gpd.read_file(tmp)
    kv_gdf = all_gdf[all_gdf["district"].isin(STUDY.keys())].copy()
    kv_gdf["district_canon"] = kv_gdf["district"].map(lambda d: STUDY[d][0])
    kv_gdf["state_canon"]    = kv_gdf["district"].map(lambda d: STUDY[d][1])
    kv_gdf = kv_gdf[["district_canon", "state_canon", "geometry"]].reset_index(drop=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    kv_gdf.to_file(DOSM_LOCAL, driver="GeoJSON")
    print(f"  Downloaded + saved study-area boundaries -> {DOSM_LOCAL}")

print(f"  Districts loaded: {sorted(kv_gdf['district_canon'].tolist())}")

# ------------------------------------------------------------
# STEP 2 — Load RAW fused stations (keep ALL columns this time)
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 2 — Loading raw fused station data")
print("=" * 60)

df = pd.read_csv(RAW_STATIONS)
df = df.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
print(f"  Raw fused records: {len(df)}")
print(f"  By source: {df['source'].value_counts().to_dict()}")

# ------------------------------------------------------------
# STEP 3 — District assignment via polygon spatial join (ALL rows)
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 3 — Polygon spatial join (replaces bounding boxes)")
print("=" * 60)

pts = gpd.GeoDataFrame(
    df.copy(),
    geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
    crs="EPSG:4326",
)

joined = gpd.sjoin(
    pts,
    kv_gdf[["district_canon", "state_canon", "geometry"]],
    how="left",
    predicate="within",
)
# guard against rare multi-polygon double matches
joined = joined[~joined.index.duplicated(keep="first")]

inside = joined["district_canon"].notna()
print(f"  Matched inside a district polygon : {inside.sum()}")
print(f"  Outside all polygons (edge cases) : {(~inside).sum()}")

# Fallback: nearest district within 2 km for boundary-precision strays
if (~inside).any():
    strays = joined[~inside].drop(columns=["index_right", "district_canon", "state_canon"])
    strays_m = strays.to_crs(3857)
    kv_m = kv_gdf.to_crs(3857)
    near = gpd.sjoin_nearest(
        strays_m, kv_m[["district_canon", "state_canon", "geometry"]],
        how="left", max_distance=2000, distance_col="dist_to_district_m",
    )
    near = near[~near.index.duplicated(keep="first")]
    for idx, row in near.iterrows():
        joined.loc[idx, "district_canon"] = row["district_canon"]
        joined.loc[idx, "state_canon"] = row["state_canon"]
    still_lost = joined["district_canon"].isna().sum()
    print(f"  Recovered via nearest (<2 km)     : {near['district_canon'].notna().sum()}")
    print(f"  Dropped (>2 km outside study area): {still_lost}")

df = pd.DataFrame(joined.drop(columns=["geometry", "index_right"], errors="ignore"))
df["district_old"] = df["district"]          # keep v1 label for audit
df["district"] = df["district_canon"]
df["state"] = df["state_canon"]
df = df.drop(columns=["district_canon", "state_canon"])
df = df.dropna(subset=["district"]).reset_index(drop=True)

changed = df[df["district_old"].notna() & (df["district_old"] != df["district"])]
print(f"\n  Stations whose district label CHANGED vs v1 source file: {len(changed)}")

# ------------------------------------------------------------
# STEP 4 — Status harmonization
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 4 — Harmonizing operational status")
print("=" * 60)

status_map = {
    "OPERATIONAL": "Operational",
    "Operational": "Operational",
    "CLOSED_TEMPORARILY": "Closed (temporary)",
    "CLOSED_PERMANENTLY": "Closed (permanent)",
}
df["status"] = df["status"].map(status_map).fillna(df["status"]).fillna("Unknown")
df["is_operational"] = df["status"].eq("Operational")
print(df["status"].value_counts().to_string())

# ------------------------------------------------------------
# STEP 5 — Access classification (Problem 2 core fix)
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 5 — Classifying public vs private access")
print("=" * 60)

PRIVATE_USAGE = {
    "Private - Restricted Access",
    "Private - For Staff, Visitors or Customers",
    "private",
}
PUBLIC_USAGE = {
    "Public",
    "Public - Membership Required",     # app-based access = normal for MY public chargers
    "Public - Pay At Location",
    "Public - Notice Required",
    "yes",                              # OSM access=yes
    "customers",                        # mall/hotel customer access -> public-facing
}

def classify_access(row):
    name = str(row.get("station_name", ""))
    usage = row.get("usage_type")
    if "[restricted]" in name.lower():
        return "Private (restricted)"
    if isinstance(usage, str):
        if usage in PRIVATE_USAGE:
            return "Private (restricted)"
        if usage in PUBLIC_USAGE:
            return "Public"
    # Google rows have no usage_type; Google EVCS listings are public-facing map POIs
    if row.get("source") == "Google_Maps":
        return "Public (assumed - Google listing)"
    return "Unknown"

df["access_type"] = df.apply(classify_access, axis=1)
df["is_public_facing"] = ~df["access_type"].str.startswith("Private")
print(df["access_type"].value_counts().to_string())

# ------------------------------------------------------------
# STEP 6 — Deduplication (exact + fuzzy cross-source)
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 6 — Deduplication")
print("=" * 60)

before = len(df)
df = df.drop_duplicates(subset=["latitude", "longitude"], keep="first").reset_index(drop=True)
print(f"  Exact-coordinate duplicates removed: {before - len(df)}")

STOP = re.compile(r"\b(charging|station|charger|ev|electric|vehicle|the|by|at)\b")
def norm_name(s):
    s = re.sub(r"\[.*?\]", " ", str(s).lower())
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = STOP.sub(" ", s)
    return " ".join(s.split())

def name_sim(a, b):
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return 0.0
    ta, tb = set(na.split()), set(nb.split())
    jac = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    seq = difflib.SequenceMatcher(None, na, nb).ratio()
    return max(jac, seq)

SRC_PRIORITY = {"OCM": 0, "Google_Maps": 1, "OSM": 2}   # keep lower number
gdf_m = gpd.GeoDataFrame(
    df, geometry=gpd.points_from_xy(df["longitude"], df["latitude"]), crs=4326
).to_crs(3857)

pairs = gpd.sjoin(
    gdf_m, gdf_m[["source", "station_name", "operator", "geometry"]].copy(),
    how="inner", predicate="dwithin", distance=120,
)
pairs = pairs[pairs.index < pairs["index_right"]]                     # unique pairs
pairs = pairs[pairs["source_left"] != pairs["source_right"]]          # cross-source only

drop_idx, audit = set(), []
for i, row in pairs.iterrows():
    j = row["index_right"]
    if i in drop_idx or j in drop_idx:
        continue
    same_op = (
        str(row["operator_left"]).lower() == str(row["operator_right"]).lower()
        and str(row["operator_left"]).lower() not in ("unknown", "nan", "")
    )
    sim = name_sim(row["station_name_left"], row["station_name_right"])
    if same_op or sim >= 0.75:
        keep, drop = (i, j) if SRC_PRIORITY[row["source_left"]] <= SRC_PRIORITY[row["source_right"]] else (j, i)
        drop_idx.add(drop)
        audit.append({
            "kept_name": df.loc[keep, "station_name"], "kept_source": df.loc[keep, "source"],
            "dropped_name": df.loc[drop, "station_name"], "dropped_source": df.loc[drop, "source"],
            "name_similarity": round(sim, 2), "same_operator": same_op,
            "district": df.loc[keep, "district"],
        })

pd.DataFrame(audit).to_csv(os.path.join(OUT_DIR, "audit_dedup_pairs.csv"), index=False)
df = df.drop(index=drop_idx).reset_index(drop=True)
print(f"  Fuzzy cross-source duplicates removed: {len(drop_idx)} (see audit_dedup_pairs.csv)")
print(f"  Stations after dedup: {len(df)}")

# ------------------------------------------------------------
# STEP 7 — Honest imputation with flags
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 7 — Imputation with transparency flags")
print("=" * 60)

df["ports_imputed"] = df["total_ports"].isna()
df["total_ports"] = df["total_ports"].fillna(df["total_ports"].median()).astype(int)
df["power_known"] = df["max_power_kw"].notna()        # NO fabricated power values
print(f"  total_ports imputed (median): {df['ports_imputed'].sum()} rows (flagged)")
print(f"  max_power_kw known: {df['power_known'].sum()} | unknown kept as NaN: {(~df['power_known']).sum()}")

# ------------------------------------------------------------
# STEP 8 — Final schema + save
# ------------------------------------------------------------
keep_cols = [
    "station_id", "station_name", "operator", "latitude", "longitude",
    "address", "town", "postcode", "status", "is_operational",
    "usage_type", "access_type", "is_public_facing", "is_free",
    "total_ports", "ports_imputed", "fast_charge_ports",
    "max_power_kw", "power_known", "connector_types",
    "district", "state", "source",
]
df_final = df[[c for c in keep_cols if c in df.columns]].copy()
out_path = os.path.join(OUT_DIR, "ev_stations_kv_clean_v2.csv")
df_final.to_csv(out_path, index=False)

changed_audit = df[df["district_old"].notna() & (df["district_old"] != df["district"])][
    ["station_name", "latitude", "longitude", "source", "district_old", "district"]
]
changed_audit.to_csv(os.path.join(OUT_DIR, "audit_district_changes.csv"), index=False)

print(f"\n{'=' * 60}")
print("FINAL SUMMARY (v2)")
print("=" * 60)
print(f"  Total stations: {len(df_final)}")
print(f"\n  ALL stations by district:")
print(df_final["district"].value_counts().to_string())
print(f"\n  PUBLIC-FACING OPERATIONAL stations by district:")
pub = df_final[df_final["is_public_facing"] & df_final["is_operational"]]
print(pub["district"].value_counts().to_string())
print(f"\n  Private (restricted) by district:")
print(df_final[~df_final["is_public_facing"]]["district"].value_counts().to_string())
print(f"\n  Saved -> {out_path}")
print(f"  Audits -> audit_district_changes.csv, audit_dedup_pairs.csv")
