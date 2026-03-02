import pandas as pd
from log.logger import log
from config import (
    # DCA structure
    DCA_DROP_STEP_PCT,
    DCA_MAX_SPEND_PER_LEVEL,
    # Fee / edge
    FEE_RATE,
    LESS_STRICT_SHOULD_LONG,
    MIN_EDGE_PCT,
    # Momentum score thresholds
    MIN_CONFLUENCE_SCORE,
    # RSI
    RSI_BULL_ZONE,          # e.g. 55 — above = momentum
    RSI_MAX,                # e.g. 75 — above = overbought, skip
    RSI_OVERSOLD,           # e.g. 45 — below = washed out (bonus point)
    # Volume
    VOLUME_SPIKE_MULT,      # e.g. 1.5 — volume must be this × vol_ma
    # Bollinger Bands
    BB_SQUEEZE_THRESHOLD,   # e.g. 0.02 — bb_width below this = squeeze
    # HTF bias
    HTF_TREND_REQUIRED,     # True = skip entries when 50/200 trend is bearish
)


# ─────────────────────────────────────────────────────────────────────── #
#  Sub-checks (each returns bool + log string for clean debugging)        #
# ─────────────────────────────────────────────────────────────────────── #

def _check_htf_bias(row) -> tuple[bool, str]:
    """
    Higher-timeframe proxy: EMA50 > EMA200 on 5m.
    Keeps us on the right side of the macro trend.
    """
    bullish = row["ema50"] > row["ema200"]
    gap_pct = (row["ema50"] - row["ema200"]) / row["ema200"] * 100
    return bullish, f"htf_bias={'BULL' if bullish else 'BEAR'} (ema50-ema200={gap_pct:+.2f}%)"


def _check_momentum_ema(row, prev_row) -> tuple[bool, str]:
    """
    Short-term momentum: 9 EMA crossed above 21 EMA on this candle,
    and price closed above both. Signals acceleration beginning.
    """
    crossed = (row["ema9"] > row["ema21"]) and (prev_row["ema9"] <= prev_row["ema21"])
    above_both = row["close"] > row["ema9"] and row["close"] > row["ema21"]
    bullish = (row["ema9"] > row["ema21"]) and above_both  # already crossed OR just crossed
    cross_note = "FRESH_CROSS" if crossed else "above" if bullish else "below"
    return bullish, f"ema_momentum={cross_note} (9ema={row['ema9']:.2f} 21ema={row['ema21']:.2f})"


def _check_rsi(row) -> tuple[bool, str]:
    """
    RSI in bull momentum zone: above RSI_BULL_ZONE but not overbought.
    Also catches oversold bounces as a secondary signal.
    """
    rsi = row["rsi"]
    bull_zone = RSI_BULL_ZONE <= rsi <= RSI_MAX
    oversold_bounce = rsi < RSI_OVERSOLD
    ok = bull_zone or oversold_bounce
    zone = "BULL_ZONE" if bull_zone else "OVERSOLD" if oversold_bounce else "NEUTRAL"
    return ok, f"rsi={rsi:.1f} [{zone}] (need >{RSI_BULL_ZONE} or <{RSI_OVERSOLD})"


def _check_volume(row) -> tuple[bool, str]:
    """
    Volume expansion: current candle volume is at least VOLUME_SPIKE_MULT × 20-period average.
    Filters fake breakouts — real moves have participation.
    """
    ratio = row["volume"] / row["vol_ma"] if row["vol_ma"] > 0 else 0
    ok = ratio >= VOLUME_SPIKE_MULT
    return ok, f"volume={ratio:.2f}x avg (need >{VOLUME_SPIKE_MULT}x)"


def _check_macd(row, prev_row) -> tuple[bool, str]:
    """
    MACD histogram turned positive (flipped from negative or zero to positive).
    Compression → expansion = momentum ignition signal.
    """
    hist_now  = row["macd_hist"]
    hist_prev = prev_row["macd_hist"]
    flipped_positive = hist_now > 0 and hist_prev <= 0
    already_positive = hist_now > 0
    ok = already_positive  # positive histogram = bullish momentum
    note = "FLIP" if flipped_positive else "positive" if ok else f"negative({hist_now:.4f})"
    return ok, f"macd_hist={note} ({hist_now:.4f})"


def _check_bb_expansion(row, prev_row) -> tuple[bool, str]:
    """
    Bollinger Band expansion after a squeeze.
    Price closes above upper band after a low-width period = volatility breakout.
    """
    was_squeezed = prev_row["bb_width"] < BB_SQUEEZE_THRESHOLD
    broke_upper  = row["close"] > row["bb_upper"]
    expanding    = row["bb_width"] > prev_row["bb_width"]
    ok = (was_squeezed and broke_upper) or (broke_upper and expanding)
    note = "SQUEEZE_BREAK" if (was_squeezed and broke_upper) else "EXPANSION" if ok else "inside"
    return ok, f"bb={note} (width={row['bb_width']:.4f} close={'above' if broke_upper else 'below'} upper)"


def _check_atr_edge(row) -> tuple[bool, str]:
    """
    Minimum ATR to cover round-trip fees + edge buffer.
    Prevents trading during dead/flat markets.
    """
    expected = row["atr"] / row["close"]
    required = (2 * FEE_RATE) + MIN_EDGE_PCT
    ok = expected >= required
    return ok, f"atr_edge={expected:.4%} vs required {required:.4%}"


