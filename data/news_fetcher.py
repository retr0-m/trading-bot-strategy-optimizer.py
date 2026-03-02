"""
data/news_fetcher.py
────────────────────
Real-time: CryptoPanic free API (CRYPTOPANIC_KEY in .env)
Historical: cryptocurrency.cv (no key)
Fallback:   RSS feeds
"""
import sqlite3, time, threading
from pathlib import Path
from datetime import datetime, timezone
import requests
import feedparser
from dotenv import load_dotenv
import os
from log.logger import log

load_dotenv()
NEWS_DB       = Path("log/db/news.db")
CP_KEY        = os.getenv("CRYPTOPANIC_KEY", "")
POLL_INTERVAL = 300

RSS_FEEDS = [
    ("CoinDesk",      "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt",       "https://decrypt.co/feed"),
]

SYMBOL_KEYWORDS = {
    "BTCUSDT": ["bitcoin", "btc"],
    "ETHUSDT": ["ethereum", "eth"],
    "SOLUSDT": ["solana", "sol"],
}


def _init_db():
    NEWS_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(NEWS_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol       TEXT,
                headline     TEXT NOT NULL,
                source       TEXT,
                sentiment    REAL DEFAULT 0.0,
                published_at INTEGER,
                fetched_at   INTEGER,
                url          TEXT,
                UNIQUE(headline, published_at)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sym_ts ON news(symbol, published_at)")


def _insert(rows: list[tuple]):
    with sqlite3.connect(NEWS_DB) as conn:
        conn.executemany("""
            INSERT OR IGNORE INTO news (symbol,headline,source,sentiment,published_at,fetched_at,url)
            VALUES (?,?,?,?,?,?,?)
        """, rows)


def _detect_symbol(text: str) -> str:
    t = text.lower()
    for sym, keywords in SYMBOL_KEYWORDS.items():
        if any(k in t for k in keywords):
            return sym
    return "GENERAL"


def _keyword_sentiment(text: str) -> float:
    BULL = ["surge","rally","bullish","gains","rises","breakout","buy","moon","soar","ATH"]
    BEAR = ["crash","drop","bearish","falls","dumps","sell","fear","liquidation","plunge","ban"]
    t     = text.lower()
    score = sum(1 for w in BULL if w in t) - sum(1 for w in BEAR if w in t)
    return max(-1.0, min(1.0, score / 3))


def _fetch_cryptopanic() -> list[tuple]:
    if not CP_KEY:
        log("[news] CryptoPanic key not set — skipping (set CRYPTOPANIC_KEY in .env)")
        return []
    log("[news] fetching from CryptoPanic...")
    try:
        r    = requests.get("https://cryptopanic.com/api/free/v1/posts/",
                             params={"auth_token": CP_KEY, "public": "true", "kind": "news"},
                             timeout=10)
        data = r.json().get("results", [])
        log(f"[news] CryptoPanic returned {len(data)} articles")
    except Exception as e:
        log(f"[news] CryptoPanic fetch error: {e}")
        return []

    rows = []
    now  = int(time.time() * 1000)
    for item in data:
        headline  = item.get("title", "")
        source    = item.get("source", {}).get("title", "CryptoPanic")
        votes     = item.get("votes", {})
        pos, neg  = votes.get("positive", 0), votes.get("negative", 0)
        total     = pos + neg
        sentiment = (pos - neg) / total if total > 0 else 0.0
        try:
            published_ms = int(datetime.fromisoformat(
                item.get("published_at","").replace("Z","+00:00")).timestamp() * 1000)
        except Exception:
            published_ms = now
        rows.append((_detect_symbol(headline), headline, source,
                     sentiment, published_ms, now, item.get("url","")))
    return rows


def _fetch_rss() -> list[tuple]:
    rows = []
    now  = int(time.time() * 1000)
    for source, feed_url in RSS_FEEDS:
        log(f"[news] fetching RSS — {source}")
        try:
            feed = feedparser.parse(feed_url)
            count = 0
            for entry in feed.entries[:20]:
                headline     = entry.get("title", "")
                url          = entry.get("link", "")
                published_ms = now
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published_ms = int(time.mktime(entry.published_parsed) * 1000)
                rows.append((_detect_symbol(headline), headline, source,
                             _keyword_sentiment(headline), published_ms, now, url))
                count += 1
            log(f"[news] RSS {source} — {count} articles")
        except Exception as e:
            log(f"[news] RSS {source} error: {e}")
    return rows


def fetch_historical(symbol: str, start_year: int = 2021, end_year: int = 2025):
    """One-time historical fetch. Call before running backtest."""
    _init_db()
    ticker = symbol.replace("USDT", "")
    log(f"[news] fetching historical articles for {symbol} ({ticker}) from cryptocurrency.cv...")
    now  = int(time.time() * 1000)
    rows = []
    try:
        r    = requests.get("https://cryptocurrency.cv/api/archive",
                            params={"ticker": ticker, "limit": 500}, timeout=15)
        data = r.json()
        articles = data if isinstance(data, list) else data.get("data", [])
        for item in articles:
            headline     = item.get("title", "")
            source       = item.get("source", "cryptocurrency.cv")
            published_ms = int(item.get("published_at", now / 1000)) * 1000
            rows.append((symbol, headline, source, _keyword_sentiment(headline),
                        published_ms, now, item.get("url","")))
        log(f"[news] historical fetch for {symbol} — {len(rows)} articles")
    except Exception as e:
        log(f"[news] historical fetch failed for {symbol}: {e}")

    if rows:
        _insert(rows)
    log(f"[news] stored {len(rows)} historical articles for {symbol}")


def _poll_loop():
    _init_db()
    log(f"[news] daemon started — polling every {POLL_INTERVAL}s")
    while True:
        rows = _fetch_cryptopanic() + _fetch_rss()
        if rows:
            _insert(rows)
            log(f"[news] stored {len(rows)} articles this cycle")
        else:
            log(f"[news] no new articles this cycle")
        time.sleep(POLL_INTERVAL)


def start_news_fetcher():
    t = threading.Thread(target=_poll_loop, daemon=True, name="news_fetcher")
    t.start()
    log("[news] fetcher thread started")
    return t


def get_sentiment(symbol: str, from_ms: int, to_ms: int) -> float:
    """Avg sentiment for a symbol in a time window. Used by backtest engine."""
    _init_db()
    with sqlite3.connect(NEWS_DB) as conn:
        rows = conn.execute("""
            SELECT sentiment FROM news
            WHERE (symbol=? OR symbol='GENERAL') AND published_at BETWEEN ? AND ?
        """, (symbol, from_ms, to_ms)).fetchall()
    result = sum(r[0] for r in rows) / len(rows) if rows else 0.0
    log(f"[news] sentiment for {symbol} [{from_ms}→{to_ms}] = {result:.3f} ({len(rows)} articles)")
    return result