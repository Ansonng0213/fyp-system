# ============================================================
# SUPPLEMENT EV STATIONS — COMPLETE CLEAN VERSION
# Merges OCM (Open Charge Map) + OSM (OpenStreetMap) data
# Guarantees KV boundary, removes duplicates, assigns districts
# ============================================================

import pandas as pd
import geopandas as gpd
import osmnx as ox
from shapely.ops import unary_union
from shapely.geometry import Point
import os
import warnings
warnings.filterwarnings('ignore')

os.makedirs("raw_data", exist_ok=True)

# ── Step 1: Build exact KV boundary ──────────────────────────
print("=" * 55)
print("STEP 1 — Building Klang Valley boundary")
print("=" * 55)

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
print(f"\n✅ KV boundary ready — {len(boundaries)} districts merged\n")


# ── Step 2: Pull EV stations from OpenStreetMap ──────────────
print("=" * 55)
print("STEP 2 — Pulling EV stations from OpenStreetMap")
print("=" * 55)

df_osm_clean = pd.DataFrame()

try:
    tags = {'amenity': 'charging_station'}
    gdf_osm = ox.features_from_polygon(kv_boundary, tags=tags)
    print(f"  OSM raw results: {len(gdf_osm)}")

    # Fix MultiIndex issue — reset before any processing
    gdf_osm = gdf_osm.reset_index()

    # Extract accurate coordinates using projected CRS
    gdf_osm = gdf_osm.to_crs(epsg=3857)
    gdf_osm['latitude']  = gdf_osm.geometry.centroid.to_crs(epsg=4326).y
    gdf_osm['longitude'] = gdf_osm.geometry.centroid.to_crs(epsg=4326).x
    gdf_osm = gdf_osm.to_crs(epsg=4326)

    df_osm = pd.DataFrame(gdf_osm.drop(columns='geometry'))
    df_osm = df_osm.dropna(subset=['latitude', 'longitude'])
    print(f"  OSM after dropping missing coords: {len(df_osm)}")

    # Helper — safely get column, return default Series if missing
    def safe_col(df, col, default=''):
        if col in df.columns:
            return df[col]
        return pd.Series([default] * len(df), index=df.index)

    # Standardize to match OCM column format
    df_osm_clean = pd.DataFrame({
        'station_id':         'OSM_' + df_osm.index.astype(str),
        'station_name':       safe_col(df_osm, 'name', 'Unknown').fillna('Unknown'),
        'operator':           safe_col(df_osm, 'operator', 'Unknown').fillna('Unknown'),
        'latitude':           df_osm['latitude'],
        'longitude':          df_osm['longitude'],
        'address':            safe_col(df_osm, 'addr:street', '').fillna(''),
        'address2':           '',
        'town':               safe_col(df_osm, 'addr:city', '').fillna(''),
        'postcode':           safe_col(df_osm, 'addr:postcode', '').fillna(''),
        'state_province':     '',
        'status':             'Operational',
        'usage_type':         safe_col(df_osm, 'access', 'Unknown').fillna('Unknown'),
        'is_free':            safe_col(df_osm, 'fee', 'yes').eq('no'),
        'total_ports':        pd.to_numeric(
                                  safe_col(df_osm, 'capacity', 1),
                                  errors='coerce'
                              ).fillna(1).astype(int),
        'fast_charge_ports':  0,
        'max_power_kw':       pd.to_numeric(
                                  safe_col(df_osm, 'charging_station:output', None),
                                  errors='coerce'
                              ),
        'connector_types':    safe_col(df_osm, 'socket:type2', 'Unknown').fillna('Unknown'),
        'date_last_verified': '',
        'date_created':       '',
        'num_comments':       0,
        'source':             'OSM'
    })

    print(f"  ✅ OSM stations cleaned: {len(df_osm_clean)}")

except Exception as e:
    print(f"  ❌ OSM extraction failed: {e}")
    print("     Continuing with OCM data only...")
    df_osm_clean = pd.DataFrame()


# ── Step 3: Load OCM data (always from OCM-only backup) ───────
print(f"\n{'=' * 55}")
print("STEP 3 — Loading OCM stations")
print("=" * 55)

# Always load from the OCM-only file to avoid double-counting
ocm_path = 'raw_data/KV_EV_Stations_OCM_only.csv'
if not os.path.exists(ocm_path):
    print(f"  ⚠️  OCM-only file not found at {ocm_path}")
    print("     Trying KV_Existing_EV_Stations.csv as fallback...")
    ocm_path = 'raw_data/KV_Existing_EV_Stations.csv'

df_ocm = pd.read_csv(ocm_path, low_memory=False)
df_ocm['source'] = 'OCM'
print(f"  ✅ OCM stations loaded: {len(df_ocm)}")


# ── Step 4: Remove duplicates using 50m proximity check ───────
print(f"\n{'=' * 55}")
print("STEP 4 — Removing duplicates (50m proximity check)")
print("=" * 55)

