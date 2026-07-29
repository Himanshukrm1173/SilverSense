---
name: drawdown-circuit-breaker
description: Monitors cumulative trade signal losses and drawdown. Blocks or reduces new trade recommendations once defined loss thresholds are breached, protecting against overtrading during losing streaks.
---

# Drawdown Circuit Breaker

This skill acts as a safety mechanism that monitors the running performance of trade signals and halts new recommendations when loss thresholds are exceeded.

## Logic and Requirements

1. **Monitoring:**
   - Reads the persisted forecast history (e.g., `forecast_store.json`) to track recent signal outcomes (Win / Loss / Breakeven).
   - Tracks both a **consecutive loss streak** and a **cumulative drawdown percentage**.

2. **Circuit Breaker Thresholds:**
   - **Level 1 (Warning):** 3 consecutive losses or cumulative drawdown > 1.5%. Reduces position size recommendation by 50%. Shows a visible warning in the UI.
   - **Level 2 (Circuit Open):** 5 consecutive losses or cumulative drawdown > 3%. Blocks all new BUY/SELL trade recommendations entirely. Only "No trade — circuit breaker active" is shown.

3. **Reset Conditions:**
   - Circuit resets after 2 consecutive winning signals following a Level 2 trigger, or after a manual reset by the user.

4. **Output:**
   - `circuit_level`: `0` (normal), `1` (warning), or `2` (open/blocked)
   - `circuit_open`: `True` or `False`
   - `consecutive_losses`: integer count
   - `reason`: plain-English explanation of why the circuit is at its current level

## Usage

This skill runs as pipeline stage 9 (after backtesting, before final output). Trigger by asking "is the circuit breaker active?" or it runs automatically before any trade recommendation is generated.
