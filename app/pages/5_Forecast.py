"""Page 3 — Demand Forecast.

How many EVs are coming, and how many public ports that needs. Reads the two
forecast artifacts only. A monthly-registration forecast chart (actual → policy
band + accelerated comparison, with the two TIV cap lines), a year/scenario/ratio
explorer that turns projected EV stock into required ports, the district-level
2030 gap, an honest backtest strip and an assumptions expander.
"""
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import data, theme, ui

st.set_page_config(page_title="Demand Forecast", layout="wide")
theme.inject_base_css()

POLICY_CAP_MO = 6290    # 15% of TIV, national policy target, per month (KV share)
ACCEL_CAP_MO = 12580    # 30% of TIV, accelerated target, per month
NATIONAL_TARGET = 10000

f = data.load_forecast()
gap = data.load_charger_gap()
LAST_ACTUAL = f.loc[f["actual"].notna(), "ds"].max()      # 2026-03-01

CUR_PORTS = int(gap["current_ports"].sum())               # 867
# REQ_2030 / GAP_2030 are computed below via required_ports(), the single
# port computation this page uses for both the callout and the KPI cards.


@st.cache_data(show_spinner=False)
def stock_series():
    """EV stock = cumulative monthly registrations (actual where present, else the
    scenario forecast). Reproduces 61,568 today → 372,266 policy / 552,775 accel
    by end-2030."""
    d = data.load_forecast().copy()
    d["stock_policy"] = d["actual"].where(d["actual"].notna(), d["policy_cap"]).cumsum()
    d["stock_accel"] = d["actual"].where(d["actual"].notna(), d["accel_cap"]).cumsum()
    return d[["ds", "stock_policy", "stock_accel"]]


# ------------------------------------------------------------------ sidebar controls
with st.sidebar:
    st.markdown("<div class='ctl-title'>Scenario</div>", unsafe_allow_html=True)
    scenario = st.segmented_control("Scenario", ["Policy", "Accelerated"], default="Policy",
                                    label_visibility="collapsed") or "Policy"
    st.caption("**Policy** = 15% TIV penetration target · **Accelerated** = 30%.")
    st.divider()
    year = st.slider("Year", 2026, 2030, 2030)
    ratio = st.segmented_control("EVs per public port", [10, 15, 20], default=15) or 15
    st.caption("Fewer EVs per port ⇒ more ports needed. 15 is the benchmark used for the headline.")

is_accel = scenario == "Accelerated"
stock_col = "stock_accel" if is_accel else "stock_policy"
ev_col = "ev_2030_accel" if is_accel else "ev_2030_policy"

ss = stock_series()
stock_y = float(ss.loc[ss["ds"] == f"{year}-12-01", stock_col].iloc[0])


def required_ports(year_stock: float, evs_per_port: int,
                   ev_column: str, stock_column: str) -> int:
    """THE single port computation for this page -- callout and KPIs both use it.

    Ports are counted per district and then summed, exactly as
    pipeline/09_forecast.py builds charger_gap_2030.csv. That matters: a port is
    an integer object in a specific district, so the total is the sum of rounded
    district figures, not the rounded KV total. The two differ by one
    (sum-of-rounded 24,819 vs round-of-sum 24,818), which is why the callout and
    the KPI cards used to disagree on the same figure.

    Non-2030 years scale the district split by that year's share of 2030 stock;
    at year = 2030 the scale factor is 1.0 and this returns the published
    24,819 exactly.
    """
    stock_2030 = float(ss.loc[ss["ds"] == "2030-12-01", stock_column].iloc[0])
    scale = (year_stock / stock_2030) if stock_2030 > 0 else 0.0
    return int((gap[ev_column] * scale / evs_per_port).round().sum())


# fixed headline (2030, policy scenario, 15 EVs/port) -- the quotable stat
STOCK_2030_POLICY = float(ss.loc[ss["ds"] == "2030-12-01", "stock_policy"].iloc[0])
REQ_2030 = required_ports(STOCK_2030_POLICY, 15, "ev_2030_policy", "stock_policy")
GAP_2030 = max(0, REQ_2030 - CUR_PORTS)

# reactive to the sidebar, same function
req_y = required_ports(stock_y, ratio, ev_col, stock_col)
gap_y = max(0, req_y - CUR_PORTS)

# ------------------------------------------------------------------ header + headline
st.markdown(
    "<div class='page-title'>Demand Forecast</div>"
    "<div class='page-sub'>KV EV registrations to 2030 and the public-charger ports they require · "
    "Prophet logistic vs ARIMA</div>",
    unsafe_allow_html=True,
)
st.markdown("<hr>", unsafe_allow_html=True)

