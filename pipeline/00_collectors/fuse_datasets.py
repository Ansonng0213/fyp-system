# ============================================================
# MAXIMUM DETAIL DATA FUSION
# Merges OCM and Google Maps while preserving 100% of columns
# ============================================================

import pandas as pd
import geopandas as gpd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

print("="*55)
print("Starting MAXIMUM DETAIL Data Fusion")
print("="*55)

# 1. Load both datasets
df_ocm = pd.read_csv('raw_data/KV_Existing_EV_Stations.csv')
df_google = pd.read_csv('raw_data/KV_EV_Google_MicroGrid.csv')

# Drop broken GPS rows
df_ocm = df_ocm.dropna(subset=['latitude', 'longitude'])
df_google = df_google.dropna(subset=['latitude', 'longitude'])

print(f"Original OCM/OSM Stations : {len(df_ocm)}")
print(f"Original Google Stations  : {len(df_google)}")

# 2. SPATIAL DEDUPLICATION (The 100-meter rule)
gdf_ocm = gpd.GeoDataFrame(
    df_ocm, geometry=gpd.points_from_xy(df_ocm.longitude, df_ocm.latitude), crs="EPSG:4326"
)
gdf_google = gpd.GeoDataFrame(
    df_google, geometry=gpd.points_from_xy(df_google.longitude, df_google.latitude), crs="EPSG:4326"
)

# Convert to metric for precise distance calculation
gdf_ocm_metric = gdf_ocm.to_crs(epsg=3857)
gdf_google_metric = gdf_google.to_crs(epsg=3857)

print("\nScanning for spatial duplicates (100m radius)...")

def distance_to_nearest_ocm(google_point):
    return gdf_ocm_metric.distance(google_point).min()

gdf_google_metric['dist_to_ocm'] = gdf_google_metric.geometry.apply(distance_to_nearest_ocm)

# FILTER: Keep only Google stations strictly > 100 meters away
unique_google = gdf_google_metric[gdf_google_metric['dist_to_ocm'] > 100].copy()
unique_google = unique_google.to_crs(epsg=4326)

print(f"Google duplicates deleted           : {len(gdf_google_metric) - len(unique_google)}")
print(f"Brand NEW Google stations recovered : {len(unique_google)}")

# 3. FORMAT GOOGLE DATA TO MATCH OCM EXACTLY
# Create an empty dataframe that has the exact same columns as the OCM dataset
google_formatted = pd.DataFrame(columns=df_ocm.columns)

# Map the data that Google actually has into the OCM columns
google_formatted['station_name'] = unique_google['station_name']
google_formatted['operator']     = unique_google['ev_network'].fillna('Unknown')
google_formatted['latitude']     = unique_google['latitude']
google_formatted['longitude']    = unique_google['longitude']
google_formatted['address']      = unique_google['address']
google_formatted['status']       = unique_google['business_status']
google_formatted['total_ports']  = unique_google['connector_count']

# Force the 'source' column to say Google_Maps so you can track them later
if 'source' in google_formatted.columns:
    google_formatted['source'] = 'Google_Maps'
else:
    google_formatted['source_tag'] = 'Google_Maps'

# 4. THE MASTER MERGE
# Stack them safely together. All original OCM columns remain completely untouched.
master_df = pd.concat([df_ocm, google_formatted], ignore_index=True)

# Save the maximum detail fused dataset
output_filename = 'raw_data/KV_Master_Fused_EV_Stations_FullDetails.csv'
master_df.to_csv(output_filename, index=False)

print("\n" + "="*55)
print("✅ MAXIMUM DETAIL FUSION COMPLETE")
print("="*55)
print(f"Final Ultimate Station Count : {len(master_df)}")
print(f"Total Columns Preserved      : {len(master_df.columns)}")
print(f"File saved as: {output_filename}")
print("="*55)