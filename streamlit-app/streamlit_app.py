import pandas as pd
from snowflake.snowpark.context import get_active_session
import streamlit as st

st.set_page_config(
    page_title="Gold Treasury & Hedging Copilot",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="expanded",
)

session = get_active_session()

# Custom Styling
st.markdown(
    """
<style>
    .metric-card {
        background-color: #1e2130;
        border: 1px solid #2d3250;
        padding: 18px;
        border-radius: 10px;
        text-align: center;
    }
    .stMetric label { font-size: 0.9rem !important; color: #a0aec0 !important; }
    .stMetric [data-testid="stMetricValue"] { font-size: 1.5rem !important; font-weight: 700 !important; }
</style>
""",
    unsafe_allow_html=True,
)

# Fetch Data
df = session.sql("""
    SELECT * 
    FROM DEV_DB.PUBLIC.GOLD_ACTION_RECOMMENDER 
    ORDER BY TRADE_DATE ASC
""").to_pandas()

if df.empty:
  st.warning("No records found in DEV_DB.PUBLIC.GOLD_ACTION_RECOMMENDER.")
  st.stop()

latest = df.iloc[-1]
prev = df.iloc[-2] if len(df) > 1 else latest

action = latest["AGENT_RECOMMENDATION"]
close_price = latest["CLOSE_PRICE"]
sma_50 = latest["SMA_50"]
sma_200 = latest["SMA_200"]
rsi = latest["RSI_14"]
real_yield = latest["REAL_YIELD_10Y"]
dxy = latest["DXY_CLOSE"]
stop_loss = latest["DYNAMIC_STOP_LOSS"]
regime = latest["REAL_YIELD_REGIME"]
gs_ratio = latest.get("GOLD_SILVER_RATIO", 85.0)
yield_curve = latest.get("YIELD_CURVE_10Y2Y", 0.15)
vix = latest.get("VIX_CLOSE", 16.0)
yc_regime = latest.get("YIELD_CURVE_REGIME", "NORMAL")

status_map = {
    "STRONG ACCUMULATE (LONG)": {
        "badge": "#00C853",
        "icon": "🚀",
        "title": "Strong Buying Opportunity",
        "plain": (
            "Macro and technical tailwinds are aligned. Gold has strong"
            " momentum with low real yields reducing the holding opportunity"
            " cost."
        ),
        "gold_alloc": "20% - 25%",
        "cash_alloc": "5% - 10%",
        "bias": "Aggressive Accumulation",
    },
    "ACCUMULATE (LONG)": {
        "badge": "#2E7D32",
        "icon": "📈",
        "title": "Favorable Buying Zone",
        "plain": (
            "Price trend is healthy above the 50-day average. Steady"
            " accumulation is favored over aggressive lump-sum entries."
        ),
        "gold_alloc": "15% - 20%",
        "cash_alloc": "10% - 15%",
        "bias": "Dollar-Cost Averaging",
    },
    "INITIATE HEDGE (SHORT)": {
        "badge": "#D50000",
        "icon": "🛡️",
        "title": "Defensive / Hedging Mode",
        "plain": (
            "Gold is breaking below trend support or facing headwind from"
            " rising Treasury yields. Protect existing gains or reduce"
            " exposure."
        ),
        "gold_alloc": "5% - 10%",
        "cash_alloc": "25% - 30%",
        "bias": "Capital Preservation",
    },
    "TAKE PROFIT / REDUCE": {
        "badge": "#FF6D00",
        "icon": "⚠️",
        "title": "Overbought Alert: Lock In Gains",
        "plain": (
            "Gold has surged rapidly and momentum indicators are extended. High"
            " risk of a near-term pull-back."
        ),
        "gold_alloc": "10% - 15%",
        "cash_alloc": "20% - 25%",
        "bias": "Trimming Winners",
    },
    "HOLD / NEUTRAL": {
        "badge": "#546E7A",
        "icon": "⚖️",
        "title": "Neutral / Wait and Watch",
        "plain": (
            "Signals are conflicting. Wait for price or yields to confirm"
            " direction before committing new capital."
        ),
        "gold_alloc": "10% - 12%",
        "cash_alloc": "15% - 20%",
        "bias": "Observational",
    },
}

