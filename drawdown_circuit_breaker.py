"""
drawdown_circuit_breaker.py — Pipeline Stage 9

Monitors cumulative trade signal losses and consecutive losing streaks.
Blocks or reduces new trade recommendations when defined thresholds are breached.
Reads from forecast_store.json — no external dependencies.

Circuit Levels:
  Level 0 (Normal):  No circuit — trade recommendations proceed normally.
  Level 1 (Warning): 3 consecutive losses OR drawdown > 1.5% — reduce size 50%.
  Level 2 (Open):    5 consecutive losses OR drawdown > 3% — block all new recommendations.
"""
from forecast_store import _load_store

# Configurable thresholds
LEVEL1_CONSECUTIVE = 3
LEVEL2_CONSECUTIVE = 5
LEVEL1_DRAWDOWN_PCT = 1.5
LEVEL2_DRAWDOWN_PCT = 3.0

# Reset: requires N consecutive wins after Level 2
RESET_WIN_STREAK = 2


def _compute_consecutive_losses(records: list) -> int:
    """Count consecutive losses from the most recent record (with outcome)."""
    resolved = [r for r in records if r.get("outcome") in ("win", "loss")]
    if not resolved:
        return 0
    sorted_recs = sorted(resolved, key=lambda r: r.get("timestamp", ""), reverse=True)
    streak = 0
    for r in sorted_recs:
        if r["outcome"] == "loss":
            streak += 1
        else:
            break
    return streak


def _compute_consecutive_wins(records: list) -> int:
    """Count consecutive wins from the most recent record (with outcome)."""
    resolved = [r for r in records if r.get("outcome") in ("win", "loss")]
    if not resolved:
        return 0
    sorted_recs = sorted(resolved, key=lambda r: r.get("timestamp", ""), reverse=True)
    streak = 0
    for r in sorted_recs:
        if r["outcome"] == "win":
            streak += 1
        else:
            break
    return streak


def _compute_cumulative_drawdown(records: list) -> float:
    """
    Computes cumulative P&L from recent resolved forecasts.
    Returns the maximum drawdown as a positive percentage.
    """
    resolved = [r for r in records if r.get("outcome") in ("win", "loss") and r.get("pnl_pct") is not None]
    if not resolved:
        return 0.0
    sorted_recs = sorted(resolved, key=lambda r: r.get("timestamp", ""))
    # Walk-forward equity curve (start at 0, add pnl_pct)
    equity = [0.0]
    for r in sorted_recs:
        equity.append(equity[-1] + r["pnl_pct"])
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 4)


def check_circuit_breaker() -> dict:
    """
    Evaluate current circuit breaker state from persisted forecast history.

    Returns:
        dict: {
            "circuit_level": int (0, 1, 2),
            "circuit_open": bool,
            "consecutive_losses": int,
            "consecutive_wins": int,
            "cumulative_drawdown_pct": float,
            "reason": str,
            "recommendation": str,
        }
    """
    records = _load_store()
    consecutive_losses = _compute_consecutive_losses(records)
    consecutive_wins = _compute_consecutive_wins(records)
    drawdown = _compute_cumulative_drawdown(records)

    # Level 2 — check reset condition first
    if consecutive_wins >= RESET_WIN_STREAK:
        # Auto-reset after sufficient win streak
        return {
            "circuit_level": 0,
            "circuit_open": False,
            "consecutive_losses": 0,
            "consecutive_wins": consecutive_wins,
            "cumulative_drawdown_pct": drawdown,
            "reason": f"Circuit reset after {consecutive_wins} consecutive wins.",
            "recommendation": "Normal trading. Circuit has been reset.",
        }

    if consecutive_losses >= LEVEL2_CONSECUTIVE or drawdown >= LEVEL2_DRAWDOWN_PCT:
        return {
            "circuit_level": 2,
            "circuit_open": True,
            "consecutive_losses": consecutive_losses,
            "consecutive_wins": 0,
            "cumulative_drawdown_pct": drawdown,
            "reason": (
                f"Circuit breaker OPEN: "
                f"{consecutive_losses} consecutive losses "
                f"and {drawdown:.2f}% cumulative drawdown. "
                f"Threshold: {LEVEL2_CONSECUTIVE} losses or {LEVEL2_DRAWDOWN_PCT}% drawdown."
            ),
            "recommendation": (
                "No trade — circuit breaker active. "
                f"Resume after {RESET_WIN_STREAK} consecutive winning signals."
            ),
        }

    if consecutive_losses >= LEVEL1_CONSECUTIVE or drawdown >= LEVEL1_DRAWDOWN_PCT:
        return {
            "circuit_level": 1,
            "circuit_open": False,
            "consecutive_losses": consecutive_losses,
            "consecutive_wins": 0,
            "cumulative_drawdown_pct": drawdown,
            "reason": (
                f"Circuit breaker WARNING: "
                f"{consecutive_losses} consecutive losses, "
                f"{drawdown:.2f}% drawdown. "
                f"Threshold: {LEVEL1_CONSECUTIVE} losses or {LEVEL1_DRAWDOWN_PCT}% drawdown."
            ),
            "recommendation": "Reduce position size by 50%. Proceed with caution.",
        }

    return {
        "circuit_level": 0,
        "circuit_open": False,
        "consecutive_losses": consecutive_losses,
        "consecutive_wins": consecutive_wins,
        "cumulative_drawdown_pct": drawdown,
        "reason": "No circuit conditions triggered.",
        "recommendation": "Normal position sizing applies.",
    }
