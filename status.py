import csv, os, json
from dotenv import load_dotenv
import ccxt

load_dotenv()
ex_id   = os.getenv("EXCHANGE", "kraken")
symbol  = os.getenv("SYMBOL", "SOL/USD")

ex = getattr(ccxt, ex_id)({"enableRateLimit": True})

# Parse the trade log
log_path = os.path.join("logs", "trades.csv")
pos = 0.0
entry_price = None
realized = 0.0

with open(log_path, newline="") as f:
    r = csv.DictReader(f)
    for row in r:
        side = row["side"]
        qty  = float(row["qty"])
        price= float(row["price"])
        pnl  = float(row["pnl"])
        realized += pnl
        if side.startswith("BUY"):
            # entering long or covering short
            if pos == 0:
                entry_price = price
            pos += qty if side == "BUY" else qty  # BUY_STOP / BUY_KILLSWITCH counted via pnl already
        elif side.startswith("SELL"):
            if pos > 0 and side == "SELL":
                pos -= qty
                if pos <= 1e-12:
                    pos = 0.0
                    entry_price = None
            else:
                # shorting not expected in current paper run; if present, treat as negative pos
                if pos == 0:
                    entry_price = price
                pos -= qty

# Get a mark price
t = ex.fetch_ticker(symbol)
bid = t.get("bid")
ask = t.get("ask")
last = t.get("last")
mark = None
if bid and ask:
    mark = (bid + ask) / 2
else:
    mark = last

unreal = 0.0
if pos and entry_price and mark:
    # if pos > 0 => long
    unreal = (mark - entry_price) * pos

print(json.dumps({
    "symbol": symbol,
    "position_qty": pos,
    "entry_price": entry_price,
    "mark": mark,
    "unrealized_pnl": unreal,
    "realized_pnl": realized
}, indent=2))