st.markdown(
    "<div class='solution-band'><div class='solution-lead'>The 2030 gap</div>"
    f"<div class='solution-body'>By 2030 the Klang Valley needs <b>~{REQ_2030:,} public ports</b> "
    f"against <b>{CUR_PORTS:,} today</b> — a gap of <b>~{GAP_2030:,}</b>, roughly "
    f"<b>2.5× the entire national {NATIONAL_TARGET:,}-charger target</b>.</div></div>",
    unsafe_allow_html=True,
)

st.write("")

# ------------------------------------------------------------------ forecast chart
ui.section_header("Monthly EV registrations — actual & forecast")
fc = f[f["ds"] >= LAST_ACTUAL]           # forecast period, connected at last actual
act = f[f["actual"].notna()]
fig = go.Figure()
# policy uncertainty band
fig.add_trace(go.Scatter(x=fc["ds"], y=fc["policy_hi"], line=dict(width=0),
                         showlegend=False, hoverinfo="skip"))
fig.add_trace(go.Scatter(x=fc["ds"], y=fc["policy_lo"], line=dict(width=0), fill="tonexty",
                         fillcolor="rgba(62,123,250,0.15)", showlegend=False, hoverinfo="skip"))
# policy forecast
fig.add_trace(go.Scatter(x=fc["ds"], y=fc["policy_cap"], mode="lines", name="Policy forecast",
                         line=dict(color=theme.ACCENT, width=2.5),
                         hovertemplate="%{x|%b %Y}: %{y:,.0f}/mo<extra>Policy</extra>"))
# accelerated forecast (dashed comparison)
fig.add_trace(go.Scatter(x=fc["ds"], y=fc["accel_cap"], mode="lines", name="Accelerated forecast",
                         line=dict(color="#9AA1AD", width=2, dash="dash"),
                         hovertemplate="%{x|%b %Y}: %{y:,.0f}/mo<extra>Accelerated</extra>"))
# actual
fig.add_trace(go.Scatter(x=act["ds"], y=act["actual"], mode="lines", name="Actual",
                         line=dict(color=theme.TEXT, width=2),
                         hovertemplate="%{x|%b %Y}: %{y:,.0f}/mo<extra>Actual</extra>"))
# TIV cap lines
fig.add_hline(y=POLICY_CAP_MO, line=dict(color=theme.ACCENT, width=1, dash="dot"))
fig.add_hline(y=ACCEL_CAP_MO, line=dict(color="#9AA1AD", width=1, dash="dot"))
fig.add_annotation(x=f["ds"].min(), y=POLICY_CAP_MO, text="15% of TIV — policy target",
                   showarrow=False, xanchor="left", yanchor="bottom",
                   font=dict(color=theme.ACCENT, size=10.5))
fig.add_annotation(x=f["ds"].min(), y=ACCEL_CAP_MO, text="30% of TIV — accelerated target",
                   showarrow=False, xanchor="left", yanchor="bottom",
                   font=dict(color=theme.TEXT_MUTED, size=10.5))
# forecast start marker
fig.add_vline(x=LAST_ACTUAL, line=dict(color=theme.TEXT_FAINT, width=1, dash="dash"))
fig.add_annotation(x=LAST_ACTUAL, y=1.0, yref="paper", text="  actuals end · forecast →",
                   showarrow=False, xanchor="left", font=dict(color=theme.TEXT_MUTED, size=11))
fig.update_layout(
    # l=6 clipped the rotated y-axis title to "egistrations / month" (review
    # item A6). automargin lets plotly reserve what the title actually needs.
    height=430, margin=dict(l=12, r=14, t=10, b=6),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=theme.TEXT_MUTED, size=12),
    legend=dict(orientation="h", y=1.08, x=1, xanchor="right", font=dict(size=11)),
    hovermode="x unified",
    xaxis=dict(showgrid=False, zeroline=False),
    yaxis=dict(title="EV registrations / month", showgrid=True, automargin=True,
               gridcolor="rgba(255,255,255,0.06)", zeroline=False, rangemode="tozero"),
)
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
st.caption("The two dotted cap lines are 15% / 30% of Total Industry Volume — the national EV "
           "policy targets the logistic forecast bends toward.")

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ------------------------------------------------------------------ reactive stock & ports
ui.section_header("Projected EV stock & required ports")
ui.kpi_row([
    {"label": f"EV stock · end {year}", "value": theme.fmt_int(stock_y),
     "context": f"{scenario} scenario · cumulative registrations"},
    {"label": "Required public ports", "value": theme.fmt_int(req_y),
     "context": f"at {ratio} EVs per port · vs {CUR_PORTS:,} today"},
    {"label": "Port gap", "value": theme.fmt_int(gap_y),
     "context": f"required − existing · {year} {scenario.lower()} @ {ratio} EVs/port"},
])
st.caption("Reactive to the sidebar scenario / year / ratio. At 2030 · Policy · 15 EVs/port this lands "
           "on the headline ~24.8k ports.")

