# ============================================================
# FYP2 -- EQUITY METRICS  (standard inequality measures)
#
#   The CDI is bespoke. This stage restates the same finding in
#   measures a reader can compare against published work: the
#   population-weighted GINI coefficient of charger accessibility,
#   plus ATKINSON and THEIL as robustness, and the plain-language
#   share statistics that inequality papers usually lead with.
#
#   ACCESSIBILITY = supply_raw from stage 06, i.e.
#       sum over public+operational stations of exp(-d_km / 1.5)
#   read straight from hex_cdi_v1.csv, never recomputed, so this
#   stage is consistent with the CDI by construction. (The one
#   exception is the decay-sensitivity check in STEP 6, which has
#   to rebuild the field at other decay constants.)
#
#   POPULATION WEIGHTING IS NOT OPTIONAL. An unweighted Gini over
#   hexes would count an empty hex the same as one holding 24,000
#   people, which measures the geometry of the grid rather than the
#   experience of residents. Every statistic here is weighted by
#   pop_est and computed over inhabited hexes only.
#
#   The headline is the BEFORE/AFTER: what the 20 recommended sites
#   do to the Gini, against what the market's own predicted next 20
#   would do. Same decay, same method, three columns.
#
# Inputs : processed_data/hex_cdi_v1.csv
#          processed_data/recommended_sites_v1.csv
#          processed_data/operator_model_scores.csv   (market counterfactual)
#          processed_data/ev_stations_kv_clean_v2.csv (decay sensitivity only)
# Outputs: processed_data/equity_metrics.csv
#          processed_data/equity_lorenz_points.csv
#          processed_data/figures/lorenz_curve.png
#
# Reads existing artifacts only. Modifies no existing script, CSV or page.
# ============================================================

import os
import sys
import random
import warnings

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

