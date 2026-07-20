# ============================================================
# DATASET 5 — Existing EV Charging Stations
# Uses BOUNDING BOX query — single API call covers all KV
# Much more efficient and accurate than grid approach
# ============================================================

import requests
import pandas as pd
import osmnx as ox
from shapely.ops import unary_union
from shapely.geometry import Point
import geopandas as gpd
import os

os.makedirs("raw_data", exist_ok=True)

import os
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.environ["OCM_API_KEY"]  # set in .env (never commit)

# ── Step 1: Build exact KV boundary ──────────────────────────
print("Building Klang Valley boundary...")
kv_areas = [
    "Kuala Lumpur, Malaysia",
    "Putrajaya, Malaysia",
    "Petaling, Selangor, Malaysia",
    "Hulu Langat, Selangor, Malaysia",
    "Gombak, Selangor, Malaysia",
    "Klang, Selangor, Malaysia",
    "Sepang, Selangor, Malaysia"
]
boundaries = []
for area in kv_areas:
    try:
        gdf = ox.geocode_to_gdf(area)
        boundaries.append(gdf.geometry.iloc[0])
        print(f"  ✅ {area}")
    except Exception as e:
        print(f"  ❌ {area} — {e}")

kv_boundary = unary_union(boundaries)
minx, miny, maxx, maxy = kv_boundary.bounds
print(f"\n✅ KV boundary ready")
print(f"   Bounding box: ({miny:.4f},{minx:.4f}) → ({maxy:.4f},{maxx:.4f})\n")

# ── Step 2: Single bounding box API call ─────────────────────
# Format: minLat,minLon,maxLat,maxLon
print("="*55)
print("Fetching ALL EV stations within KV bounding box...")
print("="*55)

url    = "https://api.openchargemap.io/v3/poi/"
params = {
    "output":       "json",
    "key":          API_KEY,
    "boundingbox":  f"({miny},{minx}),({maxy},{maxx})",
    "maxresults":   10000,      # Set high — KV unlikely to exceed this
    "countrycode":  "MY",
    "statustypeid": 50,         # Operational stations only
    "verbose":      True,       # Full details including connections
    "compact":      False,      # Full data, not compact
}

try:
    resp = requests.get(url, params=params, timeout=60)
    data = resp.json()
    print(f"  Raw results from API: {len(data)}")
except Exception as e:
    print(f"❌ API call failed: {e}")
    exit()

# ── Step 3: Parse all available fields ───────────────────────
print("\n⏳ Parsing station data...")
all_stations = []

for s in data:
    addr   = s.get("AddressInfo",  {}) or {}
    op     = s.get("OperatorInfo", {}) or {}
    status = s.get("StatusType",   {}) or {}
    usage  = s.get("UsageType",    {}) or {}
    conns  = s.get("Connections",  []) or []
    sub    = s.get("SubmissionStatus", {}) or {}

    # ── Connection details ────────────────────────────────────
    total_ports      = len(conns)
    fast_charge      = sum(
        1 for c in conns
        if (c.get("Level") or {}).get("IsFastChargeCapable", False)
    )
    # Get unique connector types
    conn_types = list(set(
        (c.get("ConnectionType") or {}).get("Title", "Unknown")
        for c in conns
        if c.get("ConnectionType")
    ))
    # Max power output across all connections (kW)
    power_vals = [
        c.get("PowerKW") for c in conns
        if c.get("PowerKW") is not None
    ]
    max_power_kw = max(power_vals) if power_vals else None

    all_stations.append({
        # Identity
        "station_id":        s.get("ID"),
        "station_name":      addr.get("Title",          "Unknown"),
        "operator":          op.get("Title",            "Unknown"),

        # Location — exact coordinates
        "latitude":          addr.get("Latitude"),
        "longitude":         addr.get("Longitude"),
        "address":           addr.get("AddressLine1",   ""),
        "address2":          addr.get("AddressLine2",   ""),
        "town":              addr.get("Town",           ""),
        "postcode":          addr.get("Postcode",       ""),
        "state_province":    addr.get("StateOrProvince",""),

        # Status & access
        "status":            status.get("Title",        "Unknown"),
        "usage_type":        usage.get("Title",         "Unknown"),
        "is_free":           (usage.get("Title") or "").lower() in [
                                 "free", "free to use", "public - free"
                             ],

        # Equipment details
        "total_ports":       total_ports,
        "fast_charge_ports": fast_charge,
        "max_power_kw":      max_power_kw,
        "connector_types":   ", ".join(conn_types) if conn_types else "Unknown",

        # Data quality
        "date_last_verified": s.get("DateLastVerified", ""),
        "date_created":       s.get("DateCreated",      ""),
        "num_comments":       s.get("NumberOfComments", 0),
    })

