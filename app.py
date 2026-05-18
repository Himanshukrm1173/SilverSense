import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, time as dt_time
import pytz
import math
import random
from streamlit_autorefresh import st_autorefresh

from data_fetcher import (
    fetch_all_data, fetch_tata_data, fetch_bees_data,
    fetch_intraday_data, fetch_dynamic_chart, CHART_INTERVALS
)
from logic_engine import process_data_and_score
from ai_layer import generate_trade_plan
from prediction_engine import get_prediction, get_multi_timeframe_forecast

# ─────────────────────────────────────────────
#  PAGE CONFIG & PWA
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="SilverSense",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown('''
    <link rel="manifest" href="/app/static/manifest.json">
    <meta name="theme-color" content="#0f0f0f">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="SilverSense">
    <script>
      if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/app/static/sw.js');
      }
    </script>
    <div id="install-banner" style="display:none; background:#222; color:#fff; padding:10px; text-align:center; font-size:14px;">
        Install SilverSense — Add to Home Screen  <a href="#" id="install-btn" style="color:#00cc44; margin:0 10px; text-decoration:none;">[Install]</a> <a href="#" id="dismiss-btn" style="color:#ccc; text-decoration:none;">[x]</a>
    </div>
    <script>
      let deferredPrompt;
      window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault();
        deferredPrompt = e;
        document.getElementById('install-banner').style.display = 'block';
      });
      document.getElementById('install-btn').addEventListener('click', (e) => {
        e.preventDefault();
        document.getElementById('install-banner').style.display = 'none';
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then((choiceResult) => {
          deferredPrompt = null;
        });
      });
      document.getElementById('dismiss-btn').addEventListener('click', (e) => {
        e.preventDefault();
        document.getElementById('install-banner').style.display = 'none';
      });
    </script>
''', unsafe_allow_html=True)

st_autorefresh(interval=60000, key="data_refresh")
IST = pytz.timezone('Asia/Kolkata')

# ─────────────────────────────────────────────
#  STATE INIT (Market Edge & Mindset)
# ─────────────────────────────────────────────
if 'market_edge' not in st.session_state:
    st.session_state.market_edge = 40
    st.session_state.market_edge += 3
    now = datetime.now(IST)
    if now.time() < dt_time(9, 15):
        st.session_state.market_edge += 5
    st.session_state.market_edge = min(100, max(0, st.session_state.market_edge))

if 'mindset_tip' not in st.session_state:
    tips = [
        "After 2 losing trades in a row, consider stepping back instead of increasing size.",
        "Plan your risk before you look at the profit potential.",
        "Skipping a bad trade is also a win.",
        "Position size matters more than entry timing.",
        "Volatility is normal. Panic is optional.",
        "Your edge comes from consistency, not one big trade."
    ]
    st.session_state.mindset_tip = random.choice(tips)

# ─────────────────────────────────────────────
#  CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown('''
<style>
    /* ── Theme-adaptive tokens ── */
    :root {
        --ss-card-bg: rgba(255,255,255,0.04);
        --ss-border: rgba(255,255,255,0.10);
        --ss-muted: rgba(255,255,255,0.55);
    }

    .main-title { font-size:28px; font-weight:700; color:#C0C0C0; margin-bottom:0; }
    .sub-title { font-size:14px; color:var(--ss-muted); margin-top:0; }

    .card {
        padding:16px;
        border-radius:10px;
        background: var(--ss-card-bg);
        border: 1px solid var(--ss-border);
        margin-bottom:10px;
    }

    .footer {
        padding:30px 20px;
        margin-top:40px;
        border-top: 1px solid var(--ss-border);
        color: var(--ss-muted);
        font-size:12px;
        line-height:1.8;
    }
    .footer a { color: var(--ss-muted); }

    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 8px 16px; border-radius: 6px 6px 0 0; }

    .tooltip { position: relative; display: inline-block; border-bottom: 1px dotted currentColor; cursor: help; }
    .tooltip .tooltiptext {
        visibility: hidden;
        width: 200px;
        background-color: var(--background-color, #333);
        color: var(--text-color, #fff);
        border: 1px solid var(--ss-border);
        text-align: center;
        border-radius: 6px;
        padding: 5px;
        position: absolute;
        z-index: 1;
        bottom: 125%;
        left: 50%;
        margin-left: -100px;
        opacity: 0;
        transition: opacity 0.3s;
        font-size: 12px;
        font-weight: normal;
    }
    .tooltip:hover .tooltiptext { visibility: visible; opacity: 1; }

    .html-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }
    .html-table th, .html-table td { border: 1px solid var(--ss-border); padding: 8px; text-align: left; }
    .html-table th { background-color: var(--ss-card-bg); }

    /* ── Compact Recommendation badge ── */
    .rec-card {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 14px 18px;
        border-radius: 10px;
        border: 1px solid var(--ss-border);
        background: var(--ss-card-bg);
    }
    .rec-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 80px;
        padding: 6px 14px;
        border-radius: 6px;
        font-size: 18px;
        font-weight: 800;
        letter-spacing: 1px;
        flex-shrink: 0;
    }
    .rec-text { line-height: 1.5; }
    .rec-text .rec-line1 { font-size: 14px; font-weight: 600; }
    .rec-text .rec-line2 { font-size: 13px; opacity: 0.75; margin-top: 2px; }

    /* ── Holiday Banner ── */
    .holiday-banner {
        background: #332b00;
        border: 1px solid #4d4100;
        color: #d1d1d1;
        padding: 10px 16px;
        border-radius: 6px;
        margin-bottom: 20px;
        font-size: 14px;
        text-align: left;
    }

    /* ── Market Status Badge ── */
    .status-badge {
        display: inline-flex;
        align-items: center;
        background: var(--ss-card-bg);
        border: 1px solid var(--ss-border);
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 12px;
        color: var(--ss-muted);
        font-weight: 600;
        margin-top: 5px;
    }
    .live-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        background-color: #10B981;
        border-radius: 50%;
        margin-right: 6px;
        animation: pulse-dot 2s infinite ease-in-out;
    }
    @keyframes pulse-dot {
        0% { opacity: 0.4; }
        50% { opacity: 1; }
        100% { opacity: 0.4; }
    }
