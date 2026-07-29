"""
instrument_registry.py — Single Source of Truth
================================================
All instrument definitions, ticker mappings, units, currency assumptions,
price range bounds, and conversion constants live here.

All other modules MUST import from this module instead of defining their
own ticker strings, unit labels, or conversion constants.

DO NOT hard-code API keys, tickers, units, or price bounds anywhere else.
"""
import os
from dataclasses import dataclass, field
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
#  MCX Conversion Constants
#  Source: Standard commodity conversion + approximate Indian import tax structure
#  - 1 troy oz = 0.031103 kg  →  1 kg = 32.15074656 troy oz
#  - Indian import duty + GST + local warehousing premium: ~3–9% depending on period
#  - This is an APPROXIMATION. Actual MCX price depends on exchange-specific contracts.
#  Override via MCX_PREMIUM_FACTOR env var (float, e.g. 1.0622)
# ─────────────────────────────────────────────────────────────────────────────
_DEFAULT_MCX_PREMIUM = 1.0622
MCX_PREMIUM_FACTOR: float = float(os.getenv("MCX_PREMIUM_FACTOR", str(_DEFAULT_MCX_PREMIUM)))
MCX_KG_CONVERSION: float = 32.15074656  # troy oz per kg


# ─────────────────────────────────────────────────────────────────────────────
#  Instrument Definition
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Instrument:
    key: str                    # Internal key used in data dicts, e.g. "MCX_SILVER"
    display_name: str           # UI display name, e.g. "MCX Silver"
    ticker: str                 # Primary Yahoo Finance ticker
    unit: str                   # Price unit label, e.g. "Rs/kg"
    currency: str               # ISO currency, e.g. "INR"
    price_field: str            # Key in data dict holding the current price
    price_min: float            # Minimum plausible price (sanity gate)
    price_max: float            # Maximum plausible price (sanity gate)
    fetch_period: str           # yfinance history period
    fallback_ticker: Optional[str] = None  # Secondary ticker if primary fails
    fallback_multiplier: float = 1.0       # Multiplier for fallback price comparison
    is_proxy: bool = False      # True if this instrument uses derived/proxy pricing
    proxy_note: str = ""        # Description of proxy methodology if is_proxy=True
    has_oi: bool = False        # True if open interest is meaningful for this instrument
    description: str = ""       # One-line description for diagnostics panel

    def validate_price(self, price: float, fallback_price: Optional[float] = None) -> tuple[bool, str]:
        """Validate price for this instrument."""
        if price <= 0:
            return False, f"'{self.key}.{self.price_field}' = {price} — must be positive. Possible API error or market closed."

        if self.key == "TATA_SILVER":
            return True, ""

        if price < self.price_min:
            return False, (
                f"'{self.key}.{self.price_field}' = {price:.4f} is below minimum "
                f"plausible value of {self.price_min}. Possible unit error or stale feed."
            )
        if price > self.price_max:
            return False, (
                f"'{self.key}.{self.price_field}' = {price:.2f} is above maximum "
                f"plausible value of {self.price_max}. Possible API error."
            )
        return True, ""


# ─────────────────────────────────────────────────────────────────────────────
#  Registry of all supported instruments
# ─────────────────────────────────────────────────────────────────────────────
INSTRUMENTS: dict[str, Instrument] = {
    "MCX_SILVER": Instrument(
        key="MCX_SILVER",
        display_name="MCX Silver",
        ticker="SI=F",
        unit="Rs/kg",
        currency="INR",
        price_field="current_price_inr",
        price_min=50_000.0,    # Rs/kg — below this is clearly wrong
        price_max=250_000.0,   # Rs/kg — above this would be unprecedented
        fetch_period="30d",
        fallback_ticker=None,
        is_proxy=True,
        proxy_note=(
            "MCX Silver price is derived from COMEX SI=F (USD/troy oz) converted to "
            "INR/kg using live USD/INR rate, troy-oz-to-kg ratio, and an import duty + "
            f"GST premium factor of {MCX_PREMIUM_FACTOR:.4f}. This is an approximation. "
            "Actual MCX prices may deviate by 0.5–2% due to exchange-specific premiums."
        ),
        has_oi=True,
        description="MCX Silver Futures proxy via COMEX SI=F → INR/kg conversion",
    ),
    "TATA_SILVER": Instrument(
        key="TATA_SILVER",
        display_name="Tata Silver",
        ticker="TATSILV.NS",
        unit="Rs/unit",
        currency="INR",
        price_field="current_price",
        price_min=0.0,
        price_max=float("inf"),
        fetch_period="60d",
        fallback_ticker="SI=F",  # MCX-derived fallback
        fallback_multiplier=1/1000.0,  # 1kg to 1g approx conversion
        is_proxy=False,  # Primary is direct; fallback is proxy
        proxy_note=(
            "When TATSILV.NS data is unavailable, price is derived from MCX Silver "
            "(SI=F → INR/kg) divided by 1000 to approximate 1-gram NAV. "
            "Fallback is labeled as estimated and triggers a data quality warning."
        ),
        has_oi=False,
        description="Tata Silver ETF (NSE: TATSILV.NS) — tracks ~1 gram silver NAV",
    ),
    "SILVERBEES": Instrument(
        key="SILVERBEES",
        display_name="Silver Bees",
        ticker="SILVERBEES.NS",
        unit="Rs/unit",
        currency="INR",
        price_field="current_price",
        price_min=50.0,
        price_max=250.0,
        fetch_period="60d",
        fallback_ticker=None,
        is_proxy=False,
        proxy_note="",
        has_oi=False,
        description="Silver Bees ETF (NSE: SILVERBEES.NS) — tracks ~1 gram silver NAV",
    ),
}

