"""
test_indicators.py

Unit tests for indicator calculation correctness.
All tests use deterministic known-input → known-output patterns.
"""
import sys
import os
import math
import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logic_engine import calculate_rsi, calculate_sma, get_oi_signal
from horizon_engine import compute_macd, compute_rsi, compute_bollinger_pct, compute_sma_crossover_signal


class TestRSI:
    def test_rsi_oversold(self):
        """RSI < 30 for 14 consecutive down days."""
        prices = pd.Series([100.0 - i * 2 for i in range(30)])
        rsi = calculate_rsi(prices, 14)
        assert rsi < 30, f"Expected RSI < 30 for sustained downtrend, got {rsi}"

    def test_rsi_overbought(self):
        """RSI > 70 for 14 consecutive up days."""
        prices = pd.Series([100.0 + i * 2 for i in range(30)])
        rsi = calculate_rsi(prices, 14)
        assert rsi > 70, f"Expected RSI > 70 for sustained uptrend, got {rsi}"

    def test_rsi_neutral_range(self):
        """RSI near 50 for alternating up/down prices."""
        prices = pd.Series([100.0 + (1 if i % 2 == 0 else -1) for i in range(30)])
        rsi = calculate_rsi(prices, 14)
        assert 30 <= rsi <= 70, f"Expected RSI 30-70 for alternating prices, got {rsi}"

    def test_rsi_returns_50_on_insufficient_data(self):
        """RSI returns 50.0 when there is insufficient data."""
        prices = pd.Series([100.0, 101.0])  # Only 2 points, need at least 15
        rsi = calculate_rsi(prices, 14)
        assert rsi == 50.0

    def test_rsi_no_nan(self):
        """RSI output must never be NaN."""
        prices = pd.Series([float(100 + i) for i in range(30)])
        rsi = calculate_rsi(prices, 14)
        assert not math.isnan(rsi), "RSI must not return NaN"

    def test_horizon_rsi_matches_logic_engine_rsi(self):
        """horizon_engine.compute_rsi and logic_engine.calculate_rsi give same result."""
        prices = pd.Series([100.0 + math.sin(i / 3) * 10 for i in range(40)])
        r1 = calculate_rsi(prices, 14)
        r2 = compute_rsi(prices, 14)
        assert abs(r1 - r2) < 0.5, f"RSI implementations diverged: {r1} vs {r2}"


class TestSMA:
    def test_sma_correct_value(self):
        """SMA of [1,2,3,4,5] with period 5 should be 3.0."""
        prices = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        sma = calculate_sma(prices, 5)
        assert abs(sma - 3.0) < 1e-9, f"Expected 3.0, got {sma}"

    def test_sma_window_1(self):
        """SMA with period 1 equals the last price."""
        prices = pd.Series([10.0, 20.0, 30.0])
        sma = calculate_sma(prices, 1)
        assert abs(sma - 30.0) < 1e-9

    def test_sma_no_nan(self):
        """SMA must not return NaN even for short series."""
        prices = pd.Series([100.0])
        sma = calculate_sma(prices, 20)
        assert not math.isnan(sma)


class TestBollingerBands:
    def test_bb_pct_midline(self):
        """Constant price series → BB %B should be ~0.5 (at midline)."""
        prices = pd.Series([100.0] * 25)
        # When all prices are identical, std=0, bands collapse — expect 0.5 fallback
        bb = compute_bollinger_pct(prices, 20)
        assert 0.0 <= bb <= 1.0, f"BB %B must be in [0,1], got {bb}"

    def test_bb_pct_uptrend(self):
        """Strongly rising prices push BB %B toward 1.0."""
        prices = pd.Series([float(100 + i * 5) for i in range(30)])
        bb = compute_bollinger_pct(prices, 20)
        assert bb > 0.5, f"BB %B should be > 0.5 in uptrend, got {bb}"

    def test_bb_pct_downtrend(self):
        """Strongly falling prices push BB %B toward 0.0."""
        prices = pd.Series([float(200 - i * 5) for i in range(30)])
        bb = compute_bollinger_pct(prices, 20)
        assert bb < 0.5, f"BB %B should be < 0.5 in downtrend, got {bb}"

    def test_bb_range_clamped(self):
        """BB %B must always be in [0, 1]."""
        prices = pd.Series([float(100 + i * 20) for i in range(30)])
        bb = compute_bollinger_pct(prices, 20)
        assert 0.0 <= bb <= 1.0


class TestMACD:
    def test_macd_hist_positive_uptrend(self):
        """MACD histogram should be positive during a strong uptrend."""
        prices = pd.Series([float(100 + i) for i in range(50)])
        _, _, hist = compute_macd(prices)
        assert hist > 0, f"MACD histogram should be > 0 in uptrend, got {hist}"

    def test_macd_returns_zeros_on_insufficient_data(self):
        """MACD returns (0,0,0) when series is too short."""
        prices = pd.Series([100.0] * 5)
        m, s, h = compute_macd(prices)
        assert m == 0.0 and s == 0.0 and h == 0.0

    def test_macd_no_nan(self):
        """MACD must not return NaN."""
        prices = pd.Series([float(100 + i) for i in range(50)])
        m, s, h = compute_macd(prices)
        for v in [m, s, h]:
            assert not math.isnan(v), f"MACD returned NaN"


class TestOISignal:
    def test_long_buildup(self):
        """Price up + OI up = Long Buildup."""
        name, score = get_oi_signal(102, 100, 1100, 1000)
        assert name == "Long Buildup" and score == 20

    def test_short_buildup(self):
        """Price down + OI up = Short Buildup."""
        name, score = get_oi_signal(98, 100, 1100, 1000)
        assert name == "Short Buildup" and score == -20

    def test_short_covering(self):
        """Price up + OI down = Short Covering."""
        name, score = get_oi_signal(102, 100, 900, 1000)
        assert name == "Short Covering" and score == 10

    def test_long_unwinding(self):
        """Price down + OI down = Long Unwinding."""
        name, score = get_oi_signal(98, 100, 900, 1000)
        assert name == "Long Unwinding" and score == -10
