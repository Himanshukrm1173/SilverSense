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
from data_quality import validate_pipeline_data
from diagnostics import DiagnosticsLog, render_diagnostics_panel
from market_regime import classify_market_regime
from macro_regime import detect_macro_regime
from drawdown_circuit_breaker import check_circuit_breaker
from forecast_store import (
    get_all_accuracy, get_recent_forecasts, store_forecast,
    get_due_forecasts, resolve_forecast, _load_store
)

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
        deferredPrompt.userChoice.then((choiceResult) => { deferredPrompt = null; });
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
#  STATE INIT
# ─────────────────────────────────────────────
if 'market_edge' not in st.session_state:
    st.session_state.market_edge = 43
    now = datetime.now(IST)
    if now.time() < dt_time(9, 15):
        st.session_state.market_edge += 5
    st.session_state.market_edge = min(100, max(0, st.session_state.market_edge))

if 'theme' not in st.session_state:
    st.session_state.theme = 'dark'

if 'mindset_tip' not in st.session_state:
    tips = [
        "After 2 losing trades in a row, consider stepping back instead of increasing size.",
        "Plan your risk before you look at the profit potential.",
        "Skipping a bad trade is also a win.",
        "Position size matters more than entry timing.",
        "Volatility is normal. Panic is optional.",
        "Your edge comes from consistency, not one big trade.",
    ]
    st.session_state.mindset_tip = random.choice(tips)

# ─────────────────────────────────────────────
#  CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown('''
<style>
    /* ── Design Tokens — Dark Theme (default) ────────────────────── */
    :root {
        --bg:            #0d0d0d;
        --card-bg:       rgba(255,255,255,0.04);
        --card-bg-solid: #141414;
        --border:        rgba(255,255,255,0.10);
        --border-strong: rgba(255,255,255,0.18);
        --text:          #e8e8e8;
        --muted:         rgba(255,255,255,0.50);
        --muted2:        #666;
        --gold:          #FFDF00;
        --gold-muted:    rgba(255,223,0,0.14);
        --green:         #00cc44;
        --red:           #cc0000;
        --amber:         #ff8800;
        --ss-gold:       #FFDF00;
        --ss-gold-muted: rgba(255,223,0,0.14);
        --ss-card-bg:    rgba(255,255,255,0.04);
        --ss-border:     rgba(255,255,255,0.10);
        --ss-muted:      rgba(255,255,255,0.50);
    }

    /* ── Light Theme overrides ──────────────────────────────────── */
    body[data-theme="light"] {
        --bg:            #f2f2f2;
        --card-bg:       rgba(0,0,0,0.04);
        --card-bg-solid: #ffffff;
        --border:        rgba(0,0,0,0.13);
        --border-strong: rgba(0,0,0,0.22);
        --text:          #111111;
        --muted:         rgba(0,0,0,0.50);
        --muted2:        #888;
        --gold:          #b89200;
        --gold-muted:    rgba(184,146,0,0.12);
        --green:         #008a2e;
        --red:           #aa0000;
        --amber:         #cc6600;
        --ss-gold:       #b89200;
        --ss-gold-muted: rgba(184,146,0,0.12);
        --ss-card-bg:    rgba(0,0,0,0.04);
        --ss-border:     rgba(0,0,0,0.13);
        --ss-muted:      rgba(0,0,0,0.50);
    }
    body[data-theme="light"] .stApp { background: var(--bg) !important; }
    body[data-theme="light"] .stMarkdown p,
    body[data-theme="light"] .stMarkdown span { color: var(--text); }

    /* ── Typography ─────────────────────────────────────────────── */
    .main-title { font-size:28px; font-weight:700; color:var(--gold); margin-bottom:0; letter-spacing:-0.01em; }
    .sub-title  { font-size:14px; color:var(--muted); margin-top:0; }
    h4 { color: var(--gold) !important; letter-spacing: 0.02em; }

    /* ── Card System ─────────────────────────────────────────────── */
    .ss-card {
        border: 1px solid var(--border);
        border-radius: 8px;
        background: var(--card-bg);
        overflow: hidden;
        margin-bottom: 10px;
    }
    .ss-card-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 9px 14px 8px 14px;
        border-bottom: 1px solid var(--border);
    }
    .ss-card-title {
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.08em;
        color: var(--muted);
        text-transform: uppercase;
    }
    .ss-card-body { padding: 12px 14px; }
    .ss-card-footer {
        padding: 7px 14px;
        border-top: 1px solid var(--border);
        font-size: 11px;
        color: var(--muted2);
    }

    /* ── Pill Badges ─────────────────────────────────────────────── */
    .ss-badge {
        display: inline-flex;
        align-items: center;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        border: 1px solid;
        white-space: nowrap;
    }
    .ss-badge-green { background:rgba(0,204,68,0.12);   color:var(--green); border-color:rgba(0,204,68,0.30); }
    .ss-badge-red   { background:rgba(204,0,0,0.12);    color:var(--red);   border-color:rgba(204,0,0,0.30); }
    .ss-badge-gold  { background:var(--gold-muted);     color:var(--gold);  border-color:rgba(255,223,0,0.30); }
    .ss-badge-muted { background:rgba(128,128,128,0.10);color:var(--muted); border-color:rgba(128,128,128,0.20); }

    /* ── Small tag (card header top-right) ──────────────────────── */
    .ss-tag {
        font-size: 10px;
        padding: 1px 7px;
        border-radius: 4px;
        border: 1px solid var(--border);
        color: var(--muted);
        background: var(--card-bg);
    }

    /* ── Existing restyled to tokens ─────────────────────────────── */
    .card {
        padding: 14px; border-radius: 8px;
        background: var(--card-bg); border: 1px solid var(--border); margin-bottom: 10px;
    }
    .footer {
        padding: 30px 20px; margin-top: 40px;
        border-top: 1px solid var(--gold-muted);
        color: var(--muted); font-size: 12px; line-height: 1.8;
    }
    .footer a { color: var(--muted); }

    .stTabs [data-baseweb="tab-list"] { gap: 8px; border-bottom: 1px solid var(--gold-muted); }
    .stTabs [data-baseweb="tab"] { padding: 8px 16px; border-radius: 6px 6px 0 0; }
    .stTabs [aria-selected="true"] { border-bottom: 2px solid var(--gold) !important; color: var(--gold) !important; }

    .tooltip { position:relative; display:inline-block; border-bottom:1px dotted currentColor; cursor:help; }
    .tooltip .tooltiptext {
        visibility:hidden; width:200px;
        background-color:var(--card-bg-solid); color:var(--text);
        border:1px solid var(--border); text-align:center; border-radius:6px;
        padding:5px; position:absolute; z-index:1; bottom:125%; left:50%;
        margin-left:-100px; opacity:0; transition:opacity 0.3s; font-size:12px; font-weight:normal;
    }
    .tooltip:hover .tooltiptext { visibility:visible; opacity:1; }

    .html-table { width:100%; border-collapse:collapse; margin-top:10px; font-size:14px; }
    .html-table th, .html-table td { border:1px solid var(--border); padding:8px; text-align:left; }
    .html-table th { background-color:var(--card-bg); }

    .rec-card {
        display:flex; align-items:center; gap:16px; padding:14px 18px;
        border-radius:8px; border:1px solid var(--border); background:var(--card-bg);
    }
    .rec-badge {
        display:inline-flex; align-items:center; justify-content:center;
        min-width:80px; padding:6px 14px; border-radius:6px;
        font-size:18px; font-weight:800; letter-spacing:1px; flex-shrink:0;
    }
    .rec-text { line-height:1.5; }
    .rec-text .rec-line1 { font-size:14px; font-weight:600; }
    .rec-text .rec-line2 { font-size:13px; opacity:0.75; margin-top:2px; }

    .holiday-banner {
        background:rgba(51,43,0,0.6); border:1px solid rgba(77,65,0,0.8); color:var(--text);
        padding:10px 16px; border-radius:6px; margin-bottom:20px; font-size:14px;
    }
    .status-badge {
        display:inline-flex; align-items:center; background:var(--card-bg);
        border:1px solid var(--border); padding:4px 10px; border-radius:4px;
        font-size:12px; color:var(--muted); font-weight:600; margin-top:5px;
    }
    .live-dot {
        display:inline-block; width:8px; height:8px; background-color:var(--green);
        border-radius:50%; margin-right:6px; animation:pulse-dot 2s infinite ease-in-out;
    }
    @keyframes pulse-dot { 0%{opacity:0.4;} 50%{opacity:1;} 100%{opacity:0.4;} }

    .circuit-banner-2 {
        background:rgba(61,0,0,0.7); border:2px solid var(--red); color:#ffcccc;
        padding:12px 16px; border-radius:6px; margin-bottom:16px; font-size:14px; font-weight:600;
    }
    .circuit-banner-1 {
        background:rgba(61,40,0,0.6); border:1px solid var(--amber); color:#ffd480;
        padding:10px 16px; border-radius:6px; margin-bottom:16px; font-size:13px;
    }
    .source-tag { font-size:11px; color:var(--muted); font-style:italic; margin-left:6px; }
    .no-pred-box {
        background:var(--card-bg); border:1px solid var(--border); color:var(--text);
        padding:20px; border-radius:8px; font-size:14px; text-align:center;
    }
