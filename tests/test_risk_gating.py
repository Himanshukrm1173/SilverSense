"""
test_risk_gating.py

Tests that:
1. Trade plan is only recommended when confidence >= threshold AND circuit is not open.
2. Circuit breaker open → no trade recommendation under any condition.
"""
import sys
import os
import json
import pytest
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from horizon_engine import CONFIDENCE_THRESHOLD, get_multi_horizon_forecast


class TestConfidenceGating:
    def test_no_trade_when_confidence_below_threshold(self):
        """Horizon with confidence < threshold must have no_trade_flag=True."""
        import pandas as pd
        hist = pd.DataFrame({
            "Close": [100.0] * 60, "High": [100.5] * 60, "Low": [99.5] * 60
        })
        # Flat prices → indicators near zero → very low confidence
        data = {
            "XAGUSD": {"history": hist, "current_price": 100.0},
            "MCX_SILVER": {"current_price_inr": 90000.0, "prev_price_inr": 90000.0, "oi_signal_name": "Neutral"},
            "DXY": {"current_dxy": 100.0, "prev_dxy": 100.0, "rising": False},
            "US10Y": {"current_yield": 4.0, "prev_yield": 4.0, "rising": False},
            "USDINR": {"current_rate": 85.0, "prev_rate": 85.0, "weakening": False},
        }
        forecasts = get_multi_horizon_forecast(data=data, inst_price=90000.0)
        for f in forecasts:
            if f["confidence_score"] < CONFIDENCE_THRESHOLD:
                assert f["no_trade_flag"] is True
                assert len(f["no_trade_reason"]) > 0

    def test_trade_allowed_above_threshold(self):
        """Horizon with confidence >= threshold must have no_trade_flag=False (if valid data)."""
        import pandas as pd
        # Strong uptrend → high confidence bullish signals
        prices = [float(100 + i * 3) for i in range(60)]
        hist = pd.DataFrame({
            "Close": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
        })
        data = {
            "XAGUSD": {"history": hist, "current_price": prices[-1]},
            "MCX_SILVER": {"current_price_inr": 90000.0, "prev_price_inr": 87000.0, "oi_signal_name": "Long Buildup"},
            "DXY": {"current_dxy": 98.0, "prev_dxy": 100.0, "rising": False},
            "US10Y": {"current_yield": 3.8, "prev_yield": 4.1, "rising": False},
            "USDINR": {"current_rate": 86.0, "prev_rate": 85.0, "weakening": True},
        }
        macro = {"macro_regime": "risk-on", "macro_silver_bias": "bullish",
                 "macro_summary": "Bullish.", "regime_transition_risk": False}
        regime = {"regime": "trend-up", "regime_strength": 0.9, "sma20": 200.0, "sma50": 160.0}
        forecasts = get_multi_horizon_forecast(data=data, inst_price=90000.0,
                                               macro_result=macro, market_regime_result=regime)
        any_tradeable = any(not f["no_trade_flag"] for f in forecasts)
        assert any_tradeable, "At least one horizon should be tradeable with strong bullish conditions"


class TestCircuitBreakerGating:
    def test_circuit_open_blocks_recommendation(self):
        """When circuit is open (level 2), no BUY/SELL recommendation should be issued."""
        # Mock forecast_store to return 5 consecutive losses
        losing_records = [
            {
                "forecast_id": f"test-{i:04d}",
                "timestamp": f"2026-07-27T0{i}:00:00+00:00",
                "horizon": "24H",
                "outcome": "loss",
                "pnl_pct": -0.8,
            }
            for i in range(5)
        ]
        with mock.patch("drawdown_circuit_breaker._load_store", return_value=losing_records):
            from drawdown_circuit_breaker import check_circuit_breaker
            result = check_circuit_breaker()
            assert result["circuit_open"] is True, \
                f"Expected circuit_open=True after 5 losses, got {result}"
            assert result["circuit_level"] == 2
            assert "No trade" in result["recommendation"]

    def test_circuit_level_1_warns_but_allows(self):
        """Level 1 circuit (3 consecutive losses) warns but does NOT block trades."""
        losing_records = [
            {
                "forecast_id": f"test-{i:04d}",
                "timestamp": f"2026-07-27T0{i}:00:00+00:00",
                "horizon": "24H",
                "outcome": "loss",
                "pnl_pct": -0.5,
            }
            for i in range(3)
        ]
        with mock.patch("drawdown_circuit_breaker._load_store", return_value=losing_records):
            from drawdown_circuit_breaker import check_circuit_breaker
            result = check_circuit_breaker()
            assert result["circuit_level"] == 1
            assert result["circuit_open"] is False, \
                "Level 1 circuit should NOT set circuit_open=True"

    def test_no_history_means_no_circuit(self):
        """With no trade history, circuit should be at level 0."""
        with mock.patch("drawdown_circuit_breaker._load_store", return_value=[]):
            from drawdown_circuit_breaker import check_circuit_breaker
            result = check_circuit_breaker()
            assert result["circuit_level"] == 0
            assert result["circuit_open"] is False

    def test_circuit_resets_after_wins(self):
        """After 2+ consecutive wins following losses, circuit should reset to level 0."""
        records = [
            {"forecast_id": "old-loss", "timestamp": "2026-07-26T00:00:00+00:00",
             "horizon": "24H", "outcome": "loss", "pnl_pct": -1.0},
            {"forecast_id": "win-1", "timestamp": "2026-07-27T01:00:00+00:00",
             "horizon": "24H", "outcome": "win", "pnl_pct": 0.8},
            {"forecast_id": "win-2", "timestamp": "2026-07-27T02:00:00+00:00",
             "horizon": "24H", "outcome": "win", "pnl_pct": 0.9},
        ]
        with mock.patch("drawdown_circuit_breaker._load_store", return_value=records):
            from drawdown_circuit_breaker import check_circuit_breaker
            result = check_circuit_breaker()
            assert result["circuit_level"] == 0, \
                f"Circuit should reset after 2 consecutive wins, got level {result['circuit_level']}"
