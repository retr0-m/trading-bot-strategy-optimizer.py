"""
strategies/dca_momentum/params.py
──────────────────────────────────
Default params + Optuna search space definitions.
DEFAULTS = what live trading uses.
SPACE    = what optimizer searches over.
"""

DEFAULTS = {
    # Indicator lengths
    "ema_fast": 9, "ema_slow": 21,
    "ema_trend_fast": 50, "ema_trend_slow": 200,
    "rsi_length": 14, "atr_length": 14,
    "vol_ma_length": 20, "adx_length": 14,
    "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
    "bb_length": 20, "bb_std": 2.0,
    # Entry filters
    "min_confluence": 3,
    "rsi_bull_zone": 55, "rsi_max": 75, "rsi_oversold": 45,
    "volume_spike_mult": 1.5,
    "bb_squeeze_threshold": 0.02,
    "htf_trend_required": False,
    "min_edge_pct": 0.002,
    # DCA structure
    "dca_drop_step_pct": 1.5,
    "dca_max_spend": 15.0,
    "dca_cooldown_s": 180,
    "dca_high_lookback": 24,
    # Exit
    "tp_multiplier": 6.0,
    "sl_multiplier": 3.0,
    "breakeven_trigger_pct": 0.012,
    "trail_start_pct": 0.020,
    "trail_distance_pct": 0.010,
    # ADX filter (0 = disabled)
    "adx_min": 20,
}

def build_space(trial) -> dict:
    """Define Optuna search space. Called once per trial."""
    return {
        # Indicator lengths
        "ema_fast":            trial.suggest_int("ema_fast", 5, 20),
        "ema_slow":            trial.suggest_int("ema_slow", 15, 50),
        "ema_trend_fast":      trial.suggest_int("ema_trend_fast", 30, 80),
        "ema_trend_slow":      200,  # fixed — changing this rarely helps
        "rsi_length":          trial.suggest_int("rsi_length", 7, 21),
        "atr_length":          trial.suggest_int("atr_length", 7, 21),
        "vol_ma_length":       trial.suggest_int("vol_ma_length", 10, 40),
        "adx_length":          14,
        "macd_fast":           trial.suggest_int("macd_fast", 8, 16),
        "macd_slow":           trial.suggest_int("macd_slow", 20, 35),
        "macd_signal":         trial.suggest_int("macd_signal", 7, 12),
        "bb_length":           trial.suggest_int("bb_length", 10, 30),
        "bb_std":              trial.suggest_float("bb_std", 1.5, 3.0),
        # Entry filters
        "min_confluence":      trial.suggest_int("min_confluence", 1, 4),
        "rsi_bull_zone":       trial.suggest_int("rsi_bull_zone", 45, 65),
        "rsi_max":             trial.suggest_int("rsi_max", 65, 85),
        "rsi_oversold":        trial.suggest_int("rsi_oversold", 30, 50),
        "volume_spike_mult":   trial.suggest_float("volume_spike_mult", 1.0, 3.0),
        "bb_squeeze_threshold":trial.suggest_float("bb_squeeze_threshold", 0.01, 0.05),
        "htf_trend_required":  trial.suggest_categorical("htf_trend_required", [True, False]),
        "min_edge_pct":        trial.suggest_float("min_edge_pct", 0.001, 0.005),
        # DCA structure
        "dca_drop_step_pct":   trial.suggest_float("dca_drop_step_pct", 0.5, 4.0),
        "dca_max_spend":       trial.suggest_float("dca_max_spend", 5.0, 25.0),
        "dca_cooldown_s":      trial.suggest_int("dca_cooldown_s", 60, 600),
        "dca_high_lookback":   trial.suggest_int("dca_high_lookback", 6, 72),
        # Exit
        "tp_multiplier":       trial.suggest_float("tp_multiplier", 2.0, 10.0),
        "sl_multiplier":       trial.suggest_float("sl_multiplier", 1.0, 5.0),
        "breakeven_trigger_pct":trial.suggest_float("breakeven_trigger_pct", 0.005, 0.02),
        "trail_start_pct":     trial.suggest_float("trail_start_pct", 0.01, 0.04),
        "trail_distance_pct":  trial.suggest_float("trail_distance_pct", 0.005, 0.02),
        "adx_min":             trial.suggest_int("adx_min", 0, 35),
    }