</style>
''', unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def check_market_holiday():
    now_ist = datetime.now(IST)
    date_str = now_ist.strftime('%Y-%m-%d')
    TESTING_OVERRIDE = False
    if TESTING_OVERRIDE:
        return True, "Weekend (Testing Mode)"
    if now_ist.weekday() >= 5:
        return True, "Weekend"
    holidays = {
        "2024-11-01": "Diwali-Laxmi Pujan", "2024-11-15": "Guru Nanak Jayanti",
        "2024-12-25": "Christmas", "2025-01-26": "Republic Day",
        "2025-03-14": "Holi", "2025-03-31": "Id-ul-Fitr",
        "2025-04-10": "Mahavir Jayanti", "2025-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
        "2025-04-18": "Good Friday", "2025-05-01": "Maharashtra Day",
    }
    if date_str in holidays:
        return True, holidays[date_str]
    return False, ""


def get_market_timing_status(inst_name):
    now_ist = datetime.now(IST)
    current_time = now_ist.time()
    if "MCX" in inst_name:
        open_time, close_time = dt_time(9, 0), dt_time(23, 30)
    else:
        open_time, close_time = dt_time(9, 15), dt_time(15, 30)
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
        hours, mins = diff_mins // 60, diff_mins % 60
        time_str = f"Closes in {hours}h {mins}m" if hours > 0 else f"Closes in {mins}m"
        return f"<div class='status-badge'><span class='live-dot'></span>LIVE &nbsp;&middot;&nbsp; {time_str}</div>"
    else:
        if current_time < open_time and not full_closed:
            diff_mins = time_diff_mins(current_time, open_time)
            hours, mins = diff_mins // 60, diff_mins % 60
            time_str = f"Opens in {hours}h {mins}m" if hours > 0 else f"Opens in {mins}m"
        else:
            time_str = "Opens next session"
        return f"<div class='status-badge'>CLOSED &nbsp;&middot;&nbsp; {time_str}</div>"


def safe_val(v, fmt="{:.2f}", unit="", fallback="--"):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return fallback
    try:
        return fmt.format(v) + unit
    except Exception:
        return fallback


def _source_tag(source_str, fetched_at=None):
    """Renders a small source + freshness tag."""
    age_str = ""
    if fetched_at:
        try:
            from datetime import timezone
            ft = datetime.fromisoformat(fetched_at)
            if ft.tzinfo is None:
                ft = ft.replace(tzinfo=timezone.utc)
            age_m = (datetime.now(timezone.utc) - ft).total_seconds() / 60
            age_str = f" · {age_m:.0f}m ago"
        except Exception:
            pass
    return f"<span class='source-tag'>{source_str}{age_str}</span>"


def _source_caption(source_str, fetched_at=None):
    """Returns plain-text source + freshness string for st.caption()."""
    age_str = ""
    if fetched_at:
        try:
            from datetime import timezone
            ft = datetime.fromisoformat(fetched_at)
            if ft.tzinfo is None:
                ft = ft.replace(tzinfo=timezone.utc)
            age_m = (datetime.now(timezone.utc) - ft).total_seconds() / 60
            age_str = f" · {age_m:.0f}m ago"
        except Exception:
            pass
    return f"{source_str}{age_str}"



def _hex_to_rgba(hex_color: str, alpha: float = 0.15) -> str:
    h = hex_color.lstrip('#')
    if len(h) == 6:
        return f"rgba({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}, {alpha})"
    return hex_color


def _regime_color(regime: str) -> str:
    return {
        "trend-up": "#00cc44", "trend-down": "#cc0000",
        "range": "#888888", "high-volatility": "#ff8800",
        "breakout": "#00ccff", "reversal": "#cc88ff",
    }.get(regime, "#888888")


def _macro_color(macro: str) -> str:
    return {
        "risk-on": "#00cc44", "risk-off": "#cc0000",
        "stagflation": "#ff8800", "neutral": "#888888",
    }.get(macro, "#888888")


# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("<h1 style='color:#C9A84C; font-size:22px; font-weight:700; margin-bottom:0;'>SilverSense</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color:#888; font-size:13px; margin-top:2px;'>Silver Price Predictor &amp; Analyzer</p>", unsafe_allow_html=True)
    st.markdown("<hr style='border:none; border-top:1px solid rgba(201,168,76,0.25); margin:10px 0;'>", unsafe_allow_html=True)

    instrument = st.selectbox(
        "Select Instrument",
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
    return scored, plan, rsi_series, pred, ft, raw


@st.cache_data(ttl=60)
def load_tata_data():
    raw = fetch_tata_data()
    scored = process_data_and_score(raw)
    tata = raw.get("TATA_SILVER")
    tata_price = tata["current_price"] if tata else None
    plan = generate_trade_plan(scored, inst_price=tata_price, inst_name="Tata Silver", inst_unit="Rs/unit")
    pred = get_prediction(scored["enriched_data"], inst_price=tata_price, inst_unit="Rs/unit", inst_name="Tata Silver")
    ft = datetime.now(IST)
    return scored, plan, pred, ft, tata, raw


@st.cache_data(ttl=60)
def load_bees_data():
    raw = fetch_bees_data()
    scored = process_data_and_score(raw)
    bees = raw.get("SILVERBEES")
    bees_price = bees["current_price"] if bees else None
    plan = generate_trade_plan(scored, inst_price=bees_price, inst_name="Silver Bees (ETF)", inst_unit="Rs/unit")
    pred = get_prediction(scored["enriched_data"], inst_price=bees_price, inst_unit="Rs/unit", inst_name="Silver Bees (ETF)")
    ft = datetime.now(IST)
    return scored, plan, pred, ft, bees, raw


@st.cache_data(ttl=60)
def load_chart(ticker, tf):
    return fetch_dynamic_chart(ticker, tf)


# ─────────────────────────────────────────────
#  DETERMINE INSTRUMENT
# ─────────────────────────────────────────────
if "MCX" in instrument:
    inst_name, inst_unit, chart_ticker = "Silver (MCX)", "Rs/kg", "SI=F"
    inst_key = "MCX_SILVER"
    with st.spinner("Fetching Silver MCX data..."):
        scored_data, ai_plan, rsi_series, prediction, fetch_time, raw_data = load_mcx_data()
    inst_data = None
elif "Tata" in instrument:
    inst_name, inst_unit, chart_ticker = "Tata Silver", "Rs/unit", "TATSILV.NS"
    inst_key = "TATA_SILVER"
    with st.spinner("Fetching Tata Silver data..."):
        scored_data, ai_plan, prediction, fetch_time, inst_data, raw_data = load_tata_data()
    rsi_series = None
else:
    inst_name, inst_unit, chart_ticker = "Silver Bees (ETF)", "Rs/unit", "SILVERBEES.NS"
    inst_key = "SILVERBEES"
    with st.spinner("Fetching Silver Bees data..."):
        scored_data, ai_plan, prediction, fetch_time, inst_data, raw_data = load_bees_data()
    rsi_series = None

data = scored_data["enriched_data"]
score = scored_data["total_score"]
interpretation = scored_data["interpretation"].replace('🟢','').replace('🟡','').replace('⚪','').replace('🟠','').replace('🔴','').strip()
breakdown = scored_data["breakdown"]
now_ist = datetime.now(IST)
minutes_since = (now_ist - fetch_time).total_seconds() / 60

# ─────────────────────────────────────────────
#  PIPELINE STAGES (run after data load)
# ─────────────────────────────────────────────

# Stage 1: Data Quality Check (with diagnostics logging)
diag_log = DiagnosticsLog()
dq_result = validate_pipeline_data(raw_data, inst_key, diag_log=diag_log)

# Stage 3: Market Regime
inst_specific_data = raw_data.get(inst_key) or raw_data.get("MCX_SILVER") or {}
market_regime_result = classify_market_regime(inst_specific_data)

# Stage 4: Macro Regime
macro_result = detect_macro_regime(
    raw_data.get("DXY"), raw_data.get("US10Y"), raw_data.get("USDINR")
)

# Stage 9: Circuit Breaker
circuit = check_circuit_breaker()

# Stage 10: Multi-horizon forecasts (needed by Dashboard tab)
try:
    forecasts = get_multi_timeframe_forecast(
        prediction=prediction,
        data=data,
        macro_result=macro_result,
        market_regime_result=market_regime_result,
        inst_name=inst_name,
        inst_unit=inst_unit,
    )
except Exception:
    forecasts = []

# Stage 11: Auto-log forecasts for postmortem tracking.
# Dedup: uses a content fingerprint (hash of bias + rounded targets per horizon) stored in
# session_state. Same forecast on 60s auto-refresh → same fingerprint → skipped.
# Forecast materially changes (direction, confidence band, targets) → new fingerprint → logged.
import hashlib as _hashlib
def _forecast_fingerprint(fcs: list) -> str:
    parts = []
    for _f in sorted(fcs, key=lambda x: x.get("timeframe", "")):
        parts.append("|".join([
            str(_f.get("timeframe", "")),
            str(_f.get("bias", "")),
            str(round(float(_f.get("confidence_score") or 0), 2)),
            str(round(float(_f.get("target_low") or 0), -1)),   # round to nearest 10 to absorb trivial price drift
            str(round(float(_f.get("target_high") or 0), -1)),
        ]))
    return _hashlib.md5(";".join(parts).encode()).hexdigest()[:12]

_auto_log_key = f"_fc_fp_{inst_name}"
_fp = _forecast_fingerprint(forecasts) if forecasts else ""
if forecasts and st.session_state.get(_auto_log_key) != _fp:
    _entry_price = (
        (inst_data.get("current_price") if inst_data else None)
        or (raw_data.get("MCX_SILVER") or {}).get("current_price_inr", 0)
        or 0
    )
    for _fc in forecasts:
        try:
            store_forecast(
                horizon=_fc.get("timeframe", "24H"),
                bias=_fc.get("bias", "Neutral"),
                confidence=float(_fc.get("confidence_score") or 0),
                regime=_fc.get("current_regime", "--"),
                macro_regime=_fc.get("macro_regime", "--"),
                expected_low=float(_fc.get("target_low") or 0),
                expected_high=float(_fc.get("target_high") or 0),
                invalidation_level=float(_fc.get("invalidation_level") or 0),
                instrument=inst_name,
                inst_price=float(_entry_price or 0),
            )
        except Exception:
            pass  # Never block UI on logging failure
    st.session_state[_auto_log_key] = _fp
# Stage 12: Auto-resolve due forecasts using live price data
try:
    _due = get_due_forecasts()
    _current_price = (
        (inst_data.get("current_price") if inst_data else None)
        or (raw_data.get("MCX_SILVER") or {}).get("current_price_inr", 0)
        or 0
    )
    if _current_price and _current_price > 0:
        for _due_fc in _due:
            if _due_fc.get("instrument") == inst_name:
                resolve_forecast(_due_fc["forecast_id"], float(_current_price))
except Exception:
    pass



# ─────────────────────────────────────────────
#  HEADER & STALE WARNING
# ─────────────────────────────────────────────
if minutes_since > 10:
    st.markdown(
        f"<div style='background:#b35900; color:#fff; padding:10px; text-align:center;"
        f"font-weight:bold; border-radius:4px; margin-bottom:15px;'>"
        f"Data may be stale — last updated {int(minutes_since)} minutes ago.</div>",
        unsafe_allow_html=True
    )

# Circuit breaker banner
if circuit["circuit_level"] == 2:
    st.markdown(
        f"<div class='circuit-banner-2'>Circuit Breaker OPEN — "
        f"{circuit['reason']} {circuit['recommendation']}</div>",
        unsafe_allow_html=True
    )
elif circuit["circuit_level"] == 1:
    st.markdown(
        f"<div class='circuit-banner-1'>Circuit Breaker WARNING — "
        f"{circuit['reason']} {circuit['recommendation']}</div>",
        unsafe_allow_html=True
    )

hc1, hc2 = st.columns([3, 1])
with hc1:
    st.markdown(f"<p class='main-title'>SilverSense — {inst_name}</p>", unsafe_allow_html=True)
    # Regime tags in header
    r_color = _regime_color(market_regime_result["regime"])
    m_color = _macro_color(macro_result["macro_regime"])
    st.markdown(
        f"<p class='sub-title'>Real-time analysis, predictions &amp; trade signals &nbsp;|&nbsp; "
        f"Market Regime: <span style='color:{r_color}; font-weight:600;'>{market_regime_result['regime'].upper()}</span> &nbsp;|&nbsp; "
        f"Macro: <span style='color:{m_color}; font-weight:600;'>{macro_result['macro_regime'].upper()}</span></p>",
        unsafe_allow_html=True
    )
    
    # Surface proxy/fallback warnings compactly
    if dq_result.get("has_warnings") and dq_result.get("warning_checks"):
        for w in dq_result["warning_checks"]:
            with st.popover("Data source note"):
                st.markdown(f"**DATA WARNING:** {w['reason'][:120]}")

with hc2:
    c2a, c2b = st.columns([1,1])
    with c2b:
        st.markdown(
            f"<div style='text-align: right; margin-bottom: 5px;'>"
            f"<span style='color: var(--muted); font-size: 13px; font-weight: bold;'>Last Updated:</span> "
            f"<span style='color: var(--text); font-size: 13px;'>{now_ist.strftime('%I:%M %p IST')}</span></div>",
            unsafe_allow_html=True
        )
        status_html = get_market_timing_status(inst_name)
        st.markdown(f"<div style='text-align: right;'>{status_html}</div>", unsafe_allow_html=True)
    with c2a:
        if st.button("🌓 Theme" if st.session_state.theme == "dark" else "🌕 Theme"):
            st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
            st.rerun()

# Inject theme to DOM
st.markdown(f'''
<script>
    const parent = window.parent.document;
    if (parent) {{
        parent.body.dataset.theme = "{st.session_state.theme}";
    }}
    document.body.dataset.theme = "{st.session_state.theme}";
