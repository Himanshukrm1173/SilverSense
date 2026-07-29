---
name: trading-plan-generator
description: Generates a trade plan for MCX Silver including entry zone, stop-loss, target levels, risk-reward ratio, and no-trade conditions.
---

# Trading Plan Generator Skill (MCX Silver)

This skill generates a concrete, actionable trading plan for MCX Silver based on technical setups.

## Logic and Requirements

1. **Trade Setup Definition:**
   - Evaluates current market conditions to identify a valid setup (e.g., breakout, pullback, or reversal).
   
2. **Entry & Exit Parameters:**
   - **Entry Zone:** Specifies an exact price range for entry.
   - **Stop-Loss (SL):** Sets a hard stop-loss level to invalidate the trade.
   - **Target Levels:** Defines multiple take-profit targets (T1, T2, T3) for scaling out of the position.

3. **Risk-Reward Ratio:**
   - Calculates the risk-reward ratio based on the entry, SL, and T1/T2 targets. Rejects trades with poor R:R (e.g., less than 1:1.5).

4. **"No-Trade" Conditions:**
   - Explicitly defines conditions where no trade should be taken (e.g., low volume, choppy consolidation, or conflicting indicators). If no valid setup exists, the output must clearly state "NO TRADE" with the reasoning.

## Usage
Trigger this skill by requesting a "trading plan for MCX silver" or similar.
