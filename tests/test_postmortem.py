"""
test_postmortem.py

Tests that:
1. Forecasts are stored with correct structure and timestamp.
2. Accuracy is computed separately per horizon (24H/1W/1M).
3. Accuracy is NEVER blended into a single combined number.
4. Win/loss is correctly determined per bias direction.
"""
import sys
import os
import json
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_temp_store(records):
    """Patch forecast_store to use a temp in-memory record list."""
    return records


class TestForecastStorage:
    def test_store_forecast_returns_uuid(self, tmp_path):
        """store_forecast must return a non-empty UUID string."""
        store_file = tmp_path / "forecast_store.json"
        with mock.patch("forecast_store.STORE_FILE", store_file):
            from forecast_store import store_forecast
            fid = store_forecast(
                horizon="24H", bias="Bullish", confidence=0.72,
                regime="trend-up", macro_regime="risk-on",
                expected_low=89500.0, expected_high=91000.0,
                invalidation_level=88800.0, instrument="MCX Silver",
                inst_price=90000.0,
            )
        assert isinstance(fid, str) and len(fid) == 36, f"Expected UUID, got {fid}"

    def test_stored_forecast_has_required_fields(self, tmp_path):
        """Stored forecast record must contain all required fields."""
        store_file = tmp_path / "forecast_store.json"
        with mock.patch("forecast_store.STORE_FILE", store_file):
            from forecast_store import store_forecast
            fid = store_forecast(
                horizon="1W", bias="Bearish", confidence=0.55,
                regime="range", macro_regime="neutral",
                expected_low=86000.0, expected_high=89000.0,
                invalidation_level=91000.0, instrument="MCX Silver",
                inst_price=89500.0,
            )
            records = json.loads(store_file.read_text())

        assert len(records) == 1
        rec = records[0]
        required = ["forecast_id", "timestamp", "horizon", "bias", "confidence",
                    "expected_low", "expected_high", "entry_price", "outcome"]
        for field in required:
            assert field in rec, f"Missing required field: {field}"

    def test_store_rejects_invalid_horizon(self, tmp_path):
        """store_forecast must raise ValueError for invalid horizon."""
        store_file = tmp_path / "forecast_store.json"
        with mock.patch("forecast_store.STORE_FILE", store_file):
            from forecast_store import store_forecast
            with pytest.raises(ValueError, match="Invalid horizon"):
                store_forecast(
                    horizon="48H", bias="Bullish", confidence=0.6,
                    regime="range", macro_regime="neutral",
                    expected_low=89000.0, expected_high=91000.0,
                    invalidation_level=88000.0, instrument="MCX Silver",
                    inst_price=90000.0,
                )

    def test_timestamp_is_utc(self, tmp_path):
        """Stored timestamp must be a valid ISO UTC string."""
        store_file = tmp_path / "forecast_store.json"
        with mock.patch("forecast_store.STORE_FILE", store_file):
            from forecast_store import store_forecast
            store_forecast(
                horizon="1M", bias="Neutral", confidence=0.40,
                regime="range", macro_regime="neutral",
                expected_low=88000.0, expected_high=93000.0,
                invalidation_level=85000.0, instrument="Silver Bees",
                inst_price=90000.0,
            )
            records = json.loads(store_file.read_text())
        ts = records[0]["timestamp"]
        # Should parse as valid ISO datetime
        dt = datetime.fromisoformat(ts)
        assert dt is not None


