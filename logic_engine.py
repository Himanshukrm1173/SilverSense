import pandas as pd
import numpy as np

def calculate_rsi(series, period=14):
    """Calculate RSI from a pandas Series."""
    delta = series.diff()
    # Separate gains and losses
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)

    # Calculate exponential moving average for gains and losses
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    # Calculate RS
    rs = avg_gain / avg_loss
    # Calculate RSI
    rsi = 100 - (100 / (1 + rs))
    
    return rsi.iloc[-1] if not rsi.empty and not pd.isna(rsi.iloc[-1]) else 50.0

def calculate_sma(series, period):
    """Calculate Simple Moving Average."""
    sma = series.rolling(window=period, min_periods=1).mean()
    return sma.iloc[-1] if not sma.empty and not pd.isna(sma.iloc[-1]) else 0.0

def get_oi_signal(price_current, price_prev, oi_current, oi_prev):
    """Determine Open Interest Signal logic."""
    price_up = price_current > price_prev
    oi_up = oi_current > oi_prev
    
    if price_up and oi_up:
        return "Long Buildup", 20
    elif not price_up and oi_up:
        return "Short Buildup", -20
    elif price_up and not oi_up:
        return "Short Covering", 10
    elif not price_up and not oi_up:
        return "Long Unwinding", -10
    return "Neutral", 0

def process_data_and_score(data):
    """Process all raw data and calculate the 100-point score."""
    breakdown = {}
    total_score = 0
    
    # 1. RSI and SMA on XAGUSD
    xag_data = data.get("XAGUSD")
    if xag_data and xag_data.get("history") is not None:
        hist = xag_data["history"]
        close_series = hist["Close"]
        
        rsi_val = calculate_rsi(close_series, 14)
        sma20 = calculate_sma(close_series, 20)
        sma50 = calculate_sma(close_series, 50)
        current_price = xag_data["current_price"]
        
        # RSI Score
        if rsi_val < 30:
            breakdown['RSI'] = {"score": 20, "value": f"{rsi_val:.2f}", "desc": "Oversold"}
            total_score += 20
        elif rsi_val > 70:
            breakdown['RSI'] = {"score": -20, "value": f"{rsi_val:.2f}", "desc": "Overbought"}
            total_score -= 20
        else:
            breakdown['RSI'] = {"score": 0, "value": f"{rsi_val:.2f}", "desc": "Neutral"}
            
        # SMA Score
        if current_price > sma20 and sma20 > sma50:
            breakdown['SMA'] = {"score": 20, "value": "Price > 20 > 50", "desc": "Strong Uptrend"}
            total_score += 20
        elif current_price < sma20 and sma20 < sma50:
            breakdown['SMA'] = {"score": -20, "value": "Price < 20 < 50", "desc": "Strong Downtrend"}
            total_score -= 20
        else:
            breakdown['SMA'] = {"score": 0, "value": "Mixed", "desc": "Neutral Trend"}
            
        xag_data["rsi"] = rsi_val
        xag_data["sma20"] = sma20
        xag_data["sma50"] = sma50
    else:
        breakdown['RSI'] = {"score": 0, "value": "N/A", "desc": "Data Unavailable"}
        breakdown['SMA'] = {"score": 0, "value": "N/A", "desc": "Data Unavailable"}
        
    # 2. DXY Signal
    dxy_data = data.get("DXY")
    if dxy_data:
        if not dxy_data["rising"]:
            breakdown['DXY'] = {"score": 20, "value": f"{dxy_data['current_dxy']:.2f}", "desc": "Falling (Bullish)"}
            total_score += 20
        else:
            breakdown['DXY'] = {"score": -20, "value": f"{dxy_data['current_dxy']:.2f}", "desc": "Rising (Bearish)"}
            total_score -= 20
    else:
        breakdown['DXY'] = {"score": 0, "value": "N/A", "desc": "Data Unavailable"}
        
    # 3. Bond Yield Signal
    us10y_data = data.get("US10Y")
    if us10y_data:
        if not us10y_data["rising"]:
            breakdown['US10Y'] = {"score": 20, "value": f"{us10y_data['current_yield']:.3f}%", "desc": "Falling (Bullish)"}
            total_score += 20
        else:
            breakdown['US10Y'] = {"score": -20, "value": f"{us10y_data['current_yield']:.3f}%", "desc": "Rising (Bearish)"}
            total_score -= 20
    else:
        breakdown['US10Y'] = {"score": 0, "value": "N/A", "desc": "Data Unavailable"}
        
    # 4. OI Signal (MCX/Tata Silver Standard proxy)
    mcx_data = data.get("MCX_SILVER")
    if mcx_data:
        signal_name, oi_score = get_oi_signal(
            mcx_data["current_price_inr"], 
            mcx_data["prev_price_inr"],
            mcx_data["open_interest_current"],
            mcx_data["open_interest_prev"]
        )
        breakdown['OI'] = {"score": oi_score, "value": signal_name, "desc": "Futures Signal"}
        total_score += oi_score
        mcx_data["oi_signal_name"] = signal_name
    else:
        breakdown['OI'] = {"score": 0, "value": "N/A", "desc": "Data Unavailable"}
        
    # Score interpretation
    if total_score >= 60:
        interpretation = "STRONG BUY"
    elif total_score >= 20:
        interpretation = "MILD BUY"
    elif total_score >= -19:
        interpretation = "NEUTRAL"
    elif total_score >= -59:
        interpretation = "MILD SELL"
    else:
        interpretation = "STRONG SELL"
        
    return {
        "total_score": total_score,
        "interpretation": interpretation,
        "breakdown": breakdown,
        "enriched_data": data
    }
