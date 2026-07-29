"""
data_quality.py — Pipeline Stage 1
====================================
Validates every incoming data feed for:
  1. Existence (key present, not None)
  2. Freshness (timestamp present, within staleness threshold)
  3. Completeness (required fields non-None, non-NaN/Inf)
  4. Range plausibility (price within defined min/max bounds)
  5. Instrument mapping (correct ticker for the instrument)
  6. Proxy/fallback labeling (fallback data gets WARNING, not VALID)

Validation status levels:
  "valid"   — all checks passed; prediction can proceed
  "warning" — data is usable but a non-fatal issue exists (proxy, estimated data)
  "blocked" — a fatal check failed; pipeline MUST halt for this instrument
  "missing" — no data returned from fetch at all

Signals, forecasts, and trade plans MUST NOT run when status is "blocked" or "missing".
A "warning" status allows the pipeline to continue but MUST surface the warning to the user.
"""
import math
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from instrument_registry import (
    INSTRUMENTS,
    MACRO_FEEDS,
    get_price_range,
    get_price_field,
)
from diagnostics import DiagnosticsLog, DataStatus, build_status_from_data_dict, get_logger

_log = get_logger("data_quality")

# ─────────────────────────────────────────────────────────────────────────────
#  Configurable staleness threshold (read from env, default 15 min)
# ─────────────────────────────────────────────────────────────────────────────
DATA_STALENESS_THRESHOLD_MINUTES: int = int(
    os.getenv("DATA_STALENESS_THRESHOLD_MINUTES", "15")
)

# ─────────────────────────────────────────────────────────────────────────────
#  Required fields per instrument/feed key
# ─────────────────────────────────────────────────────────────────────────────
REQUIRED_FIELDS: dict[str, list[str]] = {
    "MCX_SILVER":   ["current_price_inr", "prev_price_inr"],
    "TATA_SILVER":  ["current_price", "prev_price"],
    "SILVERBEES":   ["current_price", "prev_price"],
    "XAGUSD":       ["current_price", "change_pct"],
    "DXY":          ["current_dxy"],
    "US10Y":        ["current_yield"],
    "USDINR":       ["current_rate"],
}

# ─────────────────────────────────────────────────────────────────────────────
#  Instrument → expected primary ticker
# ─────────────────────────────────────────────────────────────────────────────
INSTRUMENT_TICKERS: dict[str, str] = {
    inst.key: inst.ticker for inst in INSTRUMENTS.values()
}


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_nan_or_inf(v) -> bool:
    """Returns True if v is None, NaN, or Inf."""
    if v is None:
        return True
    try:
        fv = float(v)
        return math.isnan(fv) or math.isinf(fv)
    except (TypeError, ValueError):
        return False  # non-numeric is handled separately


def _check_freshness(data_dict: dict, instrument_key: str) -> tuple[bool, str]:
    """
    Checks _fetched_at timestamp. Returns (True, "") if fresh.
    Returns (False, reason) if stale or missing.
    """
    fetched_at_str = data_dict.get("_fetched_at")
    if not fetched_at_str:
        return False, (
            f"No freshness timestamp (_fetched_at) found for '{instrument_key}'. "
            "Data source integrity cannot be confirmed."
        )
    try:
        fetched_at = datetime.fromisoformat(fetched_at_str)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        age_minutes = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 60
        if age_minutes > DATA_STALENESS_THRESHOLD_MINUTES:
            return False, (
                f"Data for '{instrument_key}' is stale — last fetched "
                f"{age_minutes:.1f} minutes ago (threshold: {DATA_STALENESS_THRESHOLD_MINUTES} min)."
            )
    except (ValueError, TypeError) as e:
        return False, f"Could not parse _fetched_at for '{instrument_key}': {e}"
    return True, ""


def _check_completeness(data_dict: dict, instrument_key: str) -> tuple[bool, str]:
    """
    Checks required fields exist, are non-None, and non-NaN/Inf.
    Also validates that any history DataFrame has at least 2 rows.
    """
    required = REQUIRED_FIELDS.get(instrument_key, [])
    for field in required:
        val = data_dict.get(field)
        if val is None:
            return False, (
                f"Missing required field '{field}' for '{instrument_key}'. "
                "Cannot generate forecast."
            )
        if _is_nan_or_inf(val):
            return False, (
                f"NaN or Inf detected in field '{field}' for '{instrument_key}'. "
                "Cannot generate forecast."
            )
    # History DataFrame check
    history = data_dict.get("history")
    if history is not None:
        if hasattr(history, "empty") and history.empty:
            return False, (
                f"Price history DataFrame is empty for '{instrument_key}'. "
                "Insufficient data to compute indicators."
            )
        if hasattr(history, "shape") and history.shape[0] < 2:
            return False, (
                f"Price history for '{instrument_key}' has {history.shape[0]} row(s). "
                "At least 2 rows are required."
            )
    return True, ""


