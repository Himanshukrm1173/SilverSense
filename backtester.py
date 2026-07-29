"""
backtester.py — Pipeline Stage 10

Walk-forward backtesting for MCX Silver horizon signals.
Uses historical yfinance data with STRICT point-in-time discipline (no lookahead).
Reports per-horizon: win rate, avg return, profit factor, max drawdown, Sharpe ratio,
and sample size.

Rules:
  - Only data available BEFORE the signal timestamp is used.
  - 0.05% slippage included on entry and exit.
  - Walk-forward expanding window: each signal uses all prior history up to that point.
  - Results reported separately for 24H, 1W, and 1M — never combined.
"""
import math
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone

SLIPPAGE_PCT = 0.0005  # 0.05% one-way slippage


def _safe(v, default=0.0):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return default
    return float(v)


def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).fillna(0.0)
    loss = (-delta.where(delta < 0, 0.0)).fillna(0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def _compute_macd_hist(close: pd.Series, fast=12, slow=26, signal=9) -> pd.Series:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    return macd - sig


def _compute_sma_crossover(close: pd.Series, fast=9, slow=21) -> pd.Series:
    """Returns separation (fast-slow)/slow — positive=bullish."""
    sma_fast = close.rolling(window=fast, min_periods=fast).mean()
    sma_slow = close.rolling(window=slow, min_periods=slow).mean()
    return (sma_fast - sma_slow) / sma_slow.replace(0, 1e-9)


def _generate_signals_point_in_time(hist: pd.DataFrame) -> pd.DataFrame:
    """
    Generate horizon signals for each historical bar using ONLY data available
    up to and including that bar (expanding window — no lookahead).

    Returns a DataFrame with columns: date, signal_24h, signal_1w, signal_1m
    where signal = 1 (long), -1 (short), 0 (flat).
    """
    close = hist["Close"].dropna()
    if len(close) < 52:  # Need at least ~52 bars for 1M macro proxy
        return pd.DataFrame()

    rsi = _compute_rsi(close)
    macd_hist = _compute_macd_hist(close)
    sma_cross = _compute_sma_crossover(close)

    records = []
    for i in range(52, len(close)):
        date = close.index[i]

        # 24H: RSI + MACD (point-in-time, using only data[0:i])
        rsi_val = _safe(rsi.iloc[i], 50.0)
        macd_val = _safe(macd_hist.iloc[i], 0.0)
        close_val = _safe(close.iloc[i], 1.0)

        rsi_sig = 1 if rsi_val < 40 else (-1 if rsi_val > 60 else 0)
        macd_sig = 1 if macd_val > 0 else (-1 if macd_val < 0 else 0)
        sig_24h_raw = 0.4 * rsi_sig + 0.3 * macd_sig  # OI not available historically
        sig_24h = 1 if sig_24h_raw > 0.1 else (-1 if sig_24h_raw < -0.1 else 0)

        # 1W: SMA crossover + BB %B (simplified for backtesting)
        sma_val = _safe(sma_cross.iloc[i], 0.0)
        sig_1w = 1 if sma_val > 0.002 else (-1 if sma_val < -0.002 else 0)

        # 1M: trend of last 20 bars relative to 50-bar average
        if i >= 50:
            short_avg = float(close.iloc[i-20:i].mean())
            long_avg = float(close.iloc[i-50:i].mean())
            trend_ratio = (short_avg - long_avg) / long_avg if long_avg != 0 else 0.0
            sig_1m = 1 if trend_ratio > 0.01 else (-1 if trend_ratio < -0.01 else 0)
        else:
            sig_1m = 0

        records.append({
            "date": date,
            "close": close_val,
            "signal_24h": sig_24h,
            "signal_1w": sig_1w,
            "signal_1m": sig_1m,
        })

    return pd.DataFrame(records).set_index("date") if records else pd.DataFrame()


def _simulate_trades(signals_df: pd.DataFrame, signal_col: str, hold_bars: int) -> list:
    """
    Simulate trades from signals with slippage.

    Args:
        signals_df: DataFrame with 'close' and signal_col
        signal_col: e.g. 'signal_24h'
        hold_bars:  how many bars to hold the trade (1=24H, 5=1W, 21=1M)

    Returns:
        list of trade dicts: {entry_price, exit_price, signal, return_pct}
    """
    trades = []
    prices = signals_df["close"].values
    sigs = signals_df[signal_col].values
    n = len(prices)

    for i in range(n - hold_bars):
        sig = sigs[i]
        if sig == 0:
            continue
        entry_raw = prices[i]
        exit_raw = prices[i + hold_bars]

        # Apply slippage
        if sig == 1:  # Long
            entry = entry_raw * (1 + SLIPPAGE_PCT)
            exit_p = exit_raw * (1 - SLIPPAGE_PCT)
            ret = (exit_p - entry) / entry * 100
        else:  # Short
            entry = entry_raw * (1 - SLIPPAGE_PCT)
            exit_p = exit_raw * (1 + SLIPPAGE_PCT)
            ret = (entry - exit_p) / entry * 100

        trades.append({
            "entry_price": round(entry, 4),
            "exit_price": round(exit_p, 4),
            "signal": sig,
            "return_pct": round(ret, 4),
            "win": ret > 0,
        })
    return trades


def _compute_metrics(trades: list, horizon: str) -> dict:
    """Compute all required metrics from a list of trade dicts."""
    if not trades:
        return {
            "horizon": horizon, "sample_size": 0,
            "win_rate": None, "avg_return_pct": None,
            "profit_factor": None, "max_drawdown_pct": None,
            "sharpe_ratio": None, "note": "Insufficient data for backtesting.",
        }

    total = len(trades)
    wins = sum(1 for t in trades if t["win"])
    returns = [t["return_pct"] for t in trades]
    win_returns = [r for r in returns if r > 0]
    loss_returns = [r for r in returns if r <= 0]

    win_rate = round(wins / total * 100, 2)
    avg_return = round(sum(returns) / total, 4)

    gross_profit = sum(win_returns) if win_returns else 0.0
    gross_loss = abs(sum(loss_returns)) if loss_returns else 1e-9
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else None

    # Max drawdown on equity curve
    equity = [0.0]
    for r in returns:
        equity.append(equity[-1] + r)
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    max_dd = round(max_dd, 4)

    # Sharpe Ratio (annualized, assuming 252 trading days)
    arr = np.array(returns)
    if arr.std() > 0:
        periods_per_year = {"24H": 252, "1W": 52, "1M": 12}.get(horizon, 252)
        sharpe = round(float((arr.mean() / arr.std()) * math.sqrt(periods_per_year)), 4)
    else:
        sharpe = None

    return {
        "horizon": horizon,
        "sample_size": total,
        "win_rate": win_rate,
        "avg_return_pct": avg_return,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "note": f"Walk-forward backtest. Slippage: {SLIPPAGE_PCT*100:.2f}% per side.",
    }


def run_backtest(ticker: str = "SI=F", period: str = "2y") -> dict:
    """
    Run a full walk-forward backtest for all three horizons.

    Args:
        ticker: Yahoo Finance ticker (default SI=F for silver)
        period: yfinance history period (default 2y)

    Returns:
        dict: {
            "24H": metrics_dict,
            "1W":  metrics_dict,
            "1M":  metrics_dict,
            "data_source": str,
            "bars": int,
            "period": str,
            "error": str | None,
        }
    """
    try:
        hist = yf.Ticker(ticker).history(period=period)
        if hist is None or hist.empty or len(hist) < 55:
            return {
                "24H": {"horizon": "24H", "sample_size": 0, "note": "Insufficient historical data."},
                "1W":  {"horizon": "1W",  "sample_size": 0, "note": "Insufficient historical data."},
                "1M":  {"horizon": "1M",  "sample_size": 0, "note": "Insufficient historical data."},
                "data_source": f"Yahoo Finance ({ticker})",
                "bars": 0, "period": period, "error": "Insufficient data.",
            }
    except Exception as e:
        return {
            "24H": {"horizon": "24H", "sample_size": 0, "note": f"Fetch error: {e}"},
            "1W":  {"horizon": "1W",  "sample_size": 0, "note": f"Fetch error: {e}"},
            "1M":  {"horizon": "1M",  "sample_size": 0, "note": f"Fetch error: {e}"},
            "data_source": f"Yahoo Finance ({ticker})",
            "bars": 0, "period": period, "error": str(e),
        }

    signals_df = _generate_signals_point_in_time(hist)
    if signals_df.empty:
        return {
            "24H": {"horizon": "24H", "sample_size": 0, "note": "Signal generation failed."},
            "1W":  {"horizon": "1W",  "sample_size": 0, "note": "Signal generation failed."},
            "1M":  {"horizon": "1M",  "sample_size": 0, "note": "Signal generation failed."},
            "data_source": f"Yahoo Finance ({ticker})",
            "bars": len(hist), "period": period, "error": "No signals generated.",
        }

    trades_24h = _simulate_trades(signals_df, "signal_24h", hold_bars=1)
    trades_1w = _simulate_trades(signals_df, "signal_1w", hold_bars=5)
    trades_1m = _simulate_trades(signals_df, "signal_1m", hold_bars=21)

    return {
        "24H": _compute_metrics(trades_24h, "24H"),
        "1W":  _compute_metrics(trades_1w, "1W"),
        "1M":  _compute_metrics(trades_1m, "1M"),
        "data_source": f"Yahoo Finance ({ticker})",
        "bars": len(hist),
        "period": period,
        "slippage_pct": SLIPPAGE_PCT * 100,
        "error": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
