---
name: data-quality-checker
description: Validates every incoming price and data feed for freshness, completeness, NaN values, and correct instrument-symbol mapping before any signal or forecast is generated. Halts the pipeline with an exact reason if data fails validation.
---

# Data Quality Checker

This skill is the first stage of the SilverSense pipeline. It validates all incoming market data before any calculations are performed.

## Logic and Requirements

1. **Freshness Check:**
   - Every data feed must include a `_fetched_at` UTC timestamp.
   - If data is older than 15 minutes (configurable), it is considered stale.
   - Stale data returns: `{"valid": False, "reason": "Data stale — last fetched X minutes ago. Expected refresh within 15 minutes."}`

2. **Completeness Check:**
   - Required fields must be present and non-None for each instrument:
     - MCX Silver: `current_price_inr`, `prev_price_inr`, `history` (non-empty DataFrame)
     - Tata Silver / Silver Bees: `current_price`, `history` (non-empty DataFrame)
     - Macro data: `current_price`/`current_yield`/`current_rate` as applicable
   - Missing or None fields return: `{"valid": False, "reason": "Missing field '<field_name>' for instrument '<instrument>'."}`

3. **NaN/Inf Guard:**
   - Any NaN or Inf value in a price or required numeric field immediately fails validation.
   - Returns: `{"valid": False, "reason": "NaN/Inf detected in '<field_name>' for '<instrument>'. Cannot generate forecast."}`

4. **Instrument Mapping Check:**
   - Verifies that each instrument uses only its own designated price feed.
   - MCX Silver must NOT use TATSILV.NS or SILVERBEES.NS prices.
   - Tata Silver must NOT use SILVERBEES.NS prices, and vice versa.

5. **Pipeline Halt:**
   - If ANY check fails, the entire pipeline halts for that instrument and surfaces: `"No prediction available — <exact reason>"`. No forecast, trade plan, or signal is generated.

## Usage

This skill runs first on every data refresh cycle, before any technical analysis or forecasting. Trigger by asking "validate the current data quality" or it runs automatically at the start of every pipeline execution.