def _check_range(data_dict: dict, instrument_key: str, raw_data: Optional[dict] = None) -> tuple[bool, str]:
    """
    Validates that the primary price field is within plausible bounds.
    Returns (False, reason) if the value is outside defined min/max.
    A price of 0 or negative always fails.
    """
    try:
        price_field = get_price_field(instrument_key)
    except KeyError:
        return True, ""  # No range defined for this key; skip

    val = data_dict.get(price_field)
    if val is None:
        return True, ""  # Completeness check handles None

    try:
        fval = float(val)
    except (TypeError, ValueError):
        return True, ""  # Non-numeric handled by completeness

    if instrument_key in INSTRUMENTS:
        inst = INSTRUMENTS[instrument_key]
        fallback_price = None
        if raw_data and isinstance(raw_data, dict):
            fb_dict = raw_data.get("MCX_SILVER") or raw_data.get("XAGUSD") or {}
            fallback_price = fb_dict.get("current_price_inr") or fb_dict.get("current_price")
        return inst.validate_price(fval, fallback_price=fallback_price)

    try:
        price_min, price_max = get_price_range(instrument_key)
    except KeyError:
        return True, ""

    if fval <= 0:
        return False, (
            f"'{instrument_key}.{price_field}' is {fval} — must be positive. "
            "Possible API error or market closed."
        )
    if fval < price_min:
        return False, (
            f"'{instrument_key}.{price_field}' = {fval:.4f} is below minimum "
            f"plausible value of {price_min}. Possible unit error or stale feed."
        )
    if fval > price_max:
        return False, (
            f"'{instrument_key}.{price_field}' = {fval:.2f} is above maximum "
            f"plausible value of {price_max}. Possible API error."
        )
    return True, ""


def _check_instrument_mapping(data_dict: dict, instrument_key: str) -> tuple[bool, str]:
    """
    Verifies the _ticker in data dict matches the expected primary or allowed fallback
    ticker for this instrument. Cross-instrument contamination returns (False, reason).
    """
    expected_ticker = INSTRUMENT_TICKERS.get(instrument_key)
    if not expected_ticker:
        return True, ""  # Not an instrument with ticker enforcement

    actual_ticker = data_dict.get("_ticker", "")
    if not actual_ticker:
        # No ticker tag — cannot confirm mapping; treat as warning-level (checked separately)
        return True, ""

    # Tata Silver is allowed to fall back to SI=F — check via _is_proxy flag
    if instrument_key == "TATA_SILVER":
        # Accept TATSILV.NS (primary) or any SI=F fallback (marked as proxy)
        if "TATSILV.NS" in actual_ticker or "SI=F" in actual_ticker:
            return True, ""
        return False, (
            f"Instrument mapping error: '{instrument_key}' is using ticker "
            f"'{actual_ticker}' but expected 'TATSILV.NS' or SI=F fallback. "
            "Cross-instrument price contamination detected."
        )

    if expected_ticker not in actual_ticker:
        return False, (
            f"Instrument mapping error: '{instrument_key}' is using ticker "
            f"'{actual_ticker}' but expected '{expected_ticker}'. "
            "Cross-instrument price contamination detected."
        )
    return True, ""


def _check_proxy_labeling(data_dict: dict, instrument_key: str) -> tuple[str, str]:
    """
    Returns ("warning", note) if data is proxy/fallback, ("valid", "") otherwise.
    This is a non-fatal check — proxy data is usable but must be surfaced to user.
    """
    is_proxy = data_dict.get("_is_proxy", False)
    if is_proxy:
        proxy_note = data_dict.get("_proxy_note", "")
        source = data_dict.get("_source", "")
        return "warning", (
            f"'{instrument_key}' is using proxy/fallback data. "
            f"Source: {source}. {proxy_note}"
        )
    return "valid", ""


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

