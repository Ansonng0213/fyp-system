"""Page 3 — Demand Forecast.

How many EVs are coming, and how many public ports that needs. Reads the two
forecast artifacts only. A monthly-registration forecast chart (actual → policy
band + accelerated comparison, with the two TIV cap lines), a year/scenario/ratio
explorer that turns projected EV stock into required ports, the district-level
2030 gap, an honest backtest strip and an assumptions expander.
"""
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

# fixed headline (policy scenario, 15 EVs/port) — the quotable stat
REQ_2030 = int(gap["required_ports_2030"].sum())          # 24,819
CUR_PORTS = int(gap["current_ports"].sum())               # 867
GAP_2030 = int(gap["port_gap"].sum())                     # 23,952


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
req_y = stock_y / ratio
gap_y = max(0.0, req_y - CUR_PORTS)

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
    height=430, margin=dict(l=6, r=14, t=10, b=6),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=theme.TEXT_MUTED, size=12),
    legend=dict(orientation="h", y=1.08, x=1, xanchor="right", font=dict(size=11)),
    hovermode="x unified",
    xaxis=dict(showgrid=False, zeroline=False),
    yaxis=dict(title="EV registrations / month", showgrid=True,
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
            "ev_2030": st.column_config.NumberColumn("EVs 2030", format="%d"),
            "required": st.column_config.NumberColumn("Required ports", format="%d"),
            "current_ports": st.column_config.NumberColumn("Current", format="%d", width="small"),
            "gap": st.column_config.NumberColumn("Gap", format="%d"),
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

st.markdown(
    "<div class='site-footer'>Ng Cheng Xin · TP071136 · Asia Pacific University · FYP 2026 · "
    "Forecast: Prophet logistic w/ policy cap · Backtest MAPE 17.6% (vs ARIMA 37.5%).</div>",
    unsafe_allow_html=True,
)
