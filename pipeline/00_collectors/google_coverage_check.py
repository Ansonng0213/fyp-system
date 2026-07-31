# ============================================================
# GOOGLE PLACES COVERAGE CHECK  (SECONDARY validation, read-only)
# ------------------------------------------------------------
# Independently counts EV charging stations Google Places returns
# across the Greater Klang Valley, and compares that against our
# own dataset (processed_data/ev_stations_kv_clean_v2.csv).
#
# FRAMING (important): this is a SUPPLEMENTARY check. Our dataset
# already fuses Google Places as one of its sources, so this partly
# checks against one of our own inputs. The stronger validation is
# the manual per-zone PlugShare check done separately. Treat every
# number here as a secondary data point.
#
# WHY A SWEEP, NOT PAGINATION:
#   Your key uses the NEW Places API (places:searchNearby), which
#   caps at 20 results/call and has NO next_page_token. So "get all
#   results, not just the first page" == cover the area spatially.
#   This uses an ADAPTIVE QUADTREE: query a coarse cell; only where a
#   cell returns the full 20 (saturated -> "more stations hide here")
#   does it subdivide and look closer. Deserts (Klang/Gombak) cost a
#   handful of calls; dense KL gets the fine grid. A HARD CAP on total
#   calls guards your quota. Cells still saturated at the finest size
#   are flagged as possible undercounts, honestly.
#
# WRITES (never touches ev_stations_kv_clean_v2.csv):
#   processed_data/google_coverage_raw.csv        (every distinct Google station)
#   processed_data/google_vs_ours_by_district.csv (the comparison table)
#
# Run from repo root (CWD = repo root), key in .env as GOOGLE_MAPS_API_KEY.
# ============================================================
import os
import re
import math
import time
from collections import deque

import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import shape, box, Point
from shapely.ops import unary_union

# This machine runs AVG antivirus, which intercepts HTTPS ("AVG Web/Mail Shield"
# root cert). Python's certifi bundle doesn't trust it, so requests fail with
# CERTIFICATE_VERIFY_FAILED. truststore makes Python verify against the WINDOWS
# cert store (which DOES trust AVG's root) — verification stays ON, no insecure
# verify=False hack. Harmless no-op on machines without interception.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(path=".env"):
        """Minimal .env reader (python-dotenv not installed in this venv)."""
        if not os.path.exists(path):
            return
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# ── Config (tunable) ─────────────────────────────────────────
START_CELL_DEG = 0.072    # ~8 km coarse tiles to seed the quadtree
MIN_CELL_DEG   = 0.009    # ~1 km finest cell (stop subdividing here)
SATURATE       = 20       # new-API max results/call => "saturated"
MAX_CALLS      = 700      # HARD ceiling on API calls (quota guard)
SLEEP_S        = 0.12     # politeness delay between calls
PROX_MERGE_M   = 40       # merge near-identical coords (same physical site)
BUFFER_DEG     = 0.012    # search a little past the outline to catch edge sites

DISTRICTS_GEOJSON = "processed_data/kv_districts_dosm.geojson"
OURS_CSV          = "processed_data/ev_stations_kv_clean_v2.csv"
RAW_OUT           = "processed_data/google_coverage_raw.csv"
CMP_OUT           = "processed_data/google_vs_ours_by_district.csv"

# Google exposes NO explicit public/private access field for EV chargers.
# Best-effort heuristic ONLY: names that look residential/restricted are the
# same pattern OCM used to tag "Private (restricted)" in our own data.
PRIVATE_RX = re.compile(
    r"resid|residensi|kondominium|\bcondo|apartment|apartel|\bsuites?\b|"
    r"pangsapuri|private|restricted|staff\s*only|tenant", re.I)


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def cell_radius_m(cell_deg):
    """Circle that circumscribes a square cell (searchNearby needs a circle)."""
    half_diag_deg = (cell_deg / 2.0) * math.sqrt(2.0)
    return half_diag_deg * 111_000.0 * 1.02   # ~+2% safety margin


def query_circle(lat, lon, radius_m, key):
    """One searchNearby call. Returns (places_list, ok_flag)."""
    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        # Lean field mask = cheaper SKU. includedTypes already filters to EV,
        # so we don't need evChargeOptions just to confirm they're chargers.
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.location,places.businessStatus,places.types,places.primaryType"
        ),
    }
    payload = {
        "includedTypes": ["electric_vehicle_charging_station"],
        "maxResultCount": SATURATE,
        "locationRestriction": {
            "circle": {"center": {"latitude": lat, "longitude": lon},
                       "radius": float(radius_m)}
        },
    }
    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=20)
            if r.status_code == 200:
                return r.json().get("places", []), True
            if r.status_code in (429, 500, 502, 503):
                time.sleep(1.5 * (attempt + 1))
                continue
            print(f"   ! HTTP {r.status_code}: {r.text[:200]}")
            return [], False
        except requests.RequestException as e:
            print(f"   ! request error ({e}); retry {attempt + 1}/3")
            time.sleep(1.5 * (attempt + 1))
    return [], False


