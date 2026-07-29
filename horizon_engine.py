"""
horizon_engine.py — Pipeline Stage 5

Produces THREE fully independent multi-horizon forecasts for MCX Silver
(24 Hours, 1 Week, 1 Month) using DIFFERENT indicator weightings per horizon.

CRITICAL DESIGN RULES:
  - Each horizon uses its own feature set and weighting scheme.
  - A short-term bearish 24H bias DOES NOT automatically force a bearish 1W or 1M.
  - Sentiment/macro context is a supporting factor only — it cannot override technical data.
  - All numeric outputs are computed deterministically from code. No AI text generation
    for prices, ranges, probabilities, or confidence scores.
  - If confidence_score < CONFIDENCE_THRESHOLD, no_trade_flag is set True.
"""
import math
import numpy as np
import pandas as pd

CONFIDENCE_THRESHOLD = 0.45  # Below this, no trade is recommended for that horizon


# ─────────────────────────────────────────────────────────────
#  INDICATOR HELPERS
# ─────────────────────────────────────────────────────────────

def _safe(v, default=0.0):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return default
    return float(v)


def compute_macd(close: pd.Series, fast=12, slow=26, signal=9):
    """Returns (macd_line, signal_line, histogram) for the latest bar."""
    if close is None or len(close) < slow + signal:
        return 0.0, 0.0, 0.0
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    sig_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - sig_line
    return float(macd_line.iloc[-1]), float(sig_line.iloc[-1]), float(hist.iloc[-1])


