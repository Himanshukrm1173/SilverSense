# SilverSense — Silver Price Predictor & Analyzer

A real-time Streamlit dashboard for silver market analysis, multi-horizon forecasting, and AI-powered trade signals — focused on the Indian MCX market.

![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-1.31+-red?logo=streamlit)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Features

- **Live Market Data** — Silver Spot (XAGUSD), Dollar Index (DXY), US 10-Year Yield, USD/INR, MCX Silver; data source and freshness shown next to every price
- **12-Stage Forecasting Pipeline** — Data Quality → Trade Analysis → Market Regime → Macro Regime → Multi-Horizon Forecasts → Sentiment → Trade Plan → Risk Management → Circuit Breaker → Backtesting → Postmortem
- **Three Independent Horizons** — 24H, 1W, and 1M forecasts derived from separate indicator sets and weightings — a bearish 24H never forces a bearish 1M
- **Data Quality Gate** — Validates freshness, completeness, NaN/Inf, and instrument mapping before any forecast is generated; surfaces exact technical reason for every failure
- **Market Regime Classifier** — Classifies current market into: trend-up, trend-down, range, high-volatility, breakout, or reversal using SMA20/50, Bollinger Bands, and ATR
- **Macro Regime Detector** — Evaluates DXY, US 10Y Yield, and USD/INR to classify macro environment (risk-on/off/stagflation/neutral) and flag transition risk
- **Drawdown Circuit Breaker** — Level 1 (3 consecutive losses): warns and reduces size 50%. Level 2 (5 consecutive losses): blocks all recommendations. Auto-resets after 2 wins
- **Walk-Forward Backtesting** — Strict point-in-time simulation with 0.05% slippage per side. Reports win rate, avg return, profit factor, max drawdown, and Sharpe ratio per horizon
- **Live Postmortem & Accuracy Tracking** — Stores every forecast; tracks win/loss per horizon separately; accuracy shown for 24H, 1W, 1M independently — never blended
- **AI Trade Plans** — Auto-generated via Google Gemini AI; suppressed when circuit breaker is open
- **Multiple Instruments** — MCX Silver (SI=F), Tata Silver (TATSILV.NS), Silver Bees ETF (SILVERBEES.NS); each uses strictly its own price feed — no cross-contamination
- **Auto-Refresh** — Data updates every 60 seconds during market hours
- **PWA Support** — Installable as a mobile app

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        SilverSense Pipeline                              │
│                                                                          │
│  [Data Fetcher] ──► [1. Data Quality Gate] ──► HALT if invalid          │
│         │                    │                                           │
│         ▼                    ▼                                           │
│  [2. Logic Engine]   [3. Market Regime]   [4. Macro Regime]             │
│  (100-pt score)      (trend/range/BB/ATR) (DXY/yields/INR)             │
│         │                    └─────────────────┘                        │
│         ▼                             │                                  │
│  [5. Horizon Engine]  ←───────────────┘                                 │
│    24H (RSI+MACD+OI)                                                    │
│    1W  (SMA+BB+Macro)                                                   │
│    1M  (DXY+Yield+INR+Demand)                                           │
│         │                                                                │
│  [6. Sentiment]  [7. Trade Plan]  [8. Risk Mgmt]                        │
│         │               │               │                               │
│         ▼               ▼               ▼                               │
│  [9. Circuit Breaker] ──► Block if Level 2                              │
│         │                                                                │
│  [10. Backtester]  [11. Forecast Store]  [12. Postmortem]              │
│                                                                          │
│  app.py ──► Dashboard / Prediction / Forecast / Accuracy / Backtest    │
└──────────────────────────────────────────────────────────────────────────┘
```

### Pipeline Modules

| File | Pipeline Stage | Responsibility |
|------|---------------|----------------|
| `data_fetcher.py` | 0 | Fetches data from Yahoo Finance; stamps `_fetched_at`, `_source`, `_ticker` on every dict |
| `data_quality.py` | 1 | Validates freshness (<15 min), completeness, NaN/Inf, instrument-ticker mapping |
| `logic_engine.py` | 2 | 100-point scoring: RSI, SMA, DXY, US10Y, OI |
| `market_regime.py` | 3 | Classifies market regime from instrument-specific price history |
| `macro_regime.py` | 4 | Classifies macro environment from DXY, yield, USD/INR |
| `horizon_engine.py` | 5 | Derives 24H / 1W / 1M forecasts with independent indicator weightings |
| `ai_layer.py` | 7 | Gemini AI trade plan generation with mock fallback |
| `prediction_engine.py` | wrapper | Orchestrates scoring + horizon engine; exposes `get_prediction` and `get_multi_timeframe_forecast` |
| `drawdown_circuit_breaker.py` | 9 | Monitors cumulative loss streaks; blocks recommendations at Level 2 |
| `backtester.py` | 10 | Walk-forward backtest with slippage; reports per-horizon metrics |
| `forecast_store.py` | 11 | Persists forecasts to `forecast_store.json`; computes per-horizon rolling accuracy |

---

## Quick Start (Run Locally)

### Prerequisites
- **Python 3.9 or higher** — [Download Python](https://www.python.org/downloads/)
- **Gemini API Key** (optional, for AI trade plans) — [Get free key](https://aistudio.google.com/apikey)

### Step 1: Clone the Repository
```bash
git clone https://github.com/Himanshukrm1173/SilverSense.git
cd SilverSense
```

### Step 2: Create Virtual Environment
```bash
# On Mac/Linux
python3 -m venv venv
source venv/bin/activate

# On Windows
python -m venv venv
venv\Scripts\activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Set Up API Key (Optional)
```bash
cp .env.example .env
```
Open `.env` and paste your Gemini API key:
```
GEMINI_API_KEY=your_gemini_api_key_here
```
> **Note:** The app works without an API key — it will use a built-in mock trade plan instead.