if len(df_osm_clean) > 0:
    # Project both to metres for accurate distance calculation
    gdf_ocm_proj = gpd.GeoDataFrame(
        df_ocm,
        geometry=gpd.points_from_xy(df_ocm['longitude'], df_ocm['latitude']),
        crs='EPSG:4326'
    ).to_crs(epsg=3857)

    gdf_osm_proj = gpd.GeoDataFrame(
        df_osm_clean,
        geometry=gpd.points_from_xy(
            df_osm_clean['longitude'], df_osm_clean['latitude']
        ),
        crs='EPSG:4326'
    ).to_crs(epsg=3857)

    # Flag OSM stations within 50m of any OCM station
    def is_duplicate(osm_point, ocm_gdf, threshold=50):
        return ocm_gdf.geometry.distance(osm_point).min() < threshold

    print("  Checking each OSM station against all OCM stations...")
    osm_is_dup = gdf_osm_proj.geometry.apply(
        lambda pt: is_duplicate(pt, gdf_ocm_proj)
    )

    df_osm_new = df_osm_clean[~osm_is_dup].copy()

    print(f"  OSM total             : {len(df_osm_clean)}")
    print(f"  Duplicates removed    : {osm_is_dup.sum()}")
    print(f"  ✅ New unique stations : {len(df_osm_new)}")

else:
    df_osm_new = pd.DataFrame()
    print("  No OSM data available — skipping deduplication")


# ── Step 5: Assign district labels to new OSM stations ────────
print(f"\n{'=' * 55}")
print("STEP 5 — Assigning district labels to OSM stations")
print("=" * 55)

if len(df_osm_new) > 0:
    kv_districts = {
        "WP Kuala Lumpur": ("Kuala Lumpur, Malaysia",          "W.P. Kuala Lumpur"),
        "WP Putrajaya":    ("Putrajaya, Malaysia",              "W.P. Putrajaya"),
        "Petaling":        ("Petaling, Selangor, Malaysia",     "Selangor"),
        "Hulu Langat":     ("Hulu Langat, Selangor, Malaysia",  "Selangor"),
        "Gombak":          ("Gombak, Selangor, Malaysia",       "Selangor"),
        "Klang":           ("Klang, Selangor, Malaysia",        "Selangor"),
        "Sepang":          ("Sepang, Selangor, Malaysia",       "Selangor"),
    }

    district_rows = []
    for name, (query, state) in kv_districts.items():
        try:
            g = ox.geocode_to_gdf(query)
            district_rows.append({
                'district': name,
                'state':    state,
                'geometry': g.geometry.iloc[0]
            })
            print(f"  ✅ {name}")
        except Exception as e:
            print(f"  ❌ {name} — {e}")

    districts_gdf = gpd.GeoDataFrame(district_rows, crs='EPSG:4326')

    gdf_new = gpd.GeoDataFrame(
        df_osm_new,
        geometry=gpd.points_from_xy(
            df_osm_new['longitude'], df_osm_new['latitude']
        ),
        crs='EPSG:4326'
    )

    joined = gpd.sjoin(
        gdf_new,
        districts_gdf[['district', 'state', 'geometry']],
        how='left',
        predicate='within'
    )

    df_osm_new = pd.DataFrame(
        joined.drop(columns=['geometry', 'index_right'])
    )
    df_osm_new['district'] = df_osm_new['district'].fillna('Outside KV')
    df_osm_new['state']    = df_osm_new['state'].fillna('Unknown')

    print(f"\n  ✅ Districts assigned to all {len(df_osm_new)} new OSM stations")

else:
    print("  No new OSM stations to label")


# ── Step 6: Merge OCM + OSM and save ─────────────────────────
print(f"\n{'=' * 55}")
print("STEP 6 — Merging and saving final dataset")
print("=" * 55)

# Align columns between OCM and OSM before concat
if len(df_osm_new) > 0:
    # Only keep columns that exist in OCM
    shared_cols = [c for c in df_ocm.columns if c in df_osm_new.columns]
    df_combined = pd.concat(
        [df_ocm, df_osm_new[shared_cols]],
        ignore_index=True
    )
else:
    df_combined = df_ocm.copy()

# Save final combined file
final_path = 'raw_data/KV_Existing_EV_Stations.csv'
df_combined.to_csv(final_path, index=False)

# Save OSM-only file if we got new stations
if len(df_osm_new) > 0:
    df_osm_new.to_csv('raw_data/KV_EV_Stations_OSM_only.csv', index=False)
    print("  Saved: raw_data/KV_EV_Stations_OSM_only.csv")

print(f"  ✅ Saved: {final_path}")


# ── Step 7: Final summary ─────────────────────────────────────
print(f"\n{'=' * 55}")
print("FINAL SUMMARY")
print("=" * 55)
print(f"  OCM stations             : {len(df_ocm):,}")
print(f"  New OSM stations added   : {len(df_osm_new):,}")
print(f"  TOTAL combined           : {len(df_combined):,}")
print(f"  Total charging ports     : {df_combined['total_ports'].sum():,}")
print(f"  Fast charge ports        : {df_combined['fast_charge_ports'].sum():,}")

print(f"\n📊 Stations by district:")
print("-" * 45)
dist = df_combined.groupby(['state', 'district']).size() \
                  .reset_index(name='count') \
                  .sort_values('count', ascending=False)
print(dist.to_string(index=False))

print(f"\n📊 Stations by source:")
print("-" * 45)
print(df_combined['source'].value_counts().to_string())

print(f"\n📊 Top 10 operators (combined):")
print("-" * 45)
print(df_combined['operator'].value_counts().head(10).to_string())

print(f"\n📊 Access type breakdown:")
print("-" * 45)
print(df_combined['usage_type'].value_counts().to_string())

print(f"\n{'=' * 55}")
print(f"✅ DONE — Final file: {final_path}")
print(f"   Columns: {list(df_combined.columns)}")
print(f"{'=' * 55}")