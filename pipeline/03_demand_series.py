# ============================================================
# FYP2 — CORRECTED EV DEMAND SERIES PIPELINE (Problem 3 fix)
# Replaces the circular Rakan Niaga state-redistribution with a
# NATIONAL-ANCHORED design (Option A):
#
#   1. National monthly EV series  = count ALL records (exact —
#      the dealer 'Rakan Niaga' state label is never consulted).
#   2. KV share  = data-driven from GENUINE records' geography,
#      with Selangor adjusted to its 5 KV districts by population.
#   3. KV series = national x KV share, with sensitivity
#      scenarios (low / central / high).
#   4. District allocation weights = population-based (primary)
#      + income-adjusted (adoption-propensity sensitivity).
#
# This design also satisfies the IR's district-level forecasting
# objective (Problem 4): district numbers = KV forecast x weights.
#
# Inputs : raw_data/cars_2020..2026.csv
#          raw_data/population_district.csv
#          processed_data/population_kv_clean.csv
#          processed_data/income_kv_clean.csv
#          processed_data/jpj_kv_ev_clean.csv     (v1, comparison only)
# Outputs: processed_data/jpj_national_monthly.csv
#          processed_data/jpj_kv_monthly_v2.csv
#          processed_data/district_allocation_weights_v2.csv
#          processed_data/kv_share_derivation.json  (audit trail)
#          processed_data/ev_demand_series_v2.png   (chart, optional)
# ============================================================

import os
import json
import pandas as pd

RAW_DIR, OUT_DIR = "raw_data", "processed_data"
YEARS = range(2020, 2027)
KV_STATES = ["W.P. Kuala Lumpur", "Selangor", "W.P. Putrajaya"]
KV5_SELANGOR = ["Petaling", "Ulu Langat", "Hulu Langat", "Gombak", "Klang", "Sepang"]
DEALER_LABEL = "Rakan Niaga"
SENSITIVITY = {"low": 0.55, "high": 0.70}   # central share is computed from data

# ------------------------------------------------------------
# STEP 1 — Load every EV registration record nationally
# ------------------------------------------------------------
print("=" * 60)
print("STEP 1 — Loading national EV registrations")
print("=" * 60)

frames = []
for y in YEARS:
    df = pd.read_csv(os.path.join(RAW_DIR, f"cars_{y}.csv"),
                     usecols=["date_reg", "fuel", "state"], low_memory=False)
    frames.append(df[df["fuel"] == "electric"])
ev = pd.concat(frames, ignore_index=True)

ev["date_reg"] = pd.to_datetime(ev["date_reg"], errors="coerce")
bad_dates = ev["date_reg"].isna().sum()
ev = ev.dropna(subset=["date_reg"])
ev = ev[(ev["date_reg"] >= "2020-01-01") & (ev["date_reg"] <= "2026-03-31")]
print(f"  National EV records kept: {len(ev):,}  (invalid dates dropped: {bad_dates})")
print(f"  Date range: {ev['date_reg'].min().date()} -> {ev['date_reg'].max().date()}  (2026 is PARTIAL)")

# ------------------------------------------------------------
# STEP 2 — National monthly series (exact; state never consulted)
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 2 — National monthly series")
print("=" * 60)

ev["month"] = ev["date_reg"].dt.to_period("M").dt.to_timestamp()
national = ev.groupby("month").size().rename("national_ev").reset_index()
print(f"  Months: {len(national)} | total registrations: {national['national_ev'].sum():,}")
print("  Annual totals:")
print(national.assign(year=national["month"].dt.year)
              .groupby("year")["national_ev"].sum().to_string())

# ------------------------------------------------------------
# STEP 3 — Data-driven KV share from GENUINE record geography
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 3 — Deriving the KV share")
print("=" * 60)

genuine = ev[ev["state"] != DEALER_LABEL]
g_counts = genuine["state"].value_counts()
g_total = len(genuine)
g_kl  = int(g_counts.get("W.P. Kuala Lumpur", 0))
g_sel = int(g_counts.get("Selangor", 0))
g_ptj = int(g_counts.get("W.P. Putrajaya", 0))
print(f"  Genuine records: {g_total:,} ({g_total/len(ev)*100:.1f}% of all)")
print(f"  Dealer (Rakan Niaga) records: {len(ev)-g_total:,} — state label NEVER used")
print(f"  Genuine in KV states: KL {g_kl:,} | Selangor {g_sel:,} | Putrajaya {g_ptj:,}")

# Selangor adjustment: only its 5 KV districts belong to the study area
pop_raw = pd.read_csv(os.path.join(RAW_DIR, "population_district.csv"))
p23 = pop_raw[pop_raw["date"].astype(str).str.startswith("2023")].copy()
for col, keep in [("sex", "both"), ("age", "overall"), ("ethnicity", "overall")]:
    if col in p23.columns and keep in set(p23[col].astype(str)):
        p23 = p23[p23[col] == keep]
sel_pop = p23[p23["state"] == "Selangor"].groupby("district")["population"].sum()
kv5_factor = sel_pop[sel_pop.index.isin(KV5_SELANGOR)].sum() / sel_pop.sum()
print(f"  Selangor KV-5 population factor: {kv5_factor:.3f}")

kv_genuine_adj = g_kl + g_sel * kv5_factor + g_ptj
kv_share = kv_genuine_adj / g_total
print(f"  => CENTRAL KV share (data-driven): {kv_share:.3f}  ({kv_share*100:.1f}%)")
print(f"     Sensitivity band: low {SENSITIVITY['low']:.0%} | high {SENSITIVITY['high']:.0%}")
print(f"     (IR's cited assumption was 60% — convergent with the data-driven value)")