</script>
''', unsafe_allow_html=True)
# Market Holiday Banner
is_closed, reason = check_market_holiday()
if is_closed:
    st.markdown(
        f"<div class='holiday-banner'>Market is closed today ({reason}). Showing last closing prices.</div>",
        unsafe_allow_html=True
    )

# ─────────────────────────────────────────────
#  DATA QUALITY GATE — shown inline if failed
# ─────────────────────────────────────────────

if not dq_result["pipeline_valid"]:
    st.markdown(
        f"<div class='no-pred-box'><strong>{dq_result['no_prediction_reason']}</strong>"
        f"<br><br>Please refresh or check your network connection. "
        f"No forecast will be generated until data passes validation.</div>",
        unsafe_allow_html=True
    )
    # Show diagnostics panel even when blocked — helps debugging
    with st.expander("Data Diagnostics (Debug)", expanded=True):
        render_diagnostics_panel(diag_log)
    st.stop()

# ─────────────────────────────────────────────
#  TABS
# ─────────────────────────────────────────────
tab_dash, tab_pred, tab_forecast, tab_accuracy, tab_backtest, tab_postmortem = st.tabs([
    "Dashboard", "Live Prediction", "Forecast & Chart",
    "Accuracy Dashboard", "Backtest Mode", "Live Postmortem"
])

# ═══════════════════════════════════════════════
#  TAB 1 — DASHBOARD
# ═══════════════════════════════════════════════
with tab_dash:
    color = "gray"
    if "STRONG BUY" in interpretation: color = "var(--green)"
    elif "MILD BUY" in interpretation: color = "var(--green)"
    elif "MILD SELL" in interpretation: color = "var(--red)"
    elif "STRONG SELL" in interpretation: color = "var(--red)"

    st.markdown(
        f"<div class='ss-card' style='border-color:{color};'>"
        f"<div class='ss-card-header'>"
        f"<span class='ss-card-title'>Overall Analysis</span>"
        f"<span class='ss-tag' style='color:{color}; border-color:{color}40;'>{interpretation}</span>"
        f"</div>"
        f"<div class='ss-card-body'>"
        f"<span style='font-size:32px; font-weight:bold; color:{color};'>{score}/100</span>"
        f"</div></div>",
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
        st.metric(
            "Silver Spot (USD)",
            safe_val(xag.get("current_price"), "${:.2f}"),
            safe_val(xag.get("change_pct"), "{:.2f}%")
        )
        st.caption(_source_caption(xag.get('_source', 'Yahoo Finance'), xag.get('_fetched_at')))
    with kpi2:
        dxy_rising = dxy.get("rising", False)
        st.metric(
            "DXY",
            safe_val(dxy.get('current_dxy'), "{:.2f}"),
            f"{'Rising — Bearish' if dxy_rising else 'Falling — Bullish'} for Silver",
            delta_color="inverse"
        )
        st.caption(_source_caption('Yahoo Finance', dxy.get('_fetched_at')))
    with kpi3:
        y_rising = us10y.get("rising", False)
        st.metric(
            "US 10Y Yield",
            safe_val(us10y.get('current_yield'), "{:.3f}%"),
            f"{'Rising — Bearish' if y_rising else 'Falling — Bullish'} for Silver",
            delta_color="inverse"
        )
        st.caption(_source_caption('Yahoo Finance', us10y.get('_fetched_at')))
    with kpi4:
        st.metric(
            "USD/INR",
            safe_val(usdinr.get('current_rate'), "Rs {:.2f}"),
            "Weakening" if usdinr.get("weakening") else "Strengthening"
        )
        st.caption(_source_caption('Yahoo Finance', usdinr.get('_fetched_at')))
    with kpi5:
        if inst_data:
            src = inst_data.get('_source', 'Yahoo Finance')
            st.metric(
                inst_name,
                safe_val(inst_data.get('current_price'), "{:,.2f} " + inst_unit),
                safe_val(inst_data.get('change_pct'), "{:.2f}%")
            )
            st.caption(_source_caption(src, inst_data.get('_fetched_at')))
        else:
            mcx_val = mcx.get("current_price_inr")
            mcx_prev = mcx.get("prev_price_inr")
            diff = (mcx_val - mcx_prev) if (mcx_val and mcx_prev and not math.isnan(mcx_val) and not math.isnan(mcx_prev)) else None
            st.metric(
                "MCX Silver",
                safe_val(mcx_val, "Rs {:,.0f}/kg"),
                safe_val(diff, "Rs {:,.0f}")
            )
            st.caption(_source_caption(mcx.get('_source', 'Yahoo Finance (SI=F)'), mcx.get('_fetched_at')))


    # Market Edge
    edge = st.session_state.market_edge
    if edge <= 30: edge_msg = "You are just getting started. Markets reward consistency."
    elif edge <= 60: edge_msg = "You are building discipline. Keep showing up."
    elif edge <= 85: edge_msg = "Strong edge. Traders like you outperform the crowd."
    else: edge_msg = "Elite discipline. You track silver like a professional."

    st.markdown(
        f"<div class='card' style='margin-top:15px;'>"
        f"<span style='color:#ccc; font-size:14px;'>Market Edge: <strong>{edge}</strong></span><br>"
        f"<span style='color:#fff; font-size:16px;'>{edge_msg}</span></div>",
        unsafe_allow_html=True
    )

    # Mindset tip
    st.markdown(
        f"<div style='border:1px solid #333; padding:10px; border-radius:6px; color:#aaa; font-size:12px; margin-bottom:20px;'>"
        f"{st.session_state.mindset_tip}</div>",
        unsafe_allow_html=True
    )

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

    # OI Signal (no emojis)
    st.markdown("#### Open Interest Signal")
    oi_signal = mcx.get("oi_signal_name", "N/A")
    oi_c = {"Long Buildup": "var(--green)", "Short Buildup": "var(--red)", "Short Covering": "var(--green)", "Long Unwinding": "var(--red)"}.get(oi_signal, "var(--muted)")
    st.markdown(
        f"<div class='ss-card' style='border-left:5px solid {oi_c};'>"
        f"<div class='ss-card-body'>"
        f"<strong style='color:var(--muted); font-size:13px; text-transform:uppercase;'>Signal:</strong> <span style='color:{oi_c}; font-weight:bold; font-size:16px;'>{oi_signal}</span>"
        f"</div></div>",
        unsafe_allow_html=True
    )

    st.divider()
    st.markdown("#### AI Trade Plan")
    if circuit["circuit_open"]:
        st.warning(f"Trade plan suppressed — {circuit['recommendation']}")
    else:
        st.markdown("<p style='font-size:11px; color:#666; margin-top:-10px;'>Analysis generated by AI — verify before trading. Not financial advice.</p>", unsafe_allow_html=True)

    st.divider()
    st.markdown("#### Market & Macro Environment")
    env_cols = st.columns(3)
    with env_cols[0]:
        r_name = market_regime_result.get('regime', 'N/A').upper()
        r_color = _regime_color(market_regime_result.get('regime', ''))
        r_bg = _hex_to_rgba(r_color, 0.15)
        r_bias = market_regime_result.get('rationale', 'N/A')
        st.markdown(f"<div style='margin-bottom:10px;'>"
                    f"<span style='background:{r_bg}; color:{r_color}; padding:4px 8px; border-radius:4px; font-size:12px; font-weight:600;'>MARKET REGIME: {r_name}</span><br>"
                    f"<span style='font-size:13px; color:#aaa; display:inline-block; margin-top:6px;'>Bias: {r_bias}</span></div>", unsafe_allow_html=True)
    with env_cols[1]:
        m_name = macro_result.get('macro_regime', 'N/A').upper()
        m_color = _macro_color(macro_result.get('macro_regime', ''))
        m_bg = _hex_to_rgba(m_color, 0.15)
        m_exp = macro_result.get('macro_summary', 'N/A')
        m_exp_disp = m_exp[:50] + "..." if len(m_exp) > 50 else m_exp
        st.markdown(f"<div style='margin-bottom:10px;'>"
                    f"<span style='background:{m_bg}; color:{m_color}; padding:4px 8px; border-radius:4px; font-size:12px; font-weight:600;'>MACRO REGIME: {m_name}</span><br>"
                    f"<span style='font-size:13px; color:#aaa; display:inline-block; margin-top:6px;'>{m_exp_disp}</span></div>", unsafe_allow_html=True)
    with env_cols[2]:
        c_lvl = circuit.get('circuit_level', 0)
        c_status = "BLOCKED" if c_lvl == 2 else ("WARNING" if c_lvl == 1 else "NORMAL")
        c_color = "#cc0000" if c_lvl == 2 else ("#ff8800" if c_lvl == 1 else "#00cc44")
        c_bg = _hex_to_rgba(c_color, 0.15)
        c_reason = circuit.get('reason', 'N/A')
        c_reason_disp = c_reason[:50] + "..." if len(c_reason) > 50 else c_reason
        st.markdown(f"<div style='margin-bottom:10px;'>"
                    f"<span style='background:{c_bg}; color:{c_color}; padding:4px 8px; border-radius:4px; font-size:12px; font-weight:600;'>RISK STATUS: {c_status}</span><br>"
                    f"<span style='font-size:13px; color:#aaa; display:inline-block; margin-top:6px;'>{c_reason_disp}</span></div>", unsafe_allow_html=True)

    st.markdown("#### Forecast Overview")
    if not forecasts:
        st.caption("Forecast data unavailable for this session.")
    else:
        fc_cols = st.columns(3)
        for i, fc in enumerate(forecasts):
            with fc_cols[i]:
                d = fc.get('direction', 'N/A')
                c = int(fc.get('confidence_score', 0) * 100) if fc.get('confidence_score') else 0
                t_low = fc.get('target_low')
                t_high = fc.get('target_high')
                t = f"{t_low:,.0f} - {t_high:,.0f}" if t_low and t_high else "N/A"
                factors = fc.get('contributing_factors', [])
                reason = factors[0].get('factor', 'N/A') if factors else 'N/A'
                reason_disp = reason[:40] + "..." if len(reason) > 40 else reason
                color = fc.get('color', 'gray')
                if fc.get('no_trade_flag'):
                    d = "No Trade"
                    color = "#555"
                st.markdown(
                    f"<div style='border:1px solid {color}; padding:14px 14px 12px 14px; border-radius:6px; background:rgba(0,0,0,0.2);'>"
                    f"<div style='margin-bottom:10px;'>"
                    f"<b style='color:{color}; font-size:14px;'>{fc.get('timeframe', 'N/A')}</b>"
                    f"&nbsp;|&nbsp;<b style='font-size:14px;'>{d}</b>"
                    f"<span style='font-size:12px; color:#aaa;'>&nbsp;({c}%)</span>"
                    f"</div>"
                    f"<div style='margin-bottom:8px; font-size:12px; color:#ccc;'>"
                    f"<span style='color:#888; font-size:11px; text-transform:uppercase; letter-spacing:0.05em;'>Target Range</span><br>"
                    f"<span style='font-size:13px; color:#ddd;'>{t}</span>"
                    f"</div>"
                    f"<div style='font-size:12px; color:#aaa; border-top:1px solid rgba(255,255,255,0.07); padding-top:8px;'>"
                    f"<span style='color:#888; font-size:11px; text-transform:uppercase; letter-spacing:0.05em;'>Key Factor</span><br>"
                    f"<span style='font-size:12px; color:#bbb;'>{reason_disp}</span>"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )

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
            f"<div class='ss-card' style='border-color:{d_color};'>"
            f"<div class='ss-card-body' style='text-align:center;'>"
            f"<span style='font-size:24px; font-weight:bold; color:{d_color};'>{d_text}</span><br>"
            f"<span style='font-size:14px; color:var(--muted);'>Score: {p['total_score']}/5</span>"
            f"</div></div>",
            unsafe_allow_html=True
        )
    with pc3:
        st.markdown(
            f"<div class='ss-card' style='border-color:{p['strength_color']};'>"
            f"<div class='ss-card-body' style='text-align:center;'>"
            f"<span style='font-size:14px; color:var(--muted);'>Strength</span><br>"
            f"<span style='font-size:24px; font-weight:bold; color:{p['strength_color']};'>{p['strength']}</span>"
            f"</div></div>",
            unsafe_allow_html=True
        )

    st.markdown("")
    em1, em2 = st.columns(2)
    with em1:
        st.markdown(f"**Expected Move:** {p['move_low']:.1f}% – {p['move_high']:.1f}%")
        pot_move = p.get('mcx_price', 0) * ((p['move_low'] + p['move_high']) / 2 / 100)
        if pot_move and not math.isnan(pot_move):
            st.markdown(
                f"<span style='color:#888; font-size:13px;'>Potential move if signal holds: Rs {pot_move:,.0f} per {inst_unit.split('/')[-1]}</span>",
                unsafe_allow_html=True
            )
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
    rc_col1, rc_col2, rc_col3, rc_col4 = st.columns([2.5, 1, 1, 1])
    with rc_col2:
        acct_size = st.number_input("Account Size (₹)", min_value=1000, value=100000, step=10000)
    with rc_col3:
        daily_loss_pct = st.number_input("Daily Loss Limit (%)", min_value=0.5, value=2.0, step=0.5, max_value=10.0)
    with rc_col4:
        max_setups = st.number_input("Max Setups / Day", min_value=1, value=3, step=1, max_value=10)
    with rc_col1:
        st.markdown("#### Recommendation")
        _d_loss_val = acct_size * (daily_loss_pct / 100.0)
        
        _daily_limit_reached = False
        _max_setups_reached = False
        # Calculate today's realized PnL and Setup Count
        try:
            from forecast_store import _load_store
            _recs = _load_store()
            _today_str = now_utc.strftime("%Y-%m-%d")
            
            # Setup count proxy: number of 24H horizon records logged today
            _today_setups = len([r for r in _recs if str(r.get("timestamp", "")).startswith(_today_str) and r.get("horizon") == "24H"])
            _max_setups_reached = _today_setups >= max_setups
            _setup_color = "#cc0000" if _max_setups_reached else "#ccc"
            _setup_display = f"<span style='color:{_setup_color}; font-weight:600;'>{_today_setups}</span>"
            
            _today_pnl_pct = sum(r.get("pnl_pct", 0) for r in _recs if r.get("outcome") and r.get("pnl_pct") is not None and str(r.get("timestamp", "")).startswith(_today_str))
            _today_pnl_val = acct_size * (_today_pnl_pct / 100.0)
            
            if _today_pnl_val < 0:
                _realized_loss = abs(_today_pnl_val)
                _daily_limit_reached = _realized_loss >= _d_loss_val
                _status_color = "#cc0000" if _daily_limit_reached else "#ff8800"
                _status_text = f"<span style='color:{_status_color}; font-weight:600;'>₹{_realized_loss:,.0f} loss today</span>"
                if _daily_limit_reached:
                    _status_text += " <span style='color:#cc0000; font-weight:bold;'>— LIMIT REACHED</span>"
            else:
                _status_text = f"<span style='color:#00cc44; font-weight:600;'>+₹{_today_pnl_val:,.0f} profit today</span>" if _today_pnl_val > 0 else "<span style='color:#888;'>₹0 today</span>"
        except Exception:
            _setup_display = "<span style='color:#888;'>N/A</span>"
            _status_text = "<span style='color:#888;'>N/A</span>"
            
        st.markdown(
            f"<div style='font-size:12px; color:#888; margin-top:-10px; margin-bottom:10px;'>"
            f"<strong>Daily Stop Rule:</strong> Cease trading if daily realized loss hits ₹{_d_loss_val:,.0f} ({daily_loss_pct}%) &nbsp;|&nbsp; "
            f"<strong>Max Setups:</strong> {_setup_display} / {max_setups} logged today &nbsp;|&nbsp; "
            f"<strong>Current:</strong> {_status_text}"
            f"</div>",
            unsafe_allow_html=True
        )
        
    badge_bg = {"BUY": "#00aa33", "SELL": "#cc2200", "WAIT": "#555566"}.get(p['action'], "#555566")
    clean_reason1 = p['reason_line1'].replace('✅', '').replace('❌', '').strip()

    if circuit["circuit_open"]:
        st.error(f"No trade — {circuit['recommendation']}")
    else:
        try:
            if _daily_limit_reached:
                st.markdown(
                    f"<div style='border-left:4px solid #cc0000; padding:12px 16px; background:rgba(204,0,0,0.08); margin-bottom:15px; border-radius:4px;'>"
                    f"<div style='color:#ff4444; font-weight:700; font-size:13px; letter-spacing:1px; margin-bottom:6px;'>TRADING SUSPENDED — DAILY LOSS LIMIT REACHED</div>"
                    f"<div style='color:#ddd; font-size:13px;'>You have hit your max loss rule of ₹{_d_loss_val:,.0f} for today. Stop trading to protect capital. New setups should be ignored.</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            elif _max_setups_reached:
                st.markdown(
                    f"<div style='border-left:4px solid #ff8800; padding:12px 16px; background:rgba(255,136,0,0.08); margin-bottom:15px; border-radius:4px;'>"
                    f"<div style='color:#ffaa00; font-weight:700; font-size:13px; letter-spacing:1px; margin-bottom:6px;'>TRADING SUSPENDED — MAX SETUPS REACHED</div>"
                    f"<div style='color:#ddd; font-size:13px;'>Daily setup limit ({max_setups} max) reached for today. Stop taking additional setups to prevent overtrading. New setups should be ignored.</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
        except Exception:
            pass
            
        _limit_style = "opacity: 0.35; filter: grayscale(50%); pointer-events: none;" if _daily_limit_reached or _max_setups_reached else ""
        if _limit_style:
            st.markdown(f"<div style='{_limit_style}'>", unsafe_allow_html=True)

        st.markdown(
            f"""<div class='rec-card'>
                <span class='rec-badge' style='background:{badge_bg}; color:#fff;'>{p['action']}</span>
                <div class='rec-text'>
                    <div class='rec-line1'>{clean_reason1}</div>
                </div>
            </div>""",
            unsafe_allow_html=True
        )
        
        if ai_plan:
            import re as _re
            
            def _parse_plan_price(text: str, label: str):
                """Extract first INR number from a labelled line in the plan string."""
                for line in text.split("\n"):
                    if label.lower() in line.lower():
                        nums = _re.findall(r"[\d,]+(?:\.\d+)?", line.replace(",", ""))
                        # findall after stripping commas
                        nums = _re.findall(r"[\d]+(?:\.\d+)?", line.replace(",", ""))
                        floats = [float(n) for n in nums if float(n) > 1000]
                        if floats:
                            return sum(floats) / len(floats)  # midpoint if range
                return None

            def _rr_display(plan: str, action: str):
                """Compute and return a compact R:R string, or None if uncomputable."""
                if action == "WAIT":
                    return None
                entry = _parse_plan_price(plan, "Entry Range")
                t1    = _parse_plan_price(plan, "Target 1")
                sl    = _parse_plan_price(plan, "Stop Loss")
                if not all([entry, t1, sl]):
                    return None
                reward = abs(t1 - entry)
                risk   = abs(entry - sl)
                if risk < 0.01:
                    return None
                rr = reward / risk
                rr_color = "#00cc44" if rr >= 1.5 else "#ff8800" if rr >= 1.0 else "#cc0000"
                return (
                    f"<div style='display:inline-flex; align-items:center; gap:18px; "
                    f"padding:8px 14px; background:rgba(0,0,0,0.25); border-radius:6px; "
                    f"border:1px solid rgba(255,255,255,0.08); margin: 10px 0;'>"
                    f"<span style='font-size:11px; color:#888; letter-spacing:1px;'>RISK / REWARD</span>"
                    f"<span style='font-size:18px; font-weight:700; color:{rr_color};'>1 : {rr:.2f}</span>"
                    f"<span style='font-size:11px; color:#666;'>Risk&nbsp;{risk:,.0f} &nbsp;|&nbsp; Reward&nbsp;{reward:,.0f}</span>"
                    f"</div>"
                )

            st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
            if "3. **Key risk" in ai_plan:
                parts = ai_plan.split("3. **Key risk", 1)
                primary_plan = parts[0].strip()
                caution_notes = "3. **Key risk" + parts[1]
                
                if p.get('action') == "WAIT":
                    # No-trade reason from existing signal context
                    _wait_reason = p.get('reason_line1', '').replace('✅','').replace('❌','').strip()
                    st.markdown(
                        f"<div style='border-left:3px solid #cc2200; padding:8px 12px; background:rgba(204,34,0,0.06); border-radius:0 4px 4px 0; margin-bottom:10px;'>"
                        f"<span style='color:#cc2200; font-weight:600; font-size:13px; letter-spacing:1px;'>NO TRADE SETUP</span>"
                        + (f"<div style='color:#aaa; font-size:12px; margin-top:4px;'>{_wait_reason}</div>" if _wait_reason else "")
                        + "</div>",
                        unsafe_allow_html=True
                    )
                    st.markdown(f"<div style='opacity: 0.5;'>\n\n{primary_plan}\n\n</div>", unsafe_allow_html=True)
                else:
                    st.markdown(primary_plan)
                    rr_html = _rr_display(ai_plan, p.get('action', ''))
                    if rr_html:
                        st.markdown(rr_html, unsafe_allow_html=True)
                        # Setup quality label derived from R:R band and signal strength
                        _strength = p.get('strength', '')
                        _entry = _parse_plan_price(ai_plan, 'Entry Range')
                        _t1    = _parse_plan_price(ai_plan, 'Target 1')
                        _sl    = _parse_plan_price(ai_plan, 'Stop Loss')
                        if _entry and _t1 and _sl:
                            _rr_val = abs(_t1 - _entry) / max(abs(_entry - _sl), 0.01)
                            if _rr_val >= 1.5 and _strength == 'STRONG':
                                _quality, _qcolor = 'HIGH QUALITY SETUP', '#00cc44'
                            elif _rr_val >= 1.0 and _strength in ('STRONG', 'MODERATE'):
                                _quality, _qcolor = 'ACCEPTABLE SETUP', '#ff8800'
                            else:
                                _quality, _qcolor = 'LOW QUALITY — USE CAUTION', '#cc0000'
                            st.markdown(
                                f"<div style='font-size:11px; font-weight:600; letter-spacing:1px; color:{_qcolor}; margin:2px 0 8px 0;'>{_quality}</div>",
                                unsafe_allow_html=True
                            )
                            # Risk-per-trade derived from user's own rules: daily limit ÷ max setups, capped at 1%
                            _policy_risk_pct = min((daily_loss_pct / max_setups) / 100.0, 0.01)
                            _risk_amt = acct_size * _policy_risk_pct
                            _risk_pct_display = f"{_policy_risk_pct * 100:.2f}%"
                            _stop_dist = abs(_entry - _sl)
                            if _stop_dist > 0:
                                _suggested_qty = _risk_amt / _stop_dist
                                _qty_display = f"{_suggested_qty:,.1f} units" if _suggested_qty >= 0.1 else "< 0.1 units"
                                _trades_to_limit = int(_d_loss_val / _risk_amt) if _risk_amt > 0 else 0
                                _ttl_color = "#cc0000" if _trades_to_limit <= 1 else "#ff8800" if _trades_to_limit <= 2 else "#ccc"
                                st.markdown(
                                    f"<div class='ss-card' style='border-left:3px solid var(--muted); margin-bottom:12px;'>"
                                    f"<div class='ss-card-body' style='padding-top:10px; padding-bottom:10px;'>"
                                    f"<div style='font-size:13px; color:var(--text);'>"
                                    f"<strong style='color:var(--text);'>Risk Guard ({_risk_pct_display}):</strong> Max risk ₹{_risk_amt:,.0f} &nbsp;|&nbsp; "
                                    f"<strong style='color:var(--text);'>Stop Distance:</strong> ₹{_stop_dist:,.0f} per unit &nbsp;|&nbsp; "
                                    f"<strong style='color:var(--text);'>Suggested Qty:</strong> {_qty_display}"
                                    f"</div>"
                                    f"<div style='font-size:11px; color:var(--muted); margin-top:6px; padding-top:6px; border-top:1px solid var(--border);'>"
                                    f"At this size, <span style='color:{_ttl_color}; font-weight:600;'>{_trades_to_limit} full-risk losses</span> will hit your daily loss limit of ₹{_d_loss_val:,.0f}."
                                    f"</div>"
                                    f"</div></div>",
                                    unsafe_allow_html=True
                                )
                    else:
                        st.markdown(
                            "<div style='font-size:12px; color:#555; margin:6px 0;'>R:R — N/A (price levels not parseable)</div>",
                            unsafe_allow_html=True
                        )
                
                st.markdown(
                    f"<div style='margin-top:12px; padding:12px 14px; background:rgba(255,255,255,0.03); border-left:3px solid #C9A84C; font-size:14px;'>\n\n"
                    f"**Caution & Context**\n\n"
                    f"{caution_notes}\n\n"
                    f"</div>", 
                    unsafe_allow_html=True
                )
            else:
                st.markdown(ai_plan)
                
        if _limit_style:
            st.markdown("</div>", unsafe_allow_html=True)

    st.divider()
    with st.expander("Signal Details", expanded=False):
        tooltips = {
            "XAGUSD": "Global silver price in USD. Rising spot is typically bullish for MCX silver.",
            "US 10-Year Yield": "Higher bond yields strengthen the dollar, which tends to pressure silver prices lower.",
            "Dollar Index (DXY)": "Measures dollar strength. A weaker dollar usually lifts silver prices.",
            "USD/INR": "When the rupee weakens, MCX silver prices rise even if global prices are flat.",
            "MCX Open Interest": "Open Interest shows whether new money is entering or leaving the silver futures market.",
        }
        table_html = "<table class='html-table'><tr><th>Signal</th><th>Rating</th><th>Status</th></tr>"
        for sig in p['signals']:
            t_tip = tooltips.get(sig['Signal'], "")
            clean_rating = sig['Rating'].replace('✅','').replace('❌','').replace('⚪','').strip()
            table_html += f"<tr><td><div class='tooltip'>{sig['Signal']}<span class='tooltiptext'>{t_tip}</span></div></td>"
            table_html += f"<td>{clean_rating}</td><td>{sig['Status']}</td></tr>"
        table_html += "</table>"
        st.markdown(table_html, unsafe_allow_html=True)

        copy_text = f'''SilverSense — {now_ist.strftime('%Y-%m-%d %I:%M %p IST')}
