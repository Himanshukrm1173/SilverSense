---
name: macro-regime-detector
description: Evaluates macroeconomic indicators (DXY, US yields, USDINR, inflation, Fed expectations) to classify the current macro regime and flag regime-transition risk for MCX Silver forecasting.
---

# Macro Regime Detector (MCX Silver)

This skill evaluates macroeconomic conditions to classify the current macro environment and assess its impact on MCX Silver.

## Logic and Requirements

1. **Input Factors:**
   - **DXY (Dollar Index):** Rising DXY = risk-off pressure on silver. Falling DXY = supportive.
   - **US 10-Year Yield:** Rising yields = opportunity cost pressure on non-yielding silver.
   - **USD/INR Rate:** Rising USDINR (rupee weakening) = MCX silver prices rise even if spot is flat.
   - **Fed Rate Expectations:** Hawkish Fed (rate hike expected) = bearish for silver.
   - **Inflation Proxy:** High CPI/PPI trend = bullish for silver as inflation hedge.

2. **Macro Regime Classification:**
   - **risk-on:** DXY falling, yields falling, Fed dovish — broadly bullish for silver.
   - **risk-off:** DXY rising, yields rising, Fed hawkish — broadly bearish for silver.
   - **stagflation:** Inflation high but growth slowing — mixed but potentially supportive for silver.
   - **neutral:** No dominant macro force; indicators are mixed or flat.

3. **Regime Transition Risk:**
   - Flag `regime_transition_risk = True` when two or more macro indicators have changed direction in the last 3 sessions, signaling instability.

4. **Output:**
   - `macro_regime`: one of `risk-on`, `risk-off`, `stagflation`, `neutral`
   - `regime_transition_risk`: `True` or `False`
   - `macro_summary`: 1–2 sentence plain-English explanation

## Usage

This skill runs as pipeline stage 4. It provides macro context that modifies (but does not override) technical signals. Trigger by asking "what is the current macro regime for silver?" or it is invoked automatically before multi-horizon forecasts are generated.
