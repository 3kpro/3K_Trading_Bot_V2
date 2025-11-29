import os, json, csv
import pandas as pd
import ccxt
from dotenv import load_dotenv

load_dotenv()
ex_id = os.getenv("EXCHANGE","kraken")
sym   = os.getenv("SYMBOL","SOL/USD")
tf    = os.getenv("TIMEFRAME","1h")

ex = getattr(ccxt, ex_id)({"enableRateLimit": True})

# --- ATR(14) from recent candles ---
raw = ex.fetch_ohlcv(sym, timeframe=tf, limit=200)
df = pd.DataFrame(raw, columns=["ts","open","high","low","close","vol"])
df["prev_close"] = df["close"].shift(1)
tr = pd.concat([
    df["high"] - df["low"],
    (df["high"] - df["prev_close"]).abs(),
    (df["low"]  - df["prev_close"]).abs()
], axis=1).max(axis=1)
atr_val = float(tr.rolling(14).mean().iloc[-1])

# --- Parse simple paper position from logs/trades.csv ---
log_path = os.path.join("logs","trades.csv")
pos = 0.0
entry = None
realized = 0.0

if os.path.exists(log_path):
    with open(log_path, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if row.get("symbol") != sym:
                continue
            side = row.get("side","")
            qty  = float(row.get("qty","0") or 0)
            price= float(row.get("price","0") or 0)
            pnl  = float(row.get("pnl","0") or 0)
            realized += pnl

            if side.startswith("BUY"):
                # open/increase long
                if pos == 0:
                    entry = price
                pos += qty
            elif side.startswith("SELL"):
                # reduce/close long
                pos -= qty
                if pos <= 1e-12:
                    pos = 0.0
                    entry = None

# --- Mark price ---
t = ex.fetch_ticker(sym)
bid = t.get("bid"); ask = t.get("ask"); last = t.get("last")
mark = (bid + ask)/2 if (bid and ask) else last
mark = float(mark) if mark is not None else None

# --- Build targets from engine’s ATR*3 stop logic ---
if pos > 0 and entry is not None and mark is not None and atr_val is not None:
    R = 3.0 * atr_val                   # 1R risk based on ATR*3 stop
    stop = entry - R
    tp1  = entry + 1*R
    tp2  = entry + 2*R
    tp3  = entry + 3*R
    progress_R = (mark - entry) / R if R > 0 else 0.0

    out = {
        "symbol": sym,
        "timeframe": tf,
        "position_qty": round(pos, 10),
        "entry": round(entry, 6),
        "mark": round(mark, 6),
        "ATR14": round(atr_val, 6),
        "R_value": round(R, 6),
        "stop": round(stop, 6),
        "tp1_+1R": round(tp1, 6),
        "tp2_+2R": round(tp2, 6),
        "tp3_+3R": round(tp3, 6),
        "progress_in_R": round(progress_R, 3),
        "realized_pnl": round(realized, 6)
    }
else:
    out = {"status": "no open long position detected (paper)", "symbol": sym, "timeframe": tf}

print(json.dumps(out, indent=2))
