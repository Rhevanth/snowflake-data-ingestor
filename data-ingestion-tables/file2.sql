USE WAREHOUSE COMPUTE_WH;
USE DATABASE DEV_DB;
USE SCHEMA PUBLIC;

CREATE OR REPLACE VIEW DEV_DB.PUBLIC.GOLD_ACTION_RECOMMENDER AS
WITH price_changes AS (
    SELECT 
        trade_date,
        open_price,
        high_price,
        low_price,
        close_price,
        volume,
        dxy_close,
        real_yield_10y,
        yield_10y,
        fed_funds_rate,
        inflation_breakeven_10y,
        credit_spread,
        is_training,
        close_price - LAG(close_price, 1) OVER (ORDER BY trade_date) AS change,
        close_price - LAG(close_price, 5) OVER (ORDER BY trade_date) AS change_5d,
        AVG(close_price) OVER (ORDER BY trade_date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS sma_50,
        AVG(close_price) OVER (ORDER BY trade_date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS sma_200,
        STDDEV(close_price) OVER (ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS std_20
    FROM DEV_DB.PUBLIC.GOLD_DAILY_OHLCV
),
indicators AS (
    SELECT 
        p.*,
        (p.sma_50 + (2 * p.std_20)) AS upper_band,
        (p.sma_50 - (2 * p.std_20)) AS lower_band,
        AVG(CASE WHEN change > 0 THEN change ELSE 0 END) OVER (ORDER BY trade_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_gain,
        AVG(CASE WHEN change < 0 THEN ABS(change) ELSE 0 END) OVER (ORDER BY trade_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_loss
    FROM price_changes p
),
scored AS (
    SELECT 
        trade_date,
        open_price,
        high_price,
        low_price,
        close_price,
        volume,
        dxy_close,
        real_yield_10y,
        yield_10y,
        fed_funds_rate,
        inflation_breakeven_10y,
        credit_spread,
        is_training,
        change,
        change_5d,
        ROUND(sma_50, 2) AS sma_50,
        ROUND(sma_200, 2) AS sma_200,
        ROUND(upper_band, 2) AS upper_band,
        ROUND(lower_band, 2) AS lower_band,
        ROUND(100 - (100 / (1 + (NULLIF(avg_gain, 0) / NULLIF(avg_loss, 0.00001)))), 1) AS rsi_14,
        CASE 
            WHEN real_yield_10y < LAG(real_yield_10y, 20) OVER (ORDER BY trade_date) THEN 'BULLISH_MACRO'
            ELSE 'BEARISH_MACRO'
        END AS real_yield_regime,
        CASE 
            WHEN credit_spread > 4.0 OR dxy_close < 102 THEN 'RISK_OFF / DOVISH'
            ELSE 'RISK_ON / NEUTRAL'
        END AS market_sentiment_regime
    FROM indicators
)
SELECT 
    trade_date,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    dxy_close,
    real_yield_10y,
    yield_10y,
    fed_funds_rate,
    inflation_breakeven_10y,
    credit_spread,
    is_training,
    change,
    change_5d,
    sma_50,
    sma_200,
    upper_band,
    lower_band,
    rsi_14,
    real_yield_regime,
    market_sentiment_regime,
    -- Strictly colored recommendation logic
    CASE 
        -- If price is below 50 SMA OR actively crashing (5-day change negative with high yield pressure) -> RED
        WHEN close_price < sma_50 OR (change_5d < -30 AND real_yield_regime = 'BEARISH_MACRO') THEN 'INITIATE HEDGE (SHORT)'
        -- Overbought -> ORANGE
        WHEN rsi_14 >= 70 THEN 'TAKE PROFIT / REDUCE'
        -- Strong uptrend + price rising + macro tailwind -> STRONG GREEN
        WHEN close_price > sma_50 AND change_5d >= 0 AND rsi_14 BETWEEN 45 AND 65 AND real_yield_regime = 'BULLISH_MACRO' THEN 'STRONG ACCUMULATE (LONG)'
        -- Moderate uptrend -> GREEN
        WHEN close_price > sma_50 AND change_5d >= 0 AND rsi_14 < 65 THEN 'ACCUMULATE (LONG)'
        -- In an uptrend but pulling back short-term -> NEUTRAL / CAUTION (GRAY)
        ELSE 'HOLD / NEUTRAL'
    END AS agent_recommendation,
    ROUND(close_price * 0.98, 2) AS dynamic_stop_loss
FROM scored;