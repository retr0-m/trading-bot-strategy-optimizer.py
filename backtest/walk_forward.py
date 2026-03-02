"""
backtest/walk_forward.py
────────────────────────
Rolling walk-forward: train N years → test 1 year, slide forward.
"""
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
import pandas as pd
from backtest.engine import run
from log.logger import log


def split_df(df: pd.DataFrame, train_years: int = 3, test_years: int = 1) -> list[tuple]:
    if df.empty:
        return []
    df = df.copy()
    df["dt"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    start  = df["dt"].min().to_pydatetime()
    end    = df["dt"].max().to_pydatetime()
    folds  = []
    cursor = start

    while True:
        train_end = cursor + relativedelta(years=train_years)
        test_end  = train_end + relativedelta(years=test_years)
        if test_end > end:
            break
        train_df = df[(df["dt"] >= cursor) & (df["dt"] < train_end)].drop(columns="dt")
        test_df  = df[(df["dt"] >= train_end) & (df["dt"] < test_end)].drop(columns="dt")
        if len(train_df) > 500 and len(test_df) > 100:
            folds.append((train_df.reset_index(drop=True), test_df.reset_index(drop=True)))
        cursor += relativedelta(years=test_years)

    log(f"[walk_forward] generated {len(folds)} folds (train={train_years}yr test={test_years}yr)")
    return folds


def evaluate(dfs_by_symbol: dict, p: dict, train_years: int = 3, test_years: int = 1) -> dict:
    log(f"[walk_forward] evaluating {list(dfs_by_symbol.keys())} — train={train_years}yr test={test_years}yr")
    all_metrics = []

    for symbol, df in dfs_by_symbol.items():
        folds = split_df(df, train_years, test_years)
        if not folds:
            log(f"[walk_forward] {symbol} — no valid folds, skipping")
            continue

        for fold_i, (train_df, test_df) in enumerate(folds):
            log(f"[walk_forward] {symbol} fold {fold_i+1}/{len(folds)} — test size={len(test_df)}")
            metrics = run(test_df, p, symbol=symbol)
            metrics["symbol"] = symbol
            metrics["fold"]   = fold_i + 1
            all_metrics.append(metrics)
            log(f"[walk_forward] {symbol} fold {fold_i+1} result: {metrics}")

    if not all_metrics:
        log("[walk_forward] no metrics collected — returning zeros")
        return {"calmar": 0, "sharpe": 0, "max_drawdown": 1, "win_rate": 0, "n_trades": 0, "pnl": 0}

    keys   = ["calmar", "sharpe", "max_drawdown", "win_rate", "n_trades", "pnl"]
    result = {k: round(sum(m[k] for m in all_metrics) / len(all_metrics), 4) for k in keys}
    log(f"[walk_forward] averaged across {len(all_metrics)} folds/symbols: {result}")
    return result