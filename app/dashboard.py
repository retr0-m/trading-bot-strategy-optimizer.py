from os import path
import threading
from time import sleep
from fastapi import FastAPI
from pathlib import Path
from fastapi.responses import FileResponse, HTMLResponse
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from log.database import PortfolioDB
from datetime import datetime
import uvicorn
from log.logger import log_uvicorn as log
from config import SYMBOLS
from subprocess import run

app = FastAPI()

templates = Jinja2Templates(directory="app/templates")

db : PortfolioDB  # global variable to hold the database connection

from collections import Counter
import httpx

@app.get("/api/klines")
async def get_klines(symbol: str, start_time: int): #camel lower only for front-end 
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": "1m",
        "startTime": start_time,
        "limit": 1000
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)

    return response.json()


@app.get("/api/price")
async def get_price(symbol: str):
    url = "https://api.binance.com/api/v3/ticker/price"
    params = {"symbol": symbol}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)

    return response.json()
    

def build_portfolio_from_trades(trades):
    balance = 0.0
    equity = 0.0
    trade_history = []

    open_positions = {}
    
    for t in trades:
        trade_id, symbol, side, price, amount, fee, balance_after, sl, tp, timestamp = t

        balance = balance_after
        equity = balance

        trade_history.append({
            "id": trade_id,
            "time": timestamp,
            "type": side,
            "symbol": symbol,
            "qty": amount,
            "price": price,
            "expense": (price * amount) / 5,
            "fee": fee,
            "balance_after": balance_after,
            "stop_loss": sl,
            "take_profit": tp
        })
        
        
        entry_dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        entry_ms = int(entry_dt.timestamp() * 1000)

        # Track open positions
        if side == "BUY":
            open_positions[symbol] = {
                "symbol": symbol,
                "entry": price,
                "qty": amount,
                "stop_loss": sl,
                "take_profit": tp,
                "entry_price": price,
                "entry_time": entry_ms    # milliseconds for frontend - js expects ms instead of date 
            }

        elif side == "SELL" and symbol in open_positions:
            del open_positions[symbol]
            
            

    return {
        "balance": balance,
        "equity": equity,
        "positions": list(open_positions.values()),
        "trade_history": trade_history[::-1]
    }
    

def build_charts(trade_history):
    """
    Build chart data arrays from trade_history.
    Charts are chronological: oldest trades first.
    """
    labels = []
    equity_curve = []
    drawdown_curve = []
    pnl_per_trade = []
    
    peak = 0.0

    for trade in reversed(trade_history):  # oldest first
        labels.append(trade["time"])
        equity_curve.append(trade["balance_after"])

        # Drawdown % relative to peak
        peak = max(peak, trade["balance_after"])
        drawdown_curve.append((trade["balance_after"] - peak) / peak * 100)

        # PnL per trade: approximate using SELL trades
        if trade["type"] == "SELL":
            pnl_per_trade.append(trade["balance_after"] - trade["expense"] - trade["fee"])

    # Trade frequency per minute
    minutes = [t["time"][:16] for t in reversed(trade_history)]  # oldest first
    counter = Counter(minutes)
    freq_labels = sorted(counter.keys())
    freq_data = [counter[m] for m in freq_labels]

    return {
        "chart_labels": labels,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "pnl_per_trade": pnl_per_trade,
        "trade_freq_labels": freq_labels,
        "trade_freq": freq_data,
    }



@app.get("/")
def read_dashboard(request: Request):
    log("\t[GET] dashboard")
    trades = db.temp_connection.get_all_trades()
    portfolio = build_portfolio_from_trades(trades)
    chart_data = build_charts(portfolio["trade_history"])

    log("\t[GET] -> rendering template with portfolio data + chart data")
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "portfolio": portfolio,
            **chart_data  # unpack chart arrays for Jinja
        }
    )
    
    
def generate_trade_chart(pdf_name: str):
    log("Generating PDF report...")
    result = run(["python3", "analysis/trade_chart.py", "--pdf", "--pdf-name", pdf_name], capture_output=True, text=True)
    if result.returncode != 0:
        log(f"Error generating report: {result.stderr}")
    else:
        log("Report generated successfully.")    
    
    
@app.get("/generate_report/")
def generate_report():
    ts       = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    pdf_name = f"report_{ts}"
    pdf_path = Path(f"analysis/reports/{pdf_name}.pdf")

    log(f"Generating PDF report → {pdf_path}")
    generate_trade_chart(pdf_name=pdf_name)
    sleep(0.5)
    if not pdf_path.exists():
        return HTMLResponse(content="<h1>Error: report generation failed</h1>", status_code=500)

    # Stream the PDF directly to the browser — opens inline in a new tab
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=pdf_path.name,
        headers={"Content-Disposition": f"inline; filename={pdf_path.name}"}
    )


    
def start_server(db_obj: PortfolioDB):
    global db
    db = db_obj
    uvicorn.run(app, host="127.0.0.1", port=8000)
    
def start_server_in_thread(db_obj: PortfolioDB):
    server_thread = threading.Thread(target=start_server, args=(db_obj,), daemon=True)
    server_thread.start()


if __name__ == "__main__":
    
    db = PortfolioDB()
    start_server_in_thread(db)