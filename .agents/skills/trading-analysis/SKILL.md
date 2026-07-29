---
name: trading-analysis
description: Performs trading analysis for MCX Silver, including real-time market data fetching, calculation of RSI, MACD, moving averages, Bollinger Bands, and AI-based market condition analysis.
---

# Trading Analysis Skill (MCX Silver)

This skill performs comprehensive trading analysis specifically for MCX Silver.

## Capabilities

1. **Real-time Market Data Fetching:**
   - Retrieves the latest price, volume, open, high, low, and close data for MCX Silver (using appropriate commodities ticker or specific MCX API endpoints).

2. **Technical Indicators:**
   - **RSI (Relative Strength Index):** Calculates 14-period RSI to identify overbought or oversold conditions in the silver market.
   - **MACD (Moving Average Convergence Divergence):** Analyzes momentum and trend direction.
   - **Moving Averages (SMA/EMA):** Computes short-term (e.g., 9-day, 21-day) and long-term (e.g., 50-day, 200-day) moving averages to determine trend lines.
   - **Bollinger Bands:** Evaluates volatility and potential price breakouts.

3. **AI-based Market Condition Analysis:**
   - Synthesizes technical indicators with current market news and macroeconomic factors affecting silver (e.g., USD index, inflation data, industrial demand).
   - Provides an AI-driven perspective on market sentiment (bullish, bearish, or neutral).

4. **Investment Report Generation:**
   - Generates a structured markdown report summarizing the findings.
   - Includes actionable insights, risk assessment, and key support/resistance levels for MCX Silver.

## Usage

Trigger this skill by asking the agent to "generate a trading analysis for silver" or "analyze MCX silver market". The agent will execute the technical logic to pull the required data, calculate the indicators, run the AI analysis, and output the final markdown report.
