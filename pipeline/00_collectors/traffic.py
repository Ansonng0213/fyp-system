# ============================================================
# DATASET 4 — IMPROVED VERSION
# Fixes: missing names, missing categories, garbage poi_types
# ============================================================

import pandas as pd
import osmnx as ox
import geopandas as gpd
from shapely.ops import unary_union
import os
import warnings
warnings.filterwarnings('ignore')
ox.settings.timeout = 300
os.makedirs("raw_data", exist_ok=True)

# ── Build KV boundary (same as before) ───────────────────────
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
print("✅ Boundary ready\n")

# ── IMPROVED tags — adds missing Malaysian-specific POIs ──────
tags = {
    'shop': [
        'mall', 'supermarket', 'department_store',
        'hypermarket', 'convenience', 'wholesale',
        'clothes', 'electronics', 'hardware', 'furniture'
    ],
    'office': True,
    'building': [
        'commercial', 'office', 'retail', 'government',
        'apartments', 'residential', 'industrial'
    ],
    'landuse': ['commercial', 'retail', 'industrial', 'residential'],
    'amenity': [
        # Food & drink (added Malaysian-specific)
        'restaurant', 'food_court', 'cafe', 'fast_food',
        'bar', 'pub', 'ice_cream',
        # Healthcare
        'hospital', 'clinic', 'pharmacy', 'dentist', 'doctors',
        # Education
        'university', 'college', 'school', 'library',
        'kindergarten', 'language_school', 'music_school',
        # Community & gathering
        'community_centre', 'place_of_worship',
        'events_venue', 'townhall', 'post_office',
        # Transport hubs (critical for EV demand)
        'bus_station', 'ferry_terminal', 'parking',
        # Fuel & services
        'fuel', 'bank', 'atm',
        # Entertainment
        'cinema', 'theatre', 'nightclub',
        # Markets (very Malaysian)
        'marketplace',
    ],
    # Transport
    'railway': ['station', 'halt', 'subway_entrance'],
    'highway': ['rest_area', 'services'],
    # Exercise & activity (expanded)
    'leisure': [
        'sports_centre', 'stadium', 'park',
        'golf_course', 'swimming_pool',
        'fitness_centre',          # gym
        'pitch',                   # football fields
        'track',                   # running track
        'recreation_ground',
    ],
    'tourism': [
        'hotel', 'attraction', 'museum',
        'gallery', 'theme_park', 'zoo',
        'hostel', 'guest_house'
    ],
}

# ── Extract POIs ──────────────────────────────────────────────
print("Extracting POIs from Klang Valley boundary...")
print("(This may take 10-15 minutes...)\n")

