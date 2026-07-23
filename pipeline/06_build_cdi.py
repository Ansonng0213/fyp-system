# ============================================================
# FYP2 — CHARGING DESERT INDEX (CDI) PIPELINE  (Problems 6 + 9)
#
#   CDI = 100 * norm( DemandPressure * SupplyGap )   per H3 r8 hex
#
#   DemandPressure = (w_pop*pop_n + w_act*act_n) * EquityMultiplier
#     pop_n, act_n     : p99-winsorized min-max normalized (0-1)
#     EquityMultiplier : (KV median income / district income),
#                        clipped 0.75-1.35 (tilts, never dominates)
#   SupplyGap = 1 - Supply_n
#     Supply = sum over PUBLIC-FACING OPERATIONAL stations of
#              exp(-distance_km / 1.5)   ("streetlight" decay)
#
#   Multiplicative on purpose: desert = people who need charging
#   AND nothing nearby. Zero demand -> zero CDI (no false deserts).
#
#   Built-in defenses:
#     - entropy weighting printed as the objective baseline
#     - 4-scenario sensitivity: top-50 desert overlap vs baseline
#     - every score decomposes into visible reasons (the product)
#
# Inputs : processed_data/hex_activity_v1.csv
#          processed_data/ev_stations_kv_clean_v2.csv
#          processed_data/kv_districts_dosm.geojson   (map only)
# Outputs: processed_data/hex_cdi_v1.csv
#          processed_data/cdi_map.png
# ============================================================

import os
import numpy as np
import pandas as pd
import h3

OUT_DIR = "processed_data"
W_POP, W_ACT = 0.5, 0.5          # demand blend (baseline)
EQUITY_CLIP = (0.75, 1.35)       # fairness knob limits
DECAY_KM = 1.5                   # supply "streetlight" fade distance
P99 = 0.99                       # winsorize level for normalization

def norm01(s, q=P99):
    cap = s.quantile(q)
    return (s.clip(upper=cap) / cap).fillna(0) if cap > 0 else s * 0

# ------------------------------------------------------------
# STEP 1 — Load hex layers + stations
# ------------------------------------------------------------
print("=" * 60)
print("STEP 1 — Loading layers")
print("=" * 60)

hexes = pd.read_csv(os.path.join(OUT_DIR, "hex_activity_v1.csv"))
st = pd.read_csv(os.path.join(OUT_DIR, "ev_stations_kv_clean_v2.csv"))
supply_st = st[st["is_public_facing"] & st["is_operational"]].reset_index(drop=True)
print(f"  Hexes: {len(hexes):,} | supply-side stations (public+operational): {len(supply_st)}")

latlng = [h3.cell_to_latlng(c) for c in hexes["h3_index"]]
hexes["lat"] = [p[0] for p in latlng]
hexes["lon"] = [p[1] for p in latlng]

# ------------------------------------------------------------
# STEP 2 — Demand side
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 2 — Demand pressure")
print("=" * 60)

hexes["pop_n"] = norm01(hexes["pop_est"])
hexes["act_n"] = norm01(hexes["activity_score"])

kv_median_income = hexes.drop_duplicates("district")["district_income_median"].median()
hexes["equity_mult"] = (kv_median_income / hexes["district_income_median"]).clip(*EQUITY_CLIP)
print(f"  KV median district income: RM{kv_median_income:,.0f}")
print("  Equity multipliers by district:")
print(hexes.drop_duplicates("district")[["district", "equity_mult"]]
      .sort_values("equity_mult", ascending=False)
      .assign(equity_mult=lambda d: d["equity_mult"].round(3)).to_string(index=False))

hexes["demand_pressure"] = (W_POP * hexes["pop_n"] + W_ACT * hexes["act_n"]) * hexes["equity_mult"]

# Entropy weighting — the "let the data suggest weights" objective baseline
def entropy_weights(df, cols):
    P = df[cols].to_numpy(dtype=float)
    P = P / (P.sum(axis=0) + 1e-12)
    with np.errstate(divide="ignore", invalid="ignore"):
        logs = np.where(P > 0, np.log(P), 0.0)
    e = -(P * logs).sum(axis=0) / np.log(len(df))
    d = 1 - e
    return d / d.sum()

ew = entropy_weights(hexes, ["pop_n", "act_n"])
print(f"\n  Baseline blend: pop {W_POP:.2f} / activity {W_ACT:.2f}")
print(f"  Entropy-suggested blend: pop {ew[0]:.2f} / activity {ew[1]:.2f}  (objective reference)")

# ------------------------------------------------------------
# STEP 3 — Supply side (vectorized haversine, all hexes x all stations)
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 3 — Supply access & gap")
print("=" * 60)

R = 6371.0
h_lat = np.radians(hexes["lat"].to_numpy())[:, None]
h_lon = np.radians(hexes["lon"].to_numpy())[:, None]
s_lat = np.radians(supply_st["latitude"].to_numpy())[None, :]
s_lon = np.radians(supply_st["longitude"].to_numpy())[None, :]
dlat, dlon = s_lat - h_lat, s_lon - h_lon
a = np.sin(dlat / 2) ** 2 + np.cos(h_lat) * np.cos(s_lat) * np.sin(dlon / 2) ** 2
D = 2 * R * np.arcsin(np.sqrt(a))            # (4003, n_stations) distances in km

