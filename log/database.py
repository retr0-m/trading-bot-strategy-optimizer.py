import sqlite3
from pathlib import Path
from log.logger import log

DB_PATH = Path("log/db/portfolio.db")


class TempConnection:
    """Thread-safe read-only queries."""

    @staticmethod
    def get_all_trades():
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, symbol, side, price, amount, fee, balance_after, sl, tp, timestamp
                FROM trades ORDER BY id ASC
            """)
            return cursor.fetchall()

    @staticmethod
    def get_last_trade(symbol: str):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT side, price, amount, balance_after, timestamp, sl, tp
                FROM trades WHERE symbol = ?
                ORDER BY id DESC LIMIT 1
            """, (symbol,))
            return cursor.fetchone()


class PortfolioDB:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._create_tables()
        self.temp_connection = TempConnection()
        log(f"Database initialized at {DB_PATH}")

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol       TEXT    NOT NULL,
                side         TEXT    NOT NULL,
                price        REAL    NOT NULL,
                amount       REAL    NOT NULL,
                fee          REAL    NOT NULL,
                balance_after REAL   NOT NULL,
                sl           REAL    DEFAULT 0.0,
                tp           REAL    DEFAULT 0.0,
                timestamp    TEXT    DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.commit()

    def log_trade(self, symbol, side, price, amount, fee, balance_after, sl=0.0, tp=0.0):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO trades (symbol, side, price, amount, fee, balance_after, sl, tp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, side, price, amount, fee, balance_after, sl, tp))
        self.conn.commit()
        log(f"DB | {side} | {symbol} | price={price:.4f} qty={amount:.6f} fee={fee:.4f} balance={balance_after:.2f}")

    def close(self):
        self.conn.close()
