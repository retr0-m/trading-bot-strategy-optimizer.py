from db.runs import RunsDB
runs = RunsDB()
best = runs.get_best(n=3)
for r in best:
    print(f"Score: {r['score']:.4f} | Calmar: {r['calmar']:.4f} | "
          f"Trades: {r['n_trades']} | WinRate: {r['win_rate']:.1%} | "
          f"Drawdown: {r['max_drawdown']:.1%}")
    print(f"  Params: {r['params']}\n")