Instrument: {inst_name}
Direction: {d_text}
Expected Move: {p['move_low']:.1f}% to {p['move_high']:.1f}%
Probability: {p['prob_mid']}%
Signal Strength: {p['strength']}
Recommendation: {p['action']}
Data Source: Yahoo Finance
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
#  TAB 3 — FORECAST & CHART
# ═══════════════════════════════════════════════
with tab_forecast:
    st.markdown(f"### Multi-Horizon Forecast — {inst_name}")

    inst_price_for_forecast = (
        inst_data.get("current_price") if inst_data else
        (raw_data.get("MCX_SILVER") or {}).get("current_price_inr", 0)
    )
    src_tag = _source_tag(
        inst_specific_data.get("_source", "Yahoo Finance"),
        inst_specific_data.get("_fetched_at")
    )
    st.markdown(
        f"**Current Price:** {safe_val(inst_price_for_forecast, '{:,.2f}')} {inst_unit} "
        f"{src_tag} &nbsp;|&nbsp; **Signal:** {prediction['direction']} ({prediction['total_score']}/5) "
        f"&nbsp;|&nbsp; **Updated:** {now_ist.strftime('%I:%M:%S %p IST')}",
        unsafe_allow_html=True
    )
    st.markdown("")

    # Generate independent 3-horizon forecasts
    forecasts = get_multi_timeframe_forecast(
        prediction=prediction,
        data=data,
        macro_result=macro_result,
        market_regime_result=market_regime_result,
        inst_name=inst_name,
        inst_unit=inst_unit,
    )

    # Conflict detection banner
    biases = [f["bias"] for f in forecasts if not f.get("no_trade_flag")]
    if len(set(biases)) > 1 and len(biases) > 1:
        st.warning(
            "Mixed structure across horizons — no single clear directional edge. "
            "Review each horizon independently before taking a position."
        )

    # 3-column forecast cards (24H / 1W / 1M)
    fc1, fc2, fc3 = st.columns(3)
    for col, fc in zip([fc1, fc2, fc3], forecasts):
        with col:
            conf_pct = int(fc["confidence_score"] * 100)
            prob = fc.get("prob_split", {})
            if fc["no_trade_flag"]:
                card_border = "#555555"
                direction_display = "No Trade"
            else:
                card_border = fc['color']
                direction_display = fc['direction']

            st.markdown(
                f"<div class='ss-card' style='border-color:{card_border}; text-align:center; min-height:260px;'>"
                f"<div class='ss-card-body'>"
                f"<span style='font-size:13px; color:var(--muted);'>{fc['timeframe']}</span><br>"
                f"<span style='font-size:26px; font-weight:bold; color:{card_border};'>{direction_display}</span><br><br>"
                f"<span style='font-size:11px; color:var(--muted2);'>Expected Range</span><br>"
                f"<span style='font-size:14px; color:var(--text);'>"
                f"{safe_val(fc.get('target_low'), '{:,.2f}')} – {safe_val(fc.get('target_high'), '{:,.2f}')} {inst_unit}"
                f"</span><br><br>"
                f"<span style='font-size:11px; color:var(--muted2);'>Probability Split</span><br>"
                f"<span style='font-size:12px; color:var(--muted);'>"
                f"Up {prob.get('up',33)}% / Neutral {prob.get('sideways',33)}% / Down {prob.get('down',33)}%"
                f"</span><br><br>"
                f"<span style='font-size:11px; color:var(--muted2);'>Confidence</span><br>"
                f"<span style='font-size:16px; font-weight:bold; color:{card_border};'>{conf_pct}%</span>"
                f"</div></div>",
                unsafe_allow_html=True
            )

            # No-trade reason
            if fc["no_trade_flag"]:
                st.caption(fc["no_trade_reason"])

            # "Why this forecast?" expander
            with st.expander(f"Why this forecast? ({fc['timeframe']})", expanded=False):
                factors = fc.get("contributing_factors", [])
                if factors:
                    factor_html = "<table class='html-table'><tr><th>Factor</th><th>Value</th><th>Signal</th><th>Weight</th></tr>"
                    for f_row in factors:
                        sig_color = {"Bullish": "#00cc44", "Bearish": "#cc0000", "Neutral": "#888888"}.get(f_row.get("signal",""), "#aaa")
                        factor_html += (
                            f"<tr><td>{f_row.get('factor','')}</td>"
                            f"<td>{f_row.get('value','')}</td>"
                            f"<td style='color:{sig_color}; font-weight:600;'>{f_row.get('signal','')}</td>"
                            f"<td>{f_row.get('weight','')}</td></tr>"
                        )
                    factor_html += "</table>"
                    st.markdown(factor_html, unsafe_allow_html=True)
                if fc.get("macro_note"):
                    st.info(fc["macro_note"])
                inv = fc.get("invalidation_level")
                if inv:
                    st.markdown(f"**Invalidation Level:** {safe_val(inv, '{:,.2f}')} {inst_unit}")
                if fc.get("conflict_note"):
                    st.warning(fc["conflict_note"])

    st.divider()

    # Forecast summary table
    st.markdown("#### Forecast Summary")
    summary_rows = []
    for f in forecasts:
        prob = f.get("prob_split", {})
        summary_rows.append({
            "Horizon": f["timeframe"],
            "Bias": f["bias"],
            "Direction": f["direction"],
            "Expected Range": f"{safe_val(f.get('target_low'), '{:,.2f}')} – {safe_val(f.get('target_high'), '{:,.2f}')} {inst_unit}",
            "Up / Neutral / Down": f"{prob.get('up',33)}% / {prob.get('sideways',33)}% / {prob.get('down',33)}%",
            "Confidence": f"{int(f['confidence_score']*100)}%",
            "No Trade": "Yes" if f["no_trade_flag"] else "No",
            "Regime": f.get("current_regime", "--"),
        })
    st.table(pd.DataFrame(summary_rows))

    st.divider()

    # Dynamic Chart
    st.markdown(f"#### {inst_name} — {chart_timeframe} Chart")
    chart_data, ct = load_chart(chart_ticker, chart_timeframe)
    if chart_data is not None and not chart_data.empty:
        if chart_ticker == "SI=F":
            usdinr_val = (raw_data.get("USDINR") or {}).get("current_rate", 85.0)
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
        st.markdown(
            f"**Overall Change ({chart_timeframe}):** <span style='color:{change_color}; font-weight:bold;'>{pct_change:.2f}%</span>",
            unsafe_allow_html=True
        )

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


