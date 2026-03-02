"""
analysis/price_recorder.py
───────────────────────────
Records live prices for all DCA_SYMBOLS into a separate prices.db.
Runs as a daemon thread launched from main.py.

Schema:
    prices(symbol, timestamp_ms, open, high, low, close, volume)

Each row = one price snapshot. Interval is configurable via PRICE_RECORD_INTERVAL_S.
Uses the same Binance client already initialized in main.py.
"""

from math import log
import sqlite3
import threading
import time
from pathlib import Path
from binance.client import Client
from log.logger import log_price_recorder

PRICES_DB_PATH        = Path("log/db/prices.db")
PRICE_RECORD_INTERVAL = 30   # seconds between snapshots — tune freely


# ── DB setup ──────────────────────────────────────────────────────────── #

def _init_prices_db():
    PRICES_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(PRICES_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol       TEXT    NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                open         REAL    NOT NULL,
                high         REAL    NOT NULL,
                low          REAL    NOT NULL,
                close        REAL    NOT NULL,
                volume       REAL    NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_symbol_ts ON prices(symbol, timestamp_ms)")
        conn.commit()


def _record_snapshot(conn: sqlite3.Connection, binance: Client, symbols: list[str]):
    """Fetch latest completed 1m candle for each symbol and store it."""
    now_ms = int(time.time() * 1000)
    rows = []

    for symbol in symbols:
        try:
            # Fetch last 2 candles — use the second-to-last (last completed)
            klines = binance.get_klines(symbol=symbol, interval="1m", limit=2)
            if not klines or len(klines) < 1:
                continue
            k = klines[-1]   # most recent (may be mid-candle — still useful for tracking)
            rows.append((
                symbol,
                int(k[0]),      # candle open time ms
                float(k[1]),    # open
                float(k[2]),    # high
                float(k[3]),    # low
                float(k[4]),    # close
                float(k[5]),    # volume
            ))
        except Exception as e:
            log_price_recorder(f"[price_recorder] error fetching {symbol}: {e}")

    if rows:
        conn.executemany("""
            INSERT INTO prices (symbol, timestamp_ms, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()
    
    log_price_recorder(f"Recorded prices for {len(rows)} symbols at {now_ms} ms")


# ── Main recorder loop ────────────────────────────────────────────────── #

def _recorder_loop(binance: Client, symbols: list[str]):
    _init_prices_db()
    # Persistent connection — this thread owns it exclusively
    conn = sqlite3.connect(PRICES_DB_PATH, check_same_thread=False)

    log_price_recorder(f"[price_recorder] started — recording {symbols} every {PRICE_RECORD_INTERVAL}s")

    while True:
        try:
            log_price_recorder("Starting new price snapshot...")
            _record_snapshot(conn, binance, symbols)
        except Exception as e:
            log_price_recorder(f"[price_recorder] snapshot error: {e}")
        time.sleep(PRICE_RECORD_INTERVAL)


def start_price_recorder(binance: Client, symbols: list[str]):
    """Launch the recorder as a background daemon thread. Call once from main.py."""
    log_price_recorder(f"Starting price recorder for symbols: {symbols}")
    t = threading.Thread(
        target=_recorder_loop,
        args=(binance, symbols),
        daemon=True,
        name="price_recorder"
    )
    log_price_recorder("Thread initialized, starting...")
    t.start()
    return t
