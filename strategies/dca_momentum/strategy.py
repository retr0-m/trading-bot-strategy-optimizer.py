"""
strategies/dca_momentum/strategy.py
────────────────────────────────────
Entry + exit logic. Takes params dict. Zero global config imports.
"""
import pandas as pd
from indicators.library import add_all
from log.logger import log

FEE_RATE = 0.001


def prepare(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    return add_all(df, p)


def should_entry(row, prev_row, high: float, dca_state: dict, p: dict) -> tuple[bool, float]:
    price = row["close"]
    if high <= 0:
        return False, 0.0

    # Gate 1: DCA level
    drop_pct      = (high - price) / high * 100
    last_trigger  = dca_state.get("last_trigger_pct", 0.0)
    current_level = int(drop_pct / p["dca_drop_step_pct"])
    last_level    = int(last_trigger / p["dca_drop_step_pct"])
    if not (current_level > last_level and drop_pct >= p["dca_drop_step_pct"]):
        return False, 0.0

    # Gate 2: ATR edge
    expected = row["atr"] / price
    required = 2 * FEE_RATE + p["min_edge_pct"]
    log(f"[entry] ATR edge={expected:.4%} required={required:.4%}")
    if expected < required:
        log(f"[entry] blocked: ATR edge too small")
        return False, 0.0

    # Gate 3: HTF bias
    htf_bull = row["ema_trend_fast"] > row["ema_trend_slow"]
    log(f"[entry] HTF bias={'BULL' if htf_bull else 'BEAR'} (required={p['htf_trend_required']})")
    if p["htf_trend_required"] and not htf_bull:
        log(f"[entry] blocked: HTF trend is bearish")
        return False, 0.0

    # Gate 4: ADX filter
    log(f"[entry] ADX={row['adx']:.1f} min={p['adx_min']}")
    if p["adx_min"] > 0 and row["adx"] < p["adx_min"]:
        log(f"[entry] blocked: ADX too low ({row['adx']:.1f} < {p['adx_min']})")
        return False, 0.0

    # Gate 5: Confluence score
    ema_bull  = (row["ema_fast"] > row["ema_slow"]) and (row["close"] > row["ema_fast"])
    rsi_bull  = (p["rsi_bull_zone"] <= row["rsi"] <= p["rsi_max"]) or (row["rsi"] < p["rsi_oversold"])
    vol_bull  = (row["volume"] / row["vol_ma"]) >= p["volume_spike_mult"] if row["vol_ma"] > 0 else False
    macd_bull = row["macd_hist"] > 0
    bb_bull   = (row["close"] > row["bb_upper"]) and (row["bb_width"] > prev_row["bb_width"])
    srsi_bull = row["stochrsi_k"] > row["stochrsi_d"] and row["stochrsi_k"] < 80

    score = sum([ema_bull, rsi_bull, vol_bull, macd_bull, bb_bull, srsi_bull])
    signals = [n for n, v in zip(["EMA","RSI","VOL","MACD","BB","SRSI"],
                                   [ema_bull, rsi_bull, vol_bull, macd_bull, bb_bull, srsi_bull]) if v]
    log(f"[entry] confluence score={score}/{p['min_confluence']} signals={signals}")
    log(f"[entry]   RSI={row['rsi']:.1f} | vol_ratio={row['volume']/row['vol_ma']:.2f}x | "
        f"macd_hist={row['macd_hist']:.4f} | bb_width={row['bb_width']:.4f} | "
        f"stochRSI_k={row['stochrsi_k']:.1f}")

    if score < p["min_confluence"]:
        log(f"[entry] blocked: score {score} < {p['min_confluence']} required")
        return False, 0.0

    spend_usd = min(round(drop_pct, 2), p["dca_max_spend"])
    log(f"[entry] ✓ ALL GATES PASSED — spend=${spend_usd:.2f}")
    return True, spend_usd


def get_tp_sl(avg_entry: float, atr: float, price: float, p: dict) -> tuple[float, float]:
    sl = avg_entry - (p["sl_multiplier"] * atr) + (FEE_RATE * price) * 2
    tp = avg_entry + (p["tp_multiplier"] * atr)
    return sl, tp


def should_exit(price: float, avg_entry: float, peak: float, atr: float, p: dict) -> str | None:
    sl, tp = get_tp_sl(avg_entry, atr, price, p)

    # Break-even floor
    if price > avg_entry * (1 + p["breakeven_trigger_pct"]):
        breakeven = avg_entry * (1 + 2 * FEE_RATE)
        sl = max(sl, breakeven)
        log(f"[exit] break-even active — floor at {breakeven:.4f}")

    # Trailing stop
    profit_pct = (peak - avg_entry) / avg_entry if avg_entry > 0 else 0
    if profit_pct >= p["trail_start_pct"]:
        trailing = peak * (1 - p["trail_distance_pct"])
        sl = max(sl, trailing)
        log(f"[exit] trailing stop active — profit={profit_pct:.2%} peak={peak:.4f} trail_sl={trailing:.4f}")

    log(f"[exit] price={price:.4f} sl={sl:.4f} tp={tp:.4f} avg_entry={avg_entry:.4f}")

    if price <= sl:
        log(f"[exit] → STOP triggered")
        return "stop"
    if price >= tp:
        log(f"[exit] → TAKE PROFIT triggered")
        return "take_profit"

    log(f"[exit] → HOLD")
    return None