def validate_instrument_data(raw_data: dict, instrument_key: str) -> dict:
    """
    Runs all validation checks on a single instrument's data dict.

    Args:
        raw_data: full data bundle (may contain multiple instrument keys)
        instrument_key: key to validate, e.g. "MCX_SILVER", "XAGUSD"

    Returns:
        dict: {
            "valid": bool,        # True only for "valid" or "warning" status
            "status": str,        # "valid" | "warning" | "blocked" | "missing"
            "reason": str,        # human-readable explanation
            "instrument": str,
        }
    """
    data_dict = raw_data.get(instrument_key)
    if data_dict is None:
        return {
            "valid": False,
            "status": "missing",
            "reason": (
                f"No data returned for '{instrument_key}'. "
                "Fetch may have failed or market is closed."
            ),
            "instrument": instrument_key,
        }

    # 1. Freshness
    ok, reason = _check_freshness(data_dict, instrument_key)
    if not ok:
        return {"valid": False, "status": "blocked", "reason": reason, "instrument": instrument_key}

    # 2. Completeness + NaN/Inf
    ok, reason = _check_completeness(data_dict, instrument_key)
    if not ok:
        return {"valid": False, "status": "blocked", "reason": reason, "instrument": instrument_key}

    # 3. Range plausibility
    ok, reason = _check_range(data_dict, instrument_key, raw_data=raw_data)
    if not ok:
        return {"valid": False, "status": "blocked", "reason": reason, "instrument": instrument_key}

    # 4. Instrument mapping
    ok, reason = _check_instrument_mapping(data_dict, instrument_key)
    if not ok:
        return {"valid": False, "status": "blocked", "reason": reason, "instrument": instrument_key}

    # 5. Proxy/fallback warning (non-fatal)
    proxy_status, proxy_reason = _check_proxy_labeling(data_dict, instrument_key)
    if proxy_status == "warning":
        return {
            "valid": True,   # Still usable — pipeline continues with warning
            "status": "warning",
            "reason": proxy_reason,
            "instrument": instrument_key,
        }

    return {"valid": True, "status": "valid", "reason": "", "instrument": instrument_key}


def validate_pipeline_data(
    raw_data: dict,
    selected_instrument_key: str = "MCX_SILVER",
    diag_log: Optional[DiagnosticsLog] = None,
) -> dict:
    """
    Entry point for the full pipeline data quality gate.

    Validates:
    - All macro feeds (XAGUSD, DXY, US10Y, USDINR)
    - The selected instrument (e.g. MCX_SILVER, TATA_SILVER, SILVERBEES)
    - MCX_SILVER additionally when it is needed for OI scoring even if not the
      selected instrument

    Args:
        raw_data: full data bundle from fetch_all_data / fetch_tata_data / etc.
        selected_instrument_key: the primary instrument being analysed
        diag_log: optional DiagnosticsLog to append status entries to

    Returns:
        dict: {
            "pipeline_valid": bool,
            "has_warnings": bool,
            "failed_checks": list[dict],      # list of {instrument, status, reason}
            "warning_checks": list[dict],     # list of {instrument, status, reason}
            "no_prediction_reason": str|None  # human-readable halt message if blocked
        }
    """
    # Always validate macro feeds + the selected instrument.
    # Also validate MCX_SILVER when OI scoring is needed (always, since logic_engine uses it).
    keys_to_check = list({"XAGUSD", "DXY", "US10Y", "USDINR", selected_instrument_key, "MCX_SILVER"})

    failed = []
    warnings = []

    for key in keys_to_check:
        result = validate_instrument_data(raw_data, key)
        data_dict = raw_data.get(key)

        # Build diagnostic status
        if diag_log is not None:
            status_entry = build_status_from_data_dict(key, data_dict, result)
            diag_log.add(status_entry)

        if not result["valid"]:
            failed.append({
                "instrument": key,
                "status": result["status"],
                "reason": result["reason"],
            })
        elif result["status"] == "warning":
            warnings.append({
                "instrument": key,
                "status": result["status"],
                "reason": result["reason"],
            })

    if failed:
        primary = failed[0]
        reason = f"No prediction available — {primary['reason']}"
        if diag_log is not None:
            diag_log.block_pipeline(reason)
        return {
            "pipeline_valid": False,
            "has_warnings": bool(warnings),
            "failed_checks": failed,
            "warning_checks": warnings,
            "no_prediction_reason": reason,
        }

    return {
        "pipeline_valid": True,
        "has_warnings": bool(warnings),
        "failed_checks": [],
        "warning_checks": warnings,
        "no_prediction_reason": None,
    }