def compute_rsi(close: pd.Series, period=14) -> float:
    if close is None or len(close) < period + 1:
        return 50.0
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).fillna(0.0)
    loss = (-delta.where(delta < 0, 0.0)).fillna(0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.dropna()
    return float(val.iloc[-1]) if not val.empty else 50.0


def compute_bollinger_pct(close: pd.Series, period=20) -> float:
    """Bollinger %B: 0 = at lower band, 1 = at upper band, 0.5 = at midline."""
    if close is None or len(close) < period:
        return 0.5
    sma = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    current = close.iloc[-1]
    u = upper.dropna()
    lo = lower.dropna()
    if u.empty or lo.empty:
        return 0.5
    u_val, lo_val = float(u.iloc[-1]), float(lo.iloc[-1])
    band_width = u_val - lo_val
    if band_width < 1e-9:
        return 0.5
    return max(0.0, min(1.0, (current - lo_val) / band_width))


def compute_sma_crossover_signal(close: pd.Series, fast=9, slow=21) -> float:
    """Returns a [-1, 1] score: +1 if fast>slow (bullish), -1 if fast<slow."""
    if close is None or len(close) < slow:
        return 0.0
    sma_fast = close.rolling(window=fast, min_periods=fast).mean().dropna()
    sma_slow = close.rolling(window=slow, min_periods=slow).mean().dropna()
    if sma_fast.empty or sma_slow.empty:
        return 0.0
    f, s = float(sma_fast.iloc[-1]), float(sma_slow.iloc[-1])
    if s == 0:
        return 0.0
    separation = (f - s) / s  # positive = bullish, negative = bearish
    return max(-1.0, min(1.0, separation * 100))  # scale to -1..+1


# ─────────────────────────────────────────────────────────────
#  OI SIGNAL HELPER
# ─────────────────────────────────────────────────────────────

def _oi_score(mcx_data: dict) -> float:
    """Convert OI signal name to a [-1, 1] score."""
    signal = (mcx_data or {}).get("oi_signal_name", "Neutral")
    return {"Long Buildup": 1.0, "Short Buildup": -1.0,
            "Short Covering": 0.5, "Long Unwinding": -0.5}.get(signal, 0.0)


# ─────────────────────────────────────────────────────────────
#  PER-HORIZON SCORING
# ─────────────────────────────────────────────────────────────

def _score_24h(xag_data: dict, mcx_data: dict) -> dict:
    """
    24-Hour horizon.
    Weights: RSI=0.40, MACD=0.30, OI=0.30
    No macro factors — purely short-term momentum and futures positioning.
    """
    weights = {"rsi": 0.40, "macd": 0.30, "oi": 0.30}
    hist = (xag_data or {}).get("history")
    close = hist["Close"].dropna() if hist is not None and not hist.empty else None

    # RSI
    rsi = compute_rsi(close) if close is not None else 50.0
    # Map RSI to [-1, 1]: <30 = +1 (oversold/buy), >70 = -1 (overbought/sell)
    if rsi < 30:
        rsi_signal = 1.0 - (rsi / 30.0)       # strong bullish
    elif rsi > 70:
        rsi_signal = -((rsi - 70.0) / 30.0)    # strong bearish
    else:
        rsi_signal = (50.0 - rsi) / 50.0        # mild: above 50 = slight bearish bias
    rsi_signal = max(-1.0, min(1.0, rsi_signal))

    # MACD
    macd_line, sig_line, macd_hist = compute_macd(close) if close is not None else (0.0, 0.0, 0.0)
    # Histogram positive = bullish momentum, negative = bearish
    price_scale = float(close.iloc[-1]) if close is not None and not close.empty else 1.0
    macd_signal = max(-1.0, min(1.0, macd_hist / (price_scale * 0.01 + 1e-9)))

    # OI
    oi_signal = _oi_score(mcx_data)

    raw_score = (
        weights["rsi"] * rsi_signal +
        weights["macd"] * macd_signal +
        weights["oi"] * oi_signal
    )

    contributing = [
        {"factor": "RSI (14)", "value": f"{rsi:.1f}", "signal": _direction_label(rsi_signal), "weight": "40%"},
        {"factor": "MACD Histogram", "value": f"{macd_hist:.4f}", "signal": _direction_label(macd_signal), "weight": "30%"},
        {"factor": "OI Signal", "value": (mcx_data or {}).get("oi_signal_name", "N/A"), "signal": _direction_label(oi_signal), "weight": "30%"},
    ]
    return {"raw_score": raw_score, "contributing": contributing}


def _score_1w(xag_data: dict, mcx_data: dict, macro_bias: float) -> dict:
    """
    1-Week horizon.
    Weights: SMA Crossover=0.40, Bollinger %B=0.30, Macro Sentiment=0.30
    """
    weights = {"sma": 0.40, "bb": 0.30, "macro": 0.30}
    hist = (xag_data or {}).get("history")
    close = hist["Close"].dropna() if hist is not None and not hist.empty else None

    # SMA 9/21 Crossover
    sma_signal = compute_sma_crossover_signal(close) if close is not None else 0.0

    # Bollinger %B → map to [-1, 1]: %B > 0.8 = overbought (-1), < 0.2 = oversold (+1)
    bb_pct = compute_bollinger_pct(close) if close is not None else 0.5
    if bb_pct > 0.8:
        bb_signal = -(bb_pct - 0.5) * 2.0
    elif bb_pct < 0.2:
        bb_signal = (0.5 - bb_pct) * 2.0
    else:
        bb_signal = (bb_pct - 0.5) * 0.5
    bb_signal = max(-1.0, min(1.0, bb_signal))

    raw_score = (
        weights["sma"] * sma_signal +
        weights["bb"] * bb_signal +
        weights["macro"] * macro_bias  # macro as supporting factor
    )

    contributing = [
        {"factor": "SMA 9/21 Crossover", "value": f"{sma_signal:+.3f}", "signal": _direction_label(sma_signal), "weight": "40%"},
        {"factor": "Bollinger %B", "value": f"{bb_pct:.2f}", "signal": _direction_label(bb_signal), "weight": "30%"},
        {"factor": "Macro Sentiment", "value": f"{macro_bias:+.2f}", "signal": _direction_label(macro_bias), "weight": "30%"},
    ]
    return {"raw_score": raw_score, "contributing": contributing}


def _score_1m(dxy_data: dict, us10y_data: dict, usdinr_data: dict) -> dict:
    """
    1-Month horizon.
    Weights: DXY=0.35, US10Y=0.30, USDINR=0.20, Industrial Demand Proxy=0.15
    Pure macro — no short-term technicals.
    """
    weights = {"dxy": 0.35, "yield": 0.30, "inr": 0.20, "demand": 0.15}

    dxy_rising = (dxy_data or {}).get("rising", False)
    yield_rising = (us10y_data or {}).get("rising", False)
    inr_weakening = (usdinr_data or {}).get("weakening", False)

    dxy_signal = -1.0 if dxy_rising else 1.0        # rising DXY = bearish silver
    yield_signal = -1.0 if yield_rising else 1.0     # rising yields = bearish silver
    inr_signal = 1.0 if inr_weakening else -1.0      # weakening INR = bullish MCX silver

    # Industrial demand proxy: approximated by 3M USD Libor/yield proxy.
    # Simplified: use DXY direction as a proxy for global growth conditions.
    # Rising DXY often accompanies risk-off/lower industrial demand.
    demand_signal = -0.5 if dxy_rising else 0.5

    raw_score = (
        weights["dxy"] * dxy_signal +
        weights["yield"] * yield_signal +
        weights["inr"] * inr_signal +
        weights["demand"] * demand_signal
    )

    contributing = [
        {"factor": "DXY (Dollar Index)", "value": f"{'Rising' if dxy_rising else 'Falling'}", "signal": _direction_label(dxy_signal), "weight": "35%"},
        {"factor": "US 10Y Yield", "value": f"{'Rising' if yield_rising else 'Falling'}", "signal": _direction_label(yield_signal), "weight": "30%"},
        {"factor": "USD/INR", "value": f"{'Weakening' if inr_weakening else 'Strengthening'}", "signal": _direction_label(inr_signal), "weight": "20%"},
        {"factor": "Industrial Demand Proxy", "value": f"{'Risk-Off' if dxy_rising else 'Risk-On'}", "signal": _direction_label(demand_signal), "weight": "15%"},
    ]
    return {"raw_score": raw_score, "contributing": contributing}


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def _direction_label(score: float) -> str:
    if score > 0.15:
        return "Bullish"
    elif score < -0.15:
        return "Bearish"
    return "Neutral"


def _bias_from_score(score: float) -> str:
    if score > 0.2:
        return "Bullish"
    elif score < -0.2:
        return "Bearish"
    return "Neutral"


def _confidence_from_score(score: float) -> float:
    """Maps absolute raw_score to a 0.0–1.0 confidence value."""
    return round(min(1.0, abs(score) * 1.5), 3)


def _prob_split(score: float) -> dict:
    """Returns up/sideways/down probability split that sums to 100."""
    abs_s = min(abs(score), 1.0)
    if score > 0:
        up = int(40 + abs_s * 35)
        down = max(5, int(30 - abs_s * 20))
        sideways = 100 - up - down
    elif score < 0:
        down = int(40 + abs_s * 35)
        up = max(5, int(30 - abs_s * 20))
        sideways = 100 - up - down
    else:
        up, down, sideways = 33, 33, 34
    sideways = max(0, sideways)
    return {"up": max(0, up), "sideways": max(0, sideways), "down": max(0, down)}


def _compute_range(inst_price: float, score: float, horizon: str) -> tuple:
    """
    Computes the expected price range based on horizon and score magnitude.
    Returns (low, high, move_low_pct, move_high_pct).
    """
    abs_s = min(abs(score), 1.0)
    # Horizon-specific range multipliers
    range_table = {
        "24H": {0.0: (0.0, 0.2), 0.3: (0.2, 0.5), 0.6: (0.5, 1.0), 1.0: (1.0, 1.8)},
        "1W":  {0.0: (0.0, 0.5), 0.3: (0.5, 1.5), 0.6: (1.5, 3.0), 1.0: (3.0, 5.0)},
        "1M":  {0.0: (0.0, 1.0), 0.3: (1.0, 3.0), 0.6: (3.0, 6.0), 1.0: (6.0, 10.0)},
    }
    tbl = range_table.get(horizon, range_table["24H"])
    # Find nearest bucket
    key = max([k for k in tbl.keys() if k <= abs_s], default=0.0)
    move_low_pct, move_high_pct = tbl[key]

    if score > 0:
        low = inst_price * (1 + move_low_pct / 100)
        high = inst_price * (1 + move_high_pct / 100)
    elif score < 0:
        low = inst_price * (1 - move_high_pct / 100)
        high = inst_price * (1 - move_low_pct / 100)
    else:
        low = inst_price * (1 - move_high_pct / 100)
        high = inst_price * (1 + move_high_pct / 100)

    return round(low, 2), round(high, 2), round(move_low_pct, 2), round(move_high_pct, 2)


def _invalidation_level(inst_price: float, score: float, horizon: str) -> float:
    """Returns the price level at which the forecast is invalidated."""
    buffer_pct = {"24H": 0.8, "1W": 1.5, "1M": 3.0}.get(horizon, 1.0)
    if score > 0:
        return round(inst_price * (1 - buffer_pct / 100), 2)
    elif score < 0:
        return round(inst_price * (1 + buffer_pct / 100), 2)
    return round(inst_price, 2)


# ─────────────────────────────────────────────────────────────
#  MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────

def get_multi_horizon_forecast(
    data: dict,
    inst_price: float,
    inst_name: str = "MCX Silver",
    inst_unit: str = "Rs/kg",
    macro_result: dict = None,
    market_regime_result: dict = None,
) -> list:
    """
    Generate 3 fully independent horizon forecasts.

    Args:
        data:                 dict — enriched_data from process_data_and_score
        inst_price:           float — the selected instrument's current price
        inst_name:            str
        inst_unit:            str
        macro_result:         dict — output from macro_regime.detect_macro_regime()
        market_regime_result: dict — output from market_regime.classify_market_regime()

    Returns:
        list of 3 dicts, one per horizon (24H, 1W, 1M)
    """
    xag_data = data.get("XAGUSD") or {}
    mcx_data = data.get("MCX_SILVER") or {}
    dxy_data = data.get("DXY") or {}
    us10y_data = data.get("US10Y") or {}
    usdinr_data = data.get("USDINR") or {}

    # Macro bias: convert macro_silver_bias string to numeric [-1, 1]
    macro_bias_str = (macro_result or {}).get("macro_silver_bias", "neutral")
    macro_bias = {"bullish": 0.6, "bearish": -0.6, "mixed": 0.0, "neutral": 0.0}.get(macro_bias_str, 0.0)

    current_regime = (market_regime_result or {}).get("regime", "range")
    macro_regime_str = (macro_result or {}).get("macro_regime", "neutral")
    macro_summary = (macro_result or {}).get("macro_summary", "")

    # ── Score each horizon independently ──
    score_24h = _score_24h(xag_data, mcx_data)
    score_1w = _score_1w(xag_data, mcx_data, macro_bias)
    score_1m = _score_1m(dxy_data, us10y_data, usdinr_data)

    results = []
    for horizon, scoring in [("24H", score_24h), ("1W", score_1w), ("1M", score_1m)]:
        raw = scoring["raw_score"]
        contributing = scoring["contributing"]
        bias = _bias_from_score(raw)
        confidence = _confidence_from_score(raw)
        prob = _prob_split(raw)
        low, high, move_low, move_high = _compute_range(inst_price, raw, horizon)
        invalidation = _invalidation_level(inst_price, raw, horizon)
        no_trade = confidence < CONFIDENCE_THRESHOLD

        results.append({
            "horizon": horizon,
            "bias": bias,
            "raw_score": round(raw, 4),
            "confidence_score": confidence,
            "expected_low": low,
            "expected_high": high,
            "move_low_pct": move_low,
            "move_high_pct": move_high,
            "prob_split": prob,
            "current_regime": current_regime,
            "macro_regime": macro_regime_str,
            "invalidation_level": invalidation,
            "no_trade_flag": no_trade,
            "no_trade_reason": (
                f"Confidence score ({confidence:.0%}) is below the minimum threshold "
                f"({CONFIDENCE_THRESHOLD:.0%}). No trade recommended for {horizon} horizon."
            ) if no_trade else "",
            "contributing_factors": contributing,
            "macro_note": macro_summary if horizon in ("1W", "1M") else "",
        })

    # ── Conflict detection ──
    biases = [r["bias"] for r in results]
    unique = set(biases)
    if len(unique) > 1 and "Neutral" not in unique:
        # Horizons genuinely conflict — flag it
        for r in results:
            if not r["no_trade_flag"]:
                r["conflict_note"] = (
                    "Mixed structure across horizons — no single clear directional edge. "
                    "Review individual horizon reasoning before acting."
                )
    else:
        for r in results:
            r["conflict_note"] = ""

    return results