st.write("")
st.markdown("<hr>", unsafe_allow_html=True)

# ------------------------------------------------------------------ district gap
ui.section_header("District public-port gap by 2030")
g = gap.copy()
g["ev_2030"] = g[ev_col]
g["required"] = (g["ev_2030"] / ratio).round().astype(int)
g["gap"] = (g["required"] - g["current_ports"]).clip(lower=0)
g = g.sort_values("gap", ascending=False).reset_index(drop=True)

tbl_col, bar_col = st.columns([0.52, 0.48], gap="large")
with tbl_col:
    st.dataframe(
        g[["district", "ev_2030", "required", "current_ports", "gap"]],
        hide_index=True, use_container_width=True, height=300,
        column_config={
            "district": st.column_config.TextColumn("District"),
            "ev_2030": ui.int_col("EVs 2030"),
            "required": ui.int_col("Required ports"),
            "current_ports": ui.int_col("Current", width="small"),
            "gap": ui.int_col("Gap"),
        },
    )
with bar_col:
    figg = go.Figure(go.Bar(
        x=g["gap"], y=g["district"], orientation="h",
        marker=dict(color=theme.ACCENT, cornerradius=4),
        text=[f"{v:,}" for v in g["gap"]], textposition="outside", cliponaxis=False,
        textfont=dict(color=theme.TEXT, size=11),
        hovertemplate="%{y}: %{x:,} port gap<extra></extra>",
    ))
    figg.update_layout(
        height=300, margin=dict(l=6, r=40, t=6, b=6), showlegend=False, bargap=0.35,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=theme.TEXT_MUTED, size=12),
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", zeroline=False),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(figg, use_container_width=True, config={"displayModeBar": False})
st.caption(f"Gap = required − current, for the {scenario.lower()} scenario at {ratio} EVs/port, "
           "sorted worst-first.")

st.write("")

# ------------------------------------------------------------------ model credibility
st.markdown(
    "<div class='trust-strip'><b>Backtest — trained through 2024, tested on 2025:</b> "
    "Prophet logistic + policy cap <span class='tick'>17.6% MAPE</span> · Prophet linear 28.5% · "
    "ARIMA(1,1,1) 37.5%. The logistic curve with a policy-derived ceiling was chosen a priori — it "
    "encodes that EV adoption follows an S-curve bounded by the national penetration target — and it "
    "cut ARIMA's error by more than half.</div>",
    unsafe_allow_html=True,
)

st.write("")

# ------------------------------------------------------------------ assumptions
ui.section_header("Assumptions")
with st.expander("Key modelling assumptions & caveats", expanded=False):
    st.markdown(
        "- **District allocation** is population-based (KV forecast split by 2023 district population).\n"
        "- **Uniform EVs-per-port ratio** across districts (condo-heavy areas likely need more).\n"
        "- **Zero scrappage** — EV stock is cumulative registrations, no retirements.\n"
        "- **Dec-2025 spike** is treated as a one-off (CBU import-duty-exemption deadline pull-forward), "
        "not underlying trend.\n"
        "- **2026 data is partial** — actual registrations run only through March 2026."
    )

st.write("")

