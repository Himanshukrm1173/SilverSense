"""
Prediction Engine for SilverSense Live Prediction Module.
Implements a ±5 scoring system with direction, % move, probability,
signal strength, price levels, and contextual risk alerts.

Note: Multi-horizon forecasting is delegated to horizon_engine.py
which derives 24H, 1W, and 1M independently using separate feature weights.
"""
import math
from horizon_engine import get_multi_horizon_forecast


def evaluate_xagusd_signal(xag_data):
    """XAGUSD: Price up from yesterday = +1, down = -1."""
    if not xag_data:
        return 0, "--", "N/A"
    change = xag_data.get("change_pct", 0)
    price = xag_data.get("current_price", 0)
    if change > 0:
        return 1, f"${price:.2f}", "Bullish"
    elif change < 0:
        return -1, f"${price:.2f}", "Bearish"
    return 0, f"${price:.2f}", "Neutral"


def evaluate_us10y_signal(us10y_data):
    """US10Y: Yield falling = +1 (bullish for silver), rising = -1."""
    if not us10y_data:
        return 0, "--", "N/A"
    y_val = us10y_data.get("current_yield", 0)
    rising = us10y_data.get("rising", False)
    status = "Rising" if rising else "Falling"
    if rising:
        return -1, f"{y_val:.3f}% ({status})", "Bearish"
    else:
        return 1, f"{y_val:.3f}% ({status})", "Bullish"


def evaluate_dxy_signal(dxy_data):
    """DXY: Dollar falling = +1, rising = -1."""
    if not dxy_data:
        return 0, "--", "N/A"
    dxy_val = dxy_data.get("current_dxy", 0)
    rising = dxy_data.get("rising", False)
    status = "Rising" if rising else "Falling"
    if rising:
        return -1, f"{dxy_val:.2f} ({status})", "Bearish"
    else:
        return 1, f"{dxy_val:.2f} ({status})", "Bullish"


def evaluate_usdinr_signal(usdinr_data):
    """USD/INR: Rupee weakening (USDINR rising) = +1, strengthening = -1."""
    if not usdinr_data:
        return 0, "--", "N/A"
    rate = usdinr_data.get("current_rate", 0)
    weakening = usdinr_data.get("weakening", False)
    status = "Weakening" if weakening else "Strengthening"
    if weakening:
        return 1, f"₹{rate:.2f} ({status})", "Bullish"
    else:
        return -1, f"₹{rate:.2f} ({status})", "Bearish"


def evaluate_oi_signal(mcx_data):
    """OI Signal: Long Buildup = +1, Short Buildup = -1, else = 0."""
    if not mcx_data:
        return 0, "--", "N/A"
    oi_signal = mcx_data.get("oi_signal_name", "Neutral")
    price_inr = mcx_data.get("current_price_inr", 0)
    val_str = f"₹{price_inr:,.0f}/kg | {oi_signal}"
    if oi_signal == "Long Buildup":
        return 1, val_str, "Bullish"
    elif oi_signal == "Short Buildup":
        return -1, val_str, "Bearish"
    else:
        return 0, val_str, "Neutral"


