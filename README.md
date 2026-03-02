# DCA Branch

## Strategy

For each symbol, the bot watches the **rolling 24h high** (max of last 300 x 5m candles).

Every time price drops another `DCA_DROP_STEP_PCT`% from that high, it buys **$drop_pct** worth:

```
Price drops 1% from 24h high  →  buy $1
Price drops 2% from 24h high  →  buy $2
Price drops 3% from 24h high  →  buy $3
...and so on until balance runs out
```

All entries are averaged into a single position per symbol.  
Exit uses the same **trailing stop logic** from the main branch, applied to the **average entry price**.

---

## Key config (`config.py`)

| Setting | Default | What it does |
|---|---|---|
| `DCA_SYMBOLS` | BTC, ETH, SOL | Which coins to trade |
| `DCA_DROP_STEP_PCT` | 1.0 | Trigger a new buy every X% drop |
| `START_BALANCE` | $100 | Split across all symbols by available balance |
| `STOP_LOSS_MULTIPLIER` | 1.8 | ATR multiplier for base stop (from avg entry) |
| `TAKE_PROFIT_MULTIPLIER` | 4.0 | ATR multiplier for TP (from avg entry) |
| `TRAIL_START_PCT` | 0.3% | Trailing stop kicks in after this profit |
| `TRAIL_DISTANCE_PCT` | 0.15% | Trail stays this far below the peak |

---

## Key differences from main branch

| | Main branch | DCA branch |
|---|---|---|
| Entry | EMA cross + RSI + volume | % drop from 24h high |
| Position sizing | Risk-based (ATR stop distance) | Fixed: $drop_pct per level |
| Multiple entries | No | Yes — averages into one position |
| Stop loss | From entry price | From **average** entry price |
| Leverage | 5x | 1x (spot only) |
| Symbols | 10 | 3 (BTC, ETH, SOL) |

---

## How to run

```bash
# From root of the project:
cd dca-branch
python main.py
```

Dashboard runs at `http://127.0.0.1:8000` as usual.

---

## Tuning tips

- **Too many buys / runs out of balance quickly** → increase `DCA_DROP_STEP_PCT` (e.g. 2.0 or 3.0)  
- **Never buys** → decrease `DCA_DROP_STEP_PCT` (e.g. 0.5) or check that 24h high is being computed  
- **Exits too early** → increase `STOP_LOSS_MULTIPLIER` or decrease `TRAIL_DISTANCE_PCT`  
- **Exits too late** → decrease `TAKE_PROFIT_MULTIPLIER`

---

## Known limitations

- 24h high is computed from Binance klines (last 300 x 5m = ~25h), not real-time ticker.  
  This means the high updates every loop, not truly "rolling 24h".  
  To use the real 24h high, replace with `binance.get_ticker(symbol=symbol_name)["highPrice"]`.
- No max drawdown guard — if price keeps dropping the bot keeps buying until $0.  
  Add a `MAX_TOTAL_SPEND_PER_SYMBOL` cap in config if you want a hard limit.