# ------------------------------------------------------------------ model selection
ui.section_header("Model selection")
with st.expander("Model selection — how Prophet was chosen", expanded=False):
    try:
        fcomp = data.load_forecast_comparison()
        f2030 = data.load_forecast_2030_scenarios()
    except Exception:
        fcomp = f2030 = None

    if fcomp is None or not len(fcomp):
        st.info("Benchmark artifacts not found — run "
                "`python pipeline/12_forecast_comparison.py`.")
    else:
        full = fcomp[fcomp["series"] == "full_2020_2026"]

        st.markdown("**Rolling-origin backtest** — expanding window, minimum 36 "
                    "months of training, one-month steps, every model refit at "
                    "every origin. MASE leads because the series roughly doubles "
                    "year on year, which makes MAPE reward whichever model fits "
                    "the high-volume months.")
        for h in sorted(full["h"].unique()):
            sub = full[full["h"] == h].sort_values("MASE_mean").reset_index(drop=True)
            tbl = pd.DataFrame({
                "Model": sub["model"], "Variant": sub["variant"],
                "Folds": sub["folds"],
                "MASE (mean ± std)": [f"{a:.3f} ± {b:.3f}" for a, b in
                                      zip(sub["MASE_mean"], sub["MASE_std"])],
                "MAE": sub["MAE_mean"].map("{:,.0f}".format),
                "RMSE": sub["RMSE_mean"].map("{:,.0f}".format),
                "MAPE %": sub["MAPE_mean"].map("{:.1f}".format),
            })
            st.markdown(f"*Horizon h = {int(h)} months*")
            st.markdown(ui.html_table(tbl, num_cols=list(tbl.columns[2:])),
                        unsafe_allow_html=True)
            sn = sub[sub["model"] == "SeasonalNaive"]
            if len(sn):
                st.caption(f"Seasonal-naive baseline: MASE "
                           f"{float(sn['MASE_mean'].iloc[0]):.3f}. MASE is scaled by "
                           "each fold's in-sample seasonal-naive error, so values "
                           "above 1 are expected on a series growing this fast — "
                           "the ordering is what is interpretable.")
            st.write("")

        st.markdown("**2030 plausibility** — the error table alone cannot choose "
                    "a model for a five-year projection. Two failure modes are "
                    "checked: running away above the policy ceiling, and "
                    "satisfying the ceiling by projecting almost no growth.")
        ceiling = float(f2030["policy_ceiling_monthly"].iloc[0])
        p = f2030.copy()
        ptbl = pd.DataFrame({
            "Model": p["model"], "Variant": p["variant"],
            "Dec-2030 / month": p["dec_2030_monthly"].map("{:,.0f}".format),
            "× ceiling": p["peak_over_ceiling_ratio"].map("{:.2f}×".format),
            "Growth vs last 12m": p["growth_vs_last12"].map("{:.2f}×".format),
            "2030 stock": p["cumulative_stock_2030"].map("{:,.0f}".format),
            "Verdict": p["plausible"],
        })
        st.markdown(ui.html_table(ptbl, num_cols=list(ptbl.columns[2:6])),
                    unsafe_allow_html=True)
        st.caption(f"Policy ceiling {ceiling:,.0f} registrations/month "
                   "(800,000 TIV × 15% × 62.9% KV share ÷ 12).")

        st.write("")
        fig_dir = os.path.join(str(data.DATA_DIR), "figures")
        c1, c2 = st.columns(2, gap="medium")
        for col, fn, cap in (
            (c1, "forecast_fold_errors.png", "Fold-level MASE distribution by model."),
            (c2, "forecast_2030_fan.png", "Every model projected to Dec 2030 "
                                          "against the policy ceiling."),
        ):
            path = os.path.join(fig_dir, fn)
            if os.path.exists(path):
                col.image(path, use_container_width=True, caption=cap)

        # --- summary, worded from the CSVs
        _h6 = full[full["h"] == 6].sort_values("MASE_mean").iloc[0]
        _h12 = full[full["h"] == 12].sort_values("MASE_mean").iloc[0]
        _sar = p[(p["model"] == "SARIMA")].sort_values("peak_over_ceiling_ratio").iloc[-1]
        _sar_mase = full[(full["model"] == "SARIMA") & (full["h"] == 12)]["MASE_mean"].max()
        _proph = p[(p["model"] == "ProphetLogistic") & (p["variant"] == "base")].iloc[0]
        _trend = float(_proph["trend_dec_2030"]) if pd.notna(_proph["trend_dec_2030"]) else float("nan")

        st.markdown(
            f"**Accuracy winner:** {_h6['model']} {_h6['variant']} "
            f"(MASE {_h6['MASE_mean']:.3f} at h=6, {_h12['MASE_mean']:.3f} at h=12).\n\n"
            f"**Retained model:** Prophet logistic — the only specification whose "
            f"trend saturates by construction "
            f"({_trend:,.0f}/month against a {ceiling:,.0f} ceiling). Models with "
            "better short-horizon error either exceed the ceiling or satisfy it "
            "by projecting near-zero growth.\n\n"
            f"**In-sample fit is not a forecasting criterion.** SARIMA had the "
            f"best AIC in the study (78.6) and the worst forecasts — MASE "
            f"{_sar_mase:.2f} at h=12 and a 2030 projection "
            f"{_sar['peak_over_ceiling_ratio']:.0f}× the ceiling.\n\n"
            "**The ranking is not robust.** Excluding COVID (series from 2021-01) "
            "changes the winner at both horizons, so no model here is reliably "
            "best on 74 observations with one structural break."
        )

st.write("")

st.markdown(
    "<div class='site-footer'>Ng Cheng Xin · TP071136 · Asia Pacific University · FYP 2026 · "
    "Forecast: Prophet logistic w/ policy cap · Backtest MAPE 17.6% (vs ARIMA 37.5%).</div>",
    unsafe_allow_html=True,
)
