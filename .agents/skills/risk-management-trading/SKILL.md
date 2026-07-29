---
name: risk-management-trading
description: Handles risk management for trading, including position sizing, confidence scoring, max daily loss limits, and rules to avoid overtrading.
---

# Risk Management Skill

This skill enforces strict risk management rules for trading MCX Silver (or other assets) to preserve capital.

## Logic and Requirements

1. **Position Sizing:**
   - Calculates the appropriate position size based on a predefined account risk percentage (e.g., 1-2% of total capital per trade).

2. **Confidence Scoring:**
   - Assigns a confidence score (1 to 10 or Low/Medium/High) to each trade signal based on the confluence of technical and fundamental factors.
   - Adjusts the position size proportionally to the confidence score (e.g., half-size for lower confidence).

3. **Max Daily Loss Limits:**
   - Enforces a strict daily stop-limit. If the max daily loss is hit, it mandates stopping all trading activities for the day.

4. **Overtrading Rules:**
   - Restricts the number of concurrent positions and total trades per day to prevent overexposure and emotional trading.

## Usage
Trigger this skill when assessing a potential trade to get the required position size and risk checks, e.g., "calculate position size and risk for this silver setup."