def get_prediction(data, inst_price=None, inst_unit="₹/kg", inst_name="MCX Silver"):
    """
    Run all 5 signal evaluators, compute total score (-5 to +5),
    and map to direction, % move, probability, strength, levels, and recommendation.
    If inst_price is provided, use it for all price calculations instead of MCX ₹/kg.
    """
    xag = data.get("XAGUSD") or {}
    us10y = data.get("US10Y") or {}
    dxy = data.get("DXY") or {}
    usdinr = data.get("USDINR") or {}
    mcx = data.get("MCX_SILVER") or {}

    # Evaluate each signal
    s1_score, s1_val, s1_status = evaluate_xagusd_signal(xag)
    s2_score, s2_val, s2_status = evaluate_us10y_signal(us10y)
    s3_score, s3_val, s3_status = evaluate_dxy_signal(dxy)
    s4_score, s4_val, s4_status = evaluate_usdinr_signal(usdinr)
    s5_score, s5_val, s5_status = evaluate_oi_signal(mcx)

    total_score = s1_score + s2_score + s3_score + s4_score + s5_score
    abs_score = abs(total_score)

    # --- Direction ---
    if total_score > 0:
        direction = "UP"
        direction_color = "green"
    elif total_score < 0:
        direction = "DOWN"
        direction_color = "red"
    else:
        direction = "SIDEWAYS"
        direction_color = "gray"

    # --- Expected % Move ---
    move_map = {0: (0.0, 0.0), 1: (0.3, 0.5), 2: (0.5, 1.0), 3: (1.0, 1.5), 4: (1.5, 2.5), 5: (1.5, 2.5)}
    move_low, move_high = move_map.get(abs_score, (0.0, 0.0))

    # --- Probability ---
    prob_map = {0: (40, 50), 1: (45, 55), 2: (55, 65), 3: (65, 75), 4: (75, 85), 5: (85, 92)}
    prob_low, prob_high = prob_map.get(abs_score, (40, 50))
    prob_mid = (prob_low + prob_high) // 2  # for the gauge

    # --- Signal Strength ---
    if abs_score <= 1:
        strength = "WEAK"
        strength_color = "orange"
    elif abs_score <= 3:
        strength = "MODERATE"
        strength_color = "#FFD700"  # gold
    else:
        strength = "STRONG"
        strength_color = "lime"

    # --- Action / Recommendation ---
    if total_score >= 2:
        action = "BUY"
        action_color = "green"
    elif total_score <= -2:
        action = "SELL"
        action_color = "red"
    else:
        action = "WAIT"
        action_color = "gray"

    # --- Reason (2 lines) ---
    bullish_signals = []
    bearish_signals = []
    if s1_score > 0: bullish_signals.append("Silver spot rising")
    if s1_score < 0: bearish_signals.append("Silver spot falling")
    if s2_score > 0: bullish_signals.append("Bond yields falling")
    if s2_score < 0: bearish_signals.append("Bond yields rising")
    if s3_score > 0: bullish_signals.append("Dollar weakening")
    if s3_score < 0: bearish_signals.append("Dollar strengthening")
    if s4_score > 0: bullish_signals.append("Rupee weakening (INR boost)")
    if s4_score < 0: bearish_signals.append("Rupee strengthening")
    if s5_score > 0: bullish_signals.append("Long buildup in futures")
    if s5_score < 0: bearish_signals.append("Short buildup in futures")

    if action == "BUY":
        reason_line1 = f"Bullish factors: {', '.join(bullish_signals)}."
        reason_line2 = f"Consider buying {inst_name} on dips with a tight stop loss."
    elif action == "SELL":
        reason_line1 = f"Bearish factors: {', '.join(bearish_signals)}."
        reason_line2 = f"Consider selling {inst_name} on rallies with a tight stop loss."
    else:
        active = bullish_signals + bearish_signals
        reason_line1 = f"Mixed signals: {', '.join(active) if active else 'No strong triggers'}."
        reason_line2 = "Wait for a clearer breakout before taking a position."

    # --- Price Levels ---
    # Use instrument-specific price if provided, else default to MCX ₹/kg
    if inst_price is not None and not (isinstance(inst_price, float) and math.isnan(inst_price)):
        mcx_price = inst_price
    else:
        mcx_price = mcx.get("current_price_inr", 0) if mcx else 0
    move_pct_avg = (move_low + move_high) / 2 / 100
    expected_high = mcx_price * (1 + move_pct_avg)
    expected_low = mcx_price * (1 - move_pct_avg)

    if total_score > 0:
        support = mcx_price * (1 - move_low / 100)
        resistance = mcx_price * (1 + move_high / 100)
    elif total_score < 0:
        support = mcx_price * (1 - move_high / 100)
        resistance = mcx_price * (1 + move_low / 100)
    else:
        support = mcx_price * (1 - move_pct_avg)
        resistance = mcx_price * (1 + move_pct_avg)

    # --- Risk Alert ---
    risk_factors = []
    if s3_score < 0:
        risk_factors.append("Dollar strength could cap silver gains — watch DXY closely.")
    if s2_score < 0:
        risk_factors.append("Rising US bond yields are pressuring precious metals.")
    if s5_score < 0:
        risk_factors.append("Short buildup in futures suggests selling pressure ahead.")
    if s1_score < 0:
        risk_factors.append("Global silver spot is declining — watch for further downside.")
    if s4_score < 0:
        risk_factors.append("Rupee strengthening could reduce MCX silver premiums.")
    if not risk_factors:
        risk_factors.append("No major risk triggers today. Monitor global cues and US data releases.")
    risk_alert = risk_factors[0]  # show the most relevant one

    # --- Signal Breakdown ---
    signals = [
        {"Signal": "XAGUSD Spot", "Value": s1_val, "Status": "↑ Up" if s1_score > 0 else ("↓ Down" if s1_score < 0 else "— Flat"), "Rating": s1_status},
        {"Signal": "US 10Y Yield", "Value": s2_val, "Status": "↓ Falling" if s2_score > 0 else ("↑ Rising" if s2_score < 0 else "— Flat"), "Rating": s2_status},
        {"Signal": "Dollar Index (DXY)", "Value": s3_val, "Status": "↓ Falling" if s3_score > 0 else ("↑ Rising" if s3_score < 0 else "— Flat"), "Rating": s3_status},
        {"Signal": "USD/INR", "Value": s4_val, "Status": "↑ Weakening" if s4_score > 0 else ("↓ Strengthening" if s4_score < 0 else "— Flat"), "Rating": s4_status},
        {"Signal": "MCX OI Signal", "Value": s5_val, "Status": "Long Buildup" if s5_score > 0 else ("Short Buildup" if s5_score < 0 else "Neutral"), "Rating": s5_status},
    ]

    # --- Final Conclusion ---
    bullish_count = len(bullish_signals)
    bearish_count = len(bearish_signals)
    neutral_count = 5 - bullish_count - bearish_count

    safe_resistance = f"{resistance:,.0f}" if inst_unit == "Rs/kg" else f"{resistance:,.2f}"
    safe_support = f"{support:,.0f}" if inst_unit == "Rs/kg" else f"{support:,.2f}"
    safe_expected_low = f"{expected_low:,.0f}" if inst_unit == "Rs/kg" else f"{expected_low:,.2f}"
    safe_expected_high = f"{expected_high:,.0f}" if inst_unit == "Rs/kg" else f"{expected_high:,.2f}"

    if total_score >= 4:
        conclusion = (
            f"VERDICT: {inst_name} is very likely to RISE. "
            f"{bullish_count} out of 5 factors are bullish ({', '.join(bullish_signals)}). "
            f"Strong upward momentum expected — {inst_name} could move towards {safe_resistance} {inst_unit} today."
        )
    elif total_score >= 2:
        conclusion = (
            f"VERDICT: {inst_name} is likely to RISE. "
            f"{bullish_count} out of 5 factors are bullish ({', '.join(bullish_signals)}), "
            f"while {bearish_count} are bearish ({', '.join(bearish_signals) if bearish_signals else 'none'}). "
            f"Expect moderate upside towards {safe_resistance} {inst_unit} with support near {safe_support} {inst_unit}."
        )
    elif total_score == 1:
        conclusion = (
            f"VERDICT: {inst_name} has a slight upward bias but direction is unclear. "
            f"{bullish_count} bullish vs {bearish_count} bearish factors. "
            f"Wait for confirmation before taking a strong position."
        )
    elif total_score == 0:
        conclusion = (
            f"VERDICT: {inst_name} is likely to trade SIDEWAYS today. "
            f"Bullish and bearish forces are equally balanced ({bullish_count} vs {bearish_count}). "
            f"Expect price to stay in the {safe_expected_low} – {safe_expected_high} range."
        )
    elif total_score == -1:
        conclusion = (
            f"VERDICT: {inst_name} has a slight downward bias but direction is unclear. "
            f"{bearish_count} bearish vs {bullish_count} bullish factors. "
            f"Wait for confirmation before taking a strong position."
        )
    elif total_score >= -3:
        conclusion = (
            f"VERDICT: {inst_name} is likely to FALL. "
            f"{bearish_count} out of 5 factors are bearish ({', '.join(bearish_signals)}), "
            f"while {bullish_count} are bullish ({', '.join(bullish_signals) if bullish_signals else 'none'}). "
            f"Expect downside towards {safe_support} {inst_unit} with resistance near {safe_resistance} {inst_unit}."
        )
    else:
        conclusion = (
            f"VERDICT: {inst_name} is very likely to FALL. "
            f"{bearish_count} out of 5 factors are bearish ({', '.join(bearish_signals)}). "
            f"Strong downward pressure expected — {inst_name} could drop towards {safe_support} {inst_unit} today."
        )

    return {
        "total_score": total_score,
        "direction": direction,
        "direction_color": direction_color,
        "move_low": move_low,
        "move_high": move_high,
        "prob_low": prob_low,
        "prob_high": prob_high,
        "prob_mid": prob_mid,
        "strength": strength,
        "strength_color": strength_color,
        "action": action,
        "action_color": action_color,
        "reason_line1": reason_line1,
        "reason_line2": reason_line2,
        "mcx_price": mcx_price,
        "expected_high": expected_high,
        "expected_low": expected_low,
        "support": support,
        "resistance": resistance,
        "risk_alert": risk_alert,
        "signals": signals,
        "conclusion": conclusion,
    }



