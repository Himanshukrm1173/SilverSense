---
name: multi-horizon-forecast
description: Generates separate bias and reasoning for MCX Silver across three time horizons (24H, 1W, 1M) using distinct indicators.
---

# Multi-Horizon Forecast Skill (MCX Silver)

This skill provides a multi-timeframe forecast for MCX Silver, ensuring distinct analysis for short, medium, and long-term horizons.

## Logic and Requirements

Generates SEPARATE bias (Bullish, Bearish, or Neutral) and reasoning for the following three time horizons. The bias across horizons must NOT simply be duplicated unless there is strong justification.

1. **24 Hours (Short-Term):**
   - **Focus:** Momentum, immediate price action, and intraday volatility.
   - **Indicators:** Short-term RSI, fast stochastic, hourly MACD, immediate support/resistance breakouts.

2. **1 Week (Medium-Term):**
   - **Focus:** Trend continuation, swing levels, and weekly setups.
   - **Indicators:** Daily moving averages (e.g., 9 EMA, 21 EMA), Bollinger Bands, weekly volume profiles, and significant chart patterns.

3. **1 Month (Long-Term):**
   - **Focus:** Macro factors, structural trends, and fundamental drivers.
   - **Indicators/Factors:** 50-day and 200-day SMAs, USD Index (DXY) correlation, inflation data, industrial demand metrics, and geopolitical events.

## Usage
Trigger this skill by asking for a "multi-horizon forecast for silver" or "timeframe analysis for MCX silver."
