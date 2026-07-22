# ============================================================
# HELPER — boundary artifacts for the dashboard maps.
#
# Produces two files the app READS (artifact pattern: geo work here, not in app):
#   1. kv_outline.geojson — the 7 districts dissolved into ONE outline, drawn as
#      a thin clean boundary line.
#   2. kv_mask.geojson     — a large box with the KV outline cut out as a hole;
#      the app fills it with a semi-transparent dark overlay so everything
#      OUTSIDE KV is dimmed and the study area pops by contrast (DESIGN.md).
#
# Input : processed_data/kv_districts_dosm.geojson  (7 district MultiPolygons)
# Uses shapely only. Re-run if the district boundaries ever change.
# ============================================================
import json
import os

from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

OUT_DIR = "processed_data"
SRC = os.path.join(OUT_DIR, "kv_districts_dosm.geojson")
OUTLINE_DST = os.path.join(OUT_DIR, "kv_outline.geojson")
MASK_DST = os.path.join(OUT_DIR, "kv_mask.geojson")

# generous box around peninsular Malaysia so the mask covers any reasonable
# pan/zoom of the KV-centred map
BIG_BOX = box(95.0, -3.0, 108.0, 10.0)

print("=" * 60)
print("MAKE KV OUTLINE + MASK")
print("=" * 60)

gj = json.load(open(SRC, "r", encoding="utf-8"))
geoms = [shape(f["geometry"]) for f in gj["features"]]
union = unary_union(geoms)          # dissolves shared internal edges
print(f"  Districts read: {len(geoms)} | dissolved type: {union.geom_type}")
print(f"  Bounds: {tuple(round(b, 4) for b in union.bounds)}")


def _write(path, geom, name):
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": name}, "geometry": mapping(geom)}]}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(fc, fh)
    print(f"  Saved -> {path}")


_write(OUTLINE_DST, union, "Greater Klang Valley")

mask = BIG_BOX.difference(union)    # everything outside KV
print(f"  Mask type: {mask.geom_type} | holes carve out KV")
_write(MASK_DST, mask, "outside KV")