hexes["supply_raw"] = np.exp(-D / DECAY_KM).sum(axis=1)
hexes["supply_n"] = norm01(hexes["supply_raw"])
hexes["supply_gap"] = 1 - hexes["supply_n"]
hexes["nearest_station_km"] = D.min(axis=1).round(2)
hexes["stations_2km"] = (D <= 2.0).sum(axis=1)
hexes["stations_5km"] = (D <= 5.0).sum(axis=1)
print(f"  Median nearest public station: {hexes['nearest_station_km'].median():.2f} km")
print(f"  Inhabited hexes with NO station within 5 km: "
      f"{((hexes['stations_5km']==0) & (hexes['pop_est']>0)).sum():,}")

# ------------------------------------------------------------
# STEP 4 — CDI + sensitivity
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 4 — CDI + sensitivity check")
print("=" * 60)

def compute_cdi(df, w_pop, w_act, equity_on=True):
    eq = df["equity_mult"] if equity_on else 1.0
    dp = (w_pop * df["pop_n"] + w_act * df["act_n"]) * eq
    raw = dp * df["supply_gap"]
    return 100 * raw / raw.max()

hexes["cdi"] = compute_cdi(hexes, W_POP, W_ACT, True)

base_top50 = set(hexes.nlargest(50, "cdi")["h3_index"])
scenarios = {"pop-heavy (0.7/0.3)": (0.7, 0.3, True),
             "activity-heavy (0.3/0.7)": (0.3, 0.7, True),
             "entropy weights": (ew[0], ew[1], True),
             "equity OFF (operator view)": (0.5, 0.5, False)}
print("  Top-50 desert overlap vs baseline (robustness):")
for name, (wp, wa, eq) in scenarios.items():
    alt = set(hexes.assign(c=compute_cdi(hexes, wp, wa, eq)).nlargest(50, "c")["h3_index"])
    print(f"    {name:30s}: {len(base_top50 & alt)/50*100:.0f}% same hexes")

# ------------------------------------------------------------
# STEP 5 — Results: district summary + top deserts with reasons
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 5 — Results")
print("=" * 60)

inh = hexes[hexes["pop_est"] > 0]
summary = (inh.groupby("district")
           .agg(mean_cdi=("cdi", "mean"), max_cdi=("cdi", "max"),
                severe_hexes=("cdi", lambda s: (s >= 50).sum()),
                pop_in_severe=("pop_est", lambda s: s[inh.loc[s.index, "cdi"] >= 50].sum()))
           .sort_values("mean_cdi", ascending=False).round(1))
print("  District desert summary (inhabited hexes; severe = CDI>=50):")
print(summary.to_string())

print(f"\n  TOP 10 CHARGING DESERTS (with reasons):")
top = hexes.nlargest(10, "cdi")
for i, (_, r) in enumerate(top.iterrows(), 1):
    print(f"  {i:2d}. CDI {r['cdi']:.0f} | {r['district']} | ~{r['pop_est']:,.0f} residents, "
          f"activity {r['activity_score']:.0f}, equity x{r['equity_mult']:.2f}, "
          f"nearest charger {r['nearest_station_km']:.1f} km, {r['stations_5km']} within 5 km "
          f"| map: {r['lat']:.5f},{r['lon']:.5f}")

# ------------------------------------------------------------
# STEP 6 — Save + map
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 6 — Saving")
print("=" * 60)

cols = ["h3_index", "district", "lat", "lon", "pop_est", "activity_score",
        "pop_n", "act_n", "equity_mult", "demand_pressure",
        "supply_raw", "supply_n", "supply_gap",
        "nearest_station_km", "stations_2km", "stations_5km", "cdi"]
hexes[cols].to_csv(os.path.join(OUT_DIR, "hex_cdi_v1.csv"), index=False)

try:
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from shapely.geometry import Polygon

    def cell_polygon(cell):
        b = h3.cell_to_boundary(cell)
        return Polygon([(lng, lat) for lat, lng in b])

    gdf = gpd.GeoDataFrame(hexes[["h3_index", "cdi"]],
                           geometry=[cell_polygon(c) for c in hexes["h3_index"]],
                           crs="EPSG:4326")
    kv = gpd.read_file(os.path.join(OUT_DIR, "kv_districts_dosm.geojson"))
    TXT = "#E6E9EF"                       # near-white text, legible on dark canvas
    fig, ax = plt.subplots(figsize=(11, 10))
    gdf[gdf["cdi"] > 0].plot(column="cdi", cmap="inferno", ax=ax, legend=True,
                             vmin=0, vmax=100,
                             legend_kwds={"label": "Charging Desert Index (0-100)",
                                          "shrink": 0.6})
    kv.boundary.plot(ax=ax, color="white", linewidth=1.0)
    ax.scatter(supply_st["longitude"], supply_st["latitude"],
               s=6, c="#00e5ff", alpha=0.8, linewidths=0, label="Public stations")
    ax.legend(loc="lower left", frameon=False, labelcolor=TXT)
    ax.set_title("Charging Desert Index — Greater Klang Valley (H3 res 8)",
                 color=TXT, fontsize=14, pad=12)
    ax.set_axis_off()
    # near-white colorbar label + tick labels (legend=True adds the colorbar axis)
    cax = fig.axes[-1]
    cax.yaxis.label.set_color(TXT)
    cax.tick_params(colors=TXT)
    for spine in cax.spines.values():
        spine.set_edgecolor(TXT)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "cdi_map.png"), dpi=150, facecolor="#1a1a2e")
    print("  Map saved -> cdi_map.png")
except ImportError:
    print("  (geopandas/matplotlib missing — map skipped)")

print(f"  Saved -> hex_cdi_v1.csv")