# Macro data feeds — not instruments but validated for pipeline integrity
MACRO_FEEDS: dict[str, dict] = {
    "XAGUSD": {
        "ticker": "SI=F",
        "display_name": "Silver Spot (COMEX SI=F)",
        "fetch_period": "60d",
        "price_field": "current_price",
        "price_min": 5.0,      # USD/troy oz — below this is wrong
        "price_max": 500.0,    # USD/troy oz — above this would be unprecedented
        "unit": "USD/oz",
        "description": "Global silver price via COMEX Silver Futures",
    },
    "DXY": {
        "ticker": "DX-Y.NYB",
        "display_name": "Dollar Index (DXY)",
        "fetch_period": "5d",
        "price_field": "current_dxy",
        "price_min": 60.0,
        "price_max": 130.0,
        "unit": "index",
        "description": "US Dollar Index — measures USD strength vs basket of currencies",
    },
    "US10Y": {
        "ticker": "^TNX",
        "display_name": "US 10Y Bond Yield",
        "fetch_period": "5d",
        "price_field": "current_yield",
        "price_min": 0.0,
        "price_max": 20.0,
        "unit": "%",
        "description": "US 10-Year Treasury yield — inverse relationship with silver",
    },
    "USDINR": {
        "ticker": "USDINR=X",
        "display_name": "USD/INR",
        "fetch_period": "5d",
        "price_field": "current_rate",
        "price_min": 60.0,
        "price_max": 100.0,
        "unit": "INR",
        "description": "US Dollar to Indian Rupee exchange rate",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
#  Accessor helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_instrument(key: str) -> Instrument:
    """Return Instrument definition. Raises KeyError if unknown key."""
    if key not in INSTRUMENTS:
        raise KeyError(
            f"Unknown instrument key '{key}'. "
            f"Valid keys: {sorted(INSTRUMENTS.keys())}"
        )
    return INSTRUMENTS[key]


def get_macro_feed(key: str) -> dict:
    """Return macro feed definition. Raises KeyError if unknown."""
    if key not in MACRO_FEEDS:
        raise KeyError(
            f"Unknown macro feed key '{key}'. "
            f"Valid keys: {sorted(MACRO_FEEDS.keys())}"
        )
    return MACRO_FEEDS[key]


def instrument_keys() -> list[str]:
    """Return sorted list of all instrument keys."""
    return sorted(INSTRUMENTS.keys())


def get_price_range(key: str) -> tuple[float, float]:
    """Return (min, max) plausible price for an instrument or macro feed."""
    if key in INSTRUMENTS:
        inst = INSTRUMENTS[key]
        return (inst.price_min, inst.price_max)
    if key in MACRO_FEEDS:
        feed = MACRO_FEEDS[key]
        return (feed["price_min"], feed["price_max"])
    raise KeyError(f"Unknown key '{key}'")


def get_price_field(key: str) -> str:
    """Return the dict key that holds current price for this instrument/feed."""
    if key in INSTRUMENTS:
        return INSTRUMENTS[key].price_field
    if key in MACRO_FEEDS:
        return MACRO_FEEDS[key]["price_field"]
    raise KeyError(f"Unknown key '{key}'")


# ─────────────────────────────────────────────────────────────────────────────
#  Unit consistency helpers (used by ai_layer, prediction_engine)
# ─────────────────────────────────────────────────────────────────────────────

def format_price(price: float, instrument_key: str) -> str:
    """Return a consistently formatted price string for any instrument."""
    if instrument_key in INSTRUMENTS:
        unit = INSTRUMENTS[instrument_key].unit
    elif instrument_key in MACRO_FEEDS:
        unit = MACRO_FEEDS[instrument_key]["unit"]
    else:
        unit = ""

    if unit in ("Rs/kg",):
        return f"Rs {price:,.0f}"
    elif unit in ("Rs/unit",):
        return f"Rs {price:,.2f}"
    elif unit == "USD/oz":
        return f"${price:.2f}"
    elif unit == "%":
        return f"{price:.3f}%"
    else:
        return f"{price:,.2f} {unit}"
