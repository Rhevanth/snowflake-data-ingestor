import os
import xml.etree.ElementTree as ET
from datetime import date, datetime
import pandas as pd
import requests
from snowflake.snowpark import Session
import yfinance as yf

# ---------------------------------------------------------
# Configuration & Credentials
# ---------------------------------------------------------
FRED_API_KEY = os.getenv("FRED_API_KEY")
CUTOFF_DATE = date(2023, 1, 1)

CONNECTION_PARAMS = {
    "account": "HSXBAWS-XT16491",
    "user": "RHEVANTH.M@GMAIL.COM",
    "password": os.getenv("SNOWFLAKE_PASSWORD"),
    "warehouse": "COMPUTE_WH",
    "database": "DEV_DB",
    "schema": "PUBLIC",
    "role": "ACCOUNTADMIN",
}

FRED_SERIES = {
    "REAL_YIELD_10Y": "DFII10",  # 10Y TIPS Real Yield
    "YIELD_10Y": "DGS10",  # 10Y Nominal Treasury Yield
    "FED_FUNDS_RATE": "DFF",  # Effective Fed Funds Rate
    "INFLATION_BREAKEVEN_10Y": "T10YIE",  # 10Y Breakeven Inflation
    "CREDIT_SPREAD": "BAMLH0A0HYM2",  # HY Credit Spread
    "YIELD_CURVE_10Y2Y": "T10Y2Y",  # 10Y minus 2Y Treasury Yield Spread
}


# ---------------------------------------------------------
# 1. Fetch Market Data (Gold, Silver, DXY, VIX)
# ---------------------------------------------------------
def fetch_yahoo_market_data() -> pd.DataFrame:
  print(
      "\n[1/3] Fetching authentic OHLCV from Yahoo Finance (GC=F, SI=F,"
      " DX-Y.NYB, ^VIX)..."
  )

  # Fetch 3 years history to ensure moving averages (200 SMA) have enough data
  gold = yf.Ticker("GC=F").history(period="3y").reset_index()
  silver = yf.Ticker("SI=F").history(period="3y").reset_index()
  dxy = yf.Ticker("DX-Y.NYB").history(period="3y").reset_index()
  vix = yf.Ticker("^VIX").history(period="3y").reset_index()

  # Clean Gold
  gold = (
      gold[["Date", "Open", "High", "Low", "Close", "Volume"]].dropna().copy()
  )
  gold["TRADE_DATE"] = pd.to_datetime(gold["Date"]).dt.date
  gold.drop(columns=["Date"], inplace=True)
  gold.rename(
      columns={
          "Open": "OPEN_PRICE",
          "High": "HIGH_PRICE",
          "Low": "LOW_PRICE",
          "Close": "CLOSE_PRICE",
          "Volume": "VOLUME",
      },
      inplace=True,
  )

  # Clean Silver (for Gold/Silver Ratio)
  silver = silver[["Date", "Close"]].dropna().copy()
  silver["TRADE_DATE"] = pd.to_datetime(silver["Date"]).dt.date
  silver.rename(columns={"Close": "SILVER_CLOSE"}, inplace=True)
  silver.drop(columns=["Date"], inplace=True)

  # Clean DXY
  dxy = dxy[["Date", "Close"]].dropna().copy()
  dxy["TRADE_DATE"] = pd.to_datetime(dxy["Date"]).dt.date
  dxy.rename(columns={"Close": "DXY_CLOSE"}, inplace=True)
  dxy.drop(columns=["Date"], inplace=True)

  # Clean VIX
  vix = vix[["Date", "Close"]].dropna().copy()
  vix["TRADE_DATE"] = pd.to_datetime(vix["Date"]).dt.date
  vix.rename(columns={"Close": "VIX_CLOSE"}, inplace=True)
  vix.drop(columns=["Date"], inplace=True)

  # Merge market data
  market_df = pd.merge(gold, silver, on="TRADE_DATE", how="left")
  market_df = pd.merge(market_df, dxy, on="TRADE_DATE", how="left")
  market_df = pd.merge(market_df, vix, on="TRADE_DATE", how="left")

  # Forward fill weekend gaps or missing market holidays
  market_df["SILVER_CLOSE"] = market_df["SILVER_CLOSE"].ffill()
  market_df["DXY_CLOSE"] = market_df["DXY_CLOSE"].ffill()
  market_df["VIX_CLOSE"] = market_df["VIX_CLOSE"].ffill()

  # Compute Gold/Silver Physical Demand Ratio
  market_df["GOLD_SILVER_RATIO"] = (
      market_df["CLOSE_PRICE"] / market_df["SILVER_CLOSE"]
  ).round(2)

  market_df = (
      market_df[market_df["TRADE_DATE"] >= CUTOFF_DATE]
      .sort_values("TRADE_DATE")
      .reset_index(drop=True)
  )

  for col in [
      "OPEN_PRICE",
      "HIGH_PRICE",
      "LOW_PRICE",
      "CLOSE_PRICE",
      "SILVER_CLOSE",
      "DXY_CLOSE",
      "VIX_CLOSE",
  ]:
    market_df[col] = market_df[col].round(2)

  print(
      f"  -> Successfully fetched {len(market_df)} market trading day records."
  )
  return market_df


