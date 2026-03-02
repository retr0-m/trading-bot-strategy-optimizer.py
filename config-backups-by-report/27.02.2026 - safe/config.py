LOG_FILE         = "./log/log.txt"
UVICORN_LOG_FILE = "./log/uvicorn_log.txt"
POSITIONS_LOG_CSV_FILE = "./log/positions_log.csv"
LOG_PRICE_RECORDER_FILE = "./log/price_recorder_log.txt"

# ── Paper trading ──────────────────────────────────────────────────────── #
PAPER_TRADING = True
START_BALANCE = 100.0
FEE_RATE      = 0.001    # 0.1% Binance spot fee
LEVERAGE      = 3.0      # spot only

# ── Symbols ────────────────────────────────────────────────────────────── #
DCA_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
]
SYMBOLS = DCA_SYMBOLS

# ── Loop timing ────────────────────────────────────────────────────────── #
INTERVAL       = "5m"
SLEEP_INTERVAL = 10      # seconds between iterations

# ── DCA entry structure ────────────────────────────────────────────────── #
DCA_DROP_STEP_PCT       = 1.5   # trigger a new buy every X% drop from DCA_HIGH_LOOKBACK_CANDLES / 12 high
                                # 1.0 = very frequent, 3.0 = only on real dips
DCA_MAX_SPEND_PER_LEVEL = 15.0  # max $ per DCA trigger (spend = drop_pct, capped here)
DCA_COOLDOWN_SECONDS    = 180   # seconds to wait after any exit before re-entering
DCA_HIGH_LOOKBACK_CANDLES = 24  # 12 × 5m = 1h  |  288 = 24h  |  72 = 6h - max 24 hrs

# ── Exit config ────────────────────────────────────────────────────────── #
TAKE_PROFIT_MULTIPLIER = 6.0    # ATR multiples above avg entry
STOP_LOSS_MULTIPLIER   = 3.0    # ATR multiples below avg entry
BREAKEVEN_TRIGGER_PCT = 0.012  # 0.8% profit before break-even activates

# Trailing stop — give the position room to run
TRAIL_START_PCT    = 0.020      # start trailing after x% profit 
TRAIL_DISTANCE_PCT = 0.010      # trail x% below peak 

# ── Accelerating trail ─────────────────────────────────────────────────── #
# As profit grows, trail tightens to lock in gains
# Format: (min_profit_pct, trail_distance_pct) — checked top to bottom
TRAIL_TIERS = [
    (0.05, 0.003),   # 5%+ profit  → trail 0.3% below peak (very tight)
    (0.03, 0.005),   # 3-5% profit → trail 0.5% below peak
    (0.015, 0.008),  # 1.5-3%      → trail 0.8% below peak (normal)
]
# Below the first tier threshold → no trailing, just base SL

# ── Indicator lengths ──────────────────────────────────────────────────── #
# Short-term momentum EMAs (5m)
EMA_FAST        = 9
EMA_SLOW        = 21

# Higher-timeframe trend proxy (5m)
EMA_TREND_FAST  = 50
EMA_TREND_SLOW  = 200

RSI_LENGTH      = 14
ATR_LENGTH      = 14
VOL_MA_LENGTH   = 20

# MACD
MACD_FAST       = 12
MACD_SLOW       = 26
MACD_SIGNAL     = 9

# Bollinger Bands
BB_LENGTH       = 20
BB_STD          = 2

# ── Entry quality filters ──────────────────────────────────────────────── #
# Confluence score: 4 signals available (EMA, RSI, Volume, MACD) + 1 bonus (BB)
# Set to 2 for more trades, 3 for balanced, 4 for very selective
MIN_CONFLUENCE_SCORE = 2

# RSI zones
RSI_BULL_ZONE   = 55    # above = bull momentum zone
RSI_MAX         = 75    # above = overbought, skip
RSI_OVERSOLD    = 45    # below = washed out (counts as RSI signal)

# Volume
VOLUME_SPIKE_MULT = 1.5  # volume must be this × 20-period average

# Bollinger Band squeeze threshold (bb_width = (upper-lower)/mid)
BB_SQUEEZE_THRESHOLD = 0.02   # below this = squeeze, breakout above upper = signal

# Macro trend gate: if True, skips ALL entries when EMA50 < EMA200
# Set False to allow counter-trend DCA entries (riskier but more frequent)
HTF_TREND_REQUIRED = False

# ── ATR edge ───────────────────────────────────────────────────────────── #
MIN_EDGE_PCT    = 0.002  # minimum expected move above fees


# For testing less strict entry conditions (e.g. for backtesting or more frequent trades)
LESS_STRICT_SHOULD_LONG = True