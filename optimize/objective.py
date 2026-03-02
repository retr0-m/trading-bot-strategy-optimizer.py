"""
optimize/objective.py
─────────────────────
Single scalar score for Optuna to maximize.
Primary: Calmar ratio. Penalty: too few trades (overfit risk).
"""

MIN_TRADES = 10  # penalize heavily if fewer trades than this


def score(metrics: dict) -> float:
    """
    Higher = better. Optuna maximizes this.
    Calmar is return/drawdown — naturally balances PnL vs risk.
    Trade count penalty prevents 1-lucky-trade strategies.
    """
    calmar    = metrics.get("calmar", 0)
    n_trades  = metrics.get("n_trades", 0)
    drawdown  = metrics.get("max_drawdown", 1)
    win_rate  = metrics.get("win_rate", 0)

    if n_trades < MIN_TRADES:
        penalty = (n_trades / MIN_TRADES) * 0.5  # max 50% score if too few trades
    else:
        penalty = 1.0

    # Bonus for win rate above 50%
    wr_bonus = max(0, (win_rate - 0.5) * 0.2)

    # Drawdown cap: if max_drawdown > 40%, heavily penalize
    dd_penalty = max(0, (drawdown - 0.4) * 2) if drawdown > 0.4 else 0

    return (calmar + wr_bonus - dd_penalty) * penalty