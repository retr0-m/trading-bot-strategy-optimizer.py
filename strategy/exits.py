from log.logger import log
from config import *

# Per-symbol tracking of highest price seen since entry
_highest_prices: dict[str, float] = {}


def should_exit(entry_price: float, position, current_price: float, atr: float, symbol: str = "") -> str | None:
    """
    Exit logic with trailing stop.
    Same as main branch but:
        - per-symbol highest price tracking (not a single global)
        - trailing stop is applied BEFORE the exit check (bug fix)
    """
    # Update peak price for this symbol
    prev_high = _highest_prices.get(symbol, entry_price)
    if current_price > prev_high:
        _highest_prices[symbol] = current_price
    last_highest_price = _highest_prices.get(symbol, entry_price)

    # --- Base stop / take profit (uses average_entry_price for DCA) ---
    avg_entry = getattr(position, "average_entry_price", entry_price)
    stop_loss, take_profit = get_tp_sl(avg_entry, current_price, atr)
    # print(f"[{symbol}]      Base stop loss: {stop_loss:.2f}, take profit: {take_profit:.2f}, current price: {current_price:.2f}")
    
    # Break-even: if price moved 1 ATR above avg entry, floor stop at avg entry
    if current_price > avg_entry * (1 + BREAKEVEN_TRIGGER_PCT):
        breakeven = avg_entry * (1 + 2 * FEE_RATE)  # floor covers fees too
        stop_loss = max(stop_loss, breakeven)
        log(f"Break-even activated for {symbol} — stop_loss floored at {stop_loss:.2f}")
        # print("break-even activated — stop loss floored at avg entry")
    
    # Trailing stop: accelerating — tightens as profit grows
    profit_pct = (last_highest_price - avg_entry) / avg_entry

    # Find the right tier
    trail_dist = None
    for min_profit, dist in sorted(TRAIL_TIERS, reverse=True):  # highest tier first
        if profit_pct >= min_profit:
            trail_dist = dist
            break

    if trail_dist is not None:
        trailing_stop = last_highest_price * (1 - trail_dist)
        log(f"Trail [{symbol}] profit={profit_pct:.2%} → dist={trail_dist:.1%} → stop={trailing_stop:.2f}")
        stop_loss = max(stop_loss, trailing_stop)
        


    log(
        f"should_exit [{symbol}] -> avg_entry={avg_entry:.2f}, "
        f"stop={stop_loss:.2f}, tp={take_profit:.2f}, "
        f"price={current_price:.2f}, trail_high={last_highest_price:.2f}"
    )

    if current_price <= stop_loss:
        log(f"should_exit [{symbol}] decision: STOP")
        _highest_prices.pop(symbol, None)
        return "stop"

    if current_price >= take_profit:
        log(f"should_exit [{symbol}] decision: TAKE_PROFIT")
        _highest_prices.pop(symbol, None)
        return "take_profit"

    log(f"should_exit [{symbol}] decision: None")
    return None


def reset_symbol(symbol: str):
    """Call this after a position is fully closed to clean up state."""
    _highest_prices.pop(symbol, None)


def get_tp_sl(avg_entry_price: float, current_price: float, atr: float):
    stop_loss   = avg_entry_price - (STOP_LOSS_MULTIPLIER * atr) + (FEE_RATE * current_price) * 2
    take_profit = avg_entry_price + (TAKE_PROFIT_MULTIPLIER * atr)
    return stop_loss, take_profit

