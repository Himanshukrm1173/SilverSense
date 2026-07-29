"""
test_data_quality.py

Tests that:
1. Stale data (> 15 min) → pipeline returns no_prediction=True with reason.
2. NaN/None in required fields → pipeline halts with reason.
3. Empty/missing data → pipeline halts with reason.
4. An invalid/stale feed CANNOT produce a trade plan under any condition.
"""
import sys
import os
import math
import pytest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_quality import (
    validate_instrument_data, validate_pipeline_data,
    DATA_STALENESS_THRESHOLD_MINUTES,
)


def _fresh_ts():
    return datetime.now(timezone.utc).isoformat()


def _stale_ts(minutes=30):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _make_valid_mcx():
    return {
        "current_price_inr": 90000.0,
        "prev_price_inr": 89500.0,
        "_fetched_at": _fresh_ts(),
        "_ticker": "SI=F",
        "_source": "Yahoo Finance (SI=F → INR/kg conversion)",
    }


def _make_valid_xag():
    import pandas as pd
    hist = pd.DataFrame({"Close": [30.0 + i * 0.01 for i in range(20)],
                         "High": [30.5] * 20, "Low": [29.5] * 20})
    return {
        "current_price": 30.5,
        "change_pct": 0.5,
        "_fetched_at": _fresh_ts(),
        "_source": "Yahoo Finance (SI=F)",
        "history": hist,
    }


def _make_valid_dxy():
    return {"current_dxy": 100.5, "_fetched_at": _fresh_ts()}


def _make_valid_us10y():
    return {"current_yield": 4.2, "_fetched_at": _fresh_ts()}


def _make_valid_usdinr():
    return {"current_rate": 85.0, "_fetched_at": _fresh_ts()}


class TestFreshnessCheck:
    def test_fresh_data_passes(self):
        """Data fetched < 1 minute ago must pass freshness check."""
        raw = {"MCX_SILVER": _make_valid_mcx()}
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert result["valid"] is True, result["reason"]

    def test_stale_data_fails(self):
        """Data fetched > 15 minutes ago must fail with staleness reason."""
        mcx = _make_valid_mcx()
        mcx["_fetched_at"] = _stale_ts(DATA_STALENESS_THRESHOLD_MINUTES + 5)
        raw = {"MCX_SILVER": mcx}
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert result["valid"] is False
        assert "stale" in result["reason"].lower()

    def test_missing_timestamp_fails(self):
        """Data without _fetched_at timestamp must fail."""
        mcx = _make_valid_mcx()
        del mcx["_fetched_at"]
        raw = {"MCX_SILVER": mcx}
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert result["valid"] is False
        assert "timestamp" in result["reason"].lower() or "fetched_at" in result["reason"].lower()


class TestCompletenessCheck:
    def test_none_price_fails(self):
        """None in required price field must fail validation."""
        mcx = _make_valid_mcx()
        mcx["current_price_inr"] = None
        raw = {"MCX_SILVER": mcx}
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert result["valid"] is False
        assert "current_price_inr" in result["reason"]

    def test_nan_price_fails(self):
        """NaN in required price field must fail validation."""
        mcx = _make_valid_mcx()
        mcx["current_price_inr"] = float("nan")
        raw = {"MCX_SILVER": mcx}
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert result["valid"] is False
        assert "NaN" in result["reason"] or "nan" in result["reason"].lower()

    def test_inf_price_fails(self):
        """Inf in required price field must fail validation."""
        mcx = _make_valid_mcx()
        mcx["current_price_inr"] = float("inf")
        raw = {"MCX_SILVER": mcx}
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert result["valid"] is False

    def test_missing_instrument_key_fails(self):
        """Missing instrument key in raw dict must fail."""
        raw = {}  # No MCX_SILVER key at all
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert result["valid"] is False
        assert "MCX_SILVER" in result["reason"]

    def test_empty_history_fails(self):
        """Empty price history DataFrame must fail validation."""
        import pandas as pd
        mcx = _make_valid_mcx()
        mcx["history"] = pd.DataFrame()
        raw = {"MCX_SILVER": mcx}
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert result["valid"] is False
        assert "empty" in result["reason"].lower()


class TestPipelineGate:
    def _make_full_valid_raw(self):
        return {
            "XAGUSD": _make_valid_xag(),
            "DXY": _make_valid_dxy(),
            "US10Y": _make_valid_us10y(),
            "USDINR": _make_valid_usdinr(),
            "MCX_SILVER": _make_valid_mcx(),
        }

    def test_valid_pipeline_passes(self):
        """A fully valid data set must pass the pipeline gate."""
        raw = self._make_full_valid_raw()
        result = validate_pipeline_data(raw, "MCX_SILVER")
        assert result["pipeline_valid"] is True
        assert result["no_prediction_reason"] is None

    def test_stale_instrument_halts_pipeline(self):
        """Stale instrument data must halt the pipeline with exact reason."""
        raw = self._make_full_valid_raw()
        raw["MCX_SILVER"]["_fetched_at"] = _stale_ts(DATA_STALENESS_THRESHOLD_MINUTES + 10)
        result = validate_pipeline_data(raw, "MCX_SILVER")
        assert result["pipeline_valid"] is False
        assert result["no_prediction_reason"].startswith("No prediction available")
        assert "stale" in result["no_prediction_reason"].lower()

    def test_nan_instrument_halts_pipeline(self):
        """NaN in instrument price must halt the pipeline."""
        raw = self._make_full_valid_raw()
        raw["MCX_SILVER"]["current_price_inr"] = float("nan")
        result = validate_pipeline_data(raw, "MCX_SILVER")
        assert result["pipeline_valid"] is False
        assert "No prediction available" in result["no_prediction_reason"]

    def test_stale_data_cannot_produce_trade_plan(self):
        """
        CRITICAL: An invalid/stale feed CANNOT produce a trade plan under any condition.
        Validates that pipeline_valid=False must block all downstream logic.
        """
        raw = self._make_full_valid_raw()
        raw["MCX_SILVER"]["_fetched_at"] = _stale_ts(60)  # 60 min stale
        result = validate_pipeline_data(raw, "MCX_SILVER")
        # Must return pipeline_valid=False — caller MUST check this before generating plan
        assert result["pipeline_valid"] is False, \
            "Stale data MUST result in pipeline_valid=False — no trade plan should be generated"
        assert result["no_prediction_reason"] is not None
        assert len(result["no_prediction_reason"]) > 0

    def test_failed_checks_list_is_populated(self):
        """failed_checks list must contain the failing instrument(s) with reason."""
        raw = self._make_full_valid_raw()
        raw["MCX_SILVER"]["current_price_inr"] = None
        result = validate_pipeline_data(raw, "MCX_SILVER")
        assert len(result["failed_checks"]) > 0
        assert any(fc["instrument"] == "MCX_SILVER" for fc in result["failed_checks"])
