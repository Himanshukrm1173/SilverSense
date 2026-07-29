"""
test_phase0_audit.py
=====================
Phase 0 data-integrity tests. All 10 mandatory requirements from the Phase 0 spec.

Tests are organized by the specific data-integrity guarantee they verify.
All tests use deterministic inputs — no network calls, no LLM calls.
"""
import sys
import os
import math
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from instrument_registry import INSTRUMENTS, MACRO_FEEDS, get_price_range, get_price_field
from data_quality import (
    validate_instrument_data,
    validate_pipeline_data,
    DATA_STALENESS_THRESHOLD_MINUTES,
    _check_range,
)
from diagnostics import DataStatus, DiagnosticsLog, build_status_from_data_dict


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fresh_ts():
    return datetime.now(timezone.utc).isoformat()


def _stale_ts(minutes=30):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _valid_mcx():
    return {
        "current_price_inr": 92000.0,
        "prev_price_inr": 91500.0,
        "current_price_usd": 31.5,
        "usdinr_rate_used": 85.0,
        "mcx_premium_factor": 1.0622,
        "today_volume": 50000,
        "avg_volume_20d": 45000.0,
        "open_interest_current": 50000,
        "open_interest_prev": 47500,
        "oi_is_synthetic": True,
        "oi_source": "volume-proxy",
        "history": MagicMock(empty=False, shape=(30, 5)),
        "_fetched_at": _fresh_ts(),
        "_source": "Yahoo Finance (SI=F -> INR/kg)",
        "_ticker": "SI=F",
        "_is_proxy": True,
        "_proxy_note": "MCX Silver derived from COMEX SI=F",
    }


def _valid_xag():
    return {
        "current_price": 31.5,
        "change_pct": 0.5,
        "history": MagicMock(empty=False, shape=(60, 5)),
        "_fetched_at": _fresh_ts(),
        "_source": "Yahoo Finance (SI=F)",
        "_ticker": "SI=F",
    }


def _valid_dxy():
    return {
        "current_dxy": 100.5,
        "prev_dxy": 100.0,
        "rising": True,
        "_fetched_at": _fresh_ts(),
        "_source": "Yahoo Finance (DX-Y.NYB)",
        "_ticker": "DX-Y.NYB",
    }


def _valid_us10y():
    return {
        "current_yield": 4.2,
        "prev_yield": 4.1,
        "rising": True,
        "_fetched_at": _fresh_ts(),
        "_source": "Yahoo Finance (^TNX)",
        "_ticker": "^TNX",
    }


def _valid_usdinr():
    return {
        "current_rate": 85.0,
        "prev_rate": 84.5,
        "weakening": True,
        "_fetched_at": _fresh_ts(),
        "_source": "Yahoo Finance (USDINR=X)",
        "_ticker": "USDINR=X",
    }


def _full_valid_raw():
    return {
        "XAGUSD": _valid_xag(),
        "DXY": _valid_dxy(),
        "US10Y": _valid_us10y(),
        "USDINR": _valid_usdinr(),
        "MCX_SILVER": _valid_mcx(),
    }


# ─── TEST 1: NaN input blocks signal generation ──────────────────────────────

class TestNaNBlocks:
    def test_nan_price_blocks_mcx(self):
        """NaN in current_price_inr MUST block signal generation."""
        raw = _full_valid_raw()
        raw["MCX_SILVER"]["current_price_inr"] = float("nan")
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert not result["valid"]
        assert result["status"] == "blocked"
        assert "NaN" in result["reason"] or "nan" in result["reason"].lower()

    def test_inf_price_blocks_xag(self):
        """Inf in XAGUSD current_price MUST block."""
        raw = _full_valid_raw()
        raw["XAGUSD"]["current_price"] = float("inf")
        result = validate_instrument_data(raw, "XAGUSD")
        assert not result["valid"]
        assert result["status"] == "blocked"

    def test_nan_yield_blocks_pipeline(self):
        """NaN in US10Y yield MUST block the full pipeline."""
        raw = _full_valid_raw()
        raw["US10Y"]["current_yield"] = float("nan")
        result = validate_pipeline_data(raw, "MCX_SILVER")
        assert not result["pipeline_valid"]
        assert result["no_prediction_reason"] is not None


# ─── TEST 2: Missing timestamp blocks signal generation ─────────────────────