# ─────────────────────────────────────────────────────────────────────── #
#  DCA level check                                                         #
# ─────────────────────────────────────────────────────────────────────── #

def _check_dca_level(current_price: float, high: float, symbol_state: dict) -> tuple[bool, float, str]:
    """
    Returns (new_level_hit, spend_usd, log_msg).
    Only True when price crosses a new DCA_DROP_STEP_PCT% level below 24h high.
    """
    if high <= 0:
        return False, 0.0, "invalid high"

    drop_pct      = (high - current_price) / high * 100
    last_trigger  = symbol_state.get("last_trigger_pct", 0.0)
    current_level = int(drop_pct / DCA_DROP_STEP_PCT)
    last_level    = int(last_trigger / DCA_DROP_STEP_PCT)

    msg = f"drop={drop_pct:.2f}% level={current_level} (was {last_level})"

    if current_level > last_level and drop_pct >= DCA_DROP_STEP_PCT:
        spend_usd = min(round(drop_pct, 2), DCA_MAX_SPEND_PER_LEVEL)
        return True, spend_usd, msg + f" -> NEW LEVEL spend=${spend_usd:.2f}"

    return False, 0.0, msg + " -> no new level"


# ─────────────────────────────────────────────────────────────────────── #
#  Main entry function                                                     #
# ─────────────────────────────────────────────────────────────────────── #

def should_long_dca(
    current_price: float,
    high: float,
    symbol_state: dict,
    df: pd.DataFrame,
) -> tuple[bool, float]:
    """
    High-confluence DCA entry system.

    Gate 1 — DCA structure : price must have dropped a new level from 24h high
    Gate 2 — ATR edge      : must be enough volatility to cover fees
    Gate 3 — HTF bias      : skip if macro trend is bearish (configurable)
    Gate 4 — Momentum score: need MIN_CONFLUENCE_SCORE out of 4 signals:
                            +1 EMA9 > EMA21 (momentum shift)
                            +1 RSI in bull zone or oversold bounce
                            +1 Volume spike > VOLUME_SPIKE_MULT × avg
                            +1 MACD histogram positive
                            +1 BB expansion / squeeze break  (bonus)

    Returns (should_buy, spend_usd).
    """
    
    

    
    row      = df.iloc[-1]
    prev_row = df.iloc[-2]

    # ── Gate 1: DCA level ─────────────────────────────────────────────── #
    new_level, spend_usd, dca_msg = _check_dca_level(current_price, high, symbol_state)
    
    
    # -- Gate 1.1: if LESS_STRICT_SHOULD_LONG, allow same level re-entry if confluence is very strong (score 4/5) ---
    if LESS_STRICT_SHOULD_LONG: #! FOR TESTING ONLY: skips all gates except, and ignores HTF bias even if required. Use to generate more trades and test exit logic.
        log(f"[ENTRY] [LESS STRICT SHOULD LONG ENABLED]✓  -> spend=${spend_usd:.2f}")
        return True, 10.0  # fixed spend for testing
    
    
    log(f"[DCA] {dca_msg}")
    if not new_level:
        return False, 0.0



    # ── Gate 2: ATR edge ──────────────────────────────────────────────── #
    edge_ok, edge_msg = _check_atr_edge(row)
    log(f"[ATR] {edge_msg}")
    if not edge_ok:
        return False, 0.0

    # ── Gate 3: HTF bias (optional hard gate) ─────────────────────────── #
    htf_ok, htf_msg = _check_htf_bias(row)
    log(f"[HTF] {htf_msg}")
    if HTF_TREND_REQUIRED and not htf_ok:
        log("[ENTRY] blocked: HTF_TREND_REQUIRED and trend is bearish")
        return False, 0.0

    # ── Gate 4: Momentum confluence score ─────────────────────────────── #
    score = 0
    signals = []

    ema_ok,  ema_msg  = _check_momentum_ema(row, prev_row)
    rsi_ok,  rsi_msg  = _check_rsi(row)
    vol_ok,  vol_msg  = _check_volume(row)
    macd_ok, macd_msg = _check_macd(row, prev_row)
    bb_ok,   bb_msg   = _check_bb_expansion(row, prev_row)

    if ema_ok:  score += 1; signals.append("EMA_MOM")
    if rsi_ok:  score += 1; signals.append("RSI")
    if vol_ok:  score += 1; signals.append("VOLUME")
    if macd_ok: score += 1; signals.append("MACD")
    if bb_ok:   score += 1; signals.append("BB_EXPAND")   # bonus — can push score to 5

    log(f"[SCORE] {score}/{MIN_CONFLUENCE_SCORE} needed | signals={signals}")
    log(f"  {ema_msg}")
    log(f"  {rsi_msg}")
    log(f"  {vol_msg}")
    log(f"  {macd_msg}")
    log(f"  {bb_msg}")

    if score < MIN_CONFLUENCE_SCORE:
        log(f"[ENTRY] blocked: score {score} < {MIN_CONFLUENCE_SCORE} required")
        return False, 0.0
    

    log(f"[ENTRY] ✓ DCA level + score={score} + {'BULL' if htf_ok else 'BEAR'} trend -> spend=${spend_usd:.2f}")
    return True, spend_usd