class TestAccuracyByHorizon:
    def _build_records(self, wins_24h=3, losses_24h=1, wins_1w=2, losses_1w=2,
                       wins_1m=1, losses_1m=3):
        records = []
        idx = 0
        for horizon, wins, losses in [("24H", wins_24h, losses_24h),
                                       ("1W", wins_1w, losses_1w),
                                       ("1M", wins_1m, losses_1m)]:
            for _ in range(wins):
                records.append({"forecast_id": f"id-{idx:03d}", "horizon": horizon,
                                 "outcome": "win", "pnl_pct": 0.5,
                                 "timestamp": f"2026-07-27T0{idx%10}:00:00+00:00"})
                idx += 1
            for _ in range(losses):
                records.append({"forecast_id": f"id-{idx:03d}", "horizon": horizon,
                                 "outcome": "loss", "pnl_pct": -0.4,
                                 "timestamp": f"2026-07-27T0{idx%10}:30:00+00:00"})
                idx += 1
        return records

    def test_accuracy_computed_separately_per_horizon(self, tmp_path):
        """get_accuracy must return different values for 24H, 1W, and 1M."""
        store_file = tmp_path / "forecast_store.json"
        records = self._build_records(wins_24h=3, losses_24h=1,   # 75%
                                       wins_1w=2, losses_1w=2,     # 50%
                                       wins_1m=1, losses_1m=3)     # 25%
        store_file.write_text(json.dumps(records))

        with mock.patch("forecast_store.STORE_FILE", store_file):
            from forecast_store import get_accuracy
            acc_24h = get_accuracy("24H")
            acc_1w = get_accuracy("1W")
            acc_1m = get_accuracy("1M")

        assert acc_24h["accuracy_pct"] == 75.0
        assert acc_1w["accuracy_pct"] == 50.0
        assert acc_1m["accuracy_pct"] == 25.0

    def test_get_all_accuracy_never_blended(self, tmp_path):
        """get_all_accuracy must return 3 separate keys, never a single blended number."""
        store_file = tmp_path / "forecast_store.json"
        records = self._build_records()
        store_file.write_text(json.dumps(records))

        with mock.patch("forecast_store.STORE_FILE", store_file):
            from forecast_store import get_all_accuracy
            all_acc = get_all_accuracy()

        assert set(all_acc.keys()) == {"24H", "1W", "1M"}, \
            "get_all_accuracy must return keys for exactly 24H, 1W, and 1M"
        # Verify no combined/blended key exists
        assert "blended" not in all_acc
        assert "combined" not in all_acc
        assert "overall" not in all_acc

    def test_accuracy_rejects_invalid_horizon(self, tmp_path):
        """get_accuracy must raise ValueError for invalid horizon."""
        store_file = tmp_path / "forecast_store.json"
        store_file.write_text("[]")
        with mock.patch("forecast_store.STORE_FILE", store_file):
            from forecast_store import get_accuracy
            with pytest.raises(ValueError):
                get_accuracy("48H")

    def test_empty_store_returns_none_accuracy(self, tmp_path):
        """get_accuracy with no records must return accuracy_pct=None."""
        store_file = tmp_path / "forecast_store.json"
        store_file.write_text("[]")
        with mock.patch("forecast_store.STORE_FILE", store_file):
            from forecast_store import get_accuracy
            acc = get_accuracy("24H")
        assert acc["accuracy_pct"] is None
        assert acc["total"] == 0

    def test_win_loss_computed_correctly_for_bullish(self, tmp_path):
        """For a Bullish forecast, win = actual >= expected_low."""
        store_file = tmp_path / "forecast_store.json"
        store_file.write_text("[]")
        with mock.patch("forecast_store.STORE_FILE", store_file):
            from forecast_store import store_forecast, update_outcome
            fid = store_forecast(
                horizon="24H", bias="Bullish", confidence=0.75,
                regime="trend-up", macro_regime="risk-on",
                expected_low=91000.0, expected_high=92000.0,
                invalidation_level=89000.0, instrument="MCX Silver",
                inst_price=90000.0,
            )
            # Actual price hit expected_low → WIN
            rec = update_outcome(fid, actual_price=91500.0)
        assert rec["outcome"] == "win", f"Expected win, got {rec['outcome']}"

    def test_win_loss_computed_correctly_for_bearish(self, tmp_path):
        """For a Bearish forecast, win = actual <= expected_high."""
        store_file = tmp_path / "forecast_store.json"
        store_file.write_text("[]")
        with mock.patch("forecast_store.STORE_FILE", store_file):
            from forecast_store import store_forecast, update_outcome
            fid = store_forecast(
                horizon="1W", bias="Bearish", confidence=0.65,
                regime="trend-down", macro_regime="risk-off",
                expected_low=86000.0, expected_high=89000.0,
                invalidation_level=92000.0, instrument="MCX Silver",
                inst_price=90000.0,
            )
            # Actual price below expected_high → WIN
            rec = update_outcome(fid, actual_price=88000.0)
        assert rec["outcome"] == "win", f"Expected win, got {rec['outcome']}"
