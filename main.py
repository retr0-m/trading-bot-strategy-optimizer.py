"""
main.py
───────
Usage:
    python main.py                        # live paper trading (unchanged)
    python main.py --backtest             # run Optuna optimization
    python main.py --backtest --trials 100
    python3.12 main.py --backtest --trials 50 --train-years 3 --test-years 1
"""
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--backtest", action="store_true", help="Run Optuna optimization")
parser.add_argument("--trials",   type=int, default=50, help="Number of Optuna trials")
parser.add_argument("--train-years", type=int, default=3)
parser.add_argument("--test-years",  type=int, default=1)
args = parser.parse_args()

# ── Backtest mode ─────────────────────────────────────────────────────── #
if args.backtest:
    from dotenv import load_dotenv
    import os
    from binance.client import Client
    from optimize.optimizer import run_optimization

    load_dotenv()
    client = Client(os.getenv("API_KEY"), os.getenv("API_SECRET"))

    best_params, best_metrics = run_optimization(
        client,
        n_trials=args.trials,
        train_years=args.train_years,
        test_years=args.test_years,
    )
    print("\nDone. Best params saved to log/db/runs.db")
    raise SystemExit(0)

# ── Live trading mode (original code below, untouched) ────────────────── #
from dotenv import load_dotenv
import os, time
import pandas as pd
from binance.client import Client
import requests.exceptions

load_dotenv()
API_KEY    = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

from config import *
from strategy.indicators import add_indicators
from strategy.logic import should_long_dca
from strategy.exits import should_exit, reset_symbol
from paper.portfolio import PaperPortfolio
from log.logger import log
from log.database import PortfolioDB
from app.dashboard import start_server_in_thread
from analysis.price_recorder import start_price_recorder
from data.news_fetcher import start_news_fetcher

log("Starting DCA bot...")

binance     = Client(API_KEY, API_SECRET)
portfolioDB = PortfolioDB()
portfolio   = PaperPortfolio(starting_balance=START_BALANCE, db_obj=portfolioDB, leverage=LEVERAGE)

start_server_in_thread(portfolioDB)
start_price_recorder(binance, DCA_SYMBOLS)
start_news_fetcher()

banner = r"""
██████╗  ██████╗ █████╗     ██████╗  ██████╗ ████████╗
██╔══██╗██╔════╝██╔══██╗    ██╔══██╗██╔═══██╗╚══██╔══╝
██║  ██║██║     ███████║    ██████╔╝██║   ██║   ██║   
██║  ██║██║     ██╔══██║    ██╔══██╗██║   ██║   ██║   
██████╔╝╚██████╗██║  ██║    ██████╔╝╚██████╔╝   ██║   
╚═════╝  ╚═════╝╚═╝  ╚═╝    ╚═════╝  ╚═════╝    ╚═╝   
"""
print(banner)

if LESS_STRICT_SHOULD_LONG:
    log("WARNING: LESS_STRICT_SHOULD_LONG is ENABLED")

while True:
    try:
        for symbol_name, symbol in portfolio.symbols.items():
            log(f"── Processing {symbol_name} ──")
            klines = binance.get_klines(symbol=symbol_name,
                                         interval=Client.KLINE_INTERVAL_5MINUTE, limit=300)
            df = pd.DataFrame(klines, columns=[
                "time","open","high","low","close","volume","_","_","_","_","_","_"
            ]).astype({"open":float,"high":float,"low":float,"close":float,"volume":float})
            df = add_indicators(df)
            last = df.iloc[-1]
            high = df["high"].iloc[-DCA_HIGH_LOOKBACK_CANDLES:].max()
            symbol._last_high = high
            current_price = last.close
            log(f"{symbol_name} — price={current_price:.4f}, high={high:.4f}, atr={last.atr:.6f}")

            if symbol.in_position():
                if symbol.check_liquidation(current_price):
                    symbol.sell(current_price, FEE_RATE)
                    reset_symbol(symbol_name)
                    continue
                exit_reason = should_exit(symbol.entry_price, symbol, current_price, last.atr, symbol_name)
                if exit_reason:
                    symbol.sell(current_price, FEE_RATE)
                    reset_symbol(symbol_name)
                    print(f"[SELL {exit_reason.upper()}] {symbol_name} @ {current_price:.4f} | Balance: {portfolio.balance:.2f}")
                    continue

            free_balance = portfolio.balance - portfolio.used_margin
            if free_balance < 0.5:
                continue
            if time.time() < symbol.cooldown_until:
                continue

            should_buy, spend_usd = should_long_dca(current_price=current_price, high=high,
                                                    symbol_state=symbol.dca_state, df=df)
            if should_buy:
                ok = symbol.buy(current_price, spend_usd, high, last.atr, fee_rate=FEE_RATE)
                if ok:
                    print(f"[DCA BUY #{symbol.dca_levels}] {symbol_name} @ {current_price:.4f} | Balance: {portfolio.balance:.2f}")

        log(f"── Sleeping {SLEEP_INTERVAL}s ──")
        time.sleep(SLEEP_INTERVAL)

    except requests.exceptions.ReadTimeout:
        time.sleep(5)
    except requests.exceptions.ConnectionError:
        time.sleep(5)
    except Exception as e:
        log(f"Error: {e}")
        import traceback; log(traceback.format_exc())
        time.sleep(5)
