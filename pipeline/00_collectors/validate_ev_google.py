# ============================================================
# GOOGLE MAPS MICRO-GRID EXTRACTION SCRIPT
# Purpose: Bypasses the 20-result limit by using a dense 
# 1.5km micro-grid across the Klang Valley.
# ============================================================

import requests
import pandas as pd
import geopandas as gpd
import osmnx as ox
from shapely.ops import unary_union
from shapely.geometry import Point
import numpy as np
import time
import os

os.makedirs("raw_data", exist_ok=True)

# ── Your Google Maps API Key ──────────────────────────────────
import os
from dotenv import load_dotenv
load_dotenv()
GOOGLE_API_KEY = os.environ["GOOGLE_MAPS_API_KEY"]  # set in .env (never commit)

# ── Step 1: Rebuild KV boundary + Generate MICRO-GRID ───────
print("=" * 55)
print("STEP 1 — Building KV boundary & Micro-Grid")
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
minx, miny, maxx, maxy = kv_boundary.bounds

# 🌟 THE UPGRADE: 0.013 degrees is roughly 1.4km. 
# This creates a massive, dense grid of tiny circles.
step = 0.013 
grid_points = []

for lat in np.arange(miny, maxy, step):
    for lon in np.arange(minx, maxx, step):
        pt = Point(lon, lat)
        # Only add points that are actually inside the KV shape
        if kv_boundary.buffer(0.02).contains(pt):
            grid_points.append({"lat": round(lat, 5), "lon": round(lon, 5)}) 
            # Note: keeping precision to 5 decimals for exact API calls
            grid_points[-1]["lon"] = round(lon, 5) # fix typo in grid creation

print(f"\n✅ Micro-Grid Ready!")
print(f"  Total API Calls Required: {len(grid_points)}")
print(f"  Search Radius per call: 1.5km (Prevents 20-limit cutoff)")
print(f"  Estimated Time: {len(grid_points) * 0.25 / 60:.1f} minutes\n")


# ── Step 2: Search Google Maps Places API ────────────────────
print("=" * 55)
print("STEP 2 — Commencing Massive API Extraction...")
print("=" * 55)

url = "https://places.googleapis.com/v1/places:searchNearby"
all_stations = []
seen_ids = set()
total_api_hits = 0

for i, pt in enumerate(grid_points):
    try:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_API_KEY,
            "X-Goog-FieldMask": (
                "places.id,"
                "places.displayName,"
                "places.formattedAddress,"
                "places.location,"
                "places.evChargeOptions,"
                "places.businessStatus,"
                "places.types"
            )
        }

        payload = {
            "includedTypes": ["electric_vehicle_charging_station"],
            "maxResultCount": 20,
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude":  pt["lat"],
                        "longitude": pt["lon"]
                    },
                    "radius": 1500   # 🌟 1.5km micro-radius
                }
            }
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        data = resp.json()
        total_api_hits += 1

        places = data.get("places", [])
        new_count = 0

        for place in places:
            pid = place.get("id", "")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            new_count += 1

            ev_opts   = place.get("evChargeOptions", {})
            location  = place.get("location", {})
            name      = place.get("displayName", {}).get("text", "Unknown")

            all_stations.append({
                "google_place_id":    pid,
                "station_name":       name,
                "address":            place.get("formattedAddress", ""),
                "latitude":           location.get("latitude"),
                "longitude":          location.get("longitude"),
                "business_status":    place.get("businessStatus", "Unknown"),
                "connector_count":    ev_opts.get("connectorCount", None),
                "ev_network":         ev_opts.get("evNetwork", "Unknown"),
            })

        # Print update every 50 calls to reduce terminal spam
        if (i+1) % 50 == 0 or (i+1) == len(grid_points):
            print(f"  [{i+1:>4}/{len(grid_points)}] Scanning... Found {len(all_stations)} unique stations so far.")

        # Delay to respect Google's rate limits
        time.sleep(0.2)

    except Exception as e:
        print(f"  ❌ Grid point ({pt['lat']}, {pt['lon']}) failed — {e}")

print(f"\n  ✅ EXTRACTION COMPLETE.")
print(f"  Total API calls made: {total_api_hits}")
print(f"  Total unique stations found: {len(all_stations)}")


# ── Step 3: Final Boundary Cleanup & Save ────────────────────
print(f"\n{'=' * 55}")
print("STEP 3 — Cleaning Data & Saving")
print("=" * 55)

if len(all_stations) > 0:
    df_google = pd.DataFrame(all_stations)
    df_google = df_google.dropna(subset=["latitude", "longitude"])

    # Double-check points are strictly inside KV
    mask = df_google.apply(
        lambda row: kv_boundary.contains(Point(row["longitude"], row["latitude"])), axis=1
    )
    df_kv = df_google[mask].copy()

    # Save to CSV
    output_file = "raw_data/KV_EV_Google_MicroGrid.csv"
    df_kv.to_csv(output_file, index=False)
    
    print(f"  Total inside accurate KV boundary : {len(df_kv):,}")
    print(f"  ✅ Data saved successfully to: {output_file}")
    
    print("\n📊 Top EV Networks Found by Google:")
    print("-" * 40)
    print(df_kv["ev_network"].value_counts().head(10).to_string())

else:
    print("❌ No stations were found. Please check your API key or internet connection.")
print(f"{'=' * 55}")