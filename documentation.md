# Autonomous Gold Treasury & Hedging Copilot: MVP Functional Overview

## 1. System Architecture & Component Mapping

The platform operates as a closed-loop data intelligence engine designed to translate multi-asset macro volatility, central bank communications, and technical trends into institutional-grade treasury allocation signals.

```
[External Feeds: FRED + Yahoo Finance + Fed RSS]
                         │
                         ▼
     [External Runner: GitHub Actions / Self-Hosted]
                         │ (Idempotent MERGE via Snowpark)
                         ▼
             [Snowflake Raw Ingestion Layer]
   ┌─────────────────────┼─────────────────────┐
   ▼                     ▼                     ▼
GOLD_DAILY_OHLCV  MACRO_METRICS_DAILY  MACRO_NEWS_UNSTRUCTURED
   └─────────────────────┬─────────────────────┘
                         ▼
     [SQL Analytics Engine: GOLD_ACTION_RECOMMENDER]
                         │ (Real-Time Inferences & Bands)
                         ▼
   [Streamlit in Snowflake (SiS) Presentation Layer]
   ┌─────────────────────┼─────────────────────┐
   ▼                     ▼                     ▼
Executive Verdict     ELI5 Explainer      Scenario Simulator

```

---

## 2. Ingestion Pipeline & Data Schema

### Automated Ingestion (`ingest_all_data.py`)

* **Trigger Strategy:** Scheduled via GitHub Actions (`*/5 * * * *`) backed by a persistent local/self-hosted runner to bypass managed runner quota restrictions and trial network limitations.
* **Protocol:** Python 3.10 using Snowpark, `requests`, and `yfinance`.
* **Deduplication Logic:** Target tables use primary key constraints combined with SQL `MERGE` patterns to guarantee idempotency on updates.

### Core Data Models

#### `DEV_DB.PUBLIC.GOLD_DAILY_OHLCV`

Primary time-series table containing technical market metrics and aligned macro series:

* **Keys & Fundamentals:** `TRADE_DATE` (Date, PK), `OPEN_PRICE`, `HIGH_PRICE`, `LOW_PRICE`, `CLOSE_PRICE`, `VOLUME`.
* **Cross-Asset Signals:** `SILVER_CLOSE`, `GOLD_SILVER_RATIO` ($GC=F / SI=F$), `DXY_CLOSE` (US Dollar Index), `VIX_CLOSE` (CBOE S&P 500 Volatility Index).
* **Macro Drivers (FRED Aligned):** `REAL_YIELD_10Y` (10Y TIPS), `YIELD_10Y` (10Y Nominal), `FED_FUNDS_RATE`, `INFLATION_BREAKEVEN_10Y`, `CREDIT_SPREAD` (US High Yield OAS), `YIELD_CURVE_10Y2Y` (10Y minus 2Y Spread).
* **Partitioning:** `IS_TRAINING` (Boolean, splits historical calibration before 2025 vs out-of-sample forward testing).

#### `DEV_DB.PUBLIC.MACRO_METRICS_DAILY`

Dedicated macro tracking store maintaining raw historical series for independent macroeconomic regression and correlation analysis.

#### `DEV_DB.PUBLIC.MACRO_NEWS_UNSTRUCTURED`

Ingests unstructured text from the Federal Reserve Board of Governors RSS feed (`EVENT_DATE`, `HEADLINE` [PK], `SOURCE`) for downstream sentiment scoring and policy shift detection via Snowflake Cortex.

---

## 3. Decision Engine: `GOLD_ACTION_RECOMMENDER`

The analytical engine runs entirely inside Snowflake as a dynamic view, calculating continuous rolling technical indicators and multi-regime triggers across the data streams.

### Quantitative Calculations

* **Trend Detection:** 50-Day Simple Moving Average ($\text{SMA}_{50}$) and 200-Day Simple Moving Average ($\text{SMA}_{200}$).
* **Volatility Envelopes:** 20-Day Standard Deviation bands ($\text{SMA}_{50} \pm 2\sigma$).
* **Momentum:** 14-Day Relative Strength Index ($\text{RSI}_{14}$) calculated via smoothed upward and downward price changes.
* **Risk Preservation:** Dynamic trailing stop-loss level initialized at $2\%$ below the current spot close price.

### Macro & Sentiment Regimes

* **Real Yield Regime:**
* $\text{REAL\_YIELD}_{10Y} < \text{LAG}(\text{REAL\_YIELD}_{10Y}, 20) \implies \textbf{BULLISH\_MACRO}$ (Decreasing real opportunity cost).
* Otherwise $\implies \textbf{BEARISH\_MACRO}$ (Rising real rates).


