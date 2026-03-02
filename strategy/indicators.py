import pandas as pd
import pandas_ta as ta
from log.logger import log
from config import (
    EMA_FAST, EMA_SLOW,           # 5m momentum: 9, 21
    EMA_TREND_FAST, EMA_TREND_SLOW,  # HTF trend: 50, 200
    RSI_LENGTH,
    ATR_LENGTH,
    VOL_MA_LENGTH,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    BB_LENGTH, BB_STD,
)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    # ── Trend (higher timeframe proxy on 5m) ──────────────────────────── #
    df["ema50"]  = ta.ema(df["close"], length=EMA_TREND_FAST)
    df["ema200"] = ta.ema(df["close"], length=EMA_TREND_SLOW)

    # ── Short-term momentum EMAs ───────────────────────────────────────── #
    df["ema9"]   = ta.ema(df["close"], length=EMA_FAST)
    df["ema21"]  = ta.ema(df["close"], length=EMA_SLOW)

    # ── RSI ───────────────────────────────────────────────────────────── #
    df["rsi"]    = ta.rsi(df["close"], length=RSI_LENGTH)

    # ── ATR (volatility / position sizing) ────────────────────────────── #
    df["atr"]    = ta.atr(df["high"], df["low"], df["close"], length=ATR_LENGTH)

    # ── Volume MA ─────────────────────────────────────────────────────── #
    df["vol_ma"] = df["volume"].rolling(VOL_MA_LENGTH).mean()

    # ── MACD ──────────────────────────────────────────────────────────────── #
    macd = ta.macd(df["close"], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
    # Column names vary by pandas_ta version — grab by position instead of hardcoded name
    df["macd"]        = macd.iloc[:, 0]   # MACD line
    df["macd_signal"] = macd.iloc[:, 1]   # Signal line  
    df["macd_hist"]   = macd.iloc[:, 2]   # Histogram

    # ── Bollinger Bands ────────────────────────────────────────────────── #
    bb = ta.bbands(df["close"], length=BB_LENGTH, std=BB_STD)
    # Same — grab by position: lower, mid, upper, bandwidth, %b
    df["bb_lower"] = bb.iloc[:, 0]
    df["bb_mid"]   = bb.iloc[:, 1]
    df["bb_upper"] = bb.iloc[:, 2]
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

    log("Added indicators: ema9, ema21, ema50, ema200, rsi, atr, vol_ma, macd, bbands")
    return df
