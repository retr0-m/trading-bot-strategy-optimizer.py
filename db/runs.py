"""
db/runs.py
──────────
SQLite interface for storing optimization runs.
Query: "give me top 10 strategies by Calmar"
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime

RUNS_DB = Path("log/db/runs.db")


class RunsDB:
    def __init__(self):
        RUNS_DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(RUNS_DB, check_same_thread=False)
        self._init()

    def _init(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                params       TEXT    NOT NULL,
                pnl          REAL,
                calmar       REAL,
                sharpe       REAL,
                max_drawdown REAL,
                win_rate     REAL,
                n_trades     INTEGER,
                score        REAL,
                is_best      INTEGER DEFAULT 0,
                created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def save_run(self, params: dict, metrics: dict, score: float, is_best: bool = False):
        self.conn.execute("""
            INSERT INTO runs (params,pnl,calmar,sharpe,max_drawdown,win_rate,n_trades,score,is_best)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            json.dumps(params),
            metrics.get("pnl", 0),
            metrics.get("calmar", 0),
            metrics.get("sharpe", 0),
            metrics.get("max_drawdown", 1),
            metrics.get("win_rate", 0),
            metrics.get("n_trades", 0),
            score,
            1 if is_best else 0,
        ))
        self.conn.commit()

    def get_best(self, n: int = 1) -> list[dict]:
        rows = self.conn.execute("""
            SELECT params, pnl, calmar, sharpe, max_drawdown, win_rate, n_trades, score, created_at
            FROM runs ORDER BY score DESC LIMIT ?
        """, (n,)).fetchall()
        return [{"params": json.loads(r[0]), "pnl": r[1], "calmar": r[2],
                 "sharpe": r[3], "max_drawdown": r[4], "win_rate": r[5],
                 "n_trades": r[6], "score": r[7], "created_at": r[8]} for r in rows]

    def close(self):
        self.conn.close()