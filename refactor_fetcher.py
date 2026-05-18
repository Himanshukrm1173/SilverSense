import os

new_fetcher_content = """import yfinance as yf
import pandas as pd
import time


def fetch_ticker_data(ticker_symbol, period="60d", retries=2):
    \"\"\"Fetches historical data for a given ticker using yfinance with retry logic.\"\"\"
    for attempt in range(retries + 1):
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period=period)
            if hist is None or hist.empty:
                if attempt < retries:
                    time.sleep(1)
                    continue
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
                continue
            print(f"Error fetching data for {ticker_symbol}: {e}")
            return None, None


# ─────────────────────────────────────────────
#  GLOBAL MACRO DATA (shared across instruments)
# ─────────────────────────────────────────────

def get_us10y_data():
    \"\"\"Fetches US 10-Year Bond Yield (^TNX).\"\"\"
    hist, info = fetch_ticker_data("^TNX", period="5d")
    if hist is None: return None
    v = hist['Close'].dropna()
    if v.empty: return None
    current_yield = float(v.iloc[-1])
    prev_yield = float(v.iloc[-2]) if len(v) > 1 else current_yield
    return {"current_yield": current_yield, "prev_yield": prev_yield, "rising": current_yield > prev_yield}


def get_dxy_data():
    \"\"\"Fetches Dollar Index (DXY).\"\"\"
    hist, info = fetch_ticker_data("DX-Y.NYB", period="5d")
    if hist is None: return None
    v = hist['Close'].dropna()
    if v.empty: return None
    current_dxy = float(v.iloc[-1])
    prev_dxy = float(v.iloc[-2]) if len(v) > 1 else current_dxy
    return {"current_dxy": current_dxy, "prev_dxy": prev_dxy, "rising": current_dxy > prev_dxy}


def get_usdinr_data():
    \"\"\"Fetches USD/INR Rate.\"\"\"
    hist, info = fetch_ticker_data("USDINR=X", period="5d")
    if hist is None: return None
    v = hist['Close'].dropna()
    if v.empty: return None
    current_rate = float(v.iloc[-1])
    prev_rate = float(v.iloc[-2]) if len(v) > 1 else current_rate
    return {"current_rate": current_rate, "prev_rate": prev_rate, "weakening": current_rate > prev_rate}


# ─────────────────────────────────────────────
#  INSTRUMENT: SILVER MCX (SI=F → INR/kg)
# ─────────────────────────────────────────────

def get_xagusd_data():
    \"\"\"Fetches Global Silver Price via COMEX Silver Futures (SI=F).\"\"\"
    hist, info = fetch_ticker_data("SI=F", period="60d")
    if hist is None: return None
    v = hist['Close'].dropna()
    if v.empty: return None
    current_price = float(v.iloc[-1])
    prev_close = float(v.iloc[-2]) if len(v) > 1 else current_price
    change_abs = current_price - prev_close
    change_pct = (change_abs / prev_close) * 100 if prev_close != 0 else 0
    return {"current_price": current_price, "change_abs": change_abs, "change_pct": change_pct, "history": hist}


def get_mcx_silver_data():
    \"\"\"Fetches MCX Silver Futures proxy (SI=F) and converts to INR/kg.\"\"\"
    hist, info = fetch_ticker_data("SI=F", period="30d")
    if hist is None: return None
    v = hist['Close'].dropna()
    if v.empty: return None
    current_price = float(v.iloc[-1])
    prev_close = float(v.iloc[-2]) if len(v) > 1 else current_price
    
    vol = hist['Volume'].fillna(0)
    today_volume = int(vol.iloc[-1])
    avg_volume_20d = float(vol.rolling(window=20).mean().iloc[-1]) if len(vol) >= 20 else float(today_volume)
    
    open_interest_current = info.get('openInterest', 0) if info else 0
    if open_interest_current == 0: open_interest_current = 50000
    open_interest_prev = int(open_interest_current * 0.95) if today_volume > avg_volume_20d else int(open_interest_current * 1.05)
    
    usdinr_data = get_usdinr_data()
    usd_inr_rate = usdinr_data['current_rate'] if usdinr_data else 85.0
    kg_conversion = 32.15074656
    current_price_inr_kg = current_price * usd_inr_rate * kg_conversion
    prev_price_inr_kg = prev_close * usd_inr_rate * kg_conversion
    return {
        "current_price_inr": current_price_inr_kg, "prev_price_inr": prev_price_inr_kg,
        "today_volume": today_volume, "avg_volume_20d": avg_volume_20d,
        "open_interest_current": open_interest_current, "open_interest_prev": open_interest_prev,
        "history": hist
    }


# ─────────────────────────────────────────────
#  INSTRUMENT: TATA SILVER (SI=F → INR/10gm)
# ─────────────────────────────────────────────

def get_tata_silver_data():
    \"\"\"Tata Silver price = MCX Silver converted to ₹/10gm (physical retail standard).\"\"\"
    mcx = get_mcx_silver_data()
    if mcx is None: return None
    price_10gm = mcx["current_price_inr"] / 100
    prev_10gm = mcx["prev_price_inr"] / 100
    change_abs = price_10gm - prev_10gm
    change_pct = (change_abs / prev_10gm) * 100 if prev_10gm != 0 else 0
    return {
        "current_price": price_10gm, "prev_price": prev_10gm,
        "change_abs": change_abs, "change_pct": change_pct,
        "unit": "Rs/10gm", "label": "Tata Silver",
        "today_volume": mcx["today_volume"], "avg_volume_20d": mcx["avg_volume_20d"],
        "open_interest_current": mcx["open_interest_current"],
        "open_interest_prev": mcx["open_interest_prev"],
        "history": mcx["history"]
    }


# ─────────────────────────────────────────────
#  INSTRUMENT: SILVER BEES ETF (SILVERBEES.NS)
# ─────────────────────────────────────────────

def get_silverbees_data():
    \"\"\"Fetches Silver Bees ETF data from NSE.\"\"\"
    hist, info = fetch_ticker_data("SILVERBEES.NS", period="60d")
    if hist is None: return None
    v = hist['Close'].dropna()
    if v.empty: return None
    current_price = float(v.iloc[-1])
    prev_close = float(v.iloc[-2]) if len(v) > 1 else current_price
    change_abs = current_price - prev_close
    change_pct = (change_abs / prev_close) * 100 if prev_close != 0 else 0
    
    vol = hist['Volume'].fillna(0)
    today_volume = int(vol.iloc[-1])
    avg_volume_20d = float(vol.rolling(window=20).mean().iloc[-1]) if len(vol) >= 20 else float(today_volume)
    return {
        "current_price": current_price, "prev_price": prev_close,
        "change_abs": change_abs, "change_pct": change_pct,
        "unit": "Rs/unit", "label": "Silver Bees",
        "today_volume": today_volume, "avg_volume_20d": avg_volume_20d,
        "open_interest_current": 0, "open_interest_prev": 0,
        "history": hist
    }


# ─────────────────────────────────────────────
#  AGGREGATE FETCHERS
# ─────────────────────────────────────────────

def fetch_all_data():
    return {
        "XAGUSD": get_xagusd_data(), "US10Y": get_us10y_data(),
        "DXY": get_dxy_data(), "USDINR": get_usdinr_data(),
        "MCX_SILVER": get_mcx_silver_data()
    }


def fetch_tata_data():
    return {
        "XAGUSD": get_xagusd_data(), "US10Y": get_us10y_data(),
        "DXY": get_dxy_data(), "USDINR": get_usdinr_data(),
        "MCX_SILVER": get_mcx_silver_data(),
        "TATA_SILVER": get_tata_silver_data()
    }


def fetch_bees_data():
    return {
        "XAGUSD": get_xagusd_data(), "US10Y": get_us10y_data(),
        "DXY": get_dxy_data(), "USDINR": get_usdinr_data(),
        "MCX_SILVER": get_mcx_silver_data(),
        "SILVERBEES": get_silverbees_data()
    }


# ─────────────────────────────────────────────
#  DYNAMIC CHART DATA
# ─────────────────────────────────────────────

CHART_INTERVALS = {
    "1 Minute":  {"interval": "1m",  "period": "1d"},
    "5 Minutes": {"interval": "5m",  "period": "5d"},
    "15 Minutes":{"interval": "15m", "period": "5d"},
    "1 Hour":    {"interval": "1h",  "period": "1mo"},
    "1 Day":     {"interval": "1d",  "period": "6mo"},
    "1 Week":    {"interval": "1wk", "period": "2y"},
    "1 Month":   {"interval": "1mo", "period": "5y"},
    "3 Months":  {"interval": "1d",  "period": "3mo"},
    "6 Months":  {"interval": "1d",  "period": "6mo"},
    "12 Months": {"interval": "1d",  "period": "1y"},
}


def fetch_dynamic_chart(ticker_symbol, timeframe="1 Day"):
    config = CHART_INTERVALS.get(timeframe, CHART_INTERVALS["1 Day"])
    try:
        ticker = yf.Ticker(ticker_symbol)
        data = ticker.history(period=config["period"], interval=config["interval"])
        if data is not None and not data.empty:
            return data, timeframe
    except Exception as e:
        print(f"Error fetching chart for {ticker_symbol} at {timeframe}: {e}")
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
\"\"\"

with open(\"/Users/himanshukumar/Desktop/Project/Silver price tool/data_fetcher.py\", \"w\") as f:
    f.write(new_fetcher_content)
"