</style>
''', unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def check_market_holiday():
    """Checks if today is a weekend or an Indian market holiday."""
    now_ist = datetime.now(IST)
    date_str = now_ist.strftime('%Y-%m-%d')
    day_name = now_ist.strftime('%A')

    # Testing Override: Hardcode to True for verification as per requirements
    # Change to False to use real logic
    TESTING_OVERRIDE = False 
    
    if TESTING_OVERRIDE:
        return True, "Weekend (Testing Mode)"

    # Weekends
    if now_ist.weekday() >= 5:
        return True, "Weekend"

    # Indian Market Holidays (2024-2025 samples)
    holidays = {
        "2024-11-01": "Diwali-Laxmi Pujan",
        "2024-11-15": "Guru Nanak Jayanti",
        "2024-12-25": "Christmas",
        "2025-01-26": "Republic Day",
        "2025-03-14": "Holi",
        "2025-03-31": "Id-ul-Fitr",
        "2025-04-10": "Mahavir Jayanti",
        "2025-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
        "2025-04-18": "Good Friday",
        "2025-05-01": "Maharashtra Day"
    }

    if date_str in holidays:
        return True, holidays[date_str]

    return False, ""

def get_market_timing_status(inst_name):
    """Calculates time remaining until open/close and returns a styled HTML badge."""
    now_ist = datetime.now(IST)
    current_time = now_ist.time()
    
    if "MCX" in inst_name:
        open_time = dt_time(9, 0)
        close_time = dt_time(23, 30)
    else:
        open_time = dt_time(9, 15)
        close_time = dt_time(15, 30)
        
    is_live = open_time <= current_time <= close_time
    
    full_closed, _ = check_market_holiday()
    if full_closed:
        is_live = False
        
    def time_diff_mins(t1, t2):
        dt1 = datetime.combine(now_ist.date(), t1)
        dt2 = datetime.combine(now_ist.date(), t2)
        return int((dt2 - dt1).total_seconds() / 60)
        
    if is_live:
        diff_mins = time_diff_mins(current_time, close_time)
        hours = diff_mins // 60
        mins = diff_mins % 60
        time_str = f"Closes in {hours}h {mins}m" if hours > 0 else f"Closes in {mins}m"
        return f"<div class='status-badge'><span class='live-dot'></span>LIVE &nbsp;&middot;&nbsp; {time_str}</div>"
    else:
        if current_time < open_time and not full_closed:
            diff_mins = time_diff_mins(current_time, open_time)
            hours = diff_mins // 60
            mins = diff_mins % 60
            time_str = f"Opens in {hours}h {mins}m" if hours > 0 else f"Opens in {mins}m"
        else:
            time_str = "Opens next session"
            
        return f"<div class='status-badge'>CLOSED &nbsp;&middot;&nbsp; {time_str}</div>"

def safe_val(v, fmt="{:.2f}", unit="", fallback="--"):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return fallback
    try:
        return fmt.format(v) + unit
    except:
        return fallback

# ─────────────────────────────────────────────
#  SIDEBAR NAVIGATION
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("# SilverSense")
    st.markdown("<p style='color:#888; font-size:13px; margin-top:-10px;'>Silver Price Predictor & Analyzer</p>", unsafe_allow_html=True)
    st.divider()

    instrument = st.selectbox(
        "Select ETF",
        ["Silver (MCX)", "Tata Silver (TATSILV)", "Silver Bees (ETF)"],
        index=0
    )

    st.divider()
    st.markdown("##### Settings")
    chart_timeframe = st.selectbox("Chart Timeframe", list(CHART_INTERVALS.keys()), index=4)

    st.divider()
    st.markdown("<p style='color:#555; font-size:11px;'>Auto-refreshes every 60 seconds<br>Data via Yahoo Finance</p>", unsafe_allow_html=True)

    if st.button("Refresh All Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ─────────────────────────────────────────────
#  DATA LOADING (cached)
# ─────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_mcx_data():
    raw = fetch_all_data()
    scored = process_data_and_score(raw)
    mcx = raw.get("MCX_SILVER", {})
    mcx_price = mcx.get("current_price_inr")
    plan = generate_trade_plan(scored, inst_price=mcx_price, inst_name="Silver (MCX)", inst_unit="Rs/kg")
    pred = get_prediction(scored["enriched_data"], inst_price=mcx_price, inst_unit="Rs/kg", inst_name="Silver (MCX)")
    ft = datetime.now(IST)
    xag_data = raw.get("XAGUSD") or {}
    xag_hist = xag_data.get("history")
    rsi_series = None
    if xag_hist is not None and not xag_hist.empty:
        c = xag_hist["Close"]
        d = c.diff()
        g = (d.where(d > 0, 0)).fillna(0)
        l = (-d.where(d < 0, 0)).fillna(0)
        ag = g.rolling(window=14, min_periods=14).mean()
        al = l.rolling(window=14, min_periods=14).mean()
        rsi_series = 100 - (100 / (1 + ag / al))
    return scored, plan, rsi_series, pred, ft

@st.cache_data(ttl=60)
def load_tata_data():
    raw = fetch_tata_data()
    scored = process_data_and_score(raw)
    tata = raw.get("TATA_SILVER")
    tata_price = tata["current_price"] if tata else None
    plan = generate_trade_plan(scored, inst_price=tata_price, inst_name="Tata Silver", inst_unit="Rs/unit")
    pred = get_prediction(scored["enriched_data"], inst_price=tata_price, inst_unit="Rs/unit", inst_name="Tata Silver")
    ft = datetime.now(IST)
    return scored, plan, pred, ft, tata

@st.cache_data(ttl=60)
def load_bees_data():
    raw = fetch_bees_data()
    scored = process_data_and_score(raw)
    bees = raw.get("SILVERBEES")
    bees_price = bees["current_price"] if bees else None
    plan = generate_trade_plan(scored, inst_price=bees_price, inst_name="Silver Bees (ETF)", inst_unit="Rs/unit")
    pred = get_prediction(scored["enriched_data"], inst_price=bees_price, inst_unit="Rs/unit", inst_name="Silver Bees (ETF)")
    ft = datetime.now(IST)
    return scored, plan, pred, ft, bees

@st.cache_data(ttl=60)
def load_chart(ticker, tf):
    return fetch_dynamic_chart(ticker, tf)

# ─────────────────────────────────────────────
#  DETERMINE INSTRUMENT
# ─────────────────────────────────────────────
if "MCX" in instrument:
    inst_name = "Silver (MCX)"
    inst_unit = "Rs/kg"
    chart_ticker = "SI=F"
    with st.spinner("Fetching Silver MCX data..."):
        scored_data, ai_plan, rsi_series, prediction, fetch_time = load_mcx_data()
    inst_data = None
elif "Tata" in instrument:
    inst_name = "Tata Silver"
    inst_unit = "Rs/unit"
    chart_ticker = "TATSILV.NS"
    with st.spinner("Fetching Tata Silver data..."):
        scored_data, ai_plan, prediction, fetch_time, inst_data = load_tata_data()
    rsi_series = None
else:
    inst_name = "Silver Bees (ETF)"
    inst_unit = "Rs/unit"
    chart_ticker = "SILVERBEES.NS"
    with st.spinner("Fetching Silver Bees data..."):
        scored_data, ai_plan, prediction, fetch_time, inst_data = load_bees_data()
    rsi_series = None

data = scored_data["enriched_data"]
score = scored_data["total_score"]
interpretation = scored_data["interpretation"].replace('🟢','').replace('🟡','').replace('⚪','').replace('🟠','').replace('🔴','').strip()
breakdown = scored_data["breakdown"]
now_ist = datetime.now(IST)
minutes_since = (now_ist - fetch_time).total_seconds() / 60

# ─────────────────────────────────────────────
#  HEADER & STALE WARNING
# ─────────────────────────────────────────────
if minutes_since > 10:
    st.markdown(f"<div style='background:#b35900; color:#fff; padding:10px; text-align:center; font-weight:bold; border-radius:4px; margin-bottom:15px;'>Data may be stale — last updated {int(minutes_since)} minutes ago.</div>", unsafe_allow_html=True)

hc1, hc2 = st.columns([3, 1])
with hc1:
    st.markdown(f"<p class='main-title'>SilverSense — {inst_name}</p>", unsafe_allow_html=True)
    st.markdown(f"<p class='sub-title'>Real-time analysis, predictions & trade signals for your ETF</p>", unsafe_allow_html=True)
with hc2:
    st.markdown(f"<div style='text-align: right; margin-bottom: 5px;'><span style='color: var(--ss-muted); font-size: 13px; font-weight: bold;'>Last Updated:</span> <span style='color: #ccc; font-size: 13px;'>{now_ist.strftime('%I:%M %p IST')}</span></div>", unsafe_allow_html=True)
    status_html = get_market_timing_status(inst_name)
    st.markdown(f"<div style='text-align: right;'>{status_html}</div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  MARKET HOLIDAY BANNER
# ─────────────────────────────────────────────
is_closed, reason = check_market_holiday()
if is_closed:
    st.markdown(
        f"""<div class='holiday-banner'>
            Market is closed today ({reason}). Showing last closing prices.
        </div>""",
        unsafe_allow_html=True
    )

# ─────────────────────────────────────────────
#  TABS
# ─────────────────────────────────────────────
tab_dash, tab_pred, tab_forecast = st.tabs(["Dashboard", "Live Prediction", "Forecast & Chart"])

# ═══════════════════════════════════════════════
#  TAB 1 — DASHBOARD
# ═══════════════════════════════════════════════
with tab_dash:
    color = "gray"
    if "STRONG BUY" in interpretation: color = "#00cc44"
    elif "MILD BUY" in interpretation: color = "#88cc00"
    elif "MILD SELL" in interpretation: color = "orange"
    elif "STRONG SELL" in interpretation: color = "#cc0000"

    st.markdown(
        f"<div style='padding:12px 20px; border-radius:8px; background:#1a1a2e; border:2px solid {color}; display:inline-block;'>"
        f"<span style='font-size:22px; font-weight:bold; color:{color};'>{score}/100</span> "
        f"<span style='font-size:16px; color:#ccc;'>— {interpretation}</span></div>",
        unsafe_allow_html=True
    )
    st.markdown("")

    # KPI Cards
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    xag = data.get("XAGUSD") or {}
    dxy = data.get("DXY") or {}
    us10y = data.get("US10Y") or {}
    usdinr = data.get("USDINR") or {}
    mcx = data.get("MCX_SILVER") or {}

    with kpi1:
        st.metric("Silver Spot (USD)", safe_val(xag.get("current_price"), "${:.2f}"), safe_val(xag.get("change_pct"), "{:.2f}%"))
    with kpi2:
        # DXY rising = bearish for silver → always use delta_color="inverse"
        dxy_rising = dxy.get("rising", False)
        st.metric(
            "DXY",
            safe_val(dxy.get('current_dxy'), "{:.2f}"),
            f"{'↑ Rising — Bearish' if dxy_rising else '↓ Falling — Bullish'} for Silver",
            delta_color="inverse"
        )
    with kpi3:
        # US 10Y rising = bearish for silver → always use delta_color="inverse"
        y_rising = us10y.get("rising", False)
        st.metric(
            "US 10Y Yield",
            safe_val(us10y.get('current_yield'), "{:.3f}%"),
            f"{'↑ Rising — Bearish' if y_rising else '↓ Falling — Bullish'} for Silver",
            delta_color="inverse"
        )
    with kpi4:
        st.metric("USD/INR", safe_val(usdinr.get('current_rate'), "Rs {:.2f}"),
                  "Weakening" if usdinr.get("weakening") else "Strengthening")
    with kpi5:
        if inst_data:
            st.metric(inst_name, safe_val(inst_data.get('current_price'), "{:,.2f} " + inst_unit),
                      safe_val(inst_data.get('change_pct'), "{:.2f}%"))
        else:
            mcx_val = mcx.get("current_price_inr")
            mcx_prev = mcx.get("prev_price_inr")
            diff = (mcx_val - mcx_prev) if (mcx_val is not None and mcx_prev is not None and not math.isnan(mcx_val) and not math.isnan(mcx_prev)) else None
            st.metric("MCX Silver", safe_val(mcx_val, "Rs {:,.0f}/kg"), safe_val(diff, "Rs {:,.0f}"))

    # MARKET EDGE
    edge = st.session_state.market_edge
    if edge <= 30: edge_msg = "You are just getting started. Markets reward consistency."
    elif edge <= 60: edge_msg = "You are building discipline. Keep showing up."
    elif edge <= 85: edge_msg = "Strong edge. Traders like you outperform the crowd."
    else: edge_msg = "Elite discipline. You track silver like a professional."
    
    st.markdown(f"<div class='card' style='margin-top:15px;'>"
                f"<span style='color:#ccc; font-size:14px;'>Market Edge: <strong>{edge}</strong></span><br>"
                f"<span style='color:#fff; font-size:16px;'>{edge_msg}</span></div>", unsafe_allow_html=True)
    
    # MINDSET TIP
    st.markdown(f"<div style='border:1px solid #333; padding:10px; border-radius:6px; color:#aaa; font-size:12px; margin-bottom:20px;'>"
                f"{st.session_state.mindset_tip}</div>", unsafe_allow_html=True)

    st.divider()

    # Charts
    col_l, col_r = st.columns(2)
    xag_hist = xag.get("history")
    if xag_hist is not None and not xag_hist.empty:
        hist_30d = xag_hist.tail(30)
        with col_l:
            st.markdown(f"#### {inst_name} — Price & SMA (30-day)")
            fig_p = go.Figure()
            fig_p.add_trace(go.Scatter(x=hist_30d.index, y=hist_30d['Close'], mode='lines', name='Price', line=dict(color='#C0C0C0')))
            sma20 = xag_hist['Close'].rolling(window=20).mean().tail(30)
            sma50 = xag_hist['Close'].rolling(window=50).mean().tail(30)
            fig_p.add_trace(go.Scatter(x=hist_30d.index, y=sma20, mode='lines', name='20 SMA', line=dict(dash='dash', color='#00cc44')))
            fig_p.add_trace(go.Scatter(x=hist_30d.index, y=sma50, mode='lines', name='50 SMA', line=dict(dash='dot', color='#cc6600')))
            fig_p.update_layout(height=380, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_p, use_container_width=True)
        with col_r:
            st.markdown("#### RSI Indicator (14-day)")
            if rsi_series is not None and not rsi_series.empty:
                rsi_30d = rsi_series.tail(30)
                fig_r = go.Figure()
                fig_r.add_trace(go.Scatter(x=rsi_30d.index, y=rsi_30d, mode='lines', name='RSI', line=dict(color='#C0C0C0')))
                fig_r.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Overbought")
                fig_r.add_hline(y=30, line_dash="dash", line_color="green", annotation_text="Oversold")
                fig_r.update_layout(height=380, yaxis_range=[0, 100], margin=dict(l=0, r=0, t=30, b=0))
                st.plotly_chart(fig_r, use_container_width=True)
    else:
        st.warning("Price history unavailable.")

    st.divider()

    # OI Signal
    st.markdown("#### Open Interest Signal")
    oi_signal = mcx.get("oi_signal_name", "N/A").replace('✅','').replace('❌','').replace('⚪','').strip()
    oi_c = {"Long Buildup": "#00cc44", "Short Buildup": "#cc0000", "Short Covering": "#88cc00", "Long Unwinding": "orange"}.get(oi_signal, "#555")
    st.markdown(f"<div style='padding:14px; border-radius:8px; background:#1a1a2e; border-left:5px solid {oi_c};'>"
                f"<strong style='color:#eee;'>Signal:</strong> <span style='color:{oi_c}; font-weight:bold;'>{oi_signal}</span></div>",
                unsafe_allow_html=True)

    st.divider()
    st.markdown("#### AI Trade Plan")
    st.info(ai_plan)
    st.markdown("<p style='font-size:11px; color:#666; margin-top:-10px;'>Analysis generated by AI — verify before trading</p>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════
#  TAB 2 — LIVE PREDICTION
# ═══════════════════════════════════════════════
with tab_pred:
    p = prediction
    is_expired = minutes_since > 30

    st.markdown(f"### Live Prediction — {inst_name}")

    pc1, pc2, pc3 = st.columns([2, 2, 1])
    with pc1:
        st.markdown(f"**Current Time:** {now_ist.strftime('%I:%M:%S %p IST')}")
        if inst_data:
            st.markdown(f"**{inst_name} Price:** {safe_val(inst_data.get('current_price'), '{:,.2f}')} {inst_unit}")
        else:
            st.markdown(f"**{inst_name} Price:** {safe_val(p.get('mcx_price'), 'Rs {:,.0f}/kg')}")
    with pc2:
        d_color = "gray" if is_expired else p['direction_color']
        d_text = "Signal expired — refresh required" if is_expired else p['direction']
        st.markdown(
            f"<div style='text-align:center; padding:18px; border-radius:10px; background:{d_color}15; border:2px solid {d_color};'>"
            f"<span style='font-size:24px; font-weight:bold; color:{d_color};'>{d_text}</span><br>"
            f"<span style='font-size:14px; color:#ccc;'>Score: {p['total_score']}/5</span></div>",
            unsafe_allow_html=True
        )
    with pc3:
        st.markdown(
            f"<div style='text-align:center; padding:18px; border-radius:10px; background:#1a1a2e; border:2px solid {p['strength_color']};'>"
            f"<span style='font-size:14px; color:#aaa;'>Strength</span><br>"
            f"<span style='font-size:24px; font-weight:bold; color:{p['strength_color']};'>{p['strength']}</span></div>",
            unsafe_allow_html=True
        )

    st.markdown("")
    em1, em2 = st.columns(2)
    with em1:
        st.markdown(f"**Expected Move:** {p['move_low']:.1f}% – {p['move_high']:.1f}%")
        pot_move = p.get('mcx_price', 0) * ((p['move_low'] + p['move_high']) / 2 / 100)
        if pot_move and not math.isnan(pot_move):
            st.markdown(f"<span style='color:#888; font-size:13px;'>Potential move if signal holds: Rs {pot_move:,.0f} per {inst_unit.split('/')[-1]}</span>", unsafe_allow_html=True)
    with em2:
        st.markdown(f"**Probability:** {p['prob_low']}% – {p['prob_high']}%")
        st.progress(p['prob_mid'] / 100)

    st.divider()
    st.markdown("#### Today's Levels")
    lv1, lv2, lv3 = st.columns(3)
    
    fmt = "{:,.0f}" if "MCX" in inst_name else "{:,.2f}"
    
    with lv1:
        st.metric("Expected Range", f"{safe_val(p.get('expected_low'), fmt)} – {safe_val(p.get('expected_high'), fmt)} {inst_unit}")
    with lv2:
        st.metric("Support", f"{safe_val(p.get('support'), fmt)} {inst_unit}")
    with lv3:
        st.metric("Resistance", f"{safe_val(p.get('resistance'), fmt)} {inst_unit}")

    st.divider()
    st.markdown("#### Recommendation")
    badge_bg = {"BUY": "#00aa33", "SELL": "#cc2200", "WAIT": "#555566"}.get(p['action'], "#555566")
    clean_reason1 = p['reason_line1'].replace('✅', '').replace('❌', '').strip()
    st.markdown(
        f"""<div class='rec-card'>
            <span class='rec-badge' style='background:{badge_bg}; color:#fff;'>{p['action']}</span>
            <div class='rec-text'>
                <div class='rec-line1'>{clean_reason1}</div>
                <div class='rec-line2'>{p['reason_line2']}</div>
            </div>
        </div>""",
        unsafe_allow_html=True
    )

    st.divider()
    with st.expander("Signal Details", expanded=False):
        tooltips = {
            "XAGUSD": "Global silver price in USD. Rising spot is typically bullish for MCX silver.",
            "US 10-Year Yield": "Higher bond yields strengthen the dollar, which tends to pressure silver prices lower.",
            "Dollar Index (DXY)": "Measures dollar strength. A weaker dollar usually lifts silver prices.",
            "USD/INR": "When the rupee weakens, MCX silver prices rise even if global prices are flat.",
            "MCX Open Interest": "Open Interest shows whether new money is entering or leaving the silver futures market."
        }
        
        table_html = "<table class='html-table'><tr><th>Signal</th><th>Rating</th><th>Status</th></tr>"
        for sig in p['signals']:
            t_tip = tooltips.get(sig['Signal'], "")
            clean_rating = sig['Rating'].replace('✅','').replace('❌','').replace('⚪','').strip()
            table_html += f"<tr><td><div class='tooltip'>{sig['Signal']}<span class='tooltiptext'>{t_tip}</span></div></td>"
            table_html += f"<td>{clean_rating}</td><td>{sig['Status']}</td></tr>"
        table_html += "</table>"
        st.markdown(table_html, unsafe_allow_html=True)

        # Copy Signal Summary Button
        copy_text = f'''SilverSense — {now_ist.strftime('%Y-%m-%d %I:%M %p IST')}
