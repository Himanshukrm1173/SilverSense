"""
test_instrument_mapping.py

Tests that price data for each instrument is NEVER sourced from
another instrument's feed. Cross-contamination must be impossible.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_quality import validate_instrument_data, INSTRUMENT_TICKERS


class TestInstrumentMapping:
    def _make_data_dict(self, ticker, price_key="current_price_inr", price_val=90000.0):
        from datetime import datetime, timezone
        return {
            price_key: price_val,
            "prev_price_inr" if price_key == "current_price_inr" else "prev_price": price_val - 100,
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "_ticker": ticker,
            "_source": f"Yahoo Finance ({ticker})",
        }

    def test_mcx_silver_uses_sif(self):
        """MCX Silver with SI=F ticker passes mapping validation."""
        raw = {"MCX_SILVER": self._make_data_dict("SI=F")}
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert result["valid"] is True, result["reason"]

    def test_mcx_silver_rejects_tatsilv(self):
        """MCX Silver using TATSILV.NS ticker fails mapping check."""
        raw = {"MCX_SILVER": self._make_data_dict("TATSILV.NS")}
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert result["valid"] is False
        assert "mapping error" in result["reason"].lower() or "contamination" in result["reason"].lower()

    def test_mcx_silver_rejects_silverbees(self):
        """MCX Silver using SILVERBEES.NS ticker fails mapping check."""
        raw = {"MCX_SILVER": self._make_data_dict("SILVERBEES.NS")}
        result = validate_instrument_data(raw, "MCX_SILVER")
        assert result["valid"] is False

    def test_silverbees_uses_own_ticker(self):
        """SILVERBEES with SILVERBEES.NS ticker passes mapping validation."""
        from datetime import datetime, timezone
        raw = {"SILVERBEES": {
            "current_price": 98.0,
            "prev_price": 97.5,
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "_ticker": "SILVERBEES.NS",
            "_source": "Yahoo Finance (SILVERBEES.NS)",
        }}
        result = validate_instrument_data(raw, "SILVERBEES")
        assert result["valid"] is True, result["reason"]

    def test_silverbees_rejects_sif(self):
        """SILVERBEES using SI=F ticker fails mapping check."""
        from datetime import datetime, timezone
        raw = {"SILVERBEES": {
            "current_price": 98.0,
            "prev_price": 97.5,
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "_ticker": "SI=F",
        }}
        result = validate_instrument_data(raw, "SILVERBEES")
        assert result["valid"] is False

    def test_tata_silver_allows_fallback(self):
        """Tata Silver using SI=F as fallback ticker is acceptable."""
        from datetime import datetime, timezone
        raw = {"TATA_SILVER": {
            "current_price": 95.0,
            "prev_price": 94.5,
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "_ticker": "TATSILV.NS (fallback)",
            "_source": "Yahoo Finance (SI=F fallback)",
        }}
        result = validate_instrument_data(raw, "TATA_SILVER")
        assert result["valid"] is True, result["reason"]

    def test_tata_silver_rejects_silverbees(self):
        """Tata Silver using SILVERBEES.NS ticker fails mapping check."""
        from datetime import datetime, timezone
        raw = {"TATA_SILVER": {
            "current_price": 95.0,
            "prev_price": 94.5,
            "_fetched_at": datetime.now(timezone.utc).isoformat(),
            "_ticker": "SILVERBEES.NS",
        }}
        result = validate_instrument_data(raw, "TATA_SILVER")
        assert result["valid"] is False

    def test_instruments_have_separate_tickers(self):
        """All instruments must map to distinct expected tickers."""
        tickers = list(INSTRUMENT_TICKERS.values())
        # TATA can fallback, but the 3 base tickers must be distinct
        assert len(set(tickers)) == len(tickers), "Instrument tickers must be unique"