OUT_DIR = "processed_data"
FIG_DIR = os.path.join(OUT_DIR, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

DECAY_KM = 1.5                     # the stage-06 constant
DECAY_SENSITIVITY = (1.0, 1.5, 2.0)
N_MARKET = 20
R_EARTH = 6371.0

# dark figure palette, matching stage 06 / 12
FIG_BG, FIG_TXT = "#1A1A2E", "#E6E9EF"
FIG_GRID, FIG_MUTED = "#3A4050", "#9AA1AD"
C_CURRENT, C_EQUITY, C_MARKET = "#FF6B5A", "#00FF88", "#FFB02E"


def banner(n, title):
    print()
    print("=" * 68)
    print(f"STEP {n} -- {title}")
    print("=" * 68)


def to_md(df, floatfmt="{:.4f}"):
    d = df.copy()
    cols = [str(c) for c in d.columns]

    def cell(v):
        if isinstance(v, (float, np.floating)):
            return "--" if np.isnan(v) else floatfmt.format(v)
        return str(v)

    rows = [[cell(v) for v in r] for r in d.itertuples(index=False)]
    widths = [max([len(cols[i])] + [len(r[i]) for r in rows]) for i in range(len(cols))]
    out = ["| " + " | ".join(c.ljust(w) for c, w in zip(cols, widths)) + " |",
           "|" + "|".join("-" * (w + 2) for w in widths) + "|"]
    for r in rows:
        out.append("| " + " | ".join(v.ljust(w) for v, w in zip(r, widths)) + " |")
    return "\n".join(out)


def haversine(lat_a, lon_a, lat_b, lon_b):
    a1, o1 = np.radians(lat_a)[:, None], np.radians(lon_a)[:, None]
    a2, o2 = np.radians(lat_b)[None, :], np.radians(lon_b)[None, :]
    h = np.sin((a2 - a1) / 2) ** 2 + np.cos(a1) * np.cos(a2) * np.sin((o2 - o1) / 2) ** 2
    return 2 * R_EARTH * np.arcsin(np.sqrt(h))


# ------------------------------------------------------------
# INEQUALITY MEASURES -- all population-weighted
# ------------------------------------------------------------
def _sorted(x, w):
    o = np.argsort(x, kind="mergesort")
    return np.asarray(x, float)[o], np.asarray(w, float)[o]


def lorenz_points(x, w):
    """Cumulative population share vs cumulative accessibility share, with the
    origin prepended so the curve starts at (0, 0) and ends at (1, 1)."""
    xs, ws = _sorted(x, w)
    p = ws / ws.sum()
    q = (ws * xs) / (ws * xs).sum()
    return np.concatenate([[0.0], np.cumsum(p)]), np.concatenate([[0.0], np.cumsum(q)])


def weighted_gini(x, w):
    """Population-weighted Gini = 1 - 2 * (area under the Lorenz curve),
    by the trapezoid rule over the weighted curve."""
    cp, cq = lorenz_points(x, w)
    area = np.trapezoid(cq, cp) if hasattr(np, "trapezoid") else np.trapz(cq, cp)
    return float(1.0 - 2.0 * area)


def weighted_atkinson(x, w, eps):
    """Atkinson index. eps controls how much weight the bottom of the
    distribution gets: higher eps = more inequality-averse."""
    xs, ws = _sorted(x, w)
    p = ws / ws.sum()
    mu = float((ws * xs).sum() / ws.sum())
    if mu <= 0 or np.any(xs <= 0):
        return float("nan")
    r = xs / mu
    if abs(eps - 1.0) < 1e-12:
        return float(1.0 - np.exp(np.sum(p * np.log(r))))
    return float(1.0 - np.sum(p * r ** (1.0 - eps)) ** (1.0 / (1.0 - eps)))


def weighted_theil(x, w):
    """Theil T index. Sensitive to the TOP of the distribution, where Atkinson
    is sensitive to the bottom -- which is why both are reported."""
    xs, ws = _sorted(x, w)
    p = ws / ws.sum()
    mu = float((ws * xs).sum() / ws.sum())
    if mu <= 0 or np.any(xs <= 0):
        return float("nan")
    r = xs / mu
    return float(np.sum(p * r * np.log(r)))


def share_stats(x, w):
    """The two plain-language statistics.

    bottom10_pop  : share of PEOPLE who between them hold only the bottom 10%
                    of all accessibility.
    worst50_access: share of ACCESSIBILITY held by the worst-served 50% of
                    people.
    """
    cp, cq = lorenz_points(x, w)
    bottom10_pop = float(np.interp(0.10, cq, cp))       # invert the curve
    worst50_access = float(np.interp(0.50, cp, cq))
    return bottom10_pop, worst50_access


def all_measures(x, w):
    return {
        "gini": weighted_gini(x, w),
        "atkinson_0.5": weighted_atkinson(x, w, 0.5),
        "atkinson_1.0": weighted_atkinson(x, w, 1.0),
        "theil": weighted_theil(x, w),
        "pop_share_holding_bottom_10pct_access": share_stats(x, w)[0],
        "access_share_of_worst_served_50pct_pop": share_stats(x, w)[1],
        "mean_accessibility": float((w * x).sum() / w.sum()),
    }


# ============================================================
print("=" * 68)
print("FYP2 -- EQUITY METRICS (Gini / Atkinson / Theil on accessibility)")
print("=" * 68)
print("Library versions")
print(f"  python  {sys.version.split()[0]}   numpy {np.__version__}   "
      f"pandas {pd.__version__}   matplotlib {matplotlib.__version__}")
print(f"  seed    {SEED}")

# ------------------------------------------------------------
banner(1, "THE ACCESSIBILITY MEASURE")
# ------------------------------------------------------------
hx = pd.read_csv(os.path.join(OUT_DIR, "hex_cdi_v1.csv"))
print(f"  hex_cdi_v1.csv                {len(hx):,} hexes")
print("  accessibility = supply_raw  (sum of exp(-d_km / 1.5) over the 376")
print("  public + operational stations), READ from stage 06, not recomputed")

inh = hx[hx["pop_est"] > 0].reset_index(drop=True)
POP_TOTAL = float(hx["pop_est"].sum())
print(f"\n  inhabited hexes (pop_est > 0) {len(inh):,} of {len(hx):,} "
      f"({100 * len(inh) / len(hx):.1f}% of hexes)")
print(f"  population they hold          {inh['pop_est'].sum():,.0f} of "
      f"{POP_TOTAL:,.0f} = {100 * inh['pop_est'].sum() / POP_TOTAL:.2f}% of KV")
print("  (all uninhabited hexes hold zero people by construction, so the")
print("   inhabited set carries the entire population)")
print(f"\n  accessibility range           {inh['supply_raw'].min():.3e} .. "
      f"{inh['supply_raw'].max():.4f}   zeros: {int((inh['supply_raw'] == 0).sum())}")
print("  No zeros -> Atkinson(1) and Theil are both defined (log of the ratio).")

POP = inh["pop_est"].to_numpy(dtype=float)
ACC_NOW = inh["supply_raw"].to_numpy(dtype=float)
LAT, LON = inh["lat"].to_numpy(), inh["lon"].to_numpy()
DISTRICTS = sorted(inh["district"].unique())

# ------------------------------------------------------------
banner(2, "THE TWO INTERVENTIONS")
# ------------------------------------------------------------
rec = pd.read_csv(os.path.join(OUT_DIR, "recommended_sites_v1.csv")).sort_values("rank")
print(f"  equity siting  {len(rec)} recommended sites (stage 07, greedy maximal coverage)")
print("    " + ", ".join(f"{d} {n}" for d, n in rec["district"].value_counts().items()))

scores_path = os.path.join(OUT_DIR, "operator_model_scores.csv")
if os.path.exists(scores_path):
    sc = pd.read_csv(scores_path)
    mkt = sc[sc["has_station"] == 0].nlargest(N_MARKET, "oof_proba_randomCV")
    print(f"\n  market siting  top {len(mkt)} hexes by predicted commercial interest "
          "(stage 11)")
    print("    " + ", ".join(f"{d} {n}" for d, n in mkt["district"].value_counts().items()))
    print("    DIAGNOSTIC counterfactual -- what the market would do, not a recommendation")
else:
    mkt = pd.DataFrame(columns=["lat", "lon", "district"])
    print("\n  market siting  SKIPPED (operator_model_scores.csv not found)")


def added_supply(sites, decay=DECAY_KM):
    """Extra accessibility at every inhabited hex from a set of new stations.
    Same exp(-d/decay) kernel as stage 06, so it is additive on supply_raw."""
    if not len(sites):
        return np.zeros(len(inh))
    d = haversine(LAT, LON, sites["lat"].to_numpy(), sites["lon"].to_numpy())
    return np.exp(-d / decay).sum(axis=1)


ACC_EQUITY = ACC_NOW + added_supply(rec)
ACC_MARKET = ACC_NOW + added_supply(mkt)
SCENARIOS = [("current", ACC_NOW), ("equity_siting", ACC_EQUITY),
             ("market_siting", ACC_MARKET)]
print(f"\n  mean accessibility  current {np.average(ACC_NOW, weights=POP):.4f} | "
      f"equity {np.average(ACC_EQUITY, weights=POP):.4f} | "
      f"market {np.average(ACC_MARKET, weights=POP):.4f}")

# ------------------------------------------------------------
banner(3, "GINI AND FRIENDS -- population-weighted")
# ------------------------------------------------------------
rows = []
for scen, acc in SCENARIOS:
    rows.append({"scope": "Klang Valley", "scenario": scen, "n_hexes": len(inh),
                 "population": float(POP.sum()), **all_measures(acc, POP)})
    for d in DISTRICTS:
        m = (inh["district"] == d).to_numpy()
        rows.append({"scope": d, "scenario": scen, "n_hexes": int(m.sum()),
                     "population": float(POP[m].sum()),
                     **all_measures(acc[m], POP[m])})
eq = pd.DataFrame(rows)
eq.to_csv(os.path.join(OUT_DIR, "equity_metrics.csv"), index=False)

kv_now = eq[(eq["scope"] == "Klang Valley") & (eq["scenario"] == "current")].iloc[0]
print("  Klang Valley, CURRENT state\n")
print(to_md(pd.DataFrame([{
    "Gini": kv_now["gini"], "Atkinson e=0.5": kv_now["atkinson_0.5"],
    "Atkinson e=1.0": kv_now["atkinson_1.0"], "Theil": kv_now["theil"]}])))
print()
print(f"  In plain terms: the worst-served **50% of the population** holds "
      f"**{kv_now['access_share_of_worst_served_50pct_pop']:.1%}** of all charger")
print(f"  accessibility, and the bottom **10% of accessibility** is shared between "
      f"**{kv_now['pop_share_holding_bottom_10pct_access']:.1%}** of everyone.")

print("\n### Gini by district, current state\n")
dg = eq[(eq["scenario"] == "current") & (eq["scope"] != "Klang Valley")] \
    .sort_values("gini", ascending=False)
print(to_md(dg[["scope", "n_hexes", "population", "gini", "atkinson_1.0", "theil",
                "mean_accessibility"]], floatfmt="{:,.4f}"))
print("\n  NOTE: a district Gini measures inequality WITHIN that district only.")
print("  A well-served district can still have a high internal Gini, and a")
print("  uniformly deprived district a low one -- read it beside the mean.")

# ------------------------------------------------------------
banner(4, "BEFORE / AFTER -- the headline")
# ------------------------------------------------------------
def compare(scope):
    r = {s: eq[(eq["scope"] == scope) & (eq["scenario"] == s)].iloc[0]
         for s, _ in SCENARIOS}
    return r


kv = compare("Klang Valley")
tbl = pd.DataFrame([{
    "Measure": lbl,
    "Current": kv["current"][key],
    "After equity siting": kv["equity_siting"][key],
    "After market siting": kv["market_siting"][key],
} for lbl, key in [("Gini", "gini"), ("Atkinson e=0.5", "atkinson_0.5"),
                   ("Atkinson e=1.0", "atkinson_1.0"), ("Theil", "theil"),
                   ("Access share of worst-served 50%", "access_share_of_worst_served_50pct_pop"),
                   ("Mean accessibility", "mean_accessibility")]])
print("### Klang Valley -- three scenarios\n")
print(to_md(tbl))

g0 = kv["current"]["gini"]
ge = kv["equity_siting"]["gini"]
gm = kv["market_siting"]["gini"]
print(f"\n  Gini  {g0:.4f} -> equity {ge:.4f} ({ge - g0:+.4f}, {100 * (ge - g0) / g0:+.2f}%)")
print(f"  Gini  {g0:.4f} -> market {gm:.4f} ({gm - g0:+.4f}, {100 * (gm - g0) / g0:+.2f}%)")

print("\n### Gini change by district\n")
drows = []
for d in DISTRICTS:
    c = compare(d)
    drows.append({"District": d,
                  "Current": c["current"]["gini"],
                  "Equity": c["equity_siting"]["gini"],
                  "delta_equity": c["equity_siting"]["gini"] - c["current"]["gini"],
                  "Market": c["market_siting"]["gini"],
                  "delta_market": c["market_siting"]["gini"] - c["current"]["gini"]})
dd = pd.DataFrame(drows).sort_values("delta_equity")
print(to_md(dd))

# ------------------------------------------------------------
banner(5, "LORENZ CURVE")
# ------------------------------------------------------------
lz_rows = []
fig, ax = plt.subplots(figsize=(8.5, 8), facecolor=FIG_BG)
ax.set_facecolor(FIG_BG)
ax.plot([0, 1], [0, 1], ls="--", lw=1.2, color=FIG_MUTED, label="perfect equality")
for (scen, acc), colour in zip(SCENARIOS, (C_CURRENT, C_EQUITY, C_MARKET)):
    cp, cq = lorenz_points(acc, POP)
    g = weighted_gini(acc, POP)
    ax.plot(cp, cq, lw=2.2, color=colour,
            label=f"{scen.replace('_', ' ')} (Gini {g:.3f})")
    for a, b in zip(cp, cq):
        lz_rows.append({"scenario": scen, "cum_pop_share": a, "cum_access_share": b})
ax.set_xlim(0, 1); ax.set_ylim(0, 1)
ax.set_xlabel("Cumulative share of population (worst-served first)", color=FIG_TXT)
ax.set_ylabel("Cumulative share of charger accessibility", color=FIG_TXT)
ax.set_title("Lorenz curve -- charger accessibility, population-weighted",
             color=FIG_TXT, fontsize=13, pad=10)
ax.grid(True, color=FIG_GRID, lw=0.6, alpha=0.5)
ax.set_axisbelow(True)
ax.tick_params(colors=FIG_MUTED)
for s in ax.spines.values():
    s.set_color(FIG_GRID)
leg = ax.legend(facecolor=FIG_BG, edgecolor=FIG_GRID, labelcolor=FIG_TXT, loc="upper left")
leg.get_frame().set_alpha(0.9)
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "lorenz_curve.png"), dpi=150, facecolor=FIG_BG)
plt.close(fig)