# ── Step 4: Convert to DataFrame ─────────────────────────────
df = pd.DataFrame(all_stations)
df = df.dropna(subset=["latitude", "longitude"])

# ── Step 5: Filter to EXACT KV boundary polygon ───────────────
print(f"⏳ Filtering to exact KV polygon boundary...")
mask = df.apply(
    lambda row: kv_boundary.contains(
        Point(row["longitude"], row["latitude"])
    ), axis=1
)
df_kv      = df[mask].copy()
df_outside = df[~mask]
print(f"  Total from API       : {len(df):,}")
print(f"  Inside KV boundary   : {len(df_kv):,}")
print(f"  Outside KV (dropped) : {len(df_outside):,}")

# ── Step 6: Assign district labels ───────────────────────────
print("\n⏳ Assigning district labels...")
kv_districts = {
    "WP Kuala Lumpur": ("Kuala Lumpur, Malaysia",         "W.P. Kuala Lumpur"),
    "WP Putrajaya":    ("Putrajaya, Malaysia",             "W.P. Putrajaya"),
    "Petaling":        ("Petaling, Selangor, Malaysia",    "Selangor"),
    "Hulu Langat":     ("Hulu Langat, Selangor, Malaysia", "Selangor"),
    "Gombak":          ("Gombak, Selangor, Malaysia",      "Selangor"),
    "Klang":           ("Klang, Selangor, Malaysia",       "Selangor"),
    "Sepang":          ("Sepang, Selangor, Malaysia",      "Selangor"),
}
district_rows = []
for name, (query, state) in kv_districts.items():
    try:
        g = ox.geocode_to_gdf(query)
        district_rows.append({
            "district": name,
            "state":    state,
            "geometry": g.geometry.iloc[0]
        })
        print(f"  ✅ {name}")
    except Exception as e:
        print(f"  ❌ {name} — {e}")

districts_gdf = gpd.GeoDataFrame(district_rows, crs="EPSG:4326")
gdf_pts = gpd.GeoDataFrame(
    df_kv,
    geometry=gpd.points_from_xy(df_kv["longitude"], df_kv["latitude"]),
    crs="EPSG:4326"
)
gdf_labeled = gpd.sjoin(
    gdf_pts,
    districts_gdf[["district", "state", "geometry"]],
    how="left", predicate="within"
)
df_final = pd.DataFrame(
    gdf_labeled.drop(columns=["geometry", "index_right"])
)
df_final["district"] = df_final["district"].fillna("Outside KV")
df_final["state"]    = df_final["state"].fillna("Unknown")

# ── Step 7: Save ──────────────────────────────────────────────
output = "raw_data/KV_Existing_EV_Stations.csv"
df_final.to_csv(output, index=False)

# ── Step 8: Summary ───────────────────────────────────────────
print(f"\n{'='*55}")
print(f"✅ EV Stations saved → {output}")
print(f"\n   Total stations       : {len(df_final):,}")
print(f"   Total ports          : {df_final['total_ports'].sum():,}")
print(f"   Fast charge ports    : {df_final['fast_charge_ports'].sum():,}")
print(f"   Free stations        : {df_final['is_free'].sum():,}")

print(f"\n📊 Stations by district:")
print("-"*40)
dist = df_final.groupby(["state","district"]).size()\
               .reset_index(name="count")\
               .sort_values("count", ascending=False)
print(dist.to_string(index=False))

print(f"\n📊 Top 10 operators:")
print("-"*40)
print(df_final["operator"].value_counts().head(10).to_string())

print(f"\n📊 Connector types found:")
print("-"*40)
all_conn = []
for ct in df_final["connector_types"].dropna():
    all_conn.extend([c.strip() for c in ct.split(",")])
from collections import Counter
for conn, cnt in Counter(all_conn).most_common(10):
    print(f"  {conn:<35} {cnt:>4}")

print(f"\n📊 Power levels:")
print("-"*40)
print(df_final["max_power_kw"].describe().round(1).to_string())
print(f"{'='*55}")
print(f"\n   Columns: {list(df_final.columns)}")