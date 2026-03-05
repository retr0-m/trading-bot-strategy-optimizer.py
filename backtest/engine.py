"""
backtest/engine.py
──────────────────
Simulate DCA strategy on a price DataFrame. Returns metrics dict.
"""
import pandas as pd
from strategies.dca_momentum.strategy import prepare, should_entry, should_exit, get_tp_sl, FEE_RATE
from log.logger import log


def run(df: pd.DataFrame, p: dict, symbol: str = "", start_balance: float = 100.0) -> dict:
    log(f"[engine] starting backtest — {symbol} {len(df)} candles, balance=${start_balance}")
    df = prepare(df, p).dropna().reset_index(drop=True)

    if len(df) < 50:
        log(f"[engine] not enough candles after dropna ({len(df)}), skipping")
        return _empty_metrics()

    balance      = start_balance
    peak_balance = start_balance
    max_dd       = 0.0
    equity_curve = [start_balance]

    position = 0.0; total_cost = 0.0; avg_entry = 0.0
    peak_price = 0.0; dca_state = {"last_trigger_pct": 0.0}
    cooldown_end = -1
    trades   = []
    lookback = p["dca_high_lookback"]
    n_candles = len(df)  # ← track real candle count for time calc

    for i in range(max(50, lookback), len(df)):
        row      = df.iloc[i]
        prev_row = df.iloc[i - 1]
        price    = row["close"]
        high     = df["high"].iloc[max(0, i - lookback):i].max()

        # ── Intra-candle equity (unrealized) for drawdown tracking ── #
        unrealized = (price - avg_entry) * position if position > 0 else 0
        current_equity = balance + unrealized
        peak_balance   = max(peak_balance, current_equity)
        dd = (peak_balance - current_equity) / peak_balance if peak_balance > 0 else 0
        max_dd = max(max_dd, dd)

        if position > 0:
            peak_price = max(peak_price, price)
            reason = should_exit(price, avg_entry, peak_price, row["atr"], p)
            if reason:
                qty      = position
                fee      = qty * price * FEE_RATE
                pnl      = (price - avg_entry) * qty - fee
                balance += total_cost + pnl
                trades.append({"pnl": pnl, "reason": reason})
                log(f"[engine] {symbol} SELL [{reason}] price={price:.4f} pnl={pnl:.4f} balance={balance:.2f}")

                position = 0.0; total_cost = 0.0; avg_entry = 0.0
                peak_price = 0.0; dca_state = {"last_trigger_pct": 0.0}
                cooldown_end = i + int(p["dca_cooldown_s"] / 5 / 60)
                equity_curve.append(balance)
                continue

        if i < cooldown_end:
            continue

        buy, spend = should_entry(row, prev_row, high, dca_state, p)
        if buy and balance >= spend:
            fee         = spend * FEE_RATE
            qty         = (spend - fee) / price
            balance    -= spend + fee
            total_cost += spend
            position   += qty
            avg_entry   = total_cost / position
            dca_state["last_trigger_pct"] = (high - price) / high * 100
            peak_price  = price
            log(f"[engine] {symbol} BUY price={price:.4f} spend={spend:.2f} avg_entry={avg_entry:.4f} balance={balance:.2f}")

    metrics = _calc_metrics(trades, equity_curve, max_dd, start_balance, n_candles)
    log(f"[engine] {symbol} done — {metrics}")
    return metrics


def _calc_metrics(trades, equity, max_dd, start, n_candles) -> dict:
    import math
    n = len(trades)
    if n == 0:
        return _empty_metrics()

    pnl      = sum(t["pnl"] for t in trades)
    winners  = [t for t in trades if t["pnl"] > 0]
    win_rate = len(winners) / n

    # ← Use actual candle count, not trade count
    years    = n_candles * 5 / (60 * 24 * 365)
    end_bal  = equity[-1] if equity else start
    ann_ret  = (end_bal / start) ** (1 / max(years, 0.1)) - 1
    calmar   = ann_ret / max_dd if max_dd > 0 else 0

    if len(equity) > 1:
        rets   = [(equity[i] - equity[i-1]) / equity[i-1] for i in range(1, len(equity))]
        mean_r = sum(rets) / len(rets)
        std_r  = math.sqrt(sum((r - mean_r)**2 for r in rets) / len(rets)) if len(rets) > 1 else 0
        sharpe = (mean_r / std_r) * math.sqrt(252) if std_r > 0 else 0
    else:
        sharpe = 0

    return {"pnl": round(pnl, 4), "calmar": round(calmar, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4), "win_rate": round(win_rate, 4), "n_trades": n}
    
    
def _empty_metrics() -> dict:
    return {"pnl": 0, "calmar": 0, "sharpe": 0, "max_drawdown": 1, "win_rate": 0, "n_trades": 0}
