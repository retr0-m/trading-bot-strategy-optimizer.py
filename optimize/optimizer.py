"""
optimize/optimizer.py
─────────────────────
Optuna study. Loads data, runs walk-forward per trial, saves to runs.db.
"""
import optuna
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from binance.client import Client

from data.fetcher import fetch
from backtest.walk_forward import evaluate
from strategies.dca_momentum.params import build_space
from optimize.objective import score
from db.runs import RunsDB
from log.logger import log

optuna.logging.set_verbosity(optuna.logging.WARNING)

from config import SYMBOLS
INTERVAL = Client.KLINE_INTERVAL_5MINUTE


def _load_data(client: Client, years: int) -> dict:
    end   = datetime.now(tz=timezone.utc)
    start = end - relativedelta(years=years)
    log(f"[optimizer] loading {years}yr data for {SYMBOLS} from {start.date()} to {end.date()}")
    data = {}
    for s in SYMBOLS:
        log(f"[optimizer] fetching {s}...")
        data[s] = fetch(client, s, INTERVAL, start, end)
        log(f"[optimizer] {s} — {len(data[s])} candles loaded")
    return data


def run_optimization(client: Client, n_trials: int = 50,
                     train_years: int = 3, test_years: int = 1):
    total_years = train_years + test_years + 1
    dfs    = _load_data(client, total_years)
    db     = RunsDB()
    study  = optuna.create_study(direction="maximize",
                                  sampler=optuna.samplers.TPESampler(seed=42))

    def objective(trial):
        p       = build_space(trial)
        metrics = evaluate(dfs, p, train_years, test_years)
        s       = score(metrics)
        db.save_run(p, metrics, s)
        log(f"[optimizer] trial #{trial.number} score={s:.4f} calmar={metrics['calmar']:.4f} "
            f"trades={metrics['n_trades']} drawdown={metrics['max_drawdown']:.2%}")
        return s

    log(f"[optimizer] starting Optuna study — {n_trials} trials")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    best   = study.best_trial
    best_p = build_space(best)
    best_m = evaluate(dfs, best_p, train_years, test_years)
    best_s = score(best_m)

    log(f"[optimizer] BEST trial #{best.number} — score={best_s:.4f}")
    log(f"[optimizer] best metrics: {best_m}")
    log(f"[optimizer] best params: {best_p}")

    db.save_run(best_p, best_m, best_s, is_best=True)
    db.close()

    print(f"\n✓ Optimization complete")
    print(f"  Best score:   {best_s:.4f}")
    print(f"  Best metrics: {best_m}")
    print(f"  Saved to:     log/db/runs.db")
    return best_p, best_m