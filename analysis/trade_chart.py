"""
analysis/trade_chart.py
────────────────────────
Standalone script — run manually to visualize any completed trade.

Reads:
- log/db/portfolio.db  → trade records (entry/exit price, time, fees)
- log/db/prices.db     → recorded price snapshots during the trade

Plots:
- Price line from first BUY to SELL + padding
- Entry marker (▲ green), Exit marker (▼ red)
- Stop loss line (red dashed)
- Take profit line (green dashed)
- Break-even line (orange dashed) — entry + fees
- Trailing stop progression (purple dashed) if applicable
- Shaded holding period
- P&L summary in title

Usage:
    python analysis/trade_chart.py                     # plots all round-trips (interactive)
    python analysis/trade_chart.py --pdf               # saves PDF to analysis/reports/<datetime>.pdf
    python analysis/trade_chart.py --symbol SOLUSDT    # one symbol
    python analysis/trade_chart.py --last 5            # last N completed trades
    python analysis/trade_chart.py --sell-id 42        # trade by SELL row id

Requirements:  pip install matplotlib
"""

import sqlite3
import argparse
from datetime import datetime, timezone
from pathlib import Path

import sys
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib.gridspec import GridSpec
from matplotlib.backends.backend_pdf import PdfPages

# config.py lives one level up (bot root), not inside analysis/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import FEE_RATE, LESS_STRICT_SHOULD_LONG
# ── Config (keep in sync with your bot's config.py) ───────────────────── #
PORTFOLIO_DB = Path("log/db/portfolio.db")
PRICES_DB    = Path("log/db/prices.db")
REPORTS_DIR  = Path("analysis/reports")




# ── DB helpers ────────────────────────────────────────────────────────── #

def _parse_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def load_round_trips(symbol: str | None, last_n: int | None, sell_id: int | None) -> list[dict]:
    """
    Pair BUY→SELL rows from portfolio.db into round-trips.
    DCA: multiple BUYs averaged into one entry before a SELL.
    """
    with sqlite3.connect(PORTFOLIO_DB) as conn:
        rows = conn.execute("""
            SELECT id, symbol, side, price, amount, fee, balance_after, sl, tp, timestamp
            FROM trades ORDER BY id ASC
        """).fetchall()

    if symbol:
        rows = [r for r in rows if r[1] == symbol.upper()]

    open_buys: dict[str, list] = {}
    round_trips = []

    for row in rows:
        rid, sym, side, price, amount, fee, balance_after, sl, tp, ts = row
        dt = _parse_dt(ts)

        if side == "BUY":
            open_buys.setdefault(sym, []).append({
                "id": rid, "price": price, "amount": amount, "fee": fee, "time": dt,
                "sl": sl, "tp": tp,
            })

        elif side == "SELL" and sym in open_buys:
            buys = open_buys.pop(sym)

            total_qty     = sum(b["amount"] for b in buys)
            total_cost    = sum(b["price"] * b["amount"] for b in buys)
            total_buy_fee = sum(b["fee"] for b in buys)
            avg_entry     = total_cost / total_qty if total_qty else price

            sell_value = price * amount
            sell_fee   = fee
            pnl        = sell_value - total_cost - total_buy_fee - sell_fee
            pnl_pct    = pnl / total_cost * 100 if total_cost else 0

            hold_secs  = (dt - buys[0]["time"]).total_seconds()

            round_trips.append({
                "symbol":        sym,
                "sell_id":       rid,
                "buy_ids":       [b["id"] for b in buys],
                "dca_levels":    len(buys),
                "avg_entry":     avg_entry,
                "sl":            buys[0]["sl"],   # set at first BUY — actual bot value
                "tp":            buys[0]["tp"],   # set at first BUY — actual bot value
                "sell_price":    price,
                "qty":           total_qty,
                "total_cost":    total_cost,
                "total_buy_fee": total_buy_fee,
                "sell_fee":      sell_fee,
                "pnl":           pnl,
                "pnl_pct":       pnl_pct,
                "entry_time":    buys[0]["time"],
                "sell_time":     dt,
                "hold_secs":     hold_secs,
                "balance_after": balance_after,
                "buys":          buys,
            })

    if sell_id:
        round_trips = [rt for rt in round_trips if rt["sell_id"] == sell_id]
    if last_n:
        round_trips = round_trips[-last_n:]

    return round_trips


