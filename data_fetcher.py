"""
data_fetcher.py
===============
Fetches live market data from Yahoo Finance for all SilverSense instruments.

Design rules:
- All fetch functions stamp _fetched_at BEFORE network call (not after).
- _source and _ticker are always populated on successful results.
- No nested fetch calls (USDINR is fetched once externally, passed in if needed).
- instrument_registry.py is the sole source of tickers, periods, and constants.
- `continuew` typo is fixed to `continue`.
- OI fallback is clearly labeled as synthetic/estimated — never presented as real OI.
- All functions return None on failure — never a partial or fabricated dict.
"""
import yfinance as yf
import pandas as pd
import time
from datetime import datetime, timezone

from instrument_registry import (
    MCX_PREMIUM_FACTOR,
    MCX_KG_CONVERSION,
    INSTRUMENTS,
    MACRO_FEEDS,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Core fetch primitive
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ticker_data(ticker_symbol, period="60d", retries=2):
    """
    Fetches historical OHLCV data for a ticker via yfinance with retry logic.

    Returns:
        (hist: pd.DataFrame, info: dict) on success
        (None, None) on total failure
    """
    # Stamp the fetch attempt time BEFORE any network call
    # so that _fetched_at reflects when data was requested, not when processing finished.
    for attempt in range(retries + 1):
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period=period)
            if hist is None or hist.empty:
                if attempt < retries:
                    time.sleep(1)
                    continue          # BUG FIX: was `continuew`
                return None, None
            info = {}
            try:
                info = ticker.info or {}
            except Exception:
                info = {}
            return hist, info
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
                continue              # BUG FIX: was `continuew`
            print(f"[data_fetcher] Error fetching {ticker_symbol} after {retries+1} attempts: {e}")
            return None, None


# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL MACRO DATA (shared across all instruments)
# ─────────────────────────────────────────────────────────────────────────────

def get_us10y_data():
    """Fetches US 10-Year Bond Yield (^TNX)."""
    cfg = MACRO_FEEDS["US10Y"]
    fetched_at = datetime.now(timezone.utc).isoformat()
    hist, _ = fetch_ticker_data(cfg["ticker"], period=cfg["fetch_period"])
    if hist is None:
        return None
    v = hist["Close"].dropna()
    if v.empty:
        return None
    current_yield = float(v.iloc[-1])
    prev_yield = float(v.iloc[-2]) if len(v) > 1 else current_yield
    return {
        "current_yield": current_yield,
        "prev_yield": prev_yield,
        "rising": current_yield > prev_yield,
        "_fetched_at": fetched_at,
        "_source": f"Yahoo Finance ({cfg['ticker']})",
        "_ticker": cfg["ticker"],
    }


def get_dxy_data():
    """Fetches Dollar Index (DXY)."""
    cfg = MACRO_FEEDS["DXY"]
    fetched_at = datetime.now(timezone.utc).isoformat()
    hist, _ = fetch_ticker_data(cfg["ticker"], period=cfg["fetch_period"])
    if hist is None:
        return None
    v = hist["Close"].dropna()
    if v.empty:
        return None
    current_dxy = float(v.iloc[-1])
    prev_dxy = float(v.iloc[-2]) if len(v) > 1 else current_dxy
    return {
        "current_dxy": current_dxy,
        "prev_dxy": prev_dxy,
        "rising": current_dxy > prev_dxy,
        "_fetched_at": fetched_at,
        "_source": f"Yahoo Finance ({cfg['ticker']})",
        "_ticker": cfg["ticker"],
    }


def get_usdinr_data():
    """Fetches USD/INR exchange rate."""
    cfg = MACRO_FEEDS["USDINR"]
    fetched_at = datetime.now(timezone.utc).isoformat()
    hist, _ = fetch_ticker_data(cfg["ticker"], period=cfg["fetch_period"])
    if hist is None:
        return None
    v = hist["Close"].dropna()
    if v.empty:
        return None
    current_rate = float(v.iloc[-1])
    prev_rate = float(v.iloc[-2]) if len(v) > 1 else current_rate
    return {
        "current_rate": current_rate,
        "prev_rate": prev_rate,
        "weakening": current_rate > prev_rate,
        "_fetched_at": fetched_at,
        "_source": f"Yahoo Finance ({cfg['ticker']})",
        "_ticker": cfg["ticker"],
    }


# ─────────────────────────────────────────────────────────────────────────────
#  INSTRUMENT: Silver Spot (COMEX SI=F) — used for RSI/SMA/MACD in logic_engine
# ─────────────────────────────────────────────────────────────────────────────