# ── Step 1: KV outline + coarse seed grid ────────────────────
print("=" * 60)
print("STEP 1 — KV outline & adaptive seed grid")
print("=" * 60)

load_dotenv()
key = os.environ.get("GOOGLE_MAPS_API_KEY")
if not key:
    raise SystemExit("GOOGLE_MAPS_API_KEY not set in .env — aborting.")

import json
raw_gj = json.load(open(DISTRICTS_GEOJSON, encoding="utf-8"))
district_geoms = {f["properties"]["district_canon"]: shape(f["geometry"])
                  for f in raw_gj["features"]}
outline = unary_union(list(district_geoms.values()))
outline_buf = outline.buffer(BUFFER_DEG)
minx, miny, maxx, maxy = outline.bounds
print(f"  Districts: {len(district_geoms)} | bbox "
      f"({minx:.3f},{miny:.3f})–({maxx:.3f},{maxy:.3f})")

# seed the quadtree with coarse cells that touch KV
seeds = []
x = minx
while x < maxx:
    y = miny
    while y < maxy:
        if box(x, y, x + START_CELL_DEG, y + START_CELL_DEG).intersects(outline_buf):
            seeds.append((x, y, START_CELL_DEG))
        y += START_CELL_DEG
    x += START_CELL_DEG
print(f"  Seed cells inside KV: {len(seeds)}  (each ~8 km)")
print(f"  HARD CAP: {MAX_CALLS} API calls  "
      f"(new Places Nearby ~USD$32/1000 -> ceiling ~${MAX_CALLS * 0.032:.2f}, "
      f"usually within Google's monthly free credit)")

# ── Step 2: adaptive quadtree sweep ──────────────────────────
print("\n" + "=" * 60)
print("STEP 2 — Adaptive sweep (subdivide only where saturated)")
print("=" * 60)

found = {}                 # place_id -> record
queue = deque(seeds)
calls = 0
saturated_min = 0          # cells still full 20 at finest size (undercount risk)
hit_cap = False

while queue:
    if calls >= MAX_CALLS:
        hit_cap = True
        break
    x0, y0, side = queue.popleft()
    cell = box(x0, y0, x0 + side, y0 + side)
    if not cell.intersects(outline_buf):
        continue
    cx, cy = x0 + side / 2, y0 + side / 2
    places, ok = query_circle(cy, cx, cell_radius_m(side), key)
    calls += 1
    if not ok:
        continue
    for p in places:
        pid = p.get("id")
        if not pid or pid in found:
            continue
        loc = p.get("location", {})
        found[pid] = {
            "google_place_id": pid,
            "station_name": p.get("displayName", {}).get("text", "Unknown"),
            "address": p.get("formattedAddress", ""),
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "business_status": p.get("businessStatus", "UNKNOWN"),
            "primary_type": p.get("primaryType", ""),
            "types": "|".join(p.get("types", []) or []),
        }
    # subdivide iff this cell is saturated and not yet at the finest size
    if len(places) >= SATURATE:
        if side > MIN_CELL_DEG + 1e-9:
            h = side / 2
            for dx in (0, h):
                for dy in (0, h):
                    queue.append((x0 + dx, y0 + dy, h))
        else:
            saturated_min += 1
    if calls % 50 == 0:
        print(f"  [{calls:>4} calls] unique so far: {len(found)}  "
              f"queue={len(queue)}")
    time.sleep(SLEEP_S)

print(f"\n  API calls made : {calls}"
      + ("  (HARD CAP REACHED — coverage may be partial)" if hit_cap else ""))
print(f"  Distinct place_ids found: {len(found)}")
if saturated_min:
    print(f"  ! {saturated_min} finest (~1km) cells still returned 20 — "
          f"possible undercount in ultra-dense spots (expected: KL core).")

if not found:
    raise SystemExit("No stations returned — check the key / API enablement.")

# ── Step 3: proximity merge + district sjoin + access heuristic ──
print("\n" + "=" * 60)
print("STEP 3 — Dedup (proximity) + district assign + public/private")
print("=" * 60)

df = pd.DataFrame(found.values()).dropna(subset=["latitude", "longitude"])
df = df.reset_index(drop=True)