def load_prices(symbol: str, from_ms: int, to_ms: int) -> list[tuple]:
    """Load price rows from prices.db for a time window."""
    if not PRICES_DB.exists():
        return []
    with sqlite3.connect(PRICES_DB) as conn:
        rows = conn.execute("""
            SELECT timestamp_ms, open, high, low, close, volume
            FROM prices
            WHERE symbol = ? AND timestamp_ms BETWEEN ? AND ?
            ORDER BY timestamp_ms ASC
        """, (symbol, from_ms, to_ms)).fetchall()
    return rows


# ── Chart core ────────────────────────────────────────────────────────── #

def _ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _style_axes(axes: list):
    for ax in axes:
        ax.set_facecolor("#0d1117")
        ax.spines["bottom"].set_color("#333")
        ax.spines["top"].set_color("#333")
        ax.spines["left"].set_color("#333")
        ax.spines["right"].set_color("#333")
        ax.tick_params(colors="#aaa", labelsize=8)
        ax.tick_params(axis="x", colors="#aaa")


def plot_trade(rt: dict, ax_price: plt.Axes, ax_pnl: plt.Axes):
    symbol     = rt["symbol"]
    avg_entry  = rt["avg_entry"]
    sell_price = rt["sell_price"]
    entry_time = rt["entry_time"]
    sell_time  = rt["sell_time"]

    pad_ms  = 10 * 60 * 1000
    from_ms = int(entry_time.timestamp() * 1000) - pad_ms
    to_ms   = int(sell_time.timestamp()  * 1000) + pad_ms

    prices = load_prices(symbol, from_ms, to_ms)

    # ── Price line ─────────────────────────────────────────────────────── #
    if prices:
        times  = [_ms_to_dt(p[0]) for p in prices]
        closes = [p[4] for p in prices]
        ax_price.plot(times, closes, color="#4FC3F7", linewidth=1.5, zorder=2)
        ax_price.axvspan(entry_time, sell_time, alpha=0.08, color="#4FC3F7", zorder=1)

        pnl_curve = [(c - avg_entry) * rt["qty"] for c in closes]
        bar_colors = ["#26A69A" if p >= 0 else "#EF5350" for p in pnl_curve]
        ax_pnl.bar(times, pnl_curve, color=bar_colors, width=0.0003, zorder=2)
        ax_pnl.axhline(0, color="#555", linewidth=0.8, linestyle="--")
        ax_pnl.axvspan(entry_time, sell_time, alpha=0.06, color="#4FC3F7", zorder=1)
    else:
        ax_price.annotate("No price data in prices.db\n(price_recorder must run during trade)",
                        xy=(0.5, 0.5), xycoords="axes fraction",
                        ha="center", color="#888", fontsize=9)

    # ── Key levels — real values from DB ──────────────────────────────── #
    breakeven = avg_entry * (1 + 2 * FEE_RATE)
    sl_price  = rt["sl"]   # actual value set by bot at entry
    tp_price  = rt["tp"]   # actual value set by bot at entry

    ax_price.axhline(avg_entry,  color="#FFA726", linewidth=1.2, linestyle="--", label=f"Avg entry ${avg_entry:.4f}")
    ax_price.axhline(breakeven,  color="#FFEB3B", linewidth=0.8, linestyle=":",  label=f"Break-even ${breakeven:.4f}")
    ax_price.axhline(sl_price,   color="#EF5350", linewidth=1.0, linestyle="--", label=f"SL ${sl_price:.4f}")
    ax_price.axhline(tp_price,   color="#26A69A", linewidth=1.0, linestyle="--", label=f"TP ${tp_price:.4f}")
    ax_price.axhline(sell_price, color="#CE93D8", linewidth=1.2, linestyle="-.", label=f"Exit ${sell_price:.4f}")

    # ── Entry / exit markers ───────────────────────────────────────────── #
    for buy in rt["buys"]:
        ax_price.scatter(buy["time"], buy["price"],
                        marker="^", color="#26A69A", s=120, zorder=5,
                        label=f"BUY ${buy['price']:.4f}" if buy == rt["buys"][0] else "")

    ax_price.scatter(sell_time, sell_price,
                    marker="v", color="#EF5350", s=120, zorder=5, label=f"SELL ${sell_price:.4f}")

    for i, buy in enumerate(rt["buys"]):
        ax_price.annotate(f"L{i+1}", xy=(buy["time"], buy["price"]),
                        xytext=(5, 8), textcoords="offset points",
                        color="#26A69A", fontsize=7)

    # ── Labels ─────────────────────────────────────────────────────────── #
    pnl_color = "#26A69A" if rt["pnl"] >= 0 else "#EF5350"
    hold_str  = f"{int(rt['hold_secs']//60)}m {int(rt['hold_secs']%60)}s"

    ax_price.set_title(
        f"{symbol}  |  DCA levels: {rt['dca_levels']}  |  "
        f"Avg entry: ${avg_entry:.4f}  →  Exit: ${sell_price:.4f}  |  LESS_STRICT_SHOULD_LONG={LESS_STRICT_SHOULD_LONG}",
        color="#ccc", fontsize=9, pad=4
    )
    ax_price.text(0.98, 1.01,
                f"{'▲' if rt['pnl'] >= 0 else '▼'} ${rt['pnl']:.4f} ({rt['pnl_pct']:+.2f}%)",
                transform=ax_price.transAxes, ha="right", va="bottom",
                color=pnl_color, fontsize=9, fontweight="bold")
    ax_price.text(0.02, 1.01, f"Hold: {hold_str}",
                transform=ax_price.transAxes, ha="left", va="bottom",
                color="#aaa", fontsize=8)

    ax_price.legend(fontsize=7, loc="upper left", framealpha=0.3)
    ax_price.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax_price.set_ylabel("Price", color="#aaa", fontsize=8)
    ax_price.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    ax_pnl.set_ylabel("Unrealized P&L $", color="#aaa", fontsize=7)
    ax_pnl.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    _style_axes([ax_price, ax_pnl])


