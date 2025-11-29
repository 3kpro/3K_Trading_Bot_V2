import os, json, csv, statistics as st
from datetime import datetime, timezone
from dotenv import load_dotenv
import urllib.request, urllib.parse, json as _json

load_dotenv()
LOG = os.path.join("logs", "trades.csv")
if not os.path.exists(LOG):
    print("No trades yet."); raise SystemExit(0)

pnl = []
with open(LOG, newline="", encoding="utf-8") as f:
    r = csv.DictReader(f)
    for row in r:
        p = float(row.get("pnl") or 0.0)
        if p != 0.0: pnl.append(p)

wins   = [x for x in pnl if x > 0]
losses = [x for x in pnl if x < 0]
total  = len(pnl)
summary = {
  "trades_closed": total,
  "win_rate_pct": (len(wins)/total*100.0 if total else 0.0),
  "avg_win": (st.mean(wins) if wins else 0.0),
  "avg_loss": (st.mean(losses) if losses else 0.0),
  "expectancy": (st.mean(pnl) if pnl else 0.0),
  "profit_factor": (sum(wins)/abs(sum(losses)) if wins and losses else (float("inf") if wins and not losses else 0.0)),
  "pnl_sum": sum(pnl),
}

text = (
  f"<b>📊 DS_Bot Daily</b>\n"
  f"<b>Trades:</b> {summary['trades_closed']}\n"
  f"<b>Win Rate:</b> {summary['win_rate_pct']:.1f}%\n"
  f"<b>Expectancy:</b> {summary['expectancy']:.2f}\n"
  f"<b>PF:</b> {summary['profit_factor']:.2f}\n"
  f"<b>ΣPnL:</b> {summary['pnl_sum']:.2f}\n"
)

token = os.getenv("TELEGRAM_BOT_TOKEN","")
chat  = os.getenv("TELEGRAM_CHAT_ID","")
if token and chat:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode":"HTML", "disable_web_page_preview":"true"}).encode("utf-8")
    urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=10)
else:
    print("Telegram not configured; skipping send.")

print(text)