# ---------------------------------------------------------
# 2. Fetch Macro Series (FRED API)
# ---------------------------------------------------------
def fetch_fred_macro_data() -> pd.DataFrame:
  print("\n[2/3] Fetching Macroeconomic Series from FRED API...")
  merged_macro = None

  for col_name, series_id in FRED_SERIES.items():
    print(f"  -> Pulling {col_name} ({series_id})...")
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json"
    res = requests.get(url, timeout=30).json()

    records = []
    for obs in res.get("observations", []):
      if obs["value"] != ".":
        dt = datetime.strptime(obs["date"], "%Y-%m-%d").date()
        if dt >= CUTOFF_DATE:
          records.append(
              {"TRADE_DATE": dt, col_name: round(float(obs["value"]), 3)}
          )

    series_df = pd.DataFrame(records)
    if not series_df.empty:
      series_df = series_df.drop_duplicates(subset=["TRADE_DATE"])
      if merged_macro is None:
        merged_macro = series_df
      else:
        merged_macro = pd.merge(
            merged_macro, series_df, on="TRADE_DATE", how="outer"
        )

  merged_macro = (
      merged_macro.sort_values("TRADE_DATE").ffill().bfill().reset_index(drop=True)
  )
  print(
      f"  -> Successfully compiled {len(merged_macro)} aligned macro dates."
  )
  return merged_macro


# ---------------------------------------------------------
# 3. Fetch Central Bank Statements (Federal Reserve RSS)
# ---------------------------------------------------------
def fetch_fed_press_releases() -> pd.DataFrame:
  print("\n[3/3] Fetching official statements from Federal Reserve RSS feed...")
  fed_rss_url = "https://www.federalreserve.gov/feeds/press_all.xml"
  headers = {"User-Agent": "Mozilla/5.0"}
  resp = requests.get(fed_rss_url, headers=headers, timeout=30)
  root = ET.fromstring(resp.content)

  records = []
  for item in root.findall("./channel/item"):
    title = item.find("title").text if item.find("title") is not None else ""
    pub_date = (
        item.find("pubDate").text if item.find("pubDate") is not None else ""
    )
    try:
      event_dt = datetime.strptime(pub_date[:16], "%a, %d %b %Y").date()
    except Exception:
      event_dt = date.today()

    clean_headline = title.strip().replace("'", "")
    if clean_headline:
      records.append({
          "EVENT_DATE": event_dt,
          "HEADLINE": clean_headline,
          "SOURCE": "Federal Reserve Press",
      })

  df_news = pd.DataFrame(records).drop_duplicates(subset=["HEADLINE"])
  print(f"  -> Retrieved {len(df_news)} unique official Fed statements.")
  return df_news