# ── PDF export ────────────────────────────────────────────────────────── #

def _make_summary_fig(round_trips: list[dict]) -> plt.Figure:
    """Page 1: cumulative P&L curve + stats + per-symbol table."""
    fig = plt.figure(figsize=(16, 10), facecolor="#0d1117")
    fig.patch.set_facecolor("#0d1117")

    gs = GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.35,
                top=0.88, bottom=0.08, left=0.07, right=0.97)
    ax_equity  = fig.add_subplot(gs[0, :])
    ax_stats   = fig.add_subplot(gs[1, 0])
    ax_symbols = fig.add_subplot(gs[1, 1])
    _style_axes([ax_equity, ax_stats, ax_symbols])

    # Cumulative P&L
    times      = [rt["sell_time"] for rt in round_trips]
    cumulative = []
    running    = 0.0
    for rt in round_trips:
        running += rt["pnl"]
        cumulative.append(running)

    ax_equity.plot(times, cumulative, color="#4FC3F7", linewidth=2, zorder=2)
    ax_equity.fill_between(times, cumulative, 0,
                        where=[c >= 0 for c in cumulative], color="#26A69A", alpha=0.25)
    ax_equity.fill_between(times, cumulative, 0,
                        where=[c < 0 for c in cumulative], color="#EF5350", alpha=0.25)
    ax_equity.axhline(0, color="#444", linewidth=0.8, linestyle="--")
    ax_equity.set_title("Cumulative P&L", color="#ccc", fontsize=10, loc="left")
    ax_equity.set_ylabel("P&L ($)", color="#aaa", fontsize=9)
    ax_equity.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
    plt.setp(ax_equity.get_xticklabels(), rotation=15, ha="right", fontsize=7, color="#aaa")

    # Stats table
    wins     = [rt for rt in round_trips if rt["pnl"] > 0]
    losses   = [rt for rt in round_trips if rt["pnl"] <= 0]
    total    = sum(rt["pnl"] for rt in round_trips)
    avg_hold = sum(rt["hold_secs"] for rt in round_trips) / len(round_trips)
    win_rate = len(wins) / len(round_trips) * 100
    avg_win  = sum(rt["pnl"] for rt in wins)   / len(wins)   if wins   else 0
    avg_loss = sum(rt["pnl"] for rt in losses) / len(losses) if losses else 0

    stats = [
        ["Total trades", str(len(round_trips))],
        ["Win rate",     f"{win_rate:.1f}%"],
        ["Total P&L",    f"${total:+.4f}"],
        ["Avg win",      f"${avg_win:+.4f}"],
        ["Avg loss",     f"${avg_loss:+.4f}"],
        ["Avg hold",     f"{int(avg_hold//60)}m {int(avg_hold%60)}s"],
        ["Winners",      str(len(wins))],
        ["Losers",       str(len(losses))],
    ]
    ax_stats.axis("off")
    tbl = ax_stats.table(cellText=stats, colLabels=["Metric", "Value"],
                        cellLoc="left", loc="center", bbox=[0, 0, 1, 1])
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_facecolor("#111827" if r % 2 == 0 else "#0d1117")
        cell.set_edgecolor("#2a2a2a")
        cell.set_text_props(color="#ccc")
    ax_stats.set_title("Summary", color="#ccc", fontsize=10, loc="left", pad=10)

    # Per-symbol table
    symbols  = sorted(set(rt["symbol"] for rt in round_trips))
    sym_rows = []
    for sym in symbols:
        sym_trades = [rt for rt in round_trips if rt["symbol"] == sym]
        sym_pnl    = sum(rt["pnl"] for rt in sym_trades)
        sym_wins   = sum(1 for rt in sym_trades if rt["pnl"] > 0)
        sym_rows.append([sym, str(len(sym_trades)),
                        f"${sym_pnl:+.4f}",
                        f"{sym_wins/len(sym_trades)*100:.0f}%"])

    ax_symbols.axis("off")
    tbl2 = ax_symbols.table(cellText=sym_rows,
                            colLabels=["Symbol", "Trades", "P&L", "Win%"],
                            cellLoc="left", loc="center", bbox=[0, 0, 1, 1])
    tbl2.auto_set_font_size(False)
    tbl2.set_fontsize(9)
    for (r, c), cell in tbl2.get_celld().items():
        cell.set_facecolor("#111827" if r % 2 == 0 else "#0d1117")
        cell.set_edgecolor("#2a2a2a")
        cell.set_text_props(color="#ccc")
    ax_symbols.set_title("By Symbol", color="#ccc", fontsize=10, loc="left", pad=10)

    fig.text(0.5, 0.95,
            f"Trading Bot Report — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ha="center", color="#eee", fontsize=13, fontweight="bold")
    return fig


def _make_trade_fig(rt: dict) -> plt.Figure:
    """One full landscape page per trade — large and readable."""
    fig = plt.figure(figsize=(16, 9), facecolor="#0d1117")
    fig.patch.set_facecolor("#0d1117")

    gs = GridSpec(4, 1, figure=fig, hspace=0.08,
                top=0.88, bottom=0.08, left=0.07, right=0.97)
    ax_price = fig.add_subplot(gs[:3, 0])
    ax_pnl   = fig.add_subplot(gs[3, 0], sharex=ax_price)

    plt.setp(ax_price.get_xticklabels(), visible=False)
    plot_trade(rt, ax_price, ax_pnl)
    return fig


def save_pdf(round_trips: list[dict], custom_name: str | None = None) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_path = REPORTS_DIR / f"{ts}.pdf"

    if custom_name:
        out_path = REPORTS_DIR / f"{custom_name}.pdf"

    matplotlib.rcParams["pdf.fonttype"] = 42  # embed fonts

    with PdfPages(out_path) as pdf:
        # Page 1: summary
        fig = _make_summary_fig(round_trips)
        pdf.savefig(fig, facecolor=fig.get_facecolor(), bbox_inches="tight")
        plt.close(fig)

        # One page per trade
        for i, rt in enumerate(round_trips):
            print(f"  [{i+1}/{len(round_trips)}] {rt['symbol']} sell_id={rt['sell_id']}")
            fig = _make_trade_fig(rt)
            pdf.savefig(fig, facecolor=fig.get_facecolor(), bbox_inches="tight")
            plt.close(fig)

        d = pdf.infodict()
        d["Title"]        = "Trading Bot Report"
        d["Author"]       = "trade_chart.py"
        d["Subject"]      = f"{len(round_trips)} round-trips"
        d["CreationDate"] = datetime.now()

    print(f"\nPDF saved → {out_path}")
    return out_path


# ── Interactive viewer (unchanged) ───────────────────────────────────── #

def plot_all(round_trips: list[dict]):
    if not round_trips:
        print("No completed round-trips found.")
        return

    from matplotlib.widgets import Slider

    n            = len(round_trips)
    fig_height   = 8
    total_height = 5 * n

    fig = plt.figure(figsize=(14, fig_height), facecolor="#0d1117")
    fig.suptitle("Trade Analysis", color="#eee", fontsize=13)

    axes_price = []
    axes_pnl   = []

    for i, rt in enumerate(round_trips):
        bottom     = 1 - ((i + 1) * 5) / total_height
        height     = 3 / total_height
        pnl_height = 1 / total_height

        ax_price = fig.add_axes([0.08, bottom + pnl_height, 0.85, height])
        ax_pnl   = fig.add_axes([0.08, bottom, 0.85, pnl_height], sharex=ax_price)

        axes_price.append(ax_price)
        axes_pnl.append(ax_pnl)
        plot_trade(rt, ax_price, ax_pnl)

    ax_slider = fig.add_axes([0.95, 0.1, 0.02, 0.8])
    slider    = Slider(ax_slider, '', 0, total_height - fig_height,
                    valinit=total_height - fig_height, orientation='vertical')

    def update(val):
        offset = slider.val / total_height
        for ax in axes_price + axes_pnl:
            pos = ax.get_position()
            ax.set_position([pos.x0, pos.y0 + offset, pos.width, pos.height])
        fig.canvas.draw_idle()

    slider.on_changed(update)
    plt.show()


# ── CLI ───────────────────────────────────────────────────────────────── #

def main():
    parser = argparse.ArgumentParser(description="Visualize completed trades")
    parser.add_argument("--symbol",  type=str,            help="Filter by symbol e.g. SOLUSDT")
    parser.add_argument("--last",    type=int,            help="Show last N completed round-trips")
    parser.add_argument("--sell-id", type=int,            help="Show trade with this SELL row id")
    parser.add_argument("--pdf",     action="store_true", help="Save to analysis/reports/<datetime>.pdf")
    parser.add_argument("--pdf-name", type=str,           help="Save to analysis/reports/<name>.pdf")
    args = parser.parse_args()

    if not PORTFOLIO_DB.exists():
        print(f"portfolio.db not found at {PORTFOLIO_DB}")
        return

    round_trips = load_round_trips(
        symbol  = args.symbol,
        last_n  = args.last,
        sell_id = args.sell_id,
    )

    print(f"Found {len(round_trips)} completed round-trip(s)")
    for rt in round_trips:
        sign = "+" if rt["pnl"] >= 0 else ""
        print(f"  [{rt['sell_id']:>4}] {rt['symbol']} | "
            f"avg_entry={rt['avg_entry']:.4f} sell={rt['sell_price']:.4f} | "
            f"P&L={sign}{rt['pnl']:.4f} ({sign}{rt['pnl_pct']:.2f}%) | "
            f"DCA levels={rt['dca_levels']} | "
            f"hold={int(rt['hold_secs']//60)}m{int(rt['hold_secs']%60)}s")

    if not round_trips:
        return

    if args.pdf:
        save_pdf(round_trips, custom_name=args.pdf_name)
    else:
        plot_all(round_trips)


if __name__ == "__main__":
    main()
