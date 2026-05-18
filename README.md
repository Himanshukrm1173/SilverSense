# SilverSense — Silver Price Predictor & Analyzer

A real-time Streamlit dashboard for silver market analysis, predictions, and AI-powered trade signals — focused on the Indian MCX market.

![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-1.31+-red?logo=streamlit)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Live Market Data** — Silver Spot (XAGUSD), Dollar Index (DXY), US 10-Year Yield, USD/INR, MCX Silver
- **Technical Analysis** — RSI, 20/50 SMA, Open Interest signals with 100-point scoring system
- **AI Trade Plans** — Auto-generated trade plans using Google Gemini AI
- **Multi-Timeframe Forecasts** — 24h, 48h, 1-week, and 1-month predictions
- **Multiple Instruments** — MCX Silver, Tata Silver (TATSILV), Silver Bees ETF
- **Auto-Refresh** — Data updates every 60 seconds during market hours
- **PWA Support** — Installable as a mobile app

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

## Technologies Used

| Technology | Purpose |
|-----------|---------|
| Streamlit | Web dashboard framework |
| yfinance | Market data from Yahoo Finance |
| Plotly | Interactive charts |
| Google Generative AI | AI-powered trade plans |
| Pandas & NumPy | Data processing |
| APScheduler | Background data refresh |

## Project Structure

```
SilverSense/
├── app.py                 # Main Streamlit dashboard
├── data_fetcher.py        # Market data fetching (Yahoo Finance)
├── logic_engine.py        # Scoring & signal logic
├── ai_layer.py            # Gemini AI trade plan generation
├── prediction_engine.py   # Price prediction & forecasting
├── requirements.txt       # Python dependencies
├── .env.example           # API key template
├── .streamlit/
│   └── config.toml        # Streamlit theme config
└── static/                # PWA icons & manifest
```

## Disclaimer

This tool is for **educational and informational purposes only**. It does NOT provide financial advice. Always consult a SEBI-registered financial advisor before making investment decisions.

---

Built with ❤️ using Python & Streamlit