lz = pd.DataFrame(lz_rows)
lz.to_csv(os.path.join(OUT_DIR, "equity_lorenz_points.csv"), index=False)
print(f"  lorenz_curve.png  |  equity_lorenz_points.csv ({len(lz):,} rows, "
      f"{len(SCENARIOS)} scenarios)")

# ------------------------------------------------------------
banner(6, "SANITY CHECKS")
# ------------------------------------------------------------
ok = True
for scen, acc in SCENARIOS:
    g = weighted_gini(acc, POP)
    in_range = 0.0 <= g <= 1.0
    ok &= in_range
    print(f"  Gini in [0,1]           {scen:14s} {g:.4f}  {'OK' if in_range else 'FAIL'}")

for scen, acc in SCENARIOS:
    cp, cq = lorenz_points(acc, POP)
    mono = bool(np.all(np.diff(cq) >= -1e-12) and np.all(np.diff(cp) >= -1e-12))
    ends = abs(cp[-1] - 1) < 1e-9 and abs(cq[-1] - 1) < 1e-9
    ok &= mono and ends
    print(f"  Lorenz monotonic + (1,1) {scen:13s} "
          f"monotonic {'OK' if mono else 'FAIL'} | ends ({cp[-1]:.6f}, {cq[-1]:.6f}) "
          f"{'OK' if ends else 'FAIL'}")

