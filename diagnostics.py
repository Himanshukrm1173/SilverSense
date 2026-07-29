"""
diagnostics.py — Structured Logging & Observability
=====================================================
Provides:
  - DataStatus: dataclass capturing per-instrument validation state
  - DiagnosticsLog: collects status entries during a pipeline run
  - render_diagnostics_panel: Streamlit panel for developer/debug view
  - get_logger: returns a structured logger writing to stderr + optional file

All log output is structured text — no emojis, no rich formatting.
"""
import logging
import sys
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List

# ─────────────────────────────────────────────────────────────────────────────
#  Structured Logging Setup
# ─────────────────────────────────────────────────────────────────────────────

def get_logger(name: str = "silversense") -> logging.Logger:
    """
    Returns a named logger that writes ISO-timestamped lines to stderr.
    Usage: logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger


_log = get_logger("diagnostics")


# ─────────────────────────────────────────────────────────────────────────────
#  DataStatus: per-feed validation state
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DataStatus:
    """
    Captures the validation state of one data feed after a pipeline run.

    status values:
      "valid"   — all checks passed, prediction can proceed
      "warning" — data passed but a non-fatal issue was noted (e.g. proxy used)
      "blocked" — a fatal check failed; prediction MUST NOT proceed
      "missing" — no data was returned from the fetch function
    """
    instrument: str
    status: str                           # "valid" | "warning" | "blocked" | "missing"
    reason: str = ""                      # Human-readable explanation
    source: str = ""                      # _source tag from data dict
    ticker: str = ""                      # _ticker tag from data dict
    fetched_at: Optional[str] = None      # ISO UTC string from _fetched_at
    age_seconds: Optional[float] = None   # Age in seconds at validation time
    current_price: Optional[float] = None # Numeric price value if available
    is_proxy: bool = False                # True if using derived/fallback data
    proxy_note: str = ""                  # Describes proxy methodology if is_proxy
    logged_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def age_minutes(self) -> Optional[float]:
        if self.age_seconds is None:
            return None
        return self.age_seconds / 60

    @property
    def age_display(self) -> str:
        if self.age_seconds is None:
            return "unknown"
        m = self.age_seconds / 60
        if m < 1:
            return f"{self.age_seconds:.0f}s ago"
        return f"{m:.1f} min ago"

    @property
    def status_label(self) -> str:
        return {
            "valid": "VALID",
            "warning": "WARNING",
            "blocked": "BLOCKED",
            "missing": "MISSING",
        }.get(self.status, self.status.upper())


# ─────────────────────────────────────────────────────────────────────────────
#  DiagnosticsLog: collects all DataStatus entries for a pipeline run
# ─────────────────────────────────────────────────────────────────────────────

class DiagnosticsLog:
    """
    Collects DataStatus entries during a single pipeline run.
    Passed around by reference so any module can append to it.
    """
    def __init__(self):
        self.entries: List[DataStatus] = []
        self.run_started_at: str = datetime.now(timezone.utc).isoformat()
        self.pipeline_blocked: bool = False
        self.block_reason: str = ""

    def add(self, status: DataStatus):
        """Append a DataStatus entry and log it."""
        self.entries.append(status)
        level = {
            "valid": logging.DEBUG,
            "warning": logging.WARNING,
            "blocked": logging.ERROR,
            "missing": logging.ERROR,
        }.get(status.status, logging.INFO)
        _log.log(
            level,
            "[%s] %s | source=%s | ticker=%s | age=%s | price=%s | reason=%s",
            status.status_label,
            status.instrument,
            status.source or "unknown",
            status.ticker or "unknown",
            status.age_display,
            f"{status.current_price:,.2f}" if status.current_price is not None else "N/A",
            status.reason or "OK",
        )

    def block_pipeline(self, reason: str):
        """Mark the whole pipeline as blocked."""
        self.pipeline_blocked = True
        self.block_reason = reason
        _log.error("PIPELINE BLOCKED: %s", reason)

    def has_blocked(self) -> bool:
        return any(e.status == "blocked" or e.status == "missing" for e in self.entries)

    def has_warnings(self) -> bool:
        return any(e.status == "warning" for e in self.entries)

    def get_entry(self, instrument: str) -> Optional[DataStatus]:
        for e in self.entries:
            if e.instrument == instrument:
                return e
        return None

    def summary(self) -> dict:
        return {
            "run_started_at": self.run_started_at,
            "pipeline_blocked": self.pipeline_blocked,
            "block_reason": self.block_reason,
            "total": len(self.entries),
            "valid": sum(1 for e in self.entries if e.status == "valid"),
            "warnings": sum(1 for e in self.entries if e.status == "warning"),
            "blocked": sum(1 for e in self.entries if e.status == "blocked"),
            "missing": sum(1 for e in self.entries if e.status == "missing"),
        }


# ─────────────────────────────────────────────────────────────────────────────
#  DataStatus builder — used by data_quality.py
# ─────────────────────────────────────────────────────────────────────────────

def build_status_from_data_dict(
    instrument: str,
    data_dict: Optional[dict],
    validation_result: dict,
) -> DataStatus:
    """
    Builds a DataStatus from a raw data dict + validation result.
    This is called by data_quality after running checks.
    """
    if data_dict is None:
        return DataStatus(
            instrument=instrument,
            status="missing",
            reason=f"No data returned for '{instrument}'",
        )

    # Compute age
    age_seconds = None
    fetched_at = data_dict.get("_fetched_at")
    if fetched_at:
        try:
            dt = datetime.fromisoformat(fetched_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - dt).total_seconds()
        except Exception:
            pass

    # Extract price
    from instrument_registry import INSTRUMENTS, MACRO_FEEDS
    price = None
    if instrument in INSTRUMENTS:
        pf = INSTRUMENTS[instrument].price_field
        v = data_dict.get(pf)
        if v is not None and isinstance(v, (int, float)) and not math.isnan(float(v)):
            price = float(v)
    elif instrument in MACRO_FEEDS:
        pf = MACRO_FEEDS[instrument]["price_field"]
        v = data_dict.get(pf)
        if v is not None and isinstance(v, (int, float)) and not math.isnan(float(v)):
            price = float(v)

    is_proxy = "fallback" in data_dict.get("_source", "").lower()
    proxy_note = ""
    if is_proxy and instrument in INSTRUMENTS:
        from instrument_registry import INSTRUMENTS as _INST
        proxy_note = _INST[instrument].proxy_note

    # Determine status
    if not validation_result["valid"]:
        status = "blocked"
        reason = validation_result["reason"]
    elif is_proxy:
        status = "warning"
        reason = f"Using fallback/proxy data. {proxy_note}"
    else:
        status = "valid"
        reason = ""

    return DataStatus(
        instrument=instrument,
        status=status,
        reason=reason,
        source=data_dict.get("_source", ""),
        ticker=data_dict.get("_ticker", ""),
        fetched_at=fetched_at,
        age_seconds=age_seconds,
        current_price=price,
        is_proxy=is_proxy,
        proxy_note=proxy_note,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Streamlit Diagnostics Panel
# ─────────────────────────────────────────────────────────────────────────────

def render_diagnostics_panel(diag_log: DiagnosticsLog):
    """
    Renders a minimal but useful developer diagnostics section in Streamlit.
    Shows per-feed validation status, fetch age, source, and price.
    Call this inside a st.expander("Data Diagnostics") block.
    """
    try:
        import streamlit as st
    except ImportError:
        return

    summary = diag_log.summary()

    # Pipeline status header
    if summary["pipeline_blocked"]:
        st.error(f"PIPELINE BLOCKED — {summary['block_reason']}")
    elif summary["warnings"]:
        st.warning(
            f"Pipeline running with {summary['warnings']} warning(s). "
            "Proxy or estimated data in use."
        )
    else:
        st.success(
            f"All {summary['valid']} feeds valid. "
            f"Last checked at {summary['run_started_at']}"
        )

    # Per-feed table
    rows = []
    for entry in diag_log.entries:
        rows.append({
            "Feed": entry.instrument,
            "Status": entry.status_label,
            "Source": entry.source or "—",
            "Ticker": entry.ticker or "—",
            "Age": entry.age_display,
            "Price": (
                f"{entry.current_price:,.2f}" if entry.current_price is not None else "—"
            ),
            "Proxy": "Yes" if entry.is_proxy else "No",
            "Note": entry.reason[:80] if entry.reason else "—",
        })

    if rows:
        import pandas as pd
        df = pd.DataFrame(rows)
        # Color-code status column
        def _style_status(v):
            colors = {
                "VALID": "color: #00cc66",
                "WARNING": "color: #ffcc00",
                "BLOCKED": "color: #cc3333; font-weight: bold",
                "MISSING": "color: #cc3333; font-weight: bold",
            }
            return colors.get(v, "")
        styled = df.style.map(_style_status, subset=["Status"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    # Proxy warnings detail
    proxy_entries = [e for e in diag_log.entries if e.is_proxy and e.proxy_note]
    if proxy_entries:
        with st.expander("Proxy / Estimated Data Details", expanded=False):
            for e in proxy_entries:
                st.markdown(
                    f"**{e.instrument}**: {e.proxy_note}"
                )