try:
    gdf_pois = ox.features_from_polygon(kv_boundary, tags=tags)

    cols_to_keep = [
        'geometry', 'name', 'amenity', 'shop', 'office',
        'building', 'tourism', 'leisure', 'railway',
        'highway', 'landuse'
    ]
    cols_available = [c for c in cols_to_keep if c in gdf_pois.columns]
    gdf_pois = gdf_pois[cols_available]

    # Extract coordinates
    gdf_pois = gdf_pois.to_crs(epsg=3857)
    gdf_pois['latitude']  = gdf_pois.geometry.centroid.to_crs(epsg=4326).y
    gdf_pois['longitude'] = gdf_pois.geometry.centroid.to_crs(epsg=4326).x
    gdf_pois = gdf_pois.to_crs(epsg=4326)

    # ── IMPROVED poi_type logic ───────────────────────────────
    # Priority order: specific types first, generic last
    def get_poi_type(row):
        priority = [
            'amenity','shop','leisure','tourism',
            'railway','highway','office','landuse','building'
        ]
        for col in priority:
            val = row.get(col)
            if val and pd.notna(val) and val not in [True, False, 'yes']:
                return str(val)
        # Handle True (office=True means it's an office building)
        if row.get('office') is True or row.get('office') == True:
            return 'office_building'
        return 'other'

    gdf_pois['poi_type'] = gdf_pois.apply(get_poi_type, axis=1)

    # ── IMPROVED: Add human-readable category ─────────────────
    # Groups fine-grained types into broader demand categories
    category_map = {
        # Food & drink
        'restaurant': 'food_drink', 'cafe': 'food_drink',
        'fast_food': 'food_drink', 'food_court': 'food_drink',
        'bar': 'food_drink', 'pub': 'food_drink',
        'marketplace': 'food_drink',
        # Shopping
        'mall': 'shopping', 'supermarket': 'shopping',
        'convenience': 'shopping', 'department_store': 'shopping',
        'hypermarket': 'shopping', 'wholesale': 'shopping',
        'retail': 'shopping', 'clothes': 'shopping',
        'electronics': 'shopping',
        # Work & commercial
        'commercial': 'work', 'office': 'work',
        'office_building': 'work', 'industrial': 'work',
        'company': 'work', 'government': 'work',
        # Residential
        'apartments': 'residential', 'residential': 'residential',
        # Healthcare
        'hospital': 'healthcare', 'clinic': 'healthcare',
        'pharmacy': 'healthcare', 'dentist': 'healthcare',
        # Education
        'university': 'education', 'college': 'education',
        'school': 'education', 'library': 'education',
        'kindergarten': 'education',
        # Exercise & leisure
        'sports_centre': 'exercise', 'gym': 'exercise',
        'fitness_centre': 'exercise', 'swimming_pool': 'exercise',
        'stadium': 'exercise', 'park': 'exercise',
        'golf_course': 'exercise', 'pitch': 'exercise',
        # Community & gathering
        'place_of_worship': 'community', 'community_centre': 'community',
        'events_venue': 'community', 'townhall': 'community',
        # Transport hubs
        'station': 'transport', 'bus_station': 'transport',
        'train_station': 'transport', 'parking': 'transport',
        'fuel': 'transport', 'rest_area': 'transport',
        # Entertainment
        'hotel': 'entertainment', 'cinema': 'entertainment',
        'theatre': 'entertainment', 'attraction': 'entertainment',
        'museum': 'entertainment', 'theme_park': 'entertainment',
        'zoo': 'entertainment',
    }
    gdf_pois['category'] = gdf_pois['poi_type'].map(category_map)\
                                               .fillna('other')

    df_pois = pd.DataFrame(gdf_pois.drop(columns='geometry'))
    df_pois = df_pois.dropna(subset=['latitude', 'longitude'])

    # ── Assign district labels ────────────────────────────────
    print("\n⏳ Assigning district labels...")
    kv_districts = {
        "WP Kuala Lumpur": ("Kuala Lumpur, Malaysia",        "W.P. Kuala Lumpur"),
        "WP Putrajaya":    ("Putrajaya, Malaysia",            "W.P. Putrajaya"),
        "Petaling":        ("Petaling, Selangor, Malaysia",   "Selangor"),
        "Hulu Langat":     ("Hulu Langat, Selangor, Malaysia","Selangor"),
        "Gombak":          ("Gombak, Selangor, Malaysia",     "Selangor"),
        "Klang":           ("Klang, Selangor, Malaysia",      "Selangor"),
        "Sepang":          ("Sepang, Selangor, Malaysia",     "Selangor"),
    }
    district_rows = []
    for district_name, (query, state_name) in kv_districts.items():
        try:
            gdf_d = ox.geocode_to_gdf(query)
            district_rows.append({
                'district': district_name,
                'state':    state_name,
                'geometry': gdf_d.geometry.iloc[0]
            })
            print(f"  ✅ {district_name}")
        except Exception as e:
            print(f"  ❌ {district_name} — {e}")

    districts_gdf = gpd.GeoDataFrame(district_rows, crs="EPSG:4326")
    gdf_pts = gpd.GeoDataFrame(
        df_pois,
        geometry=gpd.points_from_xy(df_pois['longitude'], df_pois['latitude']),
        crs="EPSG:4326"
    )
    gdf_labeled = gpd.sjoin(
        gdf_pts,
        districts_gdf[['district', 'state', 'geometry']],
        how='left', predicate='within'
    )
    df_final = pd.DataFrame(
        gdf_labeled.drop(columns=['geometry', 'index_right'])
    )
    df_final['district'] = df_final['district'].fillna('Outside KV')
    df_final['state']    = df_final['state'].fillna('Unknown')

    df_final.to_csv('raw_data/KV_Demand_Proxies.csv', index=False)

    # ── Summary ───────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"✅ Extraction complete!")
    print(f"   Total POIs     : {len(df_final):,}")
    print(f"   Named POIs     : {df_final['name'].notna().sum():,}")
    print(f"\n📊 By demand category:")
    print("-"*40)
    print(df_final['category'].value_counts().to_string())
    print(f"\n📊 By district:")
    print("-"*40)
    print(df_final.groupby(['state','district']).size()\
                  .reset_index(name='count')\
                  .sort_values('count', ascending=False)\
                  .to_string(index=False))
    print(f"{'='*55}")
    print(f"\n✅ Saved → raw_data/KV_Demand_Proxies.csv")
    print(f"   Columns: {list(df_final.columns)}")

except Exception as e:
    print(f"❌ Failed: {e}")