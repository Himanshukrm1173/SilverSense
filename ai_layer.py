import os
import math
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

_cached_ai_plan = {}

def extract_field(text, field):
    for line in text.split('\n'):
        if line.strip().lower().startswith(field.lower()):
            return line.strip()[len(field):].strip()
    return "N/A"

def get_mock_trade_plan(scored_data, inst_price=None, inst_name="MCX Silver", inst_unit="₹/kg"):
    """Fallback mock plan if API fails or key is missing."""
    data = scored_data["enriched_data"]
    score = scored_data["total_score"]
    interpretation = scored_data["interpretation"]
    
    mcx = data.get("MCX_SILVER", {})
    if inst_price is not None and not (isinstance(inst_price, float) and math.isnan(inst_price)):
        price = inst_price
    else:
        price = mcx.get("current_price_inr", 0) if mcx else 0
        
    def fmt(p):
        if inst_unit == "₹/kg":
            return f"₹{p:,.0f}"
        else:
            return f"{p:,.2f} {inst_unit}"
            
    entry_off = price * 0.001
    t1_off = price * 0.0025
    t2_off = price * 0.005
    sl_off = price * 0.002
    
    if "BUY" in interpretation:
        direction = "BUY"
        entry = f"{fmt(price - entry_off)} - {fmt(price)}"
        t1 = f"{fmt(price + t1_off)}"
        t2 = f"{fmt(price + t2_off)}"
        sl = f"{fmt(price - sl_off)}"
        reasoning = "Technicals show strong bullish momentum. Buy on minor dips."
        risk = "Sudden spike in Dollar Index or US Yields."
        confidence = "High" if score >= 60 else "Medium"
    elif "SELL" in interpretation:
        direction = "SELL"
        entry = f"{fmt(price)} - {fmt(price + entry_off)}"
        t1 = f"{fmt(price - t1_off)}"
        t2 = f"{fmt(price - t2_off)}"
        sl = f"{fmt(price + sl_off)}"
        reasoning = "Technicals indicate weakness and bearish crossover. Sell on rallies."
        risk = "Unexpected drop in Dollar Index or geopolitical tensions."
        confidence = "High" if score <= -60 else "Medium"
    else:
        direction = "WAIT"
        entry = "N/A"
        t1 = "N/A"
        t2 = "N/A"
        sl = "N/A"
        reasoning = "Market is in a consolidated or neutral phase. Wait for a clear breakout."
        risk = "Whipsaw movements in a tight range."
        confidence = "Low"

    return f"""
1. **Market Summary:** {reasoning}
2. **Trade Plan for {inst_name}:**
   - **Direction:** {direction}
   - **Entry Range:** {entry}
   - **Target 1:** {t1} | **Target 2:** {t2}
   - **Stop Loss:** {sl}
3. **Key risk to watch today:** {risk}
4. **Confidence level:** {confidence}
""".strip()

def generate_trade_plan(scored_data, inst_price=None, inst_name="MCX Silver", inst_unit="₹/kg"):
    """Connects to Gemini API to generate trade plan. Falls back to mock if API key missing."""
    if not GEMINI_API_KEY:
        return get_mock_trade_plan(scored_data, inst_price, inst_name, inst_unit)
    
    data = scored_data["enriched_data"]
    score = scored_data["total_score"]
    interpretation = scored_data["interpretation"]
    
    mcx = data.get("MCX_SILVER", {})
    if inst_price is not None and not (isinstance(inst_price, float) and math.isnan(inst_price)):
        price = inst_price
    else:
        price = mcx.get("current_price_inr", 0) if mcx else 0
        
    xag = data.get("XAGUSD") or {}
    us10y = data.get("US10Y") or {}
    dxy = data.get("DXY") or {}
    usdinr = data.get("USDINR") or {}

    # SMA Comparison (apples to apples: use spot for signal)
    spot_price = xag.get("current_price", 0)
    sma20 = xag.get("sma20", 0)
    sma_signal = "Above 20 SMA" if (spot_price and sma20 and spot_price > sma20) else "Below 20 SMA"

    payload = {
        "instrument": inst_name,
        "score": score,
        "direction": interpretation,
        "rsi": xag.get("rsi", "N/A"),
        "sma_signal": sma_signal,
        "dxy": f"{dxy.get('current_dxy', 'N/A')} ({'Rising' if dxy.get('rising') else 'Falling'})",
        "us10y": f"{us10y.get('current_yield', 'N/A')} ({'Rising' if us10y.get('rising') else 'Falling'})",
        "usd_inr": f"{usdinr.get('current_rate', 'N/A')} ({'Weakening' if usdinr.get('weakening') else 'Strengthening'})",
        "oi_signal": mcx.get("oi_signal_name", "N/A"),
        "current_price": f"{price} {inst_unit}",
        "spot_usd": f"{xag.get('current_price', 'N/A')} ({xag.get('change_pct', 'N/A')}%)"
    }

    prompt = f"""You are a professional silver market analyst for Indian retail traders. Given the following live market data, write a concise trade plan. Format your response EXACTLY as:

Market Summary: [one sentence]
Direction: [BUY / SELL / WAIT]
Entry Range: [price range in INR]
Target 1: [price in INR]
Target 2: [price in INR]
Stop Loss: [price in INR]
Key Risk Today: [one sentence]
Confidence Level: [Low / Medium / High]

Be specific. Use actual price levels based on the current_price provided. No generic advice. No disclaimers. No extra text outside this format.

Live Market Data:
{payload}
"""

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        formatted = f"""
1. **Market Summary:** {extract_field(text, 'Market Summary:')}
2. **Trade Plan for {inst_name}:**
   - **Direction:** {extract_field(text, 'Direction:')}
   - **Entry Range:** {extract_field(text, 'Entry Range:')}
   - **Target 1:** {extract_field(text, 'Target 1:')} | **Target 2:** {extract_field(text, 'Target 2:')}
   - **Stop Loss:** {extract_field(text, 'Stop Loss:')}
3. **Key risk to watch today:** {extract_field(text, 'Key Risk Today:')}
4. **Confidence level:** {extract_field(text, 'Confidence Level:')}
"""
        _cached_ai_plan[inst_name] = formatted.strip()
        return formatted.strip()
    except Exception as e:
        if inst_name in _cached_ai_plan:
            return _cached_ai_plan[inst_name] + "\n\n*(Using cached analysis — live refresh failed)*"
        return get_mock_trade_plan(scored_data, inst_price, inst_name, inst_unit)