# ---------------------------------------------------------
# 4. Main Idempotent Snowflake Sync
# ---------------------------------------------------------
def main():
  # Extract
  df_market = fetch_yahoo_market_data()
  df_macro = fetch_fred_macro_data()
  df_news = fetch_fed_press_releases()

  # Transform & Align Market + Macro
  master_df = pd.merge(df_market, df_macro, on="TRADE_DATE", how="inner")
  master_df = master_df.sort_values("TRADE_DATE").reset_index(drop=True)
  master_df["IS_TRAINING"] = master_df["TRADE_DATE"] < date(2025, 1, 1)

  print(
      f"\nEstablishing connection to Snowflake ({CONNECTION_PARAMS['account']})..."
  )
  session = Session.builder.configs(CONNECTION_PARAMS).create()

  # Guarantee active database, schema, and warehouse context
  session.sql("USE WAREHOUSE COMPUTE_WH").collect()
  session.sql("CREATE DATABASE IF NOT EXISTS DEV_DB").collect()
  session.sql("CREATE SCHEMA IF NOT EXISTS DEV_DB.PUBLIC").collect()
  session.sql("USE DATABASE DEV_DB").collect()
  session.sql("USE SCHEMA PUBLIC").collect()

  # -----------------------------------------------------
  # Target Table 1: GOLD_DAILY_OHLCV (Deduplicated via MERGE on TRADE_DATE)
  # -----------------------------------------------------
  print(
      "\nSyncing DEV_DB.PUBLIC.GOLD_DAILY_OHLCV (Deduplicating via"
      " TRADE_DATE)..."
  )
  session.sql("""
        CREATE TABLE IF NOT EXISTS DEV_DB.PUBLIC.GOLD_DAILY_OHLCV (
            TRADE_DATE DATE PRIMARY KEY,
            OPEN_PRICE FLOAT,
            HIGH_PRICE FLOAT,
            LOW_PRICE FLOAT,
            CLOSE_PRICE FLOAT,
            VOLUME FLOAT,
            SILVER_CLOSE FLOAT,
            GOLD_SILVER_RATIO FLOAT,
            DXY_CLOSE FLOAT,
            VIX_CLOSE FLOAT,
            REAL_YIELD_10Y FLOAT,
            YIELD_10Y FLOAT,
            FED_FUNDS_RATE FLOAT,
            INFLATION_BREAKEVEN_10Y FLOAT,
            CREDIT_SPREAD FLOAT,
            YIELD_CURVE_10Y2Y FLOAT,
            IS_TRAINING BOOLEAN
        )
    """).collect()

  # Handle schema evolution if the table already existed with fewer columns
  schema_updates = [
      "ALTER TABLE DEV_DB.PUBLIC.GOLD_DAILY_OHLCV ADD COLUMN IF NOT EXISTS"
      " SILVER_CLOSE FLOAT",
      "ALTER TABLE DEV_DB.PUBLIC.GOLD_DAILY_OHLCV ADD COLUMN IF NOT EXISTS"
      " GOLD_SILVER_RATIO FLOAT",
      "ALTER TABLE DEV_DB.PUBLIC.GOLD_DAILY_OHLCV ADD COLUMN IF NOT EXISTS"
      " VIX_CLOSE FLOAT",
      "ALTER TABLE DEV_DB.PUBLIC.GOLD_DAILY_OHLCV ADD COLUMN IF NOT EXISTS"
      " YIELD_CURVE_10Y2Y FLOAT",
  ]
  for stmt in schema_updates:
    session.sql(stmt).collect()

  session.write_pandas(
      master_df,
      table_name="STG_GOLD_DAILY_OHLCV",
      database="DEV_DB",
      schema="PUBLIC",
      auto_create_table=True,
      overwrite=True,
  )

  session.sql("""
        MERGE INTO DEV_DB.PUBLIC.GOLD_DAILY_OHLCV t
        USING DEV_DB.PUBLIC.STG_GOLD_DAILY_OHLCV s
        ON t.TRADE_DATE = s.TRADE_DATE
        WHEN MATCHED THEN UPDATE SET
            t.OPEN_PRICE = s.OPEN_PRICE,
            t.HIGH_PRICE = s.HIGH_PRICE,
            t.LOW_PRICE = s.LOW_PRICE,
            t.CLOSE_PRICE = s.CLOSE_PRICE,
            t.VOLUME = s.VOLUME,
            t.SILVER_CLOSE = s.SILVER_CLOSE,
            t.GOLD_SILVER_RATIO = s.GOLD_SILVER_RATIO,
            t.DXY_CLOSE = s.DXY_CLOSE,
            t.VIX_CLOSE = s.VIX_CLOSE,
            t.REAL_YIELD_10Y = s.REAL_YIELD_10Y,
            t.YIELD_10Y = s.YIELD_10Y,
            t.FED_FUNDS_RATE = s.FED_FUNDS_RATE,
            t.INFLATION_BREAKEVEN_10Y = s.INFLATION_BREAKEVEN_10Y,
            t.CREDIT_SPREAD = s.CREDIT_SPREAD,
            t.YIELD_CURVE_10Y2Y = s.YIELD_CURVE_10Y2Y,
            t.IS_TRAINING = s.IS_TRAINING
        WHEN NOT MATCHED THEN INSERT (
            TRADE_DATE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE,
            VOLUME, SILVER_CLOSE, GOLD_SILVER_RATIO, DXY_CLOSE, VIX_CLOSE,
            REAL_YIELD_10Y, YIELD_10Y, FED_FUNDS_RATE, INFLATION_BREAKEVEN_10Y,
            CREDIT_SPREAD, YIELD_CURVE_10Y2Y, IS_TRAINING
        ) VALUES (
            s.TRADE_DATE, s.OPEN_PRICE, s.HIGH_PRICE, s.LOW_PRICE, s.CLOSE_PRICE,
            s.VOLUME, s.SILVER_CLOSE, s.GOLD_SILVER_RATIO, s.DXY_CLOSE, s.VIX_CLOSE,
            s.REAL_YIELD_10Y, s.YIELD_10Y, s.FED_FUNDS_RATE, s.INFLATION_BREAKEVEN_10Y,
            s.CREDIT_SPREAD, s.YIELD_CURVE_10Y2Y, s.IS_TRAINING
        )
    """).collect()
  session.sql("DROP TABLE IF EXISTS DEV_DB.PUBLIC.STG_GOLD_DAILY_OHLCV").collect()
  print("✓ GOLD_DAILY_OHLCV sync complete.")

  # -----------------------------------------------------
  # Target Table 2: MACRO_METRICS_DAILY (Deduplicated via MERGE on TRADE_DATE)
  # -----------------------------------------------------
  print(
      "Syncing DEV_DB.PUBLIC.MACRO_METRICS_DAILY (Deduplicating via"
      " TRADE_DATE)..."
  )
  session.sql("""
        CREATE TABLE IF NOT EXISTS DEV_DB.PUBLIC.MACRO_METRICS_DAILY (
            TRADE_DATE DATE PRIMARY KEY,
            REAL_YIELD_10Y FLOAT,
            YIELD_10Y FLOAT,
            FED_FUNDS_RATE FLOAT,
            INFLATION_BREAKEVEN_10Y FLOAT,
            CREDIT_SPREAD FLOAT,
            YIELD_CURVE_10Y2Y FLOAT
        )
    """).collect()

  session.sql(
      "ALTER TABLE DEV_DB.PUBLIC.MACRO_METRICS_DAILY ADD COLUMN IF NOT EXISTS"
      " YIELD_CURVE_10Y2Y FLOAT"
  ).collect()

  macro_cols = ["TRADE_DATE"] + list(FRED_SERIES.keys())
  session.write_pandas(
      master_df[macro_cols],
      table_name="STG_MACRO_METRICS_DAILY",
      database="DEV_DB",
      schema="PUBLIC",
      auto_create_table=True,
      overwrite=True,
  )

  session.sql("""
        MERGE INTO DEV_DB.PUBLIC.MACRO_METRICS_DAILY t
        USING DEV_DB.PUBLIC.STG_MACRO_METRICS_DAILY s
        ON t.TRADE_DATE = s.TRADE_DATE
        WHEN MATCHED THEN UPDATE SET
            t.REAL_YIELD_10Y = s.REAL_YIELD_10Y,
            t.YIELD_10Y = s.YIELD_10Y,
            t.FED_FUNDS_RATE = s.FED_FUNDS_RATE,
            t.INFLATION_BREAKEVEN_10Y = s.INFLATION_BREAKEVEN_10Y,
            t.CREDIT_SPREAD = s.CREDIT_SPREAD,
            t.YIELD_CURVE_10Y2Y = s.YIELD_CURVE_10Y2Y
        WHEN NOT MATCHED THEN INSERT (
            TRADE_DATE, REAL_YIELD_10Y, YIELD_10Y, FED_FUNDS_RATE,
            INFLATION_BREAKEVEN_10Y, CREDIT_SPREAD, YIELD_CURVE_10Y2Y
        ) VALUES (
            s.TRADE_DATE, s.REAL_YIELD_10Y, s.YIELD_10Y, s.FED_FUNDS_RATE,
            s.INFLATION_BREAKEVEN_10Y, s.CREDIT_SPREAD, s.YIELD_CURVE_10Y2Y
        )
    """).collect()
  session.sql(
      "DROP TABLE IF EXISTS DEV_DB.PUBLIC.STG_MACRO_METRICS_DAILY"
  ).collect()
  print("✓ MACRO_METRICS_DAILY sync complete.")

  # -----------------------------------------------------
  # Target Table 3: MACRO_NEWS_UNSTRUCTURED (Deduplicated via MERGE on HEADLINE)
  # -----------------------------------------------------
  print(
      "Syncing DEV_DB.PUBLIC.MACRO_NEWS_UNSTRUCTURED (Deduplicating via"
      " HEADLINE)..."
  )
  session.sql("""
        CREATE TABLE IF NOT EXISTS DEV_DB.PUBLIC.MACRO_NEWS_UNSTRUCTURED (
            EVENT_DATE DATE,
            HEADLINE STRING PRIMARY KEY,
            SOURCE STRING
        )
    """).collect()

  session.write_pandas(
      df_news,
      table_name="STG_MACRO_NEWS",
      database="DEV_DB",
      schema="PUBLIC",
      auto_create_table=True,
      overwrite=True,
  )

  session.sql("""
        MERGE INTO DEV_DB.PUBLIC.MACRO_NEWS_UNSTRUCTURED t
        USING DEV_DB.PUBLIC.STG_MACRO_NEWS s
        ON t.HEADLINE = s.HEADLINE
        WHEN MATCHED THEN UPDATE SET
            t.EVENT_DATE = s.EVENT_DATE,
            t.SOURCE = s.SOURCE
        WHEN NOT MATCHED THEN INSERT (
            EVENT_DATE, HEADLINE, SOURCE
        ) VALUES (
            s.EVENT_DATE, s.HEADLINE, s.SOURCE
        )
    """).collect()
  session.sql("DROP TABLE IF EXISTS DEV_DB.PUBLIC.STG_MACRO_NEWS").collect()
  print("✓ MACRO_NEWS_UNSTRUCTURED sync complete.")

  session.close()
  print(
      "\n🚀 All tables synchronized with full macroeconomic and volatility"
      " indicators!"
  )


if __name__ == "__main__":
  main()