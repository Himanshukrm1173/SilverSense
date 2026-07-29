"""
forecast_store.py — Pipeline Stage 11

Persists every timestamped forecast to a local JSON file (forecast_store.json).
Tracks outcomes and computes ROLLING accuracy SEPARATELY for 24H, 1W, and 1M.
Never blends accuracy across horizons.
"""
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

STORE_FILE = Path(__file__).parent / "forecast_store.json"

VALID_HORIZONS = {"24H", "1W", "1M"}


def _load_store() -> list:
    if STORE_FILE.exists():
        try:
            with open(STORE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_store(records: list) -> None:
    try:
        with open(STORE_FILE, "w") as f:
            json.dump(records, f, indent=2, default=str)
    except OSError as e:
        print(f"[forecast_store] Could not save store: {e}")


def store_forecast(
    horizon: str,
    bias: str,
    confidence: float,
    regime: str,
    macro_regime: str,
    expected_low: float,
    expected_high: float,
    invalidation_level: float,
    instrument: str,
    inst_price: float,
) -> str:
    """
    Store a new forecast entry.

    Returns the forecast_id (UUID string) for later outcome tracking.
    """
    if horizon not in VALID_HORIZONS:
        raise ValueError(f"Invalid horizon '{horizon}'. Must be one of {VALID_HORIZONS}.")

    forecast_id = str(uuid.uuid4())
    record = {
        "forecast_id": forecast_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "horizon": horizon,
        "instrument": instrument,
        "bias": bias,
        "confidence": round(confidence, 4),
        "regime": regime,
        "macro_regime": macro_regime,
        "expected_low": round(expected_low, 2),
        "expected_high": round(expected_high, 2),
        "invalidation_level": round(invalidation_level, 2),
        "entry_price": round(inst_price, 2),
        "outcome": None,       # "win" | "loss" | "breakeven" — filled by update_outcome
        "actual_price": None,
        "pnl_pct": None,
    }
    records = _load_store()
    records.append(record)
    _save_store(records)
    return forecast_id


def update_outcome(forecast_id: str, actual_price: float) -> dict:
    """
    Update a stored forecast with the actual outcome price.
    Computes win/loss/breakeven based on whether actual_price hit the expected range
    in the direction of the bias.

    Returns the updated record dict.
    """
    records = _load_store()
    updated = None
    for rec in records:
        if rec["forecast_id"] == forecast_id:
            actual_price = round(float(actual_price), 2)
            rec["actual_price"] = actual_price
            entry = rec.get("entry_price", actual_price)
            bias = rec.get("bias", "Neutral")
            exp_low = rec.get("expected_low", 0)
            exp_high = rec.get("expected_high", 0)
            inv = rec.get("invalidation_level", 0)

            # PnL
            if entry and entry != 0:
                if bias == "Bullish":
                    pnl_pct = (actual_price - entry) / entry * 100
                elif bias == "Bearish":
                    pnl_pct = (entry - actual_price) / entry * 100
                else:
                    pnl_pct = 0.0
            else:
                pnl_pct = 0.0

            rec["pnl_pct"] = round(pnl_pct, 4)

            # Win/Loss: did actual price reach expected range without hitting invalidation?
            if bias == "Bullish":
                if actual_price >= exp_low:
                    rec["outcome"] = "win"
                elif inv and actual_price <= inv:
                    rec["outcome"] = "loss"
                else:
                    rec["outcome"] = "breakeven"
            elif bias == "Bearish":
                if actual_price <= exp_high:
                    rec["outcome"] = "win"
                elif inv and actual_price >= inv:
                    rec["outcome"] = "loss"
                else:
                    rec["outcome"] = "breakeven"
            else:
                rec["outcome"] = "breakeven"

            updated = rec
            break

    if updated:
        _save_store(records)
    return updated or {}


def get_accuracy(horizon: str) -> dict:
    """
    Returns rolling forecast accuracy for a specific horizon.
    NEVER blends 24H, 1W, and 1M into a single number.

    Returns:
        dict: {
            "horizon": str,
            "total": int,
            "wins": int,
            "losses": int,
            "breakevens": int,
            "accuracy_pct": float | None,
            "avg_pnl_pct": float | None,
            "recent_streak": int,   # positive = win streak, negative = loss streak
        }
    """
    if horizon not in VALID_HORIZONS:
        raise ValueError(f"Invalid horizon '{horizon}'. Must be one of {VALID_HORIZONS}.")

    records = _load_store()
    horizon_records = [r for r in records if r.get("horizon") == horizon and r.get("outcome")]

    total = len(horizon_records)
    if total == 0:
        return {
            "horizon": horizon, "total": 0, "wins": 0, "losses": 0, "breakevens": 0,
            "accuracy_pct": None, "avg_pnl_pct": None, "recent_streak": 0,
        }

    wins = sum(1 for r in horizon_records if r["outcome"] == "win")
    losses = sum(1 for r in horizon_records if r["outcome"] == "loss")
    breakevens = sum(1 for r in horizon_records if r["outcome"] == "breakeven")

    accuracy_pct = round(wins / total * 100, 2) if total > 0 else None

    pnl_vals = [r["pnl_pct"] for r in horizon_records if r.get("pnl_pct") is not None]
    avg_pnl = round(sum(pnl_vals) / len(pnl_vals), 4) if pnl_vals else None

    # Recent streak: count consecutive wins(+) or losses(-) from most recent
    sorted_recs = sorted(horizon_records, key=lambda r: r.get("timestamp", ""), reverse=True)
    streak = 0
    if sorted_recs:
        last_outcome = sorted_recs[0]["outcome"]
        for r in sorted_recs:
            if r["outcome"] == last_outcome and last_outcome in ("win", "loss"):
                streak += (1 if last_outcome == "win" else -1)
            else:
                break

    return {
        "horizon": horizon,
        "total": total,
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "accuracy_pct": accuracy_pct,
        "avg_pnl_pct": avg_pnl,
        "recent_streak": streak,
    }


def get_all_accuracy() -> dict:
    """Returns accuracy dicts for all three horizons — always separate, never blended."""
    return {h: get_accuracy(h) for h in VALID_HORIZONS}


def get_recent_forecasts(limit: int = 20) -> list:
    """Returns the most recent `limit` forecast records for the Postmortem tab."""
    records = _load_store()
    sorted_recs = sorted(records, key=lambda r: r.get("timestamp", ""), reverse=True)
    return sorted_recs[:limit]


# ─────────────────────────────────────────────────────────────────
#  RESOLUTION HELPERS — determine pending vs elapsed status
# ─────────────────────────────────────────────────────────────────

from datetime import timedelta

# Elapsed time required before a forecast can be evaluated.
HORIZON_DURATIONS: dict = {
    "24H": timedelta(hours=24),
    "1W":  timedelta(days=7),
    "1M":  timedelta(days=30),
}


def is_evaluation_due(record: dict) -> bool:
    """
    Returns True if the forecast's horizon window has elapsed and it can now be evaluated.

    A forecast is due when:
      - Its horizon duration (24H / 1W / 1M) has passed since the logged timestamp.
      - It has not yet been resolved (outcome is None).

    Returns False if:
      - The horizon window has not yet elapsed (still pending).
      - The record is already resolved (outcome is not None).
      - The timestamp or horizon is missing / unrecognisable.
    """
    if record.get("outcome") is not None:
        return False  # already resolved

    horizon = record.get("horizon", "")
    duration = HORIZON_DURATIONS.get(horizon)
    if duration is None:
        return False  # unknown horizon — cannot evaluate

    ts_str = record.get("timestamp")
    if not ts_str:
        return False

    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        elapsed = datetime.now(timezone.utc) - ts
        return elapsed >= duration
    except (ValueError, TypeError):
        return False


def get_due_forecasts() -> list:
    """
    Returns all pending forecast records whose horizon window has elapsed.

    These are ready for outcome resolution — caller should supply an observed
    price and call resolve_forecast() for each.

    Records are sorted oldest-first so the caller can process in chronological order.
    """
    records = _load_store()
    due = [r for r in records if is_evaluation_due(r)]
    return sorted(due, key=lambda r: r.get("timestamp", ""))


def resolve_forecast(forecast_id: str, actual_price: float) -> dict:
    """
    Resolve a pending forecast by attaching the observed actual_price.

    Thin wrapper around update_outcome() that first checks:
      - The record exists.
      - The horizon has elapsed (is_evaluation_due is True).

    Returns:
        dict: The resolved record on success.
              {"error": str} if the record is not found or not yet due.

    The win/loss/breakeven logic is handled entirely by update_outcome().
    """
    records = _load_store()
    target = next((r for r in records if r.get("forecast_id") == forecast_id), None)

    if target is None:
        return {"error": f"forecast_id '{forecast_id}' not found"}

    if not is_evaluation_due(target):
        horizon = target.get("horizon", "?")
        duration = HORIZON_DURATIONS.get(horizon)
        if target.get("outcome") is not None:
            return {"error": f"Forecast already resolved with outcome '{target['outcome']}'"}
        return {"error": f"Horizon {horizon} ({duration}) has not yet elapsed — forecast is still pending"}

    return update_outcome(forecast_id, actual_price)
