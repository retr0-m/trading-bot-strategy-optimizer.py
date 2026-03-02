"""
indicators/library.py
─────────────────────
Pure functions. No config imports. Strategies pick what they need.
"""
import pandas as pd
import pandas_ta as ta
from log.logger import log


def ema(df, length, col="close"):       return ta.ema(df[col], length=length)
def rsi(df, length=14):                 return ta.rsi(df["close"], length=length)
def atr(df, length=14):                 return ta.atr(df["high"], df["low"], df["close"], length=length)
def volume_ma(df, length=20):           return df["volume"].rolling(length).mean()
def obv(df):                            return ta.obv(df["close"], df["volume"])
def cci(df, length=20):                 return ta.cci(df["high"], df["low"], df["close"], length=length)

def macd(df, fast=12, slow=26, signal=9):
    r = ta.macd(df["close"], fast=fast, slow=slow, signal=signal)
    return pd.DataFrame({"macd": r.iloc[:,0], "macd_signal": r.iloc[:,1], "macd_hist": r.iloc[:,2]}, index=df.index)

def bbands(df, length=20, std=2.0):
    r = ta.bbands(df["close"], length=length, std=std)
    out = pd.DataFrame({"bb_lower": r.iloc[:,0], "bb_mid": r.iloc[:,1], "bb_upper": r.iloc[:,2]}, index=df.index)
    out["bb_width"] = (out["bb_upper"] - out["bb_lower"]) / out["bb_mid"]
    return out

def stoch_rsi(df, length=14):
    r = ta.stochrsi(df["close"], length=length, rsi_length=length, k=3, d=3)
    return pd.DataFrame({"stochrsi_k": r.iloc[:,0], "stochrsi_d": r.iloc[:,1]}, index=df.index)

def adx(df, length=14):
    r = ta.adx(df["high"], df["low"], df["close"], length=length)
    return pd.DataFrame({"adx": r.iloc[:,0], "dmp": r.iloc[:,1], "dmn": r.iloc[:,2]}, index=df.index)

def add_all(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    """Attach all indicators using a params dict. Returns new df."""
    log(f"[indicators] computing all indicators — {len(df)} candles")
    df = df.copy()
    df["ema_fast"]       = ema(df, p["ema_fast"])
    df["ema_slow"]       = ema(df, p["ema_slow"])
    df["ema_trend_fast"] = ema(df, p["ema_trend_fast"])
    df["ema_trend_slow"] = ema(df, p["ema_trend_slow"])
    df["rsi"]            = rsi(df, p["rsi_length"])
    df["atr"]            = atr(df, p["atr_length"])
    df["vol_ma"]         = volume_ma(df, p["vol_ma_length"])
    df[["macd","macd_signal","macd_hist"]]          = macd(df, p["macd_fast"], p["macd_slow"], p["macd_signal"])
    df[["bb_lower","bb_mid","bb_upper","bb_width"]] = bbands(df, p["bb_length"], p["bb_std"])
    df[["adx","dmp","dmn"]]                         = adx(df, p.get("adx_length", 14))
    df[["stochrsi_k","stochrsi_d"]]                 = stoch_rsi(df, p.get("rsi_length", 14))
    log(f"[indicators] done — columns: {[c for c in df.columns if c not in ['time','open','high','low','close','volume']]}")
    return df