def get_multi_timeframe_forecast(
    prediction: dict,
    data: dict = None,
    macro_result: dict = None,
    market_regime_result: dict = None,
    inst_name: str = "MCX Silver",
    inst_unit: str = "Rs/kg",
) -> list:
    """
    Wrapper: delegates to horizon_engine.get_multi_horizon_forecast.
    Returns a list of 3 fully independent horizon dicts (24H, 1W, 1M).
    Each horizon is derived from its own set of indicators and weightings.
    A bearish 24H NEVER automatically forces a bearish 1W or 1M.
    """
    inst_price = prediction.get("mcx_price", 0)
    raw_data = data or {}

    horizons = get_multi_horizon_forecast(
        data=raw_data,
        inst_price=inst_price,
        inst_name=inst_name,
        inst_unit=inst_unit,
        macro_result=macro_result,
        market_regime_result=market_regime_result,
    )

    # Adapt to legacy dict shape used by app.py for backward compat
    adapted = []
    for h in horizons:
        bias = h["bias"]
        if bias == "Bullish":
            tf_direction = "UP"
            tf_color = "#00cc44"
        elif bias == "Bearish":
            tf_direction = "DOWN"
            tf_color = "#cc0000"
        else:
            tf_direction = "SIDEWAYS"
            tf_color = "#888888"

        prob = h["prob_split"]
        adapted.append({
            "timeframe": h["horizon"],
            "direction": tf_direction,
            "color": tf_color,
            "bias": bias,
            "move_low": h["move_low_pct"],
            "move_high": h["move_high_pct"],
            "target_low": h["expected_low"],
            "target_high": h["expected_high"],
            "probability": prob["up"] if bias == "Bullish" else (prob["down"] if bias == "Bearish" else prob["sideways"]),
            "prob_split": prob,
            "confidence_score": h["confidence_score"],
            "no_trade_flag": h["no_trade_flag"],
            "no_trade_reason": h["no_trade_reason"],
            "contributing_factors": h["contributing_factors"],
            "invalidation_level": h["invalidation_level"],
            "current_regime": h["current_regime"],
            "macro_regime": h["macro_regime"],
            "conflict_note": h.get("conflict_note", ""),
            "macro_note": h.get("macro_note", ""),
        })
    return adapted
