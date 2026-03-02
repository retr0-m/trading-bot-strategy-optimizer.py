from log.logger import log

def position_size(balance, entry_price, stop_price, risk_pct):
    """Not used in DCA branch. Kept for import compatibility."""
    stop_distance = entry_price - stop_price
    if stop_distance <= 0:
        return 0.0
    return (balance * risk_pct) / stop_distance
