---
name: signal-postmortem
description: Compares each past AI prediction against actual outcome and maintains a running accuracy percentage.
---

# Signal Postmortem (Accuracy Tracker)

This skill tracks and evaluates the historical accuracy of AI trading signals to maintain accountability and improve future predictions.

## Logic and Requirements

1. **Signal Tracking:**
   - Logs the details of every AI-generated trade signal (Timestamp, Entry Price, Direction, Targets, Stop-Loss).

2. **Outcome Comparison:**
   - Compares the predicted outcome against the actual historical price action that followed the signal.
   - Determines whether the trade was a "Win" (hit target), "Loss" (hit stop-loss), or "Breakeven."

3. **Running Accuracy:**
   - Calculates and updates the running accuracy percentage (Wins / Total Trades).

4. **Postmortem Analysis:**
   - Provides a brief analysis of *why* a specific signal failed or succeeded, helping to refine future models.

## Usage

Trigger this skill by asking the agent to "run a signal postmortem," "track the accuracy of recent trades," or "show the running accuracy percentage."