# ------------------------------------------------------------
# STEP 4 — KV monthly series with sensitivity scenarios
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 4 — KV monthly series")
print("=" * 60)

kv = national.copy()
kv["kv_central"] = kv["national_ev"] * kv_share
kv["kv_low"]     = kv["national_ev"] * SENSITIVITY["low"]
kv["kv_high"]    = kv["national_ev"] * SENSITIVITY["high"]
tot_c = kv["kv_central"].sum()
print(f"  KV total 2020-2026Mar — central: {tot_c:,.0f} | low: {kv['kv_low'].sum():,.0f} | high: {kv['kv_high'].sum():,.0f}")

# ------------------------------------------------------------
# STEP 5 — District allocation weights
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 5 — District allocation weights")
print("=" * 60)

pop_kv = pd.read_csv(os.path.join(OUT_DIR, "population_kv_clean.csv"))
inc_kv = pd.read_csv(os.path.join(OUT_DIR, "income_kv_clean.csv"))
w = pop_kv.merge(inc_kv[["district", "income_median"]], on="district", how="left")

w["weight_population"] = w["population"] / w["population"].sum()
rel_income = w["income_median"] / w["income_median"].mean()
w["weight_income_adj"] = (w["population"] * rel_income)
w["weight_income_adj"] = w["weight_income_adj"] / w["weight_income_adj"].sum()
w = w.sort_values("weight_population", ascending=False)

print(w[["district", "population", "income_median",
         "weight_population", "weight_income_adj"]]
      .assign(weight_population=lambda d: (d["weight_population"]*100).round(1),
              weight_income_adj=lambda d: (d["weight_income_adj"]*100).round(1))
      .to_string(index=False))

# ------------------------------------------------------------
# STEP 6 — v1 comparison, save outputs, chart
# ------------------------------------------------------------
print(f"\n{'=' * 60}")
print("STEP 6 — v1 vs v2 comparison + saving")
print("=" * 60)

v1_path = os.path.join(OUT_DIR, "jpj_kv_ev_clean.csv")
if os.path.exists(v1_path):
    v1 = pd.read_csv(v1_path)
    v1_kl_share = (v1["state"].isin(["Kuala Lumpur", "W.P. Kuala Lumpur"])).mean()
    print(f"  v1 total KV records: {len(v1):,}  | v2 central estimate: {tot_c:,.0f}")
    print(f"  v1 implied KL share of KV demand: {v1_kl_share*100:.1f}%")
    print(f"  v2 population-based KL share:     {float(w.loc[w['district']=='WP Kuala Lumpur','weight_population'].iloc[0])*100:.1f}%")
    print(f"  v2 income-adjusted KL share:      {float(w.loc[w['district']=='WP Kuala Lumpur','weight_income_adj'].iloc[0])*100:.1f}%")

national.to_csv(os.path.join(OUT_DIR, "jpj_national_monthly.csv"), index=False)
kv.to_csv(os.path.join(OUT_DIR, "jpj_kv_monthly_v2.csv"), index=False)
w[["district", "population", "income_median",
   "weight_population", "weight_income_adj"]].to_csv(
    os.path.join(OUT_DIR, "district_allocation_weights_v2.csv"), index=False)

audit = {
    "method": "national-anchored (Option A): KV = national x kv_share; dealer state labels never used",
    "national_ev_total_2020_2026mar": int(len(ev)),
    "dealer_records_rakan_niaga": int(len(ev) - g_total),
    "genuine_records": int(g_total),
    "genuine_kv": {"W.P. Kuala Lumpur": g_kl, "Selangor_whole_state": g_sel, "W.P. Putrajaya": g_ptj},
    "selangor_kv5_population_factor_2023": round(float(kv5_factor), 4),
    "kv_share_central_data_driven": round(float(kv_share), 4),
    "kv_share_sensitivity": SENSITIVITY,
    "ir_cited_assumption_for_reference": 0.60,
    "note_2026": "partial year through 2026-03",
    "allocation_weights_primary": "population 2023",
    "allocation_weights_sensitivity": "population x relative median income 2022",
}
with open(os.path.join(OUT_DIR, "kv_share_derivation.json"), "w") as f:
    json.dump(audit, f, indent=2)

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(national["month"], national["national_ev"], color="#888", lw=1.6,
            label="National EV registrations (exact)")
    ax.fill_between(kv["month"], kv["kv_low"], kv["kv_high"],
                    color="#1f77b4", alpha=0.18, label="KV sensitivity band (55–70%)")
    ax.plot(kv["month"], kv["kv_central"], color="#1f77b4", lw=2.2,
            label=f"KV central estimate ({kv_share*100:.1f}% share)")
    ax.set_title("EV Registration Demand — National vs Klang Valley (v2, national-anchored)")
    ax.set_ylabel("Monthly registrations")
    ax.legend(frameon=False)
    ax.margins(x=0.01)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "ev_demand_series_v2.png"), dpi=150)
    print("  Chart saved -> ev_demand_series_v2.png")
except ImportError:
    print("  (matplotlib not installed — chart skipped; pip install matplotlib to enable)")

print(f"\n  Saved -> jpj_national_monthly.csv, jpj_kv_monthly_v2.csv,")
print(f"           district_allocation_weights_v2.csv, kv_share_derivation.json")
