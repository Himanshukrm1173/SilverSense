"""
macro_regime.py — Pipeline Stage 4

Evaluates macroeconomic indicators (DXY, US10Y, USDINR) to classify the
current macro regime and flag regime-transition risk. This provides supporting
context for multi-horizon forecasting but NEVER overrides technical signals
without direct supporting data evidence.
"""
import math


def _safe_float(v, default=0.0):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return default
    return float(v)


def detect_macro_regime(dxy_data: dict, us10y_data: dict, usdinr_data: dict) -> dict:
    """
    Classify the macro regime for silver based on three macro indicators.

    Classification logic:
    - risk-on:    DXY falling + yields falling → both tailwinds for silver
    - risk-off:   DXY rising  + yields rising  → both headwinds for silver
    - stagflation: yields rising + DXY flat/falling → inflationary pressure
    - neutral:    Mixed or no dominant direction

    Regime-transition risk is flagged True if 2+ indicators changed direction
    vs their prior value (i.e., were previously trending differently).

    Args:
        dxy_data:    dict with keys: current_dxy, prev_dxy, rising
        us10y_data:  dict with keys: current_yield, prev_yield, rising
        usdinr_data: dict with keys: current_rate, prev_rate, weakening

    Returns:
        dict: {
            "macro_regime": str,          # risk-on | risk-off | stagflation | neutral
            "regime_transition_risk": bool,
            "macro_summary": str,
            "dxy_direction": str,
            "yield_direction": str,
            "usdinr_direction": str,
            "macro_silver_bias": str,     # bullish | bearish | neutral | mixed
        }
    """
    # --- Extract signals ---
    dxy_rising = (dxy_data or {}).get("rising", False)
    yield_rising = (us10y_data or {}).get("rising", False)
    inr_weakening = (usdinr_data or {}).get("weakening", False)  # weakening = bullish for MCX

    dxy_str = "rising" if dxy_rising else "falling"
    yield_str = "rising" if yield_rising else "falling"
    inr_str = "weakening" if inr_weakening else "strengthening"

    # --- Transition Risk: check if any indicator reversed vs prior ---
    dxy_current = _safe_float((dxy_data or {}).get("current_dxy"))
    dxy_prev = _safe_float((dxy_data or {}).get("prev_dxy"))
    yield_current = _safe_float((us10y_data or {}).get("current_yield"))
    yield_prev = _safe_float((us10y_data or {}).get("prev_yield"))
    inr_current = _safe_float((usdinr_data or {}).get("current_rate"))
    inr_prev = _safe_float((usdinr_data or {}).get("prev_rate"))

    # A "reversal" is when the current direction differs from what we'd infer
    # from a 2-session prior comparison (simplified: prev vs current)
    reversals = 0
    if dxy_prev and abs(dxy_current - dxy_prev) / max(dxy_prev, 1e-9) > 0.003:
        reversals += 1
    if yield_prev and abs(yield_current - yield_prev) / max(yield_prev, 1e-9) > 0.01:
        reversals += 1
    if inr_prev and abs(inr_current - inr_prev) / max(inr_prev, 1e-9) > 0.003:
        reversals += 1

    regime_transition_risk = reversals >= 2

    # --- Regime Classification ---
    bullish_count = 0
    bearish_count = 0

    if not dxy_rising:
        bullish_count += 1   # Falling DXY = bullish for silver
    else:
        bearish_count += 1

    if not yield_rising:
        bullish_count += 1   # Falling yields = bullish for silver
    else:
        bearish_count += 1

    if inr_weakening:
        bullish_count += 1   # Weakening INR = bullish for MCX silver (INR-denominated)
    else:
        bearish_count += 1

    # Macro regime determination
    if not dxy_rising and not yield_rising:
        macro_regime = "risk-on"
        macro_silver_bias = "bullish"
        summary = (
            f"Risk-on macro environment: DXY {dxy_str} and US yields {yield_str} — "
            f"both tailwinds for silver. INR is {inr_str}."
        )
    elif dxy_rising and yield_rising:
        macro_regime = "risk-off"
        macro_silver_bias = "bearish"
        summary = (
            f"Risk-off macro environment: DXY {dxy_str} and US yields {yield_str} — "
            f"both headwinds for silver. INR is {inr_str}."
        )
    elif yield_rising and not dxy_rising:
        macro_regime = "stagflation"
        macro_silver_bias = "mixed"
        summary = (
            f"Stagflationary signals: US yields {yield_str} (bearish) but DXY {dxy_str} "
            f"(bullish). Mixed environment — inflation hedge demand may support silver. "
            f"INR is {inr_str}."
        )
    else:
        macro_regime = "neutral"
        macro_silver_bias = "neutral"
        summary = (
            f"Neutral macro environment: DXY {dxy_str}, US yields {yield_str}, "
            f"INR {inr_str}. No dominant macro force on silver."
        )

    if regime_transition_risk:
        summary += " CAUTION: Multiple macro indicators showing unusual moves — regime transition risk is elevated."

    return {
        "macro_regime": macro_regime,
        "regime_transition_risk": regime_transition_risk,
        "macro_summary": summary,
        "dxy_direction": dxy_str,
        "yield_direction": yield_str,
        "usdinr_direction": inr_str,
        "macro_silver_bias": macro_silver_bias,
        "bullish_factors": bullish_count,
        "bearish_factors": bearish_count,
    }