class TestMissingTimestamp:
    def test_no_fetched_at_blocks(self):
        """Instrument data without _fetched_at MUST be blocked."""
        raw = _full_valid_raw()
        del raw["MCX_SILVER"]["_fetched_at"]
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert not result["valid"]
        assert "timestamp" in result["reason"].lower() or "fetched_at" in result["reason"].lower()

    def test_corrupt_timestamp_blocks(self):
        """Unparseable _fetched_at MUST be blocked."""
        raw = _full_valid_raw()
        raw["MCX_SILVER"]["_fetched_at"] = "not-a-date"
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert not result["valid"]


# ─── TEST 3: Stale data blocks signal generation ────────────────────────────

class TestStaleDataBlocks:
    def test_stale_data_blocked(self):
        """Data older than staleness threshold MUST be blocked."""
        raw = _full_valid_raw()
        raw["MCX_SILVER"]["_fetched_at"] = _stale_ts(DATA_STALENESS_THRESHOLD_MINUTES + 5)
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert not result["valid"]
        assert result["status"] == "blocked"
        assert "stale" in result["reason"].lower()

    def test_stale_blocks_pipeline(self):
        """Stale data in any macro feed MUST block the pipeline."""
        raw = _full_valid_raw()
        raw["DXY"]["_fetched_at"] = _stale_ts(60)
        result = validate_pipeline_data(raw, "MCX_SILVER")
        assert not result["pipeline_valid"]
        assert "stale" in result["no_prediction_reason"].lower()


# ─── TEST 4: Wrong instrument mapping is detected ───────────────────────────

class TestInstrumentMapping:
    def test_mcx_rejects_silverbees_ticker(self):
        """MCX_SILVER using SILVERBEES.NS ticker MUST be detected as contamination."""
        raw = _full_valid_raw()
        raw["MCX_SILVER"]["_ticker"] = "SILVERBEES.NS"
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert not result["valid"]
        assert "contamination" in result["reason"].lower() or "mapping" in result["reason"].lower()

    def test_silverbees_rejects_sif_ticker(self):
        """SILVERBEES using SI=F ticker MUST be detected."""
        raw = {"SILVERBEES": {
            "current_price": 98.0,
            "prev_price": 97.5,
            "_fetched_at": _fresh_ts(),
            "_ticker": "SI=F",
            "_source": "Yahoo Finance",
            "_is_proxy": False,
            "_proxy_note": "",
        }}
        result = validate_instrument_data(raw, "SILVERBEES")
        assert not result["valid"]

    def test_tata_accepts_fallback_sif(self):
        """TATA_SILVER using SI=F fallback MUST be accepted (with warning)."""
        raw = {"TATA_SILVER": {
            "current_price": 92.0,
            "prev_price": 91.5,
            "_fetched_at": _fresh_ts(),
            "_ticker": "TATSILV.NS (fallback: SI=F derived)",
            "_source": "SI=F fallback",
            "_is_proxy": True,
            "_proxy_note": "MCX-derived fallback",
        }}
        result = validate_instrument_data(raw, "TATA_SILVER")
        assert result["valid"]  # Passes — but status should be "warning" due to proxy


# ─── TEST 5: Selected instrument price used, not shared global ───────────────

class TestInstrumentPriceIsolation:
    def test_mcx_uses_own_price_field(self):
        """MCX_SILVER price_field is 'current_price_inr', not 'current_price'."""
        inst = INSTRUMENTS["MCX_SILVER"]
        assert inst.price_field == "current_price_inr"

    def test_silverbees_uses_own_price_field(self):
        """SILVERBEES price_field is 'current_price'."""
        inst = INSTRUMENTS["SILVERBEES"]
        assert inst.price_field == "current_price"

    def test_tata_uses_own_price_field(self):
        """TATA_SILVER price_field is 'current_price'."""
        inst = INSTRUMENTS["TATA_SILVER"]
        assert inst.price_field == "current_price"

    def test_instruments_have_distinct_tickers(self):
        """Each instrument MUST map to a distinct primary ticker."""
        tickers = [inst.ticker for inst in INSTRUMENTS.values()]
        assert len(set(tickers)) == len(tickers), (
            f"Instruments have duplicate tickers: {tickers}"
        )


# ─── TEST 6: Tata fallback cannot silently contaminate MCX ──────────────────

