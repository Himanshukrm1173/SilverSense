---
name: sentiment-analysis-trading
description: Summarizes macro factors relevant to silver (USD index, Fed rate decisions, inflation, industrial demand) into a short bullish, bearish, or neutral sentiment tag.
---

# Sentiment Analysis Trading (MCX Silver)

This skill evaluates macroeconomic conditions to determine the prevailing market sentiment for MCX Silver.

## Logic and Requirements

1. **Factor Evaluation:**
   - Evaluates the impact of key macroeconomic indicators on the price of silver:
     - **USD Index (DXY):** Inverse correlation (stronger USD typically pressures silver).
     - **Fed Rate Decisions:** Higher rates often decrease the appeal of non-yielding silver.
     - **Inflation Data:** High inflation can boost silver as an inflation hedge.
     - **Industrial Demand:** High demand (e.g., in electronics or green energy) supports silver prices.

2. **Sentiment Output:**
   - Synthesizes these factors and outputs a clear, single-tag summary: `[BULLISH]`, `[BEARISH]`, or `[NEUTRAL]`.

3. **Brief Rationale:**
   - Follows the tag with a 1-2 sentence explanation connecting the current macro conditions to the assigned sentiment.

## Usage

Trigger this skill by asking the agent for a "macro sentiment analysis for silver" or to "summarize the fundamental sentiment for MCX silver."