cfg = status_map.get(action, status_map["HOLD / NEUTRAL"])

st.title("🪙 Autonomous Gold Copilot")
st.caption(
    "Real-Time Institutional Intelligence Engine • Active as of"
    f" **{latest['TRADE_DATE']}**"
)

# Header Banner
st.markdown(
    f"""
<div style="background: linear-gradient(90deg, {cfg['badge']}22 0%, #111420 100%); 
            border-left: 6px solid {cfg['badge']}; 
            padding: 20px 24px; 
            border-radius: 10px; 
            margin-bottom: 24px;">
    <div style="font-size: 13px; text-transform: uppercase; letter-spacing: 1.5px; color: {cfg['badge']}; font-weight: 700;">
        Recommended Treasury Stance
    </div>
    <div style="font-size: 28px; font-weight: 800; color: #ffffff; margin: 4px 0 8px 0;">
        {cfg['icon']} {action} — {cfg['title']}
    </div>
    <div style="font-size: 15px; color: #d1d5db; line-height: 1.5; max-width: 900px;">
        {cfg['plain']}
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# KPIs
k1, k2, k3, k4, k5, k6 = st.columns(6)
day_change = close_price - prev["CLOSE_PRICE"]
k1.metric(
    "Gold Spot (GC=F)",
    f"${close_price:,.2f}",
    delta=f"${day_change:+,.2f} (1D)",
    delta_color="normal",
)
k2.metric(
    "50-Day Trend Floor",
    f"${sma_50:,.2f}",
    delta=f"${close_price - sma_50:+,.2f} vs Spot",
    delta_color="normal",
)
k3.metric(
    "10Y Real TIPS Yield",
    f"{real_yield:.2f}%",
    delta="Bullish Tailwind" if regime == "BULLISH_MACRO" else "Headwind",
    delta_color="inverse",
)
k4.metric(
    "Gold/Silver Ratio",
    f"{gs_ratio:.1f}",
    delta="Safe Haven Flight" if gs_ratio > 85 else "Balanced",
    delta_color="off",
)
k5.metric(
    "Yield Curve (10Y-2Y)",
    f"{yield_curve:+.2f}%",
    delta=yc_regime.split(" ")[0],
    delta_color="off",
)
k6.metric(
    "CBOE VIX (Fear)",
    f"{vix:.1f}",
    delta="Elevated Panic" if vix > 22 else "Low Volatility",
    delta_color="inverse",
)

st.write("")

tab_overview, tab_eli5, tab_simulator, tab_charts = st.tabs([
    "🎯 Investor Playbook & Triggers",
    "💡 Plain-English Explainer (ELI5)",
    "🧪 Scenario Simulator (What-If?)",
    "📊 Deep Analytics",
])

with tab_overview:
  c_left, c_right = st.columns([1.2, 1])
  with c_left:
    st.subheader("📋 Practical Action Plan")
    st.markdown(f"""
        - **Target Gold Allocation:** `{cfg['gold_alloc']}` of your liquid portfolio.
        - **Target Cash / Liquidity:** `{cfg['cash_alloc']}`
        - **Operational Bias:** **{cfg['bias']}**
        - **Execution Guidance:**
          - **If already long:** Keep trailing stops pinned at **`${stop_loss:,.2f}`**.
          - **If looking to buy:** Entry is favored as long as price remains above **`${sma_50:,.2f}`**.
          - **Currency Context:** DXY is at **`{dxy:.2f}`**. Sustained weakness below 102 adds upward gold momentum.
        """)

    st.subheader("🔍 Why the Model Decided This")
    reasons = []
    if close_price > sma_50:
      reasons.append({
          "Factor": "📈 Price vs Trend",
          "Condition": "Gold > 50-day average",
          "Assessment": "Positive Momentum intact",
      })
    else:
      reasons.append({
          "Factor": "📉 Price vs Trend",
          "Condition": "Gold < 50-day average",
          "Assessment": "Trend broken; caution required",
      })

    if rsi < 55:
      reasons.append({
          "Factor": "⚡ Velocity (RSI)",
          "Condition": f"RSI is {rsi:.1f} (< 55)",
          "Assessment": "Not overheated; upside runway available",
      })
    elif rsi >= 70:
      reasons.append({
          "Factor": "⚡ Velocity (RSI)",
          "Condition": f"RSI is {rsi:.1f} (≥ 70)",
          "Assessment": "Overbought; pull-back risk elevated",
      })
    else:
      reasons.append({
          "Factor": "⚡ Velocity (RSI)",
          "Condition": f"RSI is {rsi:.1f}",
          "Assessment": "Balanced momentum",
      })

    reasons.append({
        "Factor": "🏛️ Macro Yields",
        "Condition": f"10Y Real TIPS at {real_yield:.2f}%",
        "Assessment": (
            "Yields falling vs 20D average"
            if regime == "BULLISH_MACRO"
            else "Yields elevated; headwind for non-yielding gold"
        ),
    })

    reasons.append({
        "Factor": "🪙 Physical Demand",
        "Condition": f"Gold/Silver Ratio at {gs_ratio:.1f}",
        "Assessment": (
            "Monetary safe-haven premium active (>85)"
            if gs_ratio > 85
            else "Balanced industrial/monetary split"
        ),
    })
    st.dataframe(pd.DataFrame(reasons), hide_index=True)

  with c_right:
    st.subheader("⚡ Flip Triggers: When Does Advice Change?")
    triggers = [
        {
            "Trigger Event": f"Gold drops below ${sma_50:,.2f}",
            "Current Level": f"${close_price:,.2f}",
            "Impact": "Model downgrades to INITIATE HEDGE",
        },
        {
            "Trigger Event": "RSI surges above 70.0",
            "Current Level": f"{rsi:.1f}",
            "Impact": "Model flips to TAKE PROFIT / REDUCE",
        },
        {
            "Trigger Event": "10Y Real Yield expands +0.20%",
            "Current Level": f"{real_yield:.2f}%",
            "Impact": "Macro tailwind flips to BEARISH",
        },
        {
            "Trigger Event": f"CBOE VIX surges > 30.0",
            "Current Level": f"{vix:.1f}",
            "Impact": "Liquidity dislocation warning",
        },
        {
            "Trigger Event": f"Price breaches Stop-Loss (${stop_loss:,.2f})",
            "Current Level": f"${close_price:,.2f}",
            "Impact": "Automatic Capital Preservation Exit",
        },
    ]
    st.dataframe(pd.DataFrame(triggers), hide_index=True)

with tab_eli5:
  col_a, col_b = st.columns(2)
  with col_a:
    with st.expander(
        "🪙 1. 50-Day & 200-Day Moving Averages (The Trend)", expanded=True
    ):
      st.write(
          "Price above the 50-day average indicates buyers are in control. A"
          " Golden Cross (50 crossing above 200) signals sustained structural"
          " bull markets."
      )
    with st.expander("⚡ 2. RSI (The Speedometer)", expanded=True):
      st.write(
          "RSI gauges momentum speed (0-100). Above 70 is overbought (exhaustion"
          " risk), below 35 is oversold, and 45-60 represents healthy steady"
          " trend continuation."
      )
    with st.expander("🪙 3. Gold / Silver Ratio (Flight to Safety)"):
      st.write(
          "Silver has heavy industrial utility; Gold is pure monetary reserve."
          " When the ratio expands above 85, investors are shedding industrial"
          " risk in favor of gold safe-haven certainty."
      )
  with col_b:
    with st.expander(
        "🏛️ 4. 10-Year Real TIPS Yields (Gold's Competitor)", expanded=True
    ):
      st.write(
          "Gold pays zero yield. When inflation-adjusted Treasury yields fall,"
          " the opportunity cost of holding non-yielding gold drops, providing"
          " a major catalyst for institutional inflows."
      )
    with st.expander("📈 5. 10Y–2Y Yield Curve (Recession & Rate Cuts)"):
      st.write(
          "When the yield curve un-inverts after a recession watch, it"
          " historically signals imminent Fed rate cuts, which has"
          " consistently catalyzed multi-quarter gold rallies."
      )
    with st.expander("⚡ 6. CBOE VIX Index (Panic & Liquidity)"):
      st.write(
          "During rapid panic spikes (>30), gold is occasionally sold to meet"
          " equity margin calls before resuming its structural ascent."
      )

with tab_simulator:
  st.subheader("🧪 Interactive Scenario Tester")
  sim_col1, sim_col2, sim_col3 = st.columns(3)
  sim_price = sim_col1.slider(
      "Simulated Gold Price ($)",
      float(close_price * 0.85),
      float(close_price * 1.15),
      float(close_price),
      step=10.0,
  )
  sim_rsi = sim_col2.slider("Simulated RSI", 20.0, 85.0, float(rsi), step=1.0)
  sim_yield_diff = sim_col3.selectbox("Macro Yield Direction", [
      "Falling Real Yields (Bullish)",
      "Rising Real Yields (Bearish)",
  ])

  sim_regime = "BULLISH_MACRO" if "Falling" in sim_yield_diff else "BEARISH_MACRO"
  if sim_price > sma_50 and sim_rsi < 55 and sim_regime == "BULLISH_MACRO":
    sim_action = "STRONG ACCUMULATE (LONG)"
  elif sim_price > sma_50 and sim_rsi < 65:
    sim_action = "ACCUMULATE (LONG)"
  elif sim_price < sma_50 and (sim_rsi > 50 or sim_regime == "BEARISH_MACRO"):
    sim_action = "INITIATE HEDGE (SHORT)"
  elif sim_rsi >= 70:
    sim_action = "TAKE PROFIT / REDUCE"
  else:
    sim_action = "HOLD / NEUTRAL"

  sim_cfg = status_map.get(sim_action, status_map["HOLD / NEUTRAL"])
  st.markdown(
      f"""
    <div style="background-color: {sim_cfg['badge']}22; border-left: 5px solid {sim_cfg['badge']}; padding: 14px; border-radius: 6px; margin-top: 15px;">
        <b>Simulated Stance:</b> <span style="color: {sim_cfg['badge']}; font-weight: bold;">{sim_cfg['icon']} {sim_action}</span><br>
        <span style="font-size: 14px; color: #ccc;">{sim_cfg['plain']}</span>
    </div>
    """,
      unsafe_allow_html=True,
  )

with tab_charts:
  st.subheader("Price Action vs 50/200 Day Averages")
  st.line_chart(
      df.set_index("TRADE_DATE")[
          ["CLOSE_PRICE", "SMA_50", "SMA_200", "UPPER_BAND", "LOWER_BAND"]
      ]
  )

  c_m1, c_m2 = st.columns(2)
  with c_m1:
    st.caption("10Y Real TIPS Yield & 10Y-2Y Yield Curve (%)")
    st.line_chart(
        df.set_index("TRADE_DATE")[["REAL_YIELD_10Y", "YIELD_CURVE_10Y2Y"]]
    )
  with c_m2:
    st.caption("Gold/Silver Ratio & VIX")
    st.line_chart(
        df.set_index("TRADE_DATE")[["GOLD_SILVER_RATIO", "VIX_CLOSE"]]
    )