* **Market Sentiment & Liquidity:**
* $\text{VIX} > 25.0 \lor \text{CREDIT\_SPREAD} > 4.5 \implies \textbf{HIGH FEAR / RISK\_OFF}$
* $\text{GOLD\_SILVER\_RATIO} > 85.0 \implies \textbf{MONETARY DEMAND (FLIGHT TO SAFETY)}$
* Otherwise $\implies \textbf{RISK\_ON / STABLE}$


* **Yield Curve Regime:**
* $\text{T10Y2Y} < 0 \implies \textbf{INVERTED (RECESSION WATCH)}$
* $\text{T10Y2Y} \ge 0 \land \text{LAG}(\text{T10Y2Y}, 20) < 0 \implies \textbf{UN-INVERTING (EARLY RATE CUT TAILWIND)}$
* Otherwise $\implies \textbf{NORMAL EXPANSION}$



### Recommendation Matrix

| Market State & Indicator Conditions | Triggered Action | Visual Coding | Target Portfolio Action |
| --- | --- | --- | --- |
| $\text{Close} > \text{SMA}_{50} \land \Delta_{5D} \ge 0 \land 45 \le \text{RSI} \le 65 \land (\text{Bullish Macro} \lor \text{GS Ratio} > 85)$ | **STRONG ACCUMULATE (LONG)** | Vibrant Green (`#00C853`) | $20\% - 25\%$ Gold Allocation, aggressive DCA |
| $\text{Close} > \text{SMA}_{50} \land \Delta_{5D} \ge 0 \land \text{RSI} < 65$ | **ACCUMULATE (LONG)** | Forest Green (`#2E7D32`) | $15\% - 20\%$ Gold Allocation, structured buying |
| $\text{Close} < \text{SMA}_{50} \lor (\Delta_{5D} < -35 \land \text{Bearish Macro})$ | **INITIATE HEDGE (SHORT)** | Red (`#D50000`) | $5\% - 10\%$ Gold, initiate short futures/puts hedge |
| $\text{RSI} \ge 70.0$ | **TAKE PROFIT / REDUCE** | Orange (`#FF6D00`) | Trim $25\%$ of long exposure, raise cash buffers |
| Conflicting or consolidating indicators | **HOLD / NEUTRAL** | Slate Gray (`#546E7A`) | Maintain existing core allocation; pause new orders |

---

## 4. User Interface Architecture (Streamlit in Snowflake)

Built natively on the **Warehouse Runtime** using `COMPUTE_WH` to ensure dependency stability, fast start times, and zero external package failures.

```
┌────────────────────────────────────────────────────────────────────────┐
│  🪙 Autonomous Gold Copilot                 Active: 2026-10-04         │
│  [BANNER] 🚀 STRONG ACCUMULATE (LONG) - Macro & Technical Aligned     │
├────────────┬────────────┬────────────┬────────────┬────────────┬───────┤
│ Gold Spot  │ 50D Floor  │ 10Y TIPS   │ Gold/Silver│ Yield Curve│ VIX   │
│ $2,654.10  │ $2,580.40  │ 1.62%      │ 86.4       │ +0.18%     │ 15.2  │
└────────────┴────────────┴────────────┴────────────┴────────────┴───────┘
  [Tab 1: Playbook & Triggers]  [Tab 2: ELI5]  [Tab 3: Simulator]  [Tab 4: Charts]

```

### Module Breakdown

1. **Executive Verdict & Allocation Guide:** Color-coded status header communicating immediate operational posture, strategic cash vs. gold balance, and explicit stop-loss price levels.
2. **Directional KPI Strip:** 6 synchronized metrics mapping spot prices, moving average cushions, real rates, volatility, and safe-haven expansion ratios with contextual delta inversions (e.g., negative yield changes display in green).
3. **Institutional Flip Triggers:** Numerical threshold matrix highlighting the exact market price or rate adjustment required to invalidate the current stance.
4. **Investor ELI5 Guide:** Non-technical breakdowns of key financial mechanisms (TIPS opportunity cost, yield curve uninversion, and gold/silver divergence).
5. **Interactive What-If Scenario Simulator:** Local client-side parameter model allowing users to drag sliders across price points, RSI, and macro shifts to preview how the recommendation engine responds under simulated shocks.
6. **Multi-Series Historical Charts:** Native visualizations tracking spot price channels against 50/200-day moving averages and macro rate spreads.