Instrument: {inst_name}
Direction: {d_text}
Expected Move: {p['move_low']:.1f}% to {p['move_high']:.1f}%
Probability: {p['prob_mid']}%
Signal Strength: {p['strength']}
Recommendation: {p['action']}
─────────────────────────────────
Powered by SilverSense'''
        
        copy_html = f'''
        <script>
        function copyText() {{
            navigator.clipboard.writeText(`{copy_text}`);
            let el = document.getElementById('copy-msg');
            el.style.display = 'block';
            setTimeout(() => {{ el.style.display = 'none'; }}, 2000);
        }}
        </script>
        <div style="margin-top: 15px; width: 100%;">
            <button onclick="copyText()" style="width: 100%; background:#2c2c3e; color:#ccc; border:1px solid #444; padding:10px 16px; border-radius:6px; cursor:pointer; font-weight: 600; font-family: sans-serif;">Copy Signal Summary</button>
            <div id="copy-msg" style="display:none; color:#10B981; font-size:13px; margin-top:8px; text-align:center; font-family: sans-serif;">Copied to clipboard</div>
        </div>
        '''
        import streamlit.components.v1 as components
        components.html(copy_html, height=80)


# ═══════════════════════════════════════════════
#  TAB 3 — FORECAST & DAY CHART
# ═══════════════════════════════════════════════
with tab_forecast:
    st.markdown(f"### Multi-Timeframe Forecast — {inst_name}")
    st.markdown(f"**Current Price:** {safe_val(prediction.get('mcx_price'), '{:,.2f}')} {inst_unit} &nbsp;|&nbsp; "
                f"**Signal:** {prediction['direction']} ({prediction['total_score']}/5) &nbsp;|&nbsp; "
                f"**Updated:** {now_ist.strftime('%I:%M:%S %p IST')}")
    st.markdown("")

    forecasts = get_multi_timeframe_forecast(prediction)

    fc1, fc2, fc3, fc4 = st.columns(4)
    for col, fc in zip([fc1, fc2, fc3, fc4], forecasts):
        with col:
            st.markdown(
                f"<div style='padding:16px; border-radius:10px; background:#1a1a2e; border:2px solid {fc['color']}; text-align:center; min-height:220px;'>"
                f"<span style='font-size:13px; color:#aaa;'>{fc['timeframe']}</span><br>"
                f"<span style='font-size:28px; font-weight:bold; color:{fc['color']};'>{fc['direction']}</span><br><br>"
                f"<span style='font-size:12px; color:#ccc;'>Expected Move</span><br>"
                f"<span style='font-size:15px; color:#fff;'>{fc['move_low']:.1f}% – {fc['move_high']:.1f}%</span><br><br>"
                f"<span style='font-size:12px; color:#ccc;'>Target Range</span><br>"
                f"<span style='font-size:14px; color:#fff;'>{safe_val(fc.get('target_low'), '{:,.2f}')} – {safe_val(fc.get('target_high'), '{:,.2f}')} {inst_unit}</span><br><br>"
                f"<span style='font-size:12px; color:#ccc;'>Probability</span><br>"
                f"<span style='font-size:18px; font-weight:bold; color:{fc['color']};'>{fc['probability']}%</span></div>",
                unsafe_allow_html=True
            )

    st.divider()
    st.markdown("#### Forecast Summary")
    st.table(pd.DataFrame([{
        "Timeframe": f["timeframe"], "Direction": f["direction"],
        "Move": f"{f['move_low']:.1f}%–{f['move_high']:.1f}%",
        "Target Low": safe_val(f.get('target_low'), '{:,.2f} ' + inst_unit), "Target High": safe_val(f.get('target_high'), '{:,.2f} ' + inst_unit),
        "Prob": f"{f['probability']}%"
    } for f in forecasts]))

    st.divider()

    st.markdown(f"#### {inst_name} — {chart_timeframe} Chart")
    chart_data, ct = load_chart(chart_ticker, chart_timeframe)
    if chart_data is not None and not chart_data.empty:
        # CONVERT CHART PRICES IF PROXY (SI=F) IS USED
        if chart_ticker == "SI=F":
            usdinr_val = data.get("USDINR", {}).get("current_rate", 85.0)
            kg_conv = 32.15074656
            if "MCX" in inst_name:
                multiplier = usdinr_val * kg_conv
            elif "Tata" in inst_name:
                multiplier = (usdinr_val * kg_conv) / 100
            else:
                multiplier = 1.0
            
            for col in ['Open', 'High', 'Low', 'Close']:
                chart_data[col] = chart_data[col] * multiplier

        first_price = chart_data['Close'].iloc[0]
        last_price = chart_data['Close'].iloc[-1]
        pct_change = ((last_price - first_price) / first_price) * 100 if first_price != 0 else 0
        
        change_color = "green" if pct_change >= 0 else "red"
        st.markdown(f"**Overall Change ({chart_timeframe}):** <span style='color:{change_color}; font-weight:bold;'>{pct_change:.2f}%</span>", unsafe_allow_html=True)
        
        fig_dyn = go.Figure()
        fig_dyn.add_trace(go.Candlestick(
            x=chart_data.index, open=chart_data['Open'],
            high=chart_data['High'], low=chart_data['Low'], close=chart_data['Close'],
            name=inst_name, increasing_line_color='#00cc44', decreasing_line_color='#cc0000'
        ))
        fig_dyn.update_layout(
            height=500, title=f"{chart_ticker} — {chart_timeframe}",
            margin=dict(l=0, r=0, t=40, b=0),
            yaxis_title="Price", xaxis_rangeslider_visible=False
        )
        st.plotly_chart(fig_dyn, use_container_width=True)

        if 'Volume' in chart_data.columns:
            fig_v = go.Figure()
            colors = ['#00cc44' if chart_data['Close'].iloc[i] >= chart_data['Open'].iloc[i] else '#cc0000'
                      for i in range(len(chart_data))]
            fig_v.add_trace(go.Bar(x=chart_data.index, y=chart_data['Volume'], marker_color=colors, name='Volume'))
            fig_v.update_layout(height=180, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="Volume")
            st.plotly_chart(fig_v, use_container_width=True)
    else:
        st.info(f"Chart data unavailable for {chart_ticker} at {chart_timeframe}. Markets may be closed.")

    st.divider()

    st.markdown(f"#### Should You Buy {inst_name} Now?")
    p = prediction
    bullish_n = len([s for s in p['signals'] if 'Bullish' in s['Rating']])
    bearish_n = len([s for s in p['signals'] if 'Bearish' in s['Rating']])
    if p['total_score'] >= 3:
        st.success(f"YES — Strong buying opportunity. {bullish_n}/5 factors are bullish. "
                   f"Enter near {safe_val(p.get('support'), '{:,.2f}')} {inst_unit} | Targets: {safe_val(forecasts[0].get('target_high'), '{:,.2f}')} (24h), {safe_val(forecasts[2].get('target_high'), '{:,.2f}')} (1w) {inst_unit}.")
    elif p['total_score'] >= 1:
        st.warning(f"MAYBE — Mild bullish bias. Score {p['total_score']}/5. "
                   f"Enter small near {safe_val(p.get('mcx_price'), '{:,.2f}')} {inst_unit}. 24h target: {safe_val(forecasts[0].get('target_high'), '{:,.2f}')} {inst_unit}.")
    elif p['total_score'] == 0:
        st.info(f"WAIT — No clear direction. Sideways market. Wait for clarity.")
    else:
        st.error(f"NO — Not a good time to buy. {bearish_n}/5 factors are bearish. "
                 f"Could drop to {safe_val(forecasts[0].get('target_low'), '{:,.2f}')} {inst_unit} (24h).")

# ═══════════════════════════════════════════════
#  FOOTER
# ═══════════════════════════════════════════════
st.markdown("---")
st.markdown('''
<div class='footer'>
    <p><strong>DISCLAIMER & RISK WARNING</strong></p>
    <p>
        <strong>This tool is for educational and informational purposes only.</strong>
        SilverSense does NOT provide financial, investment, or trading advice.
        All predictions, scores, and signals shown here are based on algorithmic analysis of publicly available market data
        and should NOT be treated as recommendations to buy, sell, or hold any financial instrument.
    </p>
    <p>
        <strong>Trading & Investment Risk:</strong>
        Trading in commodities, ETFs, and futures involves substantial risk of loss and is not suitable for all investors.
        Past performance is not indicative of future results. You could lose some or all of your invested capital.
        Always consult a SEBI-registered financial advisor before making any investment decisions.
    </p>
    <p>
        <strong>Data Accuracy:</strong>
        Market data is sourced from Yahoo Finance and may be delayed by 1–15 minutes.
        Prices shown are approximate and may differ from actual exchange prices (MCX/NSE/BSE).
        SilverSense makes no guarantees about the accuracy, completeness, or timeliness of data.
    </p>
    <p>
        <strong>Regulatory Notice:</strong>
        This application is not affiliated with, endorsed by, or registered with SEBI, MCX, NSE, BSE, or any regulatory body.
        Users are solely responsible for their trading and investment decisions.
    </p>
    <p style='color:#555; margin-top:15px;'>
        © 2026 SilverSense | Built with Python & Streamlit | v2.1
    </p>
</div>
''', unsafe_allow_html=True)
