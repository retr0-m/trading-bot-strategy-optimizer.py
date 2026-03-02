"""
data/fetcher.py
───────────────
Paginated Binance kline fetch with SQLite cache.
"""
import sqlite3
import time
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
from binance.client import Client
from log.logger import log

CACHE_DB = Path("log/db/kline_cache.db")


def _init_cache():
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(CACHE_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS klines (
                symbol TEXT, interval TEXT, time INTEGER,
                open REAL, high REAL, low REAL, close REAL, volume REAL,
                PRIMARY KEY (symbol, interval, time)
            )
        """)


def _to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def fetch(client: Client, symbol: str, interval: str,
          start: datetime, end: datetime) -> pd.DataFrame:
    _init_cache()
    start_ms = _to_ms(start)
    end_ms   = _to_ms(end)

    with sqlite3.connect(CACHE_DB) as conn:
        cached = pd.read_sql("""
            SELECT time,open,high,low,close,volume FROM klines
            WHERE symbol=? AND interval=? AND time BETWEEN ? AND ?
            ORDER BY time ASC
        """, conn, params=(symbol, interval, start_ms, end_ms))

    cached_times = set(cached["time"].tolist()) if not cached.empty else set()
    log(f"[fetcher] {symbol} — {len(cached_times)} candles in cache, fetching missing from Binance...")

    new_rows    = []
    fetch_start = start_ms
    pages       = 0

    while fetch_start < end_ms:
        klines = client.get_klines(symbol=symbol, interval=interval,
                                    startTime=fetch_start, endTime=end_ms, limit=1000)
        if not klines:
            break

        pages += 1
        for k in klines:
            t = int(k[0])
            if t not in cached_times:
                new_rows.append((symbol, interval, t,
                                  float(k[1]), float(k[2]), float(k[3]),
                                  float(k[4]), float(k[5])))

        fetch_start = int(klines[-1][0]) + 1
        log(f"[fetcher] {symbol} page {pages} — fetched {len(klines)} candles, {len(new_rows)} new total")

        if len(klines) < 1000:
            break
        time.sleep(0.15)

    if new_rows:
        with sqlite3.connect(CACHE_DB) as conn:
            conn.executemany("""
                INSERT OR IGNORE INTO klines (symbol,interval,time,open,high,low,close,volume)
                VALUES (?,?,?,?,?,?,?,?)
            """, new_rows)
        log(f"[fetcher] {symbol} — cached {len(new_rows)} new candles")
    else:
        log(f"[fetcher] {symbol} — all data already cached, no Binance call needed")

    with sqlite3.connect(CACHE_DB) as conn:
        df = pd.read_sql("""
            SELECT time,open,high,low,close,volume FROM klines
            WHERE symbol=? AND interval=? AND time BETWEEN ? AND ?
            ORDER BY time ASC
        """, conn, params=(symbol, interval, start_ms, end_ms))

    df = df.astype({"open": float,"high": float,"low": float,"close": float,"volume": float})
    log(f"[fetcher] {symbol} — returning {len(df)} total candles")
    return df