class TestTataFallbackLabeling:
    def test_tata_fallback_marked_as_proxy(self):
        """If Tata data comes from MCX fallback, _is_proxy MUST be True."""
        raw = {"TATA_SILVER": {
            "current_price": 92.0,
            "prev_price": 91.5,
            "_fetched_at": _fresh_ts(),
            "_ticker": "TATSILV.NS (fallback: SI=F derived)",
            "_source": "Yahoo Finance (SI=F fallback)",
            "_is_proxy": True,
            "_proxy_note": "MCX-derived",
        }}
        result = validate_instrument_data(raw, "TATA_SILVER")
        assert result["valid"]
        assert result["status"] == "warning"
        assert "proxy" in result["reason"].lower() or "fallback" in result["reason"].lower()

    def test_tata_direct_feed_is_valid(self):
        """Tata direct feed (TATSILV.NS) MUST be fully valid — no warning."""
        raw = {"TATA_SILVER": {
            "current_price": 92.0,
            "prev_price": 91.5,
            "_fetched_at": _fresh_ts(),
            "_ticker": "TATSILV.NS",
            "_source": "Yahoo Finance (TATSILV.NS)",
            "_is_proxy": False,
            "_proxy_note": "",
        }}
        result = validate_instrument_data(raw, "TATA_SILVER")
        assert result["valid"]
        assert result["status"] == "valid"


# ─── TEST 7: Validation warnings do not pass as valid ────────────────────────

class TestWarningStatus:
    def test_warning_is_valid_but_has_reason(self):
        """Warning status means data is usable but the reason field is non-empty."""
        raw = {"MCX_SILVER": _valid_mcx()}  # MCX is always _is_proxy=True
        result = validate_instrument_data(raw, "MCX_SILVER")
        # MCX is a proxy instrument — should get a warning
        assert result["valid"]  # Still usable
        assert result["status"] == "warning"
        assert len(result["reason"]) > 0

    def test_pipeline_with_warnings_reports_them(self):
        """Pipeline with proxy data should report has_warnings=True."""
        raw = _full_valid_raw()  # MCX is proxy
        result = validate_pipeline_data(raw, "MCX_SILVER")
        assert result["pipeline_valid"]
        assert result["has_warnings"]
        assert len(result["warning_checks"]) > 0


# ─── TEST 8: AI trade-plan generation does not run when validation fails ────

class TestAIPlanBlockedOnInvalidData:
    def test_generate_trade_plan_rejects_none_price(self):
        """generate_trade_plan MUST return a blocked message for None price."""
        from ai_layer import generate_trade_plan
        scored_data = {
            "total_score": 40,
            "interpretation": "MILD BUY",
            "breakdown": {},
            "enriched_data": {"MCX_SILVER": {}},
        }
        result = generate_trade_plan(scored_data, inst_price=None, inst_name="MCX Silver", inst_unit="Rs/kg")
        assert "blocked" in result.lower() or "invalid" in result.lower() or "unavailable" in result.lower()

    def test_generate_trade_plan_rejects_nan_price(self):
        """generate_trade_plan MUST return a blocked message for NaN price."""
        from ai_layer import generate_trade_plan
        scored_data = {
            "total_score": 60,
            "interpretation": "STRONG BUY",
            "breakdown": {},
            "enriched_data": {"MCX_SILVER": {}},
        }
        result = generate_trade_plan(scored_data, inst_price=float("nan"), inst_name="Test", inst_unit="Rs/kg")
        assert "blocked" in result.lower() or "invalid" in result.lower() or "unavailable" in result.lower()

    def test_generate_trade_plan_rejects_zero_price(self):
        """generate_trade_plan MUST return a blocked message for price=0."""
        from ai_layer import generate_trade_plan
        scored_data = {
            "total_score": 20,
            "interpretation": "MILD BUY",
            "breakdown": {},
            "enriched_data": {"MCX_SILVER": {}},
        }
        result = generate_trade_plan(scored_data, inst_price=0.0, inst_name="Test", inst_unit="Rs/kg")
        assert "blocked" in result.lower() or "invalid" in result.lower() or "unavailable" in result.lower()


# ─── TEST 9: Timezone/session handling consistent ───────────────────────────

class TestTimezoneHandling:
    def test_fetched_at_is_utc(self):
        """All _fetched_at timestamps parsed as UTC-aware."""
        from data_quality import _check_freshness
        ts = datetime.now(timezone.utc).isoformat()
        data = {"_fetched_at": ts}
        ok, reason = _check_freshness(data, "TEST")
        assert ok, reason

    def test_naive_timestamp_treated_as_utc(self):
        """Naive timestamps (no tzinfo) MUST be treated as UTC, not rejected."""
        from data_quality import _check_freshness
        ts = datetime.utcnow().isoformat()  # naive
        data = {"_fetched_at": ts}
        ok, reason = _check_freshness(data, "TEST")
        assert ok, reason


# ─── TEST 10: Diagnostic status returns correct states ──────────────────────

class TestDiagnosticsStatus:
    def test_valid_data_produces_valid_status(self):
        """Valid data produces DataStatus with status='valid'."""
        data_dict = _valid_xag()
        validation_result = {"valid": True, "status": "valid", "reason": ""}
        ds = build_status_from_data_dict("XAGUSD", data_dict, validation_result)
        assert ds.status == "valid"
        assert ds.reason == ""
        assert ds.current_price == 31.5

    def test_missing_data_produces_missing_status(self):
        """None data dict produces DataStatus with status='missing'."""
        validation_result = {"valid": False, "status": "missing", "reason": "No data"}
        ds = build_status_from_data_dict("XAGUSD", None, validation_result)
        assert ds.status == "missing"

    def test_blocked_data_produces_blocked_status(self):
        """Failed validation produces DataStatus with status='blocked'."""
        data_dict = _valid_mcx()
        data_dict["current_price_inr"] = float("nan")
        validation_result = {"valid": False, "status": "blocked", "reason": "NaN detected"}
        ds = build_status_from_data_dict("MCX_SILVER", data_dict, validation_result)
        assert ds.status == "blocked"
        assert "NaN" in ds.reason

    def test_proxy_data_produces_warning_status(self):
        """Proxy/fallback data produces DataStatus with status='warning'."""
        data_dict = _valid_mcx()  # is_proxy is already set by _source containing "fallback"? No — _is_proxy=True
        data_dict["_source"] = "Yahoo Finance (SI=F fallback)"
        validation_result = {"valid": True, "status": "warning", "reason": "Using proxy"}
        ds = build_status_from_data_dict("MCX_SILVER", data_dict, validation_result)
        assert ds.status == "warning"
        assert ds.is_proxy

    def test_diagnostics_log_tracks_blocked_pipeline(self):
        """DiagnosticsLog correctly tracks when pipeline is blocked."""
        log = DiagnosticsLog()
        entry = DataStatus(instrument="MCX_SILVER", status="blocked", reason="Stale data")
        log.add(entry)
        log.block_pipeline("MCX_SILVER data stale")
        assert log.has_blocked()
        assert log.pipeline_blocked
        summary = log.summary()
        assert summary["blocked"] == 1
        assert summary["pipeline_blocked"] is True

    def test_diagnostics_log_warning_count(self):
        """DiagnosticsLog correctly counts warnings."""
        log = DiagnosticsLog()
        log.add(DataStatus(instrument="A", status="valid"))
        log.add(DataStatus(instrument="B", status="warning", reason="proxy"))
        log.add(DataStatus(instrument="C", status="valid"))
        assert log.has_warnings()
        assert not log.has_blocked()
        summary = log.summary()
        assert summary["valid"] == 2
        assert summary["warnings"] == 1


# ─── BONUS: Range validation tests ──────────────────────────────────────────

class TestRangeValidation:
    def test_zero_price_blocked(self):
        """Price of 0 MUST be blocked."""
        data_dict = _valid_mcx()
        data_dict["current_price_inr"] = 0.0
        ok, reason = _check_range(data_dict, "MCX_SILVER")
        assert not ok
        assert "positive" in reason.lower()

    def test_negative_price_blocked(self):
        """Negative price MUST be blocked."""
        data_dict = _valid_mcx()
        data_dict["current_price_inr"] = -100.0
        ok, reason = _check_range(data_dict, "MCX_SILVER")
        assert not ok

    def test_absurd_high_price_blocked(self):
        """Price above max plausible MUST be blocked."""
        data_dict = _valid_mcx()
        data_dict["current_price_inr"] = 999_999.0
        ok, reason = _check_range(data_dict, "MCX_SILVER")
        assert not ok
        assert "above maximum" in reason.lower()

    def test_absurd_low_price_blocked(self):
        """Price below min plausible MUST be blocked."""
        data_dict = _valid_mcx()
        data_dict["current_price_inr"] = 10.0
        ok, reason = _check_range(data_dict, "MCX_SILVER")
        assert not ok
        assert "below minimum" in reason.lower()

    def test_normal_price_passes(self):
        """Normal price within range passes."""
        data_dict = _valid_mcx()
        ok, reason = _check_range(data_dict, "MCX_SILVER")
        assert ok

    def test_dxy_range_enforced(self):
        """DXY must be within 60-130 range."""
        data_dict = {"current_dxy": 200.0}
        ok, reason = _check_range(data_dict, "DXY")
        assert not ok

    def test_xag_range_enforced(self):
        """Silver spot must be within 5-500 USD/oz."""
        data_dict = {"current_price": 0.3}
        ok, reason = _check_range(data_dict, "XAGUSD")
        assert not ok
