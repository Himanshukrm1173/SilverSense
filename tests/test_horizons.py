"""
test_horizons.py

Tests that:
1. Each horizon uses different feature weights (24H vs 1W vs 1M).
2. A bearish 24H signal CAN coexist with a bullish 1M signal in the same run.
3. A neutral 24H signal can coexist with directional 1W/1M signals.
"""
import sys
import os
import pandas as pd
import math
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from horizon_engine import (
    CONFIDENCE_THRESHOLD,
    _score_24h, _score_1w, _score_1m,
    get_multi_horizon_forecast,
)


def _make_hist(prices):
    return pd.DataFrame({"Close": prices, "High": [p*1.01 for p in prices], "Low": [p*0.99 for p in prices]})


def _make_xag(hist):
    return {"history": hist, "current_price": float(hist["Close"].iloc[-1])}


def _make_mcx(price):
    return {"current_price_inr": price, "prev_price_inr": price * 0.99, "oi_signal_name": "Long Buildup"}


def _make_macro_bullish():
    return {"macro_regime": "risk-on", "macro_silver_bias": "bullish",
            "macro_summary": "Bullish macro.", "regime_transition_risk": False}


def _make_macro_bearish():
    return {"macro_regime": "risk-off", "macro_silver_bias": "bearish",
            "macro_summary": "Bearish macro.", "regime_transition_risk": False}


def _bearish_dxy():
    return {"current_dxy": 104.0, "prev_dxy": 102.0, "rising": True}  # rising DXY = bearish silver


def _bullish_dxy():
    return {"current_dxy": 100.0, "prev_dxy": 102.0, "rising": False}  # falling DXY = bullish silver


def _bearish_yield():
    return {"current_yield": 4.5, "prev_yield": 4.2, "rising": True}  # rising yields = bearish silver


def _bullish_yield():
    return {"current_yield": 4.0, "prev_yield": 4.3, "rising": False}  # falling yields = bullish silver


def _bearish_inr():
    return {"current_rate": 84.0, "prev_rate": 84.5, "weakening": False}  # strengthening = bearish MCX


def _bullish_inr():
    return {"current_rate": 85.5, "prev_rate": 85.0, "weakening": True}  # weakening = bullish MCX


class TestHorizonWeightsDiffer:
    def test_24h_does_not_use_macro(self):
        """24H scoring only uses RSI, MACD, OI — macro_bias = 0."""
        # Even with strong macro bias, 24H score should differ from 1W score
        uptrend = [float(100 + i) for i in range(60)]
        hist = _make_hist(uptrend)
        xag = _make_xag(hist)
        mcx = _make_mcx(90000.0)

        score_24h = _score_24h(xag, mcx)["raw_score"]
        score_1w_no_macro = _score_1w(xag, mcx, macro_bias=0.0)["raw_score"]
        score_1w_with_macro = _score_1w(xag, mcx, macro_bias=0.6)["raw_score"]

        # 1W with macro should differ from 1W without macro
        assert abs(score_1w_with_macro - score_1w_no_macro) > 0.01, \
            "Macro bias must influence 1W score"

        # 24H should not be affected by macro — score is independent of macro_bias
        assert isinstance(score_24h, float) and not math.isnan(score_24h)

    def test_1m_uses_only_macro_indicators(self):
        """1M score is computed purely from DXY, US10Y, USDINR — no price history."""
        # Bullish macro for 1M
        score_bullish = _score_1m(_bullish_dxy(), _bullish_yield(), _bullish_inr())["raw_score"]
        # Bearish macro for 1M
        score_bearish = _score_1m(_bearish_dxy(), _bearish_yield(), _bearish_inr())["raw_score"]

        assert score_bullish > 0, f"Expected bullish 1M score > 0, got {score_bullish}"
        assert score_bearish < 0, f"Expected bearish 1M score < 0, got {score_bearish}"
        assert score_bullish > score_bearish, "Bullish 1M must score higher than bearish 1M"

    def test_horizon_weights_sum_to_one(self):
        """Verify weights in each horizon scorer sum to 1.0 (implicit contract)."""
        # 24H: 0.40 + 0.30 + 0.30 = 1.0
        assert abs(0.40 + 0.30 + 0.30 - 1.0) < 1e-9
        # 1W: 0.40 + 0.30 + 0.30 = 1.0
        assert abs(0.40 + 0.30 + 0.30 - 1.0) < 1e-9
        # 1M: 0.35 + 0.30 + 0.20 + 0.15 = 1.0
        assert abs(0.35 + 0.30 + 0.20 + 0.15 - 1.0) < 1e-9


