import os, csv, json, argparse, math
from datetime import datetime, timezone
from collections import defaultdict

# Optional env loader (installed earlier)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

LOG = os.path.join("logs", "trades.csv")
OUTDIR = "reports"
os.makedirs(OUTDIR, exist_ok=True)

def iso_date(ts: str) -> str:
    try:
        # handle both "...Z" and "+00:00"
        if ts.endswith("Z"):
            dt = datetime.fromisoformat(ts.replace("Z","+00:00"))
        else:
            dt = datetime.fromisoformat(ts)
        return dt.astimezone(timezone.utc).date().isoformat()
    except Exception:
        return "unknown"

def safe_float(x, default=0.0):
    try:
        if x is None or x == "": return default
        return float(x)
    except Exception:
        return default

def max_drawdown(equity_points):
    """equity_points is list[float]. Returns (max_dd_pct, peak, trough)."""
    if not equity_points: return (0.0, None, None)
    peak = equity_points[0]
    max_dd = 0.0
    peak_val = peak
    trough_val = peak
    for v in equity_points:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            peak_val = peak
            trough_val = v
    return (round(max_dd*100, 5), peak_val, trough_val)

def send_telegram(msg: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return False
    try:
        import urllib.request, urllib.parse
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False

def load_trades():
    rows = []
    if not os.path.exists(LOG):
        return rows
    with open(LOG, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows

def build_reports(rows):
    # Closed trades = rows with a non-zero pnl
    closed = [r for r in rows if safe_float(r.get("pnl")) != 0.0]
    pnl = [safe_float(r.get("pnl")) for r in closed]
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x < 0]

    # Equity curve: prefer 'equity' column; else reconstruct from EQUITY + cumsum(pnl)
    equity_col = [safe_float(r.get("equity")) for r in rows if r.get("equity") not in (None, "")]
    equity_curve = []
    if equity_col:
        equity_curve = equity_col
    else:
        start_equity = safe_float(os.getenv("EQUITY", "1000"), 1000.0)
        eq = start_equity
        for r in rows:
            eq += safe_float(r.get("pnl"))
            equity_curve.append(eq)

    # Max drawdown
    mdd_pct, peak_val, trough_val = max_drawdown(equity_curve)

    # Daily PnL (closed only)
    daily = defaultdict(float)
    for r in closed:
        d = iso_date(r.get("ts",""))
        daily[d] += safe_float(r.get("pnl"))

    total = len(pnl)
    summary = {
        "trades_closed": total,
        "win_rate_pct": round((len(wins)/total*100.0), 2) if total else 0.0,
        "avg_win": round(sum(wins)/len(wins), 6) if wins else 0.0,
        "avg_loss": round(sum(losses)/len(losses), 6) if losses else 0.0,
        "expectancy_per_trade": round((sum(pnl)/total), 6) if total else 0.0,
        "profit_factor": round((sum(wins)/abs(sum(losses))) if (wins and losses) else (float("inf") if wins and not losses else 0.0), 6),
        "pnl_sum": round(sum(pnl), 6),
        "max_drawdown_pct": mdd_pct,
    }

    # Write files
    with open(os.path.join(OUTDIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Last 30 closed trades
    last30 = closed[-30:]
    last30_fields = ["ts","mode","symbol","side","qty","price","pnl","equity"]
    with open(os.path.join(OUTDIR, "last_30_trades.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=last30_fields)
        w.writeheader()
        for r in last30:
            w.writerow({k: r.get(k,"") for k in last30_fields})

    # Daily PnL
    with open(os.path.join(OUTDIR, "daily_pnl.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date_utc","pnl"])
        for d in sorted(daily.keys()):
            w.writerow([d, round(daily[d], 6)])

    # Equity curve CSV
    with open(os.path.join(OUTDIR, "equity_curve.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["index","equity"])
        for i, v in enumerate(equity_curve):
            w.writerow([i, round(v, 6)])

    # Build a concise Telegram line
    last_trade_txt = "none"
    if last30:
        lt = last30[-1]
        last_trade_txt = f"{lt.get('side','?')} @ {lt.get('price','?')} (PnL {safe_float(lt.get('pnl')):+.2f})"

    tg = (
        f"📊 <b>DS_Bot Report</b>\n"
        f"• Closed: <b>{summary['trades_closed']}</b>  "
        f"Win%: <b>{summary['win_rate_pct']:.1f}%</b>\n"
        f"• Exp/trade: <b>{summary['expectancy_per_trade']:+.2f}</b>  "
        f"PF: <b>{'∞' if math.isinf(summary['profit_factor']) else summary['profit_factor']}</b>\n"
        f"• PnL sum: <b>{summary['pnl_sum']:+.2f}</b>  "
        f"MaxDD: <b>{summary['max_drawdown_pct']:.2f}%</b>\n"
        f"• Last closed: {last_trade_txt}"
    )

    return summary, tg

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="Send a Telegram summary if configured")
    args = ap.parse_args()

    rows = load_trades()
    if not rows:
        print("No trades found at logs/trades.csv")
        return

    summary, tg_msg = build_reports(rows)

    print(json.dumps(summary, indent=2))
    if args.send:
        ok = send_telegram(tg_msg)
        print(f"[report] telegram sent: {ok}")

if __name__ == "__main__":
    main()