# (a) proximity merge: place_id is already unique; this catches the same
#     physical station listed twice with different ids (near-identical coords).
keep_idx, kept = [], []   # kept = list of (lat, lon)
merged = 0
for i, r in df.iterrows():
    dup = any(haversine_m(r["latitude"], r["longitude"], la, lo) < PROX_MERGE_M
              for la, lo in kept)
    if dup:
        merged += 1
    else:
        keep_idx.append(i)
        kept.append((r["latitude"], r["longitude"]))
df = df.loc[keep_idx].reset_index(drop=True)
print(f"  Merged {merged} near-duplicate coords (<{PROX_MERGE_M} m). "
      f"Distinct physical stations: {len(df)}")

# (b) district assignment via official DOSM polygons (same sjoin our pipeline uses)
gpts = gpd.GeoDataFrame(
    df, geometry=[Point(xy) for xy in zip(df["longitude"], df["latitude"])],
    crs="EPSG:4326")
dgdf = gpd.GeoDataFrame(
    {"district": list(district_geoms.keys())},
    geometry=list(district_geoms.values()), crs="EPSG:4326")
gpts = gpd.sjoin(gpts, dgdf, how="left", predicate="within").drop(columns="index_right")
outside = gpts["district"].isna().sum()
gpts = gpts.dropna(subset=["district"]).copy()   # keep only inside-KV points
print(f"  Inside KV districts: {len(gpts)}  (dropped {outside} in edge buffer, outside KV)")

# (c) operational + public/private HEURISTIC (Google has no access-type field)
gpts["is_operational"] = gpts["business_status"].eq("OPERATIONAL")
gpts["likely_private"] = gpts["station_name"].str.contains(PRIVATE_RX)
gpts["access_guess"] = "likely-public"
gpts.loc[gpts["likely_private"], "access_guess"] = "likely-private (name heuristic)"

# save the raw inspectable file
out = gpts.drop(columns="geometry")
out.to_csv(RAW_OUT, index=False)
print(f"  Saved raw Google stations -> {RAW_OUT}")

# ── Step 4: comparison vs our dataset ────────────────────────
print("\n" + "=" * 60)
print("STEP 4 — Google coverage vs our dataset")
print("=" * 60)

ours = pd.read_csv(OURS_CSV)
ours_pubop = ours[(ours["is_public_facing"] == True) & (ours["is_operational"] == True)]

g_total = len(gpts)
g_op = int(gpts["is_operational"].sum())
g_pub = int((gpts["is_operational"] & ~gpts["likely_private"]).sum())
g_priv = int(gpts["likely_private"].sum())
g_op_unknown = int((~gpts["is_operational"]).sum())

print("\nTOTALS (KV-wide):")
print(f"  Google — distinct stations (any status)     : {g_total}")
print(f"  Google — operational (businessStatus)       : {g_op}")
print(f"  Google — likely-PUBLIC & operational        : {g_pub}   <- compare to ours")
print(f"  Google — likely-PRIVATE (name heuristic)    : {g_priv}")
print(f"  Google — non-operational / unknown status   : {g_op_unknown}")
print(f"  OURS   — public-facing & operational        : {len(ours_pubop)}")
print("  NOTE: Google exposes no explicit public/private access field; the")
print("        public/private split above is a NAME heuristic only — treat as soft.")

# per-district table
districts = sorted(district_geoms.keys())
rows = []
for d in districts:
    gd = gpts[gpts["district"] == d]
    rows.append({
        "district": d,
        "google_total": len(gd),
        "google_public_op": int((gd["is_operational"] & ~gd["likely_private"]).sum()),
        "google_private": int(gd["likely_private"].sum()),
        "ours_public_op": int((ours_pubop["district"] == d).sum()),
    })
cmp = pd.DataFrame(rows)
cmp["diff_public_op"] = cmp["google_public_op"] - cmp["ours_public_op"]
total_row = {
    "district": "— KV TOTAL —",
    "google_total": cmp["google_total"].sum(),
    "google_public_op": cmp["google_public_op"].sum(),
    "google_private": cmp["google_private"].sum(),
    "ours_public_op": cmp["ours_public_op"].sum(),
    "diff_public_op": cmp["diff_public_op"].sum(),
}
cmp_out = pd.concat([cmp, pd.DataFrame([total_row])], ignore_index=True)
cmp_out.to_csv(CMP_OUT, index=False)

print("\nPER-DISTRICT (the useful view — where Google and our data diverge):")
print(cmp_out.to_string(index=False))
print(f"\n  Saved comparison table -> {CMP_OUT}")
print("=" * 60)
print("Done. Secondary check only — the manual PlugShare per-zone check is the")
print("stronger validation. ev_stations_kv_clean_v2.csv was NOT modified.")
print("=" * 60)