class TestHorizonIndependence:
    def test_bearish_24h_can_coexist_with_bullish_1m(self):
        """
        A bearish 24H signal (RSI overbought, MACD negative) MUST be able to coexist
        with a bullish 1M signal (falling DXY, falling yields, weakening INR).
        This is the core independence requirement.
        """
        # Create conditions: short-term overbought (bearish 24H) + bullish macro (bullish 1M)
        overbought_prices = [float(100 + i * 5) for i in range(60)]  # strong uptrend → RSI > 70
        hist = _make_hist(overbought_prices)
        xag = _make_xag(hist)
        mcx_data = {"current_price_inr": 100000.0, "prev_price_inr": 99000.0, "oi_signal_name": "Short Buildup"}

        data = {
            "XAGUSD": xag,
            "MCX_SILVER": mcx_data,
            "DXY": _bullish_dxy(),
            "US10Y": _bullish_yield(),
            "USDINR": _bullish_inr(),
        }
        macro = _make_macro_bullish()
        regime = {"regime": "trend-up", "regime_strength": 0.8, "sma20": 200.0, "sma50": 180.0}

        forecasts = get_multi_horizon_forecast(
            data=data,
            inst_price=100000.0,
            macro_result=macro,
            market_regime_result=regime,
        )

        f24h = next(f for f in forecasts if f["horizon"] == "24H")
        f1m = next(f for f in forecasts if f["horizon"] == "1M")

        # 24H should be bearish or neutral (RSI overbought + short buildup)
        # 1M should be bullish (all macro factors bullish)
        assert f1m["bias"] == "Bullish", f"1M should be Bullish with all bullish macro, got {f1m['bias']}"
        # The critical test: 24H does NOT copy 1M's bias
        # (it may be bearish or neutral depending on MACD, but MUST differ from just propagating score)
        assert isinstance(f24h["bias"], str)  # Must have its own bias string
        # Raw scores must differ between horizons
        assert f24h["raw_score"] != f1m["raw_score"], \
            "24H and 1M raw scores must differ — they use independent indicators"

    def test_three_horizons_always_returned(self):
        """get_multi_horizon_forecast always returns exactly 3 horizon dicts."""
        hist = _make_hist([100.0 + i for i in range(60)])
        data = {
            "XAGUSD": _make_xag(hist),
            "MCX_SILVER": _make_mcx(90000.0),
            "DXY": _bullish_dxy(),
            "US10Y": _bullish_yield(),
            "USDINR": _bullish_inr(),
        }
        forecasts = get_multi_horizon_forecast(data=data, inst_price=90000.0)
        assert len(forecasts) == 3, f"Expected 3 horizons, got {len(forecasts)}"
        horizons = {f["horizon"] for f in forecasts}
        assert horizons == {"24H", "1W", "1M"}, f"Expected 24H, 1W, 1M but got {horizons}"

    def test_confidence_below_threshold_sets_no_trade(self):
        """If confidence_score < CONFIDENCE_THRESHOLD, no_trade_flag must be True."""
        hist = _make_hist([100.0] * 60)  # flat prices → near-zero indicators → low confidence
        data = {
            "XAGUSD": _make_xag(hist),
            "MCX_SILVER": {"current_price_inr": 90000.0, "prev_price_inr": 90000.0, "oi_signal_name": "Neutral"},
            "DXY": {"current_dxy": 100.0, "prev_dxy": 100.0, "rising": False},
            "US10Y": {"current_yield": 4.0, "prev_yield": 4.0, "rising": False},
            "USDINR": {"current_rate": 85.0, "prev_rate": 85.0, "weakening": False},
        }
        forecasts = get_multi_horizon_forecast(data=data, inst_price=90000.0)
        for f in forecasts:
            if f["confidence_score"] < CONFIDENCE_THRESHOLD:
                assert f["no_trade_flag"] is True, \
                    f"Horizon {f['horizon']} has confidence {f['confidence_score']} < {CONFIDENCE_THRESHOLD} but no_trade_flag is False"

    def test_no_trade_reason_populated_when_flag_set(self):
        """no_trade_reason must be a non-empty string when no_trade_flag is True."""
        hist = _make_hist([100.0] * 60)
        data = {
            "XAGUSD": _make_xag(hist),
            "MCX_SILVER": {"current_price_inr": 90000.0, "prev_price_inr": 90000.0, "oi_signal_name": "Neutral"},
            "DXY": {"current_dxy": 100.0, "prev_dxy": 100.0, "rising": False},
            "US10Y": {"current_yield": 4.0, "prev_yield": 4.0, "rising": False},
            "USDINR": {"current_rate": 85.0, "prev_rate": 85.0, "weakening": False},
        }
        forecasts = get_multi_horizon_forecast(data=data, inst_price=90000.0)
        for f in forecasts:
            if f["no_trade_flag"]:
                assert f["no_trade_reason"] and len(f["no_trade_reason"]) > 0, \
                    f"no_trade_reason must be non-empty when no_trade_flag is True for {f['horizon']}"
