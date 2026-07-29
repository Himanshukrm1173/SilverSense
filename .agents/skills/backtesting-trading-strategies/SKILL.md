---
name: backtesting-trading-strategies
description: Simulates how past AI trade signals for MCX Silver would have performed historically, and outputs win-rate, average return, and max drawdown.
---

# Backtesting Trading Strategies (MCX Silver)

This skill simulates the historical performance of AI-generated trade signals for MCX Silver to validate strategies.

## Logic and Requirements

1. **Historical Simulation:**
   - Takes historical price data and a set of past AI trade signals (entry, stop-loss, targets).
   - Simulates the execution of these signals sequentially to determine the outcome of each trade.

2. **Performance Metrics:**
   - **Win-Rate:** Percentage of trades that hit their target or resulted in a profit before stopping out.
   - **Average Return:** The mean percentage return per trade across the simulated period.
   - **Maximum Drawdown:** The maximum observed loss from a peak to a trough in the portfolio balance.

3. **Output:**
   - Provides a detailed summary report of the backtested period, highlighting the above metrics and suggesting potential optimizations for the strategy.

## Usage

Trigger this skill by asking the agent to "backtest this strategy on historical silver data" or "show the backtest results for the silver trading signals."