# ═══════════════════════════════════════════════
#  TAB 4 — ACCURACY DASHBOARD
# ═══════════════════════════════════════════════
with tab_accuracy:
    st.markdown("### Accuracy Dashboard")
    st.markdown(
        "Historical accuracy is tracked **separately** for each time horizon. "
        "No blended or combined accuracy number is shown here."
    )
    st.divider()

    all_acc = get_all_accuracy()

    for horizon_key in ["24H", "1W", "1M"]:
        acc = all_acc[horizon_key]
        h_col1, h_col2 = st.columns([1, 3])
        with h_col1:
            st.markdown(f"#### {horizon_key} Horizon")
            if acc["accuracy_pct"] is not None:
                acc_color = "#00cc44" if acc["accuracy_pct"] >= 55 else ("#cc0000" if acc["accuracy_pct"] < 45 else "#888888")
                st.markdown(
                    f"<div style='font-size:36px; font-weight:bold; color:{acc_color};'>{acc['accuracy_pct']:.1f}%</div>"
                    f"<div style='color:#aaa; font-size:12px;'>Win Rate</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown("<div style='color:#aaa;'>No data yet</div>", unsafe_allow_html=True)
        with h_col2:
            if acc["total"] > 0:
                st.markdown(
                    f"- **Total Signals:** {acc['total']}"
                    f" &nbsp;|&nbsp; **Wins:** {acc['wins']}"
                    f" &nbsp;|&nbsp; **Losses:** {acc['losses']}"
                    f" &nbsp;|&nbsp; **Breakevens:** {acc['breakevens']}"
                )
                if acc["avg_pnl_pct"] is not None:
                    pnl_color = "#00cc44" if acc["avg_pnl_pct"] > 0 else "#cc0000"
                    st.markdown(
                        f"- **Avg P&L per signal:** <span style='color:{pnl_color};'>{acc['avg_pnl_pct']:.2f}%</span>",
                        unsafe_allow_html=True
                    )
                streak = acc.get("recent_streak", 0)
                if streak > 0:
                    st.success(f"Current streak: {streak} consecutive wins")
                elif streak < 0:
                    st.error(f"Current streak: {abs(streak)} consecutive losses")
            else:
                st.markdown("No completed forecasts yet for this horizon. Accuracy will appear after the first outcome is recorded.")
        st.divider()

    st.caption(
        "Accuracy is updated only when actual price outcomes are recorded via the Live Postmortem tab. "
        "This data is stored in forecast_store.json."
    )


# ═══════════════════════════════════════════════
#  TAB 5 — BACKTEST MODE
# ═══════════════════════════════════════════════
with tab_backtest:
    st.markdown("### Backtest Mode")
    st.markdown("Walk-forward simulation using Yahoo Finance data. No lookahead. Slippage included.")
    st.divider()

    bt_col1, bt_col2 = st.columns([2, 1])
    with bt_col1:
        bt_ticker = st.selectbox("Ticker", ["SI=F (Silver Futures)", "SILVERBEES.NS", "TATSILV.NS"], index=0)
        ticker_map = {"SI=F (Silver Futures)": "SI=F", "SILVERBEES.NS": "SILVERBEES.NS", "TATSILV.NS": "TATSILV.NS"}
    with bt_col2:
        bt_period = st.selectbox("Period", ["1y", "2y", "3y", "5y"], index=1)

    if st.button("Run Backtest", use_container_width=True):
        with st.spinner("Running backtest..."):
            try:
                from backtester import run_backtest
                bt = run_backtest(ticker=ticker_map[bt_ticker], period=bt_period)
            except Exception as e:
                bt = {"error": str(e)}

        if bt.get("error"):
            st.warning(f"Backtest could not complete: {bt['error']}")
        else:
            st.markdown(
                f"<div style='border-left: 3px solid #C9A84C; padding-left: 12px; margin-bottom: 18px;'>"
                f"<div style='color:#fff; font-size:15px; font-weight:600;'>Historical Performance: {bt_ticker}</div>"
                f"<div style='color:#aaa; font-size:13px;'>Walk-forward test over the past {bt_period.upper()} ({bt.get('bars', 0):,} bars processed)</div>"
                f"</div>",
                unsafe_allow_html=True
            )
            bcols = st.columns(3)
            for col, h in zip(bcols, ["24H", "1W", "1M"]):
                m = bt.get(h, {})
                wr = m.get("win_rate")
                n = m.get("sample_size", 0)
                note = m.get("note", "")
                wr_str = f"{wr:.1f}%" if wr is not None else "N/A"
                wr_color = ("#00cc44" if wr and wr >= 55 else "#ff4d4d" if wr and wr < 45 else "#C9A84C") if wr is not None else "#888"
                with col:
                    st.markdown(
                        f"<div class='ss-card'>"
                        f"<div class='ss-card-body'>"
                        f"<div style='font-weight:600; font-size:12px; color:var(--muted); letter-spacing:1px; margin-bottom:4px;'>{h} HORIZON</div>"
                        f"<div style='font-size:26px; font-weight:700; color:{wr_color};'>{wr_str}</div>"
                        f"<div style='font-size:12px; color:var(--muted2); margin-top:2px;'>Win Rate &nbsp;|&nbsp; {n} trades</div>"
                        + (f"<div style='font-size:11px; color:var(--muted2); margin-top:6px; border-top:1px solid var(--border); padding-top:6px;'>{note}</div>" if note else "")
                        + "</div></div>",
                        unsafe_allow_html=True
                    )
    else:
        st.caption("Select a ticker and period, then click Run Backtest.")


# ═══════════════════════════════════════════════
#  TAB 6 — LIVE POSTMORTEM
# ═══════════════════════════════════════════════
with tab_postmortem:
    st.markdown("### Live Postmortem")
    st.markdown(
        "Every forecast generated is stored here. Update the actual outcome price "
        "to track live accuracy and compute win/loss per horizon."
    )
    st.divider()

    all_records = _load_store()
    total = len(all_records)
    resolved = sum(1 for r in all_records if r.get("outcome") is not None)
    pending = total - resolved
    h_24h = sum(1 for r in all_records if r.get("horizon") == "24H")
    h_1w = sum(1 for r in all_records if r.get("horizon") == "1W")
    h_1m = sum(1 for r in all_records if r.get("horizon") == "1M")

    acc_data = get_all_accuracy()

    s_col1, s_col2, s_col3, s_col4, s_col5, s_col6 = st.columns(6)
    with s_col1:
        st.metric("Total Forecasts", total)
        st.caption(f"24H: {h_24h} | 1W: {h_1w} | 1M: {h_1m}")
    with s_col2:
        st.metric("Pending", pending)
    with s_col3:
        st.metric("Resolved", resolved)

    def _fmt_acc(h: str):
        d = acc_data.get(h)
        if not d or not d.get("total"):
            return "N/A", ""
        return f"{d['accuracy_pct']:.1f}%", f"{d['wins']}/{d['total']} won"

    for col, hz in zip([s_col4, s_col5, s_col6], ["24H", "1W", "1M"]):
        with col:
            val, cap = _fmt_acc(hz)
            st.metric(f"{hz} Accuracy", val)
            if cap:
                st.caption(cap)

    st.divider()

    # Compact Horizon Breakdown Block
    st.markdown("##### Horizon Breakdown")
    hb_col1, hb_col2, hb_col3 = st.columns(3)
    for col, hz in zip([hb_col1, hb_col2, hb_col3], ["24H", "1W", "1M"]):
        hz_recs = [r for r in all_records if r.get("horizon") == hz]
        hz_total = len(hz_recs)
        hz_res = sum(1 for r in hz_recs if r.get("outcome") is not None)
        hz_pend = hz_total - hz_res
        acc = acc_data.get(hz, {})
        w = acc.get("wins", 0)
        l = acc.get("losses", 0)
        b = acc.get("breakevens", 0)

        with col:
            st.markdown(
                f"<div class='ss-card'>"
                f"<div class='ss-card-body'>"
                f"<div style='font-weight:600; font-size:13px; color:var(--gold); margin-bottom:4px;'>{hz} Horizon</div>"
                f"<div style='font-size:12px; color:var(--text); line-height:1.5;'>"
                f"Total: <b>{hz_total}</b> &nbsp;|&nbsp; Resolved: <b>{hz_res}</b> &nbsp;|&nbsp; Pending: <b>{hz_pend}</b><br/>"
                f"Wins: <b style='color:var(--green)'>{w}</b> &nbsp;|&nbsp; Losses: <b style='color:var(--red)'>{l}</b> &nbsp;|&nbsp; Breakeven: <b>{b}</b>"
                f"</div>"
                f"</div></div>",
                unsafe_allow_html=True
            )

    st.divider()

    # ── Trust & Calibration Metrics ────────────────────────────────
    _res_recs = [r for r in all_records if r.get("outcome") is not None and r.get("confidence") is not None]
    _n_cal = len(_res_recs)
    
    _wait_recs = [r for r in all_records if r.get("bias", "").lower() == "neutral" and r.get("outcome") is not None]
    _n_waits = len(_wait_recs)

    if _n_cal >= 5:
        _avg_conf = sum(r["confidence"] for r in _res_recs) / _n_cal * 100
        _actual_win_rate = sum(1 for r in _res_recs if r.get("outcome") == "win") / _n_cal * 100
        _gap = _avg_conf - _actual_win_rate
        _gap_color = "#00cc44" if abs(_gap) <= 5 else "#ff8800" if abs(_gap) <= 15 else "#cc0000"
        _gap_label = "Well-calibrated" if abs(_gap) <= 5 else "Overconfident" if _gap > 5 else "Underconfident"
        _cal_html = f"<div style='font-size:13px; color:#ccc; margin-bottom:8px;'><strong>Confidence Calibration:</strong> <span style='color:#fff;'>{_avg_conf:.1f}%</span> vs Actual <span style='color:#fff;'>{_actual_win_rate:.1f}%</span> &nbsp;|&nbsp; Gap: <strong style='color:{_gap_color};'>{_gap:+.1f}pp — {_gap_label}</strong> <span style='color:#666; font-size:11px;'>({_n_cal} records)</span></div>"
    else:
        _cal_html = f"<div style='font-size:13px; color:#666; margin-bottom:8px;'><strong>Confidence Calibration:</strong> Not enough structured data yet ({_n_cal} resolved records so far; min 5 required).</div>"

    if _n_waits >= 5:
        # Assuming an outcome of "win" on a WAIT means the user confirmed avoiding was the correct profitable choice
        _correct = sum(1 for r in _wait_recs if str(r.get("outcome")).lower() == "win")
        _wait_pct = _correct / _n_waits * 100
        _wait_html = f"<div style='font-size:13px; color:#ccc;'><strong>No-Trade Accuracy:</strong> <strong style='color:#fff;'>{_wait_pct:.1f}%</strong> of WAIT setups correctly avoided <span style='color:#666; font-size:11px;'>({_n_waits} resolved WAITs)</span></div>"
    else:
        _wait_html = f"<div style='font-size:13px; color:#666;'><strong>No-Trade Accuracy:</strong> Not enough structured data yet ({_n_waits} resolved WAITs so far; min 5 required).</div>"

    st.markdown(
        f"<div class='ss-card' style='margin-bottom:14px;'>"
        f"<div class='ss-card-body'>"
        f"<div style='font-size:11px; color:var(--muted); letter-spacing:1px; margin-bottom:8px; border-bottom:1px solid var(--border); padding-bottom:6px;'>TRUST & CALIBRATION METRICS</div>"
        f"{_cal_html}"
        f"{_wait_html}"
        f"</div></div>",
        unsafe_allow_html=True
    )

    recent = get_recent_forecasts(limit=30)
    if not recent:
        st.info("No forecasts stored yet. Forecasts will appear here after they are generated and saved.")
    else:
        # Outcome update form
        with st.expander("Update Forecast Outcome", expanded=False):
            st.markdown("Enter the forecast ID and actual exit price to record the outcome.")
            forecast_ids = [r["forecast_id"][:8] + "..." for r in recent if r.get("outcome") is None]
            if forecast_ids:
                sel_id_short = st.selectbox("Select Forecast ID (pending)", forecast_ids)
                sel_id_full = next((r["forecast_id"] for r in recent if r["forecast_id"].startswith(sel_id_short[:8])), None)
                actual_p = st.number_input("Actual Exit Price", min_value=0.0, value=0.0, step=0.01)
                if st.button("Record Outcome") and sel_id_full and actual_p > 0:
                    from forecast_store import update_outcome
                    result = update_outcome(sel_id_full, actual_p)
                    if result:
                        st.success(f"Outcome recorded: {result.get('outcome','--').upper()} | P&L: {result.get('pnl_pct','--')}%")
            else:
                st.info("All stored forecasts have outcomes recorded.")

        # Compact Postmortem Table
        rows = []
        # Display up to latest 20 records for a lightweight view
        for r in recent[:20]:
            raw_out = r.get("outcome")
            if raw_out is None:
                status = "Pending"
                outcome = "--"
            else:
                status = "Resolved"
                pnl = r.get("pnl_pct")
                if pnl is not None:
                    outcome = f"{str(raw_out).upper()} ({pnl:+.2f}%)"
                else:
                    outcome = str(raw_out).upper()
            
            # Format timestamp nicely (strip T and seconds)
            ts = r.get("timestamp", "")[:16].replace("T", " ")
            
            rows.append({
                "Timestamp": ts,
                "Instrument": r.get("instrument", "--"),
                "Horizon": r.get("horizon", "--"),
                "Bias": r.get("bias", "--"),
                "Confidence": f"{r.get('confidence', 0)*100:.0f}%",
                "Status": status,
                "Actual Price": r.get("actual_price") if r.get("actual_price") is not None else "--",
                "Outcome": outcome,
            })
        
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Store current forecast button
    st.divider()
    st.markdown("#### Store Current Forecast")
    st.markdown("Save the current forecast to track its outcome later.")
    if st.button("Store Current 3-Horizon Forecast"):
        if not forecasts:
            st.error("No forecast available to store.")
        else:
            for fc in forecasts:
                try:
                    fid = store_forecast(
                        horizon=fc["timeframe"],
                        bias=fc["bias"],
                        confidence=fc["confidence_score"],
                        regime=fc.get("current_regime", "--"),
                        macro_regime=fc.get("macro_regime", "--"),
                        expected_low=fc.get("target_low", 0),
                        expected_high=fc.get("target_high", 0),
                        invalidation_level=fc.get("invalidation_level", 0),
                        instrument=inst_name,
                        inst_price=inst_price_for_forecast,
                    )
                    st.success(f"Stored {fc['timeframe']} forecast (ID: {fid[:8]})")
                except Exception as e:
                    st.error(f"Failed to store {fc['timeframe']} forecast: {e}")


# ═══════════════════════════════════════════════
#  DATA DIAGNOSTICS PANEL
# ═══════════════════════════════════════════════
with st.expander("Data Diagnostics (Developer View)", expanded=False):
    render_diagnostics_panel(diag_log)



# ═══════════════════════════════════════════════
#  FOOTER
# ═══════════════════════════════════════════════
st.markdown("---")
st.markdown('''
<div class='footer'>
    <p><strong>DISCLAIMER &amp; RISK WARNING</strong></p>
    <p>
        <strong>This tool is for educational and informational purposes only.</strong>
        SilverSense does NOT provide financial, investment, or trading advice.
        All predictions, scores, and signals shown here are based on algorithmic analysis of publicly available market data
        and should NOT be treated as recommendations to buy, sell, or hold any financial instrument.
    </p>
    <p>
        <strong>Accuracy Disclaimer:</strong>
        No accuracy guarantee of any percentage is made or implied. Forecast accuracy varies and past performance
        does not predict future results. All probability estimates are statistical approximations, not certainties.
    </p>
    <p>
        <strong>Trading &amp; Investment Risk:</strong>
        Trading in commodities, ETFs, and futures involves substantial risk of loss and is not suitable for all investors.
        Past performance is not indicative of future results. You could lose some or all of your invested capital.
        Always consult a SEBI-registered financial advisor before making any investment decisions.
    </p>
    <p>
        <strong>Data Accuracy:</strong>
        Market data is sourced from Yahoo Finance and may be delayed by 1-15 minutes.
        Prices shown are approximate and may differ from actual exchange prices (MCX/NSE/BSE).
        SilverSense makes no guarantees about the accuracy, completeness, or timeliness of data.
    </p>
    <p>
        <strong>Regulatory Notice:</strong>
        This application is not affiliated with, endorsed by, or registered with SEBI, MCX, NSE, BSE, or any regulatory body.
        Users are solely responsible for their trading and investment decisions.
    </p>
    <p style='color:#555; margin-top:15px;'>
        &copy; 2026 SilverSense | Built with Python &amp; Streamlit | v3.0
    </p>
</div>
''', unsafe_allow_html=True)
