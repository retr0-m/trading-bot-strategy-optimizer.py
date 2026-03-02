import sqlite3



with sqlite3.connect("./log/db/portfolio.db") as conn:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, symbol, side, price, amount, fee, balance_after, sl, tp, timestamp
        FROM trades
        ORDER BY id ASC
    """)
    print(cursor.fetchall())