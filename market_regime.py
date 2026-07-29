"""
market_regime.py — Pipeline Stage 3

Classifies the current market regime for the selected instrument using
price-action relative to SMA20/SMA50, Bollinger Bands, and ATR volatility.
Always uses ONLY the selected instrument's own price history.

Returns one of: trend-up, trend-down, range, high-volatility, breakout, reversal
"""
import math
import numpy as np
import pandas as pd


def _safe_float(v, default=0.0):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return default
    return float(v)


def compute_atr(hist: pd.DataFrame, period: int = 14) -> float:
    """Average True Range over the last `period` candles."""
    if hist is None or hist.empty or len(hist) < 2:
        return 0.0
    high = hist["High"]
    low = hist["Low"]
    close_prev = hist["Close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - close_prev).abs(),
        (low - close_prev).abs(),
    ], axis=1).max(axis=1)
    atr_series = tr.rolling(window=period, min_periods=1).mean()
    val = atr_series.dropna()
    return float(val.iloc[-1]) if not val.empty else 0.0


def compute_bollinger_bands(close: pd.Series, period: int = 20, std_mult: float = 2.0):
    """Returns (upper, mid, lower) for the most recent bar."""
    if close is None or close.empty or len(close) < period:
        return None, None, None
    mid = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std()
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    mid_v = mid.dropna()
    upper_v = upper.dropna()
    lower_v = lower.dropna()
    if mid_v.empty or upper_v.empty or lower_v.empty:
        return None, None, None
    return float(upper_v.iloc[-1]), float(mid_v.iloc[-1]), float(lower_v.iloc[-1])


def classify_market_regime(instrument_data: dict) -> dict:
    """
    Classify market regime from the selected instrument's data.

    Args:
        instrument_data: dict — one instrument's data dict (e.g. MCX_SILVER, TATA_SILVER, SILVERBEES)
                          Must contain 'history' (pd.DataFrame with Close/High/Low columns)
                          and 'current_price_inr' or 'current_price'.

    Returns:
        dict: {
            "regime": str,
            "regime_strength": float (0.0-1.0),
            "rationale": str,
            "sma20": float,
            "sma50": float,
            "bb_upper": float | None,
            "bb_lower": float | None,
            "atr": float,
            "current_price": float,
        }
    """
    fallback = {
        "regime": "range",
        "regime_strength": 0.0,
        "rationale": "Insufficient data to classify regime.",
        "sma20": 0.0, "sma50": 0.0,
        "bb_upper": None, "bb_lower": None,
        "atr": 0.0, "current_price": 0.0,
    }

    if not instrument_data:
        return fallback

    hist = instrument_data.get("history")
    if hist is None or hist.empty or len(hist) < 20:
        return fallback

    close = hist["Close"].dropna()
    if len(close) < 20:
        return fallback

    # --- Price
    current_price = _safe_float(
        instrument_data.get("current_price_inr") or instrument_data.get("current_price"),
        default=float(close.iloc[-1])
    )

    # --- Moving Averages
    sma20 = float(close.rolling(window=20, min_periods=20).mean().dropna().iloc[-1]) \
        if len(close) >= 20 else float(close.mean())
    sma50 = float(close.rolling(window=50, min_periods=50).mean().dropna().iloc[-1]) \
        if len(close) >= 50 else sma20

    # --- Bollinger Bands
    bb_upper, bb_mid, bb_lower = compute_bollinger_bands(close)

    # --- ATR
    atr = compute_atr(hist)
    avg_atr = float(
        pd.Series([compute_atr(hist.iloc[:i+1]) for i in range(len(hist)-20, len(hist))])
        .mean()
    ) if len(hist) >= 20 else atr
    atr_ratio = atr / avg_atr if avg_atr > 0 else 1.0

    # --- Regime Classification Logic ---
    regime = "range"
    regime_strength = 0.5
    rationale = ""

    # High volatility overrides everything
    if atr_ratio > 1.5:
        regime = "high-volatility"
        regime_strength = min(1.0, (atr_ratio - 1.0) / 1.0)
        rationale = (
            f"ATR is {atr_ratio:.2f}x its 20-period average — "
            f"significantly elevated volatility detected."
        )
    # Breakout: price outside Bollinger Band
    elif bb_upper is not None and bb_lower is not None:
        if current_price > bb_upper:
            regime = "breakout"
            regime_strength = min(1.0, (current_price - bb_upper) / (bb_upper - bb_lower + 1e-9))
            rationale = (
                f"Price ({current_price:.2f}) has closed above the upper Bollinger Band "
                f"({bb_upper:.2f}) — bullish breakout detected."
            )
        elif current_price < bb_lower:
            regime = "breakout"
            regime_strength = min(1.0, (bb_lower - current_price) / (bb_upper - bb_lower + 1e-9))
            rationale = (
                f"Price ({current_price:.2f}) has closed below the lower Bollinger Band "
                f"({bb_lower:.2f}) — bearish breakout detected."
            )
        # Reversal: recent crossover of SMA20 after sustained trend
        elif _safe_float(close.iloc[-2]) < sma20 <= current_price and sma20 < sma50:
            regime = "reversal"
            regime_strength = 0.65
            rationale = (
                f"Price has crossed back above SMA20 ({sma20:.2f}) after trading below — "
                f"potential bullish reversal from downtrend."
            )
        elif _safe_float(close.iloc[-2]) > sma20 >= current_price and sma20 > sma50:
            regime = "reversal"
            regime_strength = 0.65
            rationale = (
                f"Price has crossed below SMA20 ({sma20:.2f}) after trading above — "
                f"potential bearish reversal from uptrend."
            )
        # Trend-Up
        elif current_price > sma20 > sma50:
            regime = "trend-up"
            separation = (sma20 - sma50) / sma50 if sma50 > 0 else 0
            regime_strength = min(1.0, 0.5 + separation * 10)
            rationale = (
                f"Price ({current_price:.2f}) > SMA20 ({sma20:.2f}) > SMA50 ({sma50:.2f}) — "
                f"established uptrend with bullish SMA alignment."
            )
        # Trend-Down
        elif current_price < sma20 < sma50:
            regime = "trend-down"
            separation = (sma50 - sma20) / sma50 if sma50 > 0 else 0
            regime_strength = min(1.0, 0.5 + separation * 10)
            rationale = (
                f"Price ({current_price:.2f}) < SMA20 ({sma20:.2f}) < SMA50 ({sma50:.2f}) — "
                f"established downtrend with bearish SMA alignment."
            )
        # Range
        else:
            regime = "range"
            regime_strength = 0.4
            rationale = (
                f"Price ({current_price:.2f}) is oscillating between SMAs and Bollinger Bands — "
                f"no clear directional trend. Sideways consolidation."
            )
    else:
        # No Bollinger Bands — use SMA only
        if current_price > sma20 > sma50:
            regime = "trend-up"
            regime_strength = 0.6
            rationale = f"Price > SMA20 > SMA50 — uptrend (limited data for BB)."
        elif current_price < sma20 < sma50:
            regime = "trend-down"
            regime_strength = 0.6
            rationale = f"Price < SMA20 < SMA50 — downtrend (limited data for BB)."
        else:
            regime = "range"
            regime_strength = 0.3
            rationale = "Mixed SMA signals — ranging market (limited data for BB)."

    return {
        "regime": regime,
        "regime_strength": round(regime_strength, 3),
        "rationale": rationale,
        "sma20": round(sma20, 4),
        "sma50": round(sma50, 4),
        "bb_upper": round(bb_upper, 4) if bb_upper is not None else None,
        "bb_lower": round(bb_lower, 4) if bb_lower is not None else None,
        "atr": round(atr, 4),
        "current_price": round(current_price, 4),
    }
