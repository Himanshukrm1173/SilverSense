---
name: market-regimes
description: Classifies current MCX Silver market state into trend-up, trend-down, range, high-volatility, breakout, or reversal using price action, moving averages, Bollinger Bands, and volatility metrics.
---

# Market Regimes Skill (MCX Silver)

This skill classifies the current market regime for MCX Silver to provide context for all downstream forecasts and trade decisions.

## Logic and Requirements

1. **Input Data (instrument-specific only):**
   - The selected instrument's own price history (MCX Silver, Tata Silver, or Silver Bees — never mixed).
   - 20-period and 50-period Simple Moving Averages (SMA20, SMA50).
   - Bollinger Bands (20-period, 2 standard deviations).
   - ATR (Average True Range) for volatility measurement.

2. **Regime Classification Rules:**
   - **trend-up:** Price consistently above SMA20, SMA20 above SMA50, low ATR relative to price.
   - **trend-down:** Price consistently below SMA20, SMA20 below SMA50, low ATR relative to price.
   - **range:** Price oscillating between Bollinger Band midline and both bands, flat SMAs.
   - **high-volatility:** ATR spiking significantly above its 20-period average (>1.5x).
   - **breakout:** Price closing decisively above/below Bollinger Band outer boundaries with increasing volume.
   - **reversal:** Price crossing back over SMA20 after sustained move, diverging from prior trend.

3. **Output:**
   - A single lowercase string: one of `trend-up`, `trend-down`, `range`, `high-volatility`, `breakout`, or `reversal`.
   - A brief one-sentence rationale for the classification.
   - A `regime_strength` score (0.0–1.0) indicating conviction in the classification.

## Usage

This skill runs as pipeline stage 3, after `data-quality-checker` and `trading-analysis`. Trigger by asking "what is the current market regime for silver?" or it is invoked automatically before any forecast is generated.