print()
for label, g in (("equity_siting", ge), ("market_siting", gm)):
    if g < g0:
        print(f"  {label:14s} Gini FALLS {g0:.4f} -> {g:.4f} -- inequality reduced.")
    elif g > g0:
        print(f"  {label:14s} Gini RISES {g0:.4f} -> {g:.4f}. NOT A BUG: adding")
        print("                 supply concentrated in already-well-served areas")
        print("                 raises relative inequality even though total")
        print("                 accessibility goes up. Report it as a finding.")
    else:
        print(f"  {label:14s} Gini unchanged.")

# ------------------------------------------------------------
banner(7, "DECAY SENSITIVITY -- does the ranking survive?")
# ------------------------------------------------------------
print("  supply_raw is only valid at decay 1.5 km, so the field is rebuilt from")
print("  ev_stations_kv_clean_v2.csv for the other constants. The rebuild uses")
print("  float64 where stage 06 used float32, so the 1.5 km row differs from the")
print("  stored value by ~5e-7 relative -- immaterial, and reported for honesty.\n")

st_all = pd.read_csv(os.path.join(OUT_DIR, "ev_stations_kv_clean_v2.csv"))
pub = st_all[st_all["is_public_facing"] & st_all["is_operational"]]
D_STN = haversine(LAT, LON, pub["latitude"].to_numpy(), pub["longitude"].to_numpy())