### Step 5: Run the App
```bash
streamlit run app.py
```
The app will open automatically at `http://localhost:8501`

### Step 6: Run Unit Tests
```bash
pytest tests/ -v
```

---



> **Data Delay:** Yahoo Finance data may be delayed 1–15 minutes. Prices shown are approximate.

---

## Instrument Isolation Guarantee

Each instrument uses **strictly its own price feed**:
- MCX Silver: `SI=F` only (converted to INR/kg)
- Tata Silver: `TATSILV.NS` (falls back to `SI=F` derivation if ETF data unavailable — flagged in source tag)
- Silver Bees: `SILVERBEES.NS` only

The `data_quality.py` module validates this at every pipeline run and raises an explicit error if cross-contamination is detected.

---

## Backtesting Methodology

- **Type:** Walk-forward expanding-window simulation (no lookahead bias)
- **Slippage:** 0.05% per side (entry and exit)
- **Signal Logic:**
  - 24H: RSI + MACD histogram (simplified, OI unavailable historically)
  - 1W: SMA 9/21 crossover
  - 1M: 20-bar vs 50-bar price trend
- **Hold Periods:** 24H = 1 bar, 1W = 5 bars, 1M = 21 bars
- **Metrics:** Win rate, avg return %, profit factor, max drawdown %, Sharpe ratio, sample size

> **Note:** Backtested signal logic uses simplified historical approximations of the live indicators (live OI, Bollinger %B, and macro feeds are not available in daily historical bars). Results reflect indicator approximations and should not be directly compared to live signal performance.

---

## Project Structure

```
SilverSense/
├── app.py                       # Main Streamlit dashboard (6 tabs)
├── data_fetcher.py              # Market data fetching (Yahoo Finance)
├── data_quality.py              # Pipeline Stage 1: Data validation gate
├── logic_engine.py              # Pipeline Stage 2: 100-pt scoring
├── market_regime.py             # Pipeline Stage 3: Market regime classifier
├── macro_regime.py              # Pipeline Stage 4: Macro regime detector
├── horizon_engine.py            # Pipeline Stage 5: Independent 24H/1W/1M forecasts
├── prediction_engine.py         # Orchestrator: scoring + horizon wrapper
├── ai_layer.py                  # Pipeline Stage 7: Gemini AI trade plans
├── drawdown_circuit_breaker.py  # Pipeline Stage 9: Loss-streak circuit breaker
├── backtester.py                # Pipeline Stage 10: Walk-forward backtester
├── forecast_store.py            # Pipeline Stage 11: Forecast persistence & accuracy
├── tests/
│   ├── test_indicators.py       # RSI, SMA, MACD, BB, OI signal tests
│   ├── test_instrument_mapping.py # Cross-contamination prevention tests
│   ├── test_horizons.py         # Horizon independence tests
│   ├── test_data_quality.py     # Staleness, NaN, pipeline gate tests
│   ├── test_risk_gating.py      # Confidence threshold & circuit breaker tests
│   └── test_postmortem.py       # Forecast storage & per-horizon accuracy tests
├── requirements.txt
├── .env.example
├── .streamlit/config.toml
└── static/                      # PWA icons & manifest
```

---

## Technologies Used

| Technology | Purpose |
|-----------|---------|
| Streamlit | Web dashboard framework |
| yfinance | Market data from Yahoo Finance |
| Plotly | Interactive charts |
| Google Generative AI | AI-powered trade plans (Gemini) |
| Pandas & NumPy | Data processing and indicator calculation |
| SciPy | Statistical metrics in backtesting |
| APScheduler | Background data refresh |
| Pytest | Unit and integration testing |

---

## Known Limitations

- **MCX Silver proxy:** There is no direct MCX Silver futures feed available in yfinance. MCX prices are derived from the COMEX SI=F (Silver Futures) contract, converted to INR/kg using the live USD/INR rate. This is an approximation — actual MCX prices may differ by 0.5–2% due to local market factors, exchange-specific premiums, and timing differences.
- **Open Interest (OI):** Live OI is approximated from SI=F volume as a proxy. True MCX OI requires exchange-direct data feeds (MCX API, not publicly available at no cost).
- **Historical OI:** Not available in yfinance daily bars — backtested 24H signals use RSI+MACD only (OI is excluded from backtest).
- **Tata Silver ETF:** TATSILV.NS liquidity is limited. The ETF price may not closely track MCX silver intraday; a fallback derivation from SI=F is used when direct data is unavailable.
- **Data delays:** Yahoo Finance data may be delayed 1–15 minutes from live exchange prices.

---

## Accuracy Disclaimer

No accuracy guarantee of any percentage is made or implied. Forecast accuracy is tracked **separately** for each time horizon (24H, 1W, 1M) and is never presented as a blended or combined figure. All probability estimates are statistical approximations based on historical signal distributions, not certainties. Past win rates do not predict future performance.

---

## Risk Warning & Legal Disclaimer

This tool is for **educational and informational purposes only**. SilverSense does NOT provide financial, investment, or trading advice. All predictions, scores, and signals are based on algorithmic analysis of publicly available market data. They should NOT be treated as recommendations to buy, sell, or hold any financial instrument.

Trading in commodities, ETFs, and futures involves substantial risk of loss and is not suitable for all investors. You could lose some or all of your invested capital. Always consult a **SEBI-registered financial advisor** before making any investment decisions.

This application is not affiliated with, endorsed by, or registered with SEBI, MCX, NSE, BSE, or any regulatory body.

---

Built with Python & Streamlit | v3.0