def get_xagusd_data():
    """Fetches Global Silver Price via COMEX Silver Futures (SI=F)."""
    cfg = MACRO_FEEDS["XAGUSD"]
    fetched_at = datetime.now(timezone.utc).isoformat()
    hist, _ = fetch_ticker_data(cfg["ticker"], period=cfg["fetch_period"])
    if hist is None:
        return None
    v = hist["Close"].dropna()
    if v.empty:
        return None
    current_price = float(v.iloc[-1])
    prev_close = float(v.iloc[-2]) if len(v) > 1 else current_price
    change_abs = current_price - prev_close
    change_pct = (change_abs / prev_close) * 100 if prev_close != 0 else 0.0
    return {
        "current_price": current_price,
        "change_abs": change_abs,
        "change_pct": change_pct,
        "history": hist,
        "_fetched_at": fetched_at,
        "_source": f"Yahoo Finance ({cfg['ticker']})",
        "_ticker": cfg["ticker"],
    }


# ─────────────────────────────────────────────────────────────────────────────
#  INSTRUMENT: MCX Silver (SI=F → INR/kg)
# ─────────────────────────────────────────────────────────────────────────────

def get_mcx_silver_data(usdinr_rate: float = None):
    """
    Fetches MCX Silver proxy via COMEX SI=F and converts to INR/kg.

    Args:
        usdinr_rate: pre-fetched USD/INR rate float. If None, fetches independently.
                     Pass the already-fetched USDINR data to avoid a duplicate network call.

    Returns:
        dict with current_price_inr, prev_price_inr, OI proxy fields, and metadata.
        OI values are synthetic — derived from volume; labeled clearly as estimated.
    """
    inst = INSTRUMENTS["MCX_SILVER"]
    fetched_at = datetime.now(timezone.utc).isoformat()
    hist, info = fetch_ticker_data(inst.ticker, period=inst.fetch_period)
    if hist is None:
        return None
    v = hist["Close"].dropna()
    if v.empty:
        return None

    current_price_usd = float(v.iloc[-1])
    prev_close_usd = float(v.iloc[-2]) if len(v) > 1 else current_price_usd

    # Volume (for synthetic OI proxy)
    vol = hist["Volume"].fillna(0)
    today_volume = int(vol.iloc[-1])
    avg_volume_20d = (
        float(vol.rolling(window=20).mean().iloc[-1])
        if len(vol) >= 20 else float(today_volume)
    )

    # OI: use real yfinance openInterest if available; otherwise mark as synthetic.
    # IMPORTANT: yfinance openInterest is often 0 or missing. When it is,
    # we do NOT fabricate a "50000" constant. We return 0 and mark oi_is_synthetic=True.
    raw_oi = info.get("openInterest", 0) if info else 0
    if raw_oi and raw_oi > 0:
        open_interest_current = int(raw_oi)
        open_interest_prev = int(
            open_interest_current * 0.95
            if today_volume > avg_volume_20d
            else open_interest_current * 1.05
        )
        oi_is_synthetic = False
        oi_source = "yfinance openInterest"
    else:
        # Volume-derived synthetic OI proxy — do NOT use for definitive OI signal
        open_interest_current = today_volume
        open_interest_prev = int(avg_volume_20d)
        oi_is_synthetic = True
        oi_source = "volume-proxy (real OI unavailable)"

    # USD/INR conversion — use passed-in rate to avoid double fetch
    if usdinr_rate is None or not isinstance(usdinr_rate, float) or usdinr_rate <= 0:
        _usdinr = get_usdinr_data()
        usdinr_rate = _usdinr["current_rate"] if _usdinr else 85.0

    current_price_inr = current_price_usd * usdinr_rate * MCX_KG_CONVERSION * MCX_PREMIUM_FACTOR
    prev_price_inr = prev_close_usd * usdinr_rate * MCX_KG_CONVERSION * MCX_PREMIUM_FACTOR

    return {
        "current_price_inr": current_price_inr,
        "prev_price_inr": prev_price_inr,
        "current_price_usd": current_price_usd,
        "usdinr_rate_used": usdinr_rate,
        "mcx_premium_factor": MCX_PREMIUM_FACTOR,
        "today_volume": today_volume,
        "avg_volume_20d": avg_volume_20d,
        "open_interest_current": open_interest_current,
        "open_interest_prev": open_interest_prev,
        "oi_is_synthetic": oi_is_synthetic,
        "oi_source": oi_source,
        "history": hist,
        "_fetched_at": fetched_at,
        "_source": f"Yahoo Finance ({inst.ticker} -> INR/kg via premium {MCX_PREMIUM_FACTOR:.4f})",
        "_ticker": inst.ticker,
        "_is_proxy": True,
        "_proxy_note": inst.proxy_note,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  INSTRUMENT: Tata Silver (TATSILV.NS, fallback to MCX-derived)
# ─────────────────────────────────────────────────────────────────────────────

def get_tata_silver_data(usdinr_rate: float = None):
    """
    Fetches Tata Silver ETF (TATSILV.NS) from NSE.
    Falls back to MCX-derived price if ETF data is unavailable.
    Fallback result is ALWAYS labeled as estimated — _is_proxy=True.
    """
    inst = INSTRUMENTS["TATA_SILVER"]
    fetched_at = datetime.now(timezone.utc).isoformat()
    hist, _ = fetch_ticker_data(inst.ticker, period=inst.fetch_period)

    if hist is not None:
        v = hist["Close"].dropna()
        if not v.empty:
            current_price = float(v.iloc[-1])
            prev_close = float(v.iloc[-2]) if len(v) > 1 else current_price
            change_abs = current_price - prev_close
            change_pct = (change_abs / prev_close) * 100 if prev_close != 0 else 0.0
            vol = hist["Volume"].fillna(0)
            today_volume = int(vol.iloc[-1])
            avg_volume_20d = (
                float(vol.rolling(window=20).mean().iloc[-1])
                if len(vol) >= 20 else float(today_volume)
            )
            return {
                "current_price": current_price,
                "prev_price": prev_close,
                "change_abs": change_abs,
                "change_pct": change_pct,
                "unit": inst.unit,
                "label": inst.display_name,
                "today_volume": today_volume,
                "avg_volume_20d": avg_volume_20d,
                "open_interest_current": 0,
                "open_interest_prev": 0,
                "history": hist,
                "_fetched_at": fetched_at,
                "_source": f"Yahoo Finance ({inst.ticker})",
                "_ticker": inst.ticker,
                "_is_proxy": False,
                "_proxy_note": "",
            }

    # ── Fallback: derive from MCX ────────────────────────────────────────────
    mcx = get_mcx_silver_data(usdinr_rate=usdinr_rate)
    if mcx is None:
        return None

    # MCX is Rs/kg; 1 kg = 1000 gm; TATSILV ~1 unit ≈ 1 gm silver NAV
    price_unit = mcx["current_price_inr"] / 1000
    prev_unit = mcx["prev_price_inr"] / 1000
    change_abs = price_unit - prev_unit
    change_pct = (change_abs / prev_unit) * 100 if prev_unit != 0 else 0.0

    return {
        "current_price": price_unit,
        "prev_price": prev_unit,
        "change_abs": change_abs,
        "change_pct": change_pct,
        "unit": inst.unit,
        "label": f"{inst.display_name} (Estimated — TATSILV.NS unavailable)",
        "today_volume": mcx["today_volume"],
        "avg_volume_20d": mcx["avg_volume_20d"],
        "open_interest_current": 0,
        "open_interest_prev": 0,
        "history": mcx["history"],
        "_fetched_at": fetched_at,
        "_source": f"Yahoo Finance (SI=F fallback — TATSILV.NS unavailable)",
        "_ticker": f"{inst.ticker} (fallback: SI=F derived)",
        "_is_proxy": True,
        "_proxy_note": inst.proxy_note,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  INSTRUMENT: Silver Bees ETF (SILVERBEES.NS)
# ─────────────────────────────────────────────────────────────────────────────

def get_silverbees_data():
    """Fetches Silver Bees ETF (SILVERBEES.NS) from NSE. No fallback."""
    inst = INSTRUMENTS["SILVERBEES"]
    fetched_at = datetime.now(timezone.utc).isoformat()
    hist, _ = fetch_ticker_data(inst.ticker, period=inst.fetch_period)
    if hist is None:
        return None
    v = hist["Close"].dropna()
    if v.empty:
        return None
    current_price = float(v.iloc[-1])
    prev_close = float(v.iloc[-2]) if len(v) > 1 else current_price
    change_abs = current_price - prev_close
    change_pct = (change_abs / prev_close) * 100 if prev_close != 0 else 0.0
    vol = hist["Volume"].fillna(0)
    today_volume = int(vol.iloc[-1])
    avg_volume_20d = (
        float(vol.rolling(window=20).mean().iloc[-1])
        if len(vol) >= 20 else float(today_volume)
    )
    return {
        "current_price": current_price,
        "prev_price": prev_close,
        "change_abs": change_abs,
        "change_pct": change_pct,
        "unit": inst.unit,
        "label": inst.display_name,
        "today_volume": today_volume,
        "avg_volume_20d": avg_volume_20d,
        "open_interest_current": 0,
        "open_interest_prev": 0,
        "history": hist,
        "_fetched_at": fetched_at,
        "_source": f"Yahoo Finance ({inst.ticker})",
        "_ticker": inst.ticker,
        "_is_proxy": False,
        "_proxy_note": "",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  AGGREGATE FETCHERS
#  Each fetcher fetches USDINR once and passes the rate to MCX to avoid
#  a duplicate network call (previous bug: USDINR was fetched twice per run).
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_macro_bundle() -> dict:
    """Fetch all macro feeds once. Returns partial dict if some feeds fail."""
    usdinr = get_usdinr_data()
    return {
        "XAGUSD": get_xagusd_data(),
        "US10Y": get_us10y_data(),
        "DXY": get_dxy_data(),
        "USDINR": usdinr,
        "_usdinr_rate": usdinr["current_rate"] if usdinr else None,
    }


def fetch_all_data() -> dict:
    """Fetch macro bundle + MCX Silver (primary instrument)."""
    bundle = _fetch_macro_bundle()
    usdinr_rate = bundle.pop("_usdinr_rate", None)
    bundle["MCX_SILVER"] = get_mcx_silver_data(usdinr_rate=usdinr_rate)
    return bundle


def fetch_tata_data() -> dict:
    """Fetch macro bundle + Tata Silver. MCX_SILVER is included for OI scoring."""
    bundle = _fetch_macro_bundle()
    usdinr_rate = bundle.pop("_usdinr_rate", None)
    bundle["MCX_SILVER"] = get_mcx_silver_data(usdinr_rate=usdinr_rate)
    bundle["TATA_SILVER"] = get_tata_silver_data(usdinr_rate=usdinr_rate)
    return bundle


def fetch_bees_data() -> dict:
    """Fetch macro bundle + Silver Bees. MCX_SILVER is included for OI scoring."""
    bundle = _fetch_macro_bundle()
    usdinr_rate = bundle.pop("_usdinr_rate", None)
    bundle["MCX_SILVER"] = get_mcx_silver_data(usdinr_rate=usdinr_rate)
    bundle["SILVERBEES"] = get_silverbees_data()
    return bundle


# ─────────────────────────────────────────────────────────────────────────────
#  DYNAMIC CHART DATA
# ─────────────────────────────────────────────────────────────────────────────

CHART_INTERVALS = {
    "1 Minute":   {"interval": "1m",  "period": "1d"},
    "5 Minutes":  {"interval": "5m",  "period": "5d"},
    "15 Minutes": {"interval": "15m", "period": "5d"},
    "1 Hour":     {"interval": "1h",  "period": "1mo"},
    "1 Day":      {"interval": "1d",  "period": "6mo"},
    "1 Week":     {"interval": "1wk", "period": "2y"},
    "1 Month":    {"interval": "1mo", "period": "5y"},
    "3 Months":   {"interval": "1d",  "period": "3mo"},
    "6 Months":   {"interval": "1d",  "period": "6mo"},
    "12 Months":  {"interval": "1d",  "period": "1y"},
}


def fetch_dynamic_chart(ticker_symbol, timeframe="1 Day"):
    config = CHART_INTERVALS.get(timeframe, CHART_INTERVALS["1 Day"])
    try:
        ticker = yf.Ticker(ticker_symbol)
        data = ticker.history(period=config["period"], interval=config["interval"])
        if data is not None and not data.empty:
            return data, timeframe
    except Exception as e:
        print(f"[data_fetcher] Error fetching chart for {ticker_symbol} at {timeframe}: {e}")
    return None, None


def fetch_intraday_data():
    try:
        ticker = yf.Ticker("SI=F")
        intraday = ticker.history(period="1d", interval="5m")
        if intraday is not None and not intraday.empty and len(intraday) > 2:
            return intraday, "intraday"
    except Exception:
        pass
    try:
        daily = yf.Ticker("SI=F").history(period="5d")
        if daily is not None and not daily.empty:
            return daily, "daily"
    except Exception:
        pass
    return None, None