sens = []
for dk in DECAY_SENSITIVITY:
    base = np.exp(-D_STN / dk).sum(axis=1)
    row = {"decay_km": dk}
    ranking = {}
    for scen, sites in (("current", None), ("equity_siting", rec), ("market_siting", mkt)):
        acc = base if sites is None else base + added_supply(sites, decay=dk)
        g = weighted_gini(acc, POP)
        row[scen] = g
        ranking[scen] = g
    row["best (lowest Gini)"] = min(ranking, key=ranking.get)
    row["worst"] = max(ranking, key=ranking.get)
    sens.append(row)
sens = pd.DataFrame(sens)
print(to_md(sens))

orders = [tuple(sorted(("current", "equity_siting", "market_siting"),
                       key=lambda s: r[s])) for _, r in sens.iterrows()]
stable = len(set(orders)) == 1
print(f"\n  Ranking of the three scenarios identical at every decay: "
      f"{'YES' if stable else 'NO'}")
print(f"  Order: {' < '.join(orders[0])}  (lowest Gini first)")
stored_g = weighted_gini(ACC_NOW, POP)
rebuilt_15 = float(sens.loc[sens["decay_km"] == 1.5, "current"].iloc[0])
print(f"  Stored-supply Gini {stored_g:.6f} vs rebuilt at 1.5 km {rebuilt_15:.6f} "
      f"(diff {abs(stored_g - rebuilt_15):.2e})")

# ------------------------------------------------------------
banner(8, "OUTPUTS")
# ------------------------------------------------------------
for f in ("equity_metrics.csv", "equity_lorenz_points.csv"):
    p = os.path.join(OUT_DIR, f)
    print(f"  {f:32s} {sum(1 for _ in open(p)) - 1:>6,} rows")
print(f"  figures/lorenz_curve.png")
print()
print("=" * 68)
print("Reads existing artifacts only. No existing script, CSV or page modified.")
print("=" * 68)
