# bot.py
# Clean baseline with Donchian breakout (20/10), ATR(14)*3 stops, RSI regime filter.
# Backtests use FractionalBacktest. Live engine has +1R partial take-profit (sell 50% once).

import os, sys, time, json, math, argparse, csv, signal, logging
from datetime import datetime, timezone
from threading import Thread
import multiprocessing
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestClassifier
from flask import Flask, jsonify
import keyring

# TA + Backtesting
import ta
from backtesting import Strategy
from backtesting.lib import FractionalBacktest as Backtest  # fractional sizing
# Exchange connector
import ccxt

# ---------- Utils ----------
def jprint(obj): print(json.dumps(obj, ensure_ascii=False))
def utcnow_iso(): return datetime.now(timezone.utc).isoformat()
def ensure_dir(p): os.makedirs(p, exist_ok=True)
def round_step(value, step):
    if not step: return value
    return math.floor(value / step) * step

# ---------- Data ----------
def fetch_ohlcv_df(ex, symbol, tf, limit=1000, retries=3):
    for attempt in range(retries):
        try:
            raw = ex.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
            df = pd.DataFrame(raw, columns=["time","open","high","low","close","volume"])
            df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
            return df
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # exponential backoff
            else:
                raise e

def add_indicators(df: pd.DataFrame):
    df = df.copy()
    df["ema20"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
    df["rsi"]   = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    df["atr"]   = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range()
    return df

class MLFilter:
    def __init__(self):
        self.model = None

    def train(self, df):
        df = df.copy()
        df['future_return'] = df['close'].pct_change().shift(-1)
        df['label'] = (df['future_return'] > 0).astype(int)
        features = df[['rsi']].dropna()
        labels = df['label'].dropna()
        common_index = features.index.intersection(labels.index)
        if len(common_index) > 10:
            X = features.loc[common_index].values
            y = labels.loc[common_index].values
            self.model = RandomForestClassifier(n_estimators=10, random_state=42)
            self.model.fit(X, y)

    def predict(self, rsi):
        if self.model and not pd.isna(rsi):
            return self.model.predict([[rsi]])[0]
        return 1  # default allow

def place_order(ex, symbol, side, qty, retries=2):
    for attempt in range(retries):
        try:
            order = ex.create_order(symbol, "market", side, qty)
            return order
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # exponential backoff
                jprint({"event": "order_retry", "attempt": attempt + 1, "side": side, "error": str(e)})
            else:
                raise e

# ---------- Risk (live/paper engine only) ----------
class Risk:
    def __init__(self, equity: float, risk_frac: float, max_daily_loss_frac: float):
        self.equity = equity
        self.start_equity = equity
        self.risk_frac = risk_frac
        self.max_daily_loss_frac = max_daily_loss_frac

    def get_risk_frac(self, realized_pnl):
        dd = (self.start_equity - (self.start_equity + realized_pnl)) / self.start_equity
        if dd >= 0.05:
            return self.risk_frac * 0.5  # reduce risk if drawdown >= 5%
        return self.risk_frac

    def position_size(self, entry: float, stop: float, lot_step=None, min_qty=None, max_qty=None, realized_pnl=0.0):
        risk_per_trade = self.equity * self.get_risk_frac(realized_pnl)
        risk_per_unit = abs(entry - stop)
        if risk_per_unit <= 0: return 0.0
        qty = risk_per_trade / risk_per_unit
        if lot_step: qty = round_step(qty, lot_step)
        if min_qty: qty = max(qty, min_qty)
        if max_qty: qty = min(qty, max_qty)
        return max(0.0, qty)

    def breached(self, realized_pnl):
        dd = (self.start_equity - (self.start_equity + realized_pnl)) / self.start_equity
        return dd >= self.max_daily_loss_frac

# ---------- Backtest Strategy ----------
class BaselineStrategy(Strategy):
    # Donchian breakout with ATR stop and RSI regime filter
    entry_n = 20
    exit_n = 10
    atr_mult = 3.0
    risk_frac = 0.02      # 2% of equity per signal
    rsi_floor = 50        # filter longs if RSI below this; shorts need RSI <= (100 - rsi_floor)

    def init(self):
        close = self.data.Close
        high  = self.data.High
        low   = self.data.Low

        # Donchian bands
        def donchian_h(h, n): return pd.Series(h).rolling(int(n)).max().values
        def donchian_l(l, n): return pd.Series(l).rolling(int(n)).min().values
        self.dc_high = self.I(donchian_h, high, self.entry_n)
        self.dc_low  = self.I(donchian_l, low,  self.entry_n)
        self.exit_high = self.I(donchian_h, high, self.exit_n)
        self.exit_low  = self.I(donchian_l, low,  self.exit_n)

        # ATR(14)
        def atr14(h, l, c):
            h = pd.Series(h); l = pd.Series(l); c = pd.Series(c)
            tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
            return tr.rolling(14).mean().values
        self.atr = self.I(atr14, high, low, close)

        # RSI(14)
        def rsi14(x):
            s = pd.Series(x); d = s.diff()
            up = (d.where(d > 0, 0)).rolling(14).mean()
            dn = (-d.where(d < 0, 0)).rolling(14).mean()
            rs = up / dn.replace(0, np.nan)
            return (100 - (100 / (1 + rs))).fillna(50).values
        self.rsi = self.I(rsi14, close)

    def next(self):
        price = self.data.Close[-1]
        dc_h = self.dc_high[-1]; dc_l = self.dc_low[-1]
        xh = self.exit_high[-1]; xl = self.exit_low[-1]
        atr = self.atr[-1]; rsi = self.rsi[-1]

        if np.isnan([dc_h, dc_l, xh, xl, atr, rsi]).any():
            return
        # volatility sanity: trade only if ATR > 0.15% of price
        if atr < 0.0015 * price:
            return

        # exits
        if self.position.is_long and price <= xl:
            self.position.close()
        if self.position.is_short and price >= xh:
            self.position.close()

        # entries (breakout)
        size_frac = max(0.002, min(self.risk_frac, 0.02))
        long_ok  = (price >= dc_h) and (rsi >= self.rsi_floor)
        short_ok = (price <= dc_l) and (rsi <= (100 - self.rsi_floor))

        if not self.position and long_ok:
            self.buy(size=size_frac, sl=price - self.atr_mult * atr)
        elif not self.position and short_ok:
            self.sell(size=size_frac, sl=price + self.atr_mult * atr)

# ---------- Live/Paper Engine ----------
class Engine:
    def __init__(self, args):
        self.args = args
        load_dotenv()
        self.exchange_id = os.getenv("EXCHANGE", "kraken")
        self.api_key = keyring.get_password("trading_bot", "api_key") or os.getenv("API_KEY", "")
        self.api_secret = keyring.get_password("trading_bot", "api_secret") or os.getenv("API_SECRET", "")
        self.password = keyring.get_password("trading_bot", "api_password") or os.getenv("API_PASSWORD", None) or os.getenv("PASSPHRASE", None)
        symbols_str = os.getenv("SYMBOLS", os.getenv("SYMBOL", "SOL/USD"))
        self.symbols = [s.strip() for s in symbols_str.split(",")]
        self.timeframe = os.getenv("TIMEFRAME", "1h")
        self.min_volume = float(os.getenv("MIN_VOLUME", "50"))
        self.max_spread = float(os.getenv("MAX_SPREAD", "0.001"))
        self.risk_frac = float(os.getenv("RISK_FRAC", "0.01"))
        self.max_daily_loss = float(os.getenv("MAX_DAILY_LOSS", "0.03"))
        self.equity = float(os.getenv("EQUITY", "1000"))
        self.paper = (not args.live)
        self.log_dir = "logs"; ensure_dir(self.log_dir)
        self.trades_csv = os.path.join(self.log_dir, "trades.csv")
        self.tg_token = keyring.get_password("trading_bot", "tg_token") or os.getenv("TELEGRAM_BOT_TOKEN","")
        self.tg_chat  = keyring.get_password("trading_bot", "tg_chat") or os.getenv("TELEGRAM_CHAT_ID","")
        self.loop_count = 0
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename='logs/bot.log', filemode='a')

        # Multi-symbol support
        self.positions = {s: 0.0 for s in self.symbols}
        self.entry_prices = {s: None for s in self.symbols}
        self.tp1_dones = {s: False for s in self.symbols}
        self.last_prices = {s: None for s in self.symbols}
        self.ml = {s: MLFilter() for s in self.symbols}

        # Web dashboard
        self.app = Flask(__name__)

        @self.app.route('/')
        def dashboard():
            html = """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Trading Bot Dashboard</title>
                <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; background-color: #f4f4f4; line-height: 1.6; }
                    h1 { color: #333; text-align: center; margin-bottom: 30px; }
                    .summary { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; text-align: center; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
                    .summary h2 { margin: 0; font-size: 1.5em; }
                    .summary p { margin: 10px 0 0; font-size: 1.2em; }
                    .summary .positive { color: #28a745; }
                    .summary .negative { color: #dc3545; }
                    .container { max-width: 1200px; margin: 0 auto; display: grid; grid-template-columns: 1fr; gap: 20px; }
                    @media (min-width: 768px) { .container { grid-template-columns: 1fr 1fr; } }
                    .full-width { grid-column: 1 / -1; }
                    .status { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
                    .status h2 { margin-top: 0; color: #555; }
                    .status-item { margin: 10px 0; }
                    .positions { margin-top: 20px; }
                    .trades { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                    table { width: 100%; border-collapse: collapse; }
                    th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #ddd; }
                    th { background-color: #f2f2f2; }
                    .pnl-positive { color: green; }
                    .pnl-negative { color: red; }
                    .chart-container { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
                    .help { background: #e9ecef; padding: 20px; border-radius: 8px; margin-top: 20px; }
                    .help ul { list-style-type: disc; padding-left: 20px; }
                    .readiness { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
                    .readiness h2 { margin-top: 0; }
                    .progress-bar { width: 100%; background-color: #f0f0f0; border-radius: 10px; overflow: hidden; height: 20px; margin: 10px 0; }
                    .progress-fill { height: 100%; background-color: #28a745; transition: width 0.5s; }
                    .criteria { list-style: none; padding: 0; }
                    .criteria li { margin: 5px 0; }
                    .criteria li:before { content: "❌"; color: red; margin-right: 10px; }
                    .criteria li.met:before { content: "✅"; color: green; }
                    button { background-color: #dc3545; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-size: 16px; }
                    button:hover { background-color: #c82333; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Trading Bot Dashboard</h1>
                    <div id="summary" class="summary full-width"></div>
                    <div class="chart-container full-width">
                        <h3>Equity Over Time <span title="Shows how your virtual balance changes as the bot trades">(?)</span></h3>
                        <canvas id="equityChart"></canvas>
                    </div>
                    <div id="readiness" class="readiness"></div>
                    <div id="status" class="status"></div>
                    <div id="trades" class="trades full-width"></div>
                    <button onclick="stopBot()" class="full-width" style="width: auto; margin: 20px auto; display: block;">Stop Bot</button>
                    <div class="help full-width">
                        <h3>How to Read This</h3>
                        <ul>
                            <li><strong>Equity Chart:</strong> Tracks your simulated balance over time.</li>
                            <li><strong>Status:</strong> Current bot state, positions, and balance.</li>
                            <li><strong>Trades:</strong> List of recent simulated trades. Green PnL = profit, Red = loss.</li>
                            <li><strong>Stop Bot:</strong> Safely stops the bot.</li>
                        </ul>
                    </div>
                </div>
                <script>
                let equityChart;
                function initChart() {
                    const ctx = document.getElementById('equityChart').getContext('2d');
                    equityChart = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: [],
                            datasets: [{
                                label: 'Equity',
                                data: [],
                                borderColor: 'rgba(75, 192, 192, 1)',
                                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                                fill: true,
                            }]
                        },
                        options: {
                            responsive: true,
                            animation: {
                                duration: 1000,
                                easing: 'easeInOutQuad'
                            },
                            scales: {
                                x: { display: false },
                                y: { beginAtZero: false }
                            }
                        }
                    });
                }
                function updateChart() {
                    fetch('/equity').then(r=>r.json()).then(d=>{
                        const data = d.equity;
                        const labels = data.map((_, i) => i);
                        equityChart.data.labels = labels;
                        equityChart.data.datasets[0].data = data;
                        equityChart.update();
                    });
                }
                function updateSummary() {
                    fetch('/readiness').then(r=>r.json()).then(d=>{
                        let pnlClass = d.details.total_pnl > 0 ? 'positive' : d.details.total_pnl < 0 ? 'negative' : '';
                        let html = '<h2>Quick Summary</h2>';
                        html += '<p>Balance: $' + (1000 + d.details.total_pnl).toFixed(2) + ' | Trades: ' + d.details.total_trades + ' | Win Rate: ' + d.details.win_rate.toFixed(1) + '% | PnL: <span class="' + pnlClass + '">$' + d.details.total_pnl.toFixed(2) + '</span></p>';
                        document.getElementById('summary').innerHTML = html;
                    });
                }
                function updateReadiness() {
                    fetch('/readiness').then(r=>r.json()).then(d=>{
                        let html = '<h2>Live Trading Readiness</h2>';
                        html += '<p>Score: ' + d.score.toFixed(0) + '% ready for real money trading.</p>';
                        html += '<div class="progress-bar"><div class="progress-fill" style="width: ' + d.score + '%"></div></div>';
                        html += '<ul class="criteria">';
                        const labels = {
                            "backtest_run": "Backtest completed",
                            "sufficient_trades": "At least 10 trades in paper mode",
                            "win_rate_good": "Win rate >= 50%",
                            "positive_pnl": "Total profit > $0",
                            "low_drawdown": "Max drawdown <= 10%",
                            "api_keys_set": "API keys configured"
                        };
                        for (let key in d.criteria) {
                            let met = d.criteria[key];
                            html += '<li class="' + (met ? 'met' : '') + '">' + labels[key] + '</li>';
                        }
                        html += '</ul>';
                        if (d.score >= 80) {
                            html += '<p style="color: lightgreen; font-weight: bold;">🎉 Ready for live trading! Set --live flag and connect wallet.</p>';
                        } else {
                            html += '<p>Keep testing in paper mode to improve score.</p>';
                        }
                        document.getElementById('readiness').innerHTML = html;
                    });
                }
                function updateStatus() {
                    fetch('/status').then(r=>r.json()).then(d=>{
                        let html = '<h2>Bot Status</h2>';
                        html += '<div class="status-item"><strong>Trading Mode:</strong> ' + (d.mode === 'paper' ? 'Simulation (No Real Money)' : 'Live Trading (Real Money)') + '</div>';
                        html += '<div class="status-item"><strong>Trading Pairs:</strong> ' + d.symbols.join(', ') + '</div>';
                        html += '<div class="status-item"><strong>Current Balance:</strong> $' + d.equity.toFixed(2) + ' <span title="Your total simulated funds">(?)</span></div>';
                        let pnlClass = d.realized_pnl > 0 ? 'pnl-positive' : d.realized_pnl < 0 ? 'pnl-negative' : '';
                        html += '<div class="status-item"><strong>Total Profit/Loss:</strong> <span class="' + pnlClass + '">$' + d.realized_pnl.toFixed(2) + '</span> <span title="Profits from closed trades">(?)</span></div>';
                        html += '<div class="positions"><strong>Open Positions:</strong> <span title="Trades currently open">(?)</span><ul>';
                        let hasPositions = false;
                        for (let sym in d.positions) {
                            let pos = d.positions[sym];
                            if (pos != 0) {
                                hasPositions = true;
                                let entry = d.entry_prices[sym];
                                html += '<li>' + sym + ': Holding ' + Math.abs(pos).toFixed(6) + ' at $' + (entry ? entry.toFixed(6) : 'N/A') + '</li>';
                            }
                        }
                        if (!hasPositions) html += '<li>No open positions</li>';
                        html += '</ul></div>';
                        document.getElementById('status').innerHTML = html;
                    });
                }
                function updateTrades() {
                    fetch('/trades').then(r=>r.json()).then(d=>{
                        let html = '<h2>Recent Trades</h2>';
                        if (d.trades.length === 0) {
                            html += '<p>No trades yet. The bot is waiting for good opportunities.</p>';
                        } else {
                            html += '<table><thead><tr><th>Time</th><th>Type</th><th>Pair</th><th>Action</th><th>Amount</th><th>Price</th><th>Profit/Loss</th><th>Balance After</th></tr></thead><tbody>';
                            d.trades.forEach(t=>{
                                let pnlClass = t[6] > 0 ? 'pnl-positive' : t[6] < 0 ? 'pnl-negative' : '';
                                html += '<tr><td>' + t[0] + '</td><td>' + t[1] + '</td><td>' + t[2] + '</td><td>' + t[3] + '</td><td>' + t[4] + '</td><td>$' + t[5] + '</td><td class="' + pnlClass + '">$' + t[6] + '</td><td>$' + t[7] + '</td></tr>';
                            });
                            html += '</tbody></table>';
                        }
                        document.getElementById('trades').innerHTML = html;
                    });
                }
                function stopBot() {
                    if (confirm('Are you sure you want to stop the bot?')) {
                        fetch('/stop').then(r=>r.json()).then(d=>alert(d.message));
                    }
                }
                initChart();
                setInterval(updateStatus, 5000);
                setInterval(updateTrades, 10000);
                setInterval(updateChart, 5000);
                setInterval(updateReadiness, 10000);
                setInterval(updateSummary, 5000);
                updateStatus();
                updateTrades();
                updateChart();
                updateReadiness();
                updateSummary();
                </script>
            </body>
            </html>
            """
            return html

        @self.app.route('/status')
        def status():
            return jsonify({
                "mode": "paper" if self.paper else "live",
                "symbols": self.symbols,
                "positions": self.positions,
                "entry_prices": self.entry_prices,
                "realized_pnl": self.realized_pnl,
                "equity": self.equity + self.realized_pnl
            })

        @self.app.route('/trades')
        def trades():
            if os.path.exists(self.trades_csv):
                with open(self.trades_csv, 'r') as f:
                    lines = f.readlines()
                return jsonify({"trades": [line.strip().split(',') for line in lines[1:]]})
            return jsonify({"trades": []})

        @self.app.route('/equity')
        def equity():
            return jsonify({"equity": self.equity_history})

        @self.app.route('/readiness')
        def readiness():
            # Compute readiness metrics
            trades = []
            if os.path.exists(self.trades_csv):
                with open(self.trades_csv, 'r') as f:
                    lines = f.readlines()
                trades = [line.strip().split(',') for line in lines[1:]]
            closed_trades = [t for t in trades if float(t[6] or 0) != 0]
            total_trades = len(closed_trades)
            wins = sum(1 for t in closed_trades if float(t[6]) > 0)
            win_rate = (wins / total_trades * 100) if total_trades else 0
            total_pnl = sum(float(t[6]) for t in closed_trades)
            max_dd = 0
            if self.equity_history:
                peak = self.equity_history[0]
                for v in self.equity_history:
                    if v > peak: peak = v
                    dd = (peak - v) / peak
                    if dd > max_dd: max_dd = dd
            # Criteria
            criteria = {
                "backtest_run": os.path.exists("logs/backtest_optimized_stats.txt"),
                "sufficient_trades": total_trades >= 10,
                "win_rate_good": win_rate >= 50,
                "positive_pnl": total_pnl > 0,
                "low_drawdown": max_dd <= 0.1,
                "api_keys_set": bool(self.api_key and self.api_secret)
            }
            score = sum(criteria.values()) / len(criteria) * 100
            return jsonify({"criteria": criteria, "score": score, "details": {
                "total_trades": total_trades,
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "max_drawdown": max_dd * 100
            }})

        @self.app.route('/stop')
        def stop():
            self.kill = True
            return jsonify({"message": "Bot stopping"})

        self.web_thread = Thread(target=lambda: self.app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False))
        self.web_thread.start()

        ex_class = getattr(ccxt, self.exchange_id)
        self.ex = ex_class({
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "password": self.password,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"}
        })
        self.ex.load_markets()
        # Use first symbol for market precision (all symbols assumed same exchange)
        first_symbol = self.symbols[0]
        m = self.ex.market(first_symbol)
        self.price_step = m.get("precision", {}).get("price", None)
        self.qty_step = m.get("precision", {}).get("amount", None)
        self.min_qty = m.get("limits", {}).get("amount", {}).get("min", None)
        self.max_qty = m.get("limits", {}).get("amount", {}).get("max", None)

        self.realized_pnl = 0.0
        self.position = 0.0
        self.entry_price = None
        self.kill = False
        self.tp1_done = False
        self.last_price = None
        self.max_positions = 1  # portfolio-level: max concurrent positions
        self.equity_history = []  # for chart
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "kill", True))

        if not os.path.exists(self.trades_csv):
            with open(self.trades_csv, "w", newline="") as f:
                csv.writer(f).writerow(["ts","mode","symbol","side","qty","price","pnl","equity"])

    def _send_tg(self, html: str) -> bool:
        if not getattr(self, "tg_token", "") or not getattr(self, "tg_chat", ""):
            return False
        try:
            import urllib.request, urllib.parse, json as _json
            url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": self.tg_chat,
                "text": html,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true"
            }).encode("utf-8")
            with urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=10) as resp:
                body = resp.read().decode("utf-8","ignore")
                try:
                    obj = _json.loads(body)
                    return bool(obj.get("ok", False))
                except Exception:
                    return True
        except Exception as e:
            jprint({"event":"error","msg":f"tg_send: {e}"})
            return False

    def _notify_trade_html(self, side, qty, price, pnl, equity, symbol=None):
        symbol = symbol or self.symbol
        try:
            p = 0.0 if pnl is None else float(pnl)
        except:
            p = 0.0
        up = "🟢" if p>0 else ("🔴" if p<0 else "⚪")
        html = (
            f"<b>{up} Trade</b>\n"
            f"<b>{symbol}</b> <code>{self.timeframe}</code>\n"
            f"• Side: <b>{side}</b>\n"
            f"• Qty: <b>{qty:.6f}</b>\n"
            f"• Price: <b>{price:.6f}</b>\n"
            f"• PnL: <b>{p:.2f}</b>\n"
            f"• Equity: <b>{equity:.2f}</b>"
        )
        self._send_tg(html)

    def log_trade(self, side, qty, price, pnl=0.0, symbol=None):
        symbol = symbol or self.symbol
        self.realized_pnl += pnl
        eq = self.equity + self.realized_pnl
        with open(self.trades_csv, "a", newline="") as f:
            csv.writer(f).writerow([utcnow_iso(), "PAPER" if self.paper else "LIVE", symbol, side, qty, price, pnl, eq])
        jprint({"t": utcnow_iso(), "event": "trade", "mode": "paper" if self.paper else "live",
                "symbol": symbol, "side": side, "qty": qty, "price": price, "pnl": pnl, "equity": eq})
        # Telegram notify (HTML)
        try:
            self._notify_trade_html(side, qty, price, pnl, eq, symbol)
        except Exception as _e:
            jprint({"event":"warn","msg":f"notify_trade failed: {_e}"})

    def spread_ok(self, ticker):
        bid = ticker.get("bid"); ask = ticker.get("ask")
        if not bid or not ask: return False
        spread = (ask - bid)/ask
        return spread <= self.max_spread

    def volume_ok(self, df):
        return df["volume"].iloc[-1] >= self.min_volume

    def loop(self):
        jprint({"event":"start","mode":"paper" if self.paper else "live","symbols":self.symbols,"tf":self.timeframe})
        risk = Risk(self.equity, self.risk_frac, self.max_daily_loss)

        while not self.kill:
            self.loop_count += 1
            if self.loop_count % 100 == 0 and not self.paper:
                try:
                    balance = self.ex.fetch_balance()
                    usd_balance = balance.get("total", {}).get("USD", 0)
                    jprint({"event": "health_check", "usd_balance": usd_balance})
                    logging.info(f"Health check: USD balance {usd_balance}")
                except Exception as e:
                    jprint({"event": "health_check_error", "error": str(e)})
                    logging.error(f"Health check error: {e}")

            for symbol in self.symbols:
                try:
                    ticker = self.ex.fetch_ticker(symbol)
                    if not self.spread_ok(ticker):
                        time.sleep(1)
                        continue

                    df = add_indicators(fetch_ohlcv_df(self.ex, symbol, self.timeframe, limit=200))
                    if not self.volume_ok(df):
                        time.sleep(1)
                        continue

                    # Train ML on first loop
                    if self.loop_count == 1:
                        self.ml[symbol].train(df)

                    row = df.iloc[-1]
                    price, ema20, ema50, rsi, atr = row["close"], row["ema20"], row["ema50"], row["rsi"], row["atr"]
                    if any(pd.isna([ema20, ema50, rsi, atr])):
                        time.sleep(1)
                        continue

                    # Circuit breaker per symbol
                    if self.last_prices[symbol] is not None:
                        change_pct = abs(price - self.last_prices[symbol]) / self.last_prices[symbol]
                        circuit_breaker = change_pct > 0.05
                    else:
                        circuit_breaker = False
                        change_pct = 0.0
                    self.last_prices[symbol] = price

                    position = self.positions[symbol]
                    entry_price = self.entry_prices[symbol]
                    tp1_done = self.tp1_dones[symbol]

                    # --- TP1: take half at +1R
                    if position != 0 and entry_price is not None and not pd.isna(atr):
                        R = 3.0*atr
                        if position > 0 and (price >= entry_price + R) and not tp1_done:
                            qty_close = round(abs(position) * 0.5, 10)
                            if qty_close > 0:
                                pnl = (price - entry_price) * qty_close
                                if self.paper:
                                    position -= qty_close
                                    self.log_trade("SELL_TP1", qty_close, price, pnl, symbol)
                                else:
                                    order = place_order(self.ex, symbol, "sell", qty_close)
                                    fill_price = order.get("price") or price
                                    pnl = (fill_price - entry_price) * qty_close
                                    position -= qty_close
                                    self.log_trade("SELL_TP1", qty_close, fill_price, pnl, symbol)
                                tp1_done = True

                    long_sig  = ema20 > ema50
                    short_sig = ema20 < ema50

                    long_ok = long_sig
                    short_ok = short_sig

                    # manage existing pos with ATR*3 stops
                    if position != 0 and entry_price is not None and not pd.isna(atr):
                        if position > 0:
                            stop = entry_price - 3.0*atr
                            if price <= stop:
                                pnl = (price - entry_price) * position
                                self.log_trade("SELL_STOP", position, price, pnl, symbol)
                                position = 0; entry_price = None; tp1_done = False
                        else:
                            stop = entry_price + 3.0*atr
                            if price >= stop:
                                pnl = (entry_price - price) * abs(position)
                                self.log_trade("BUY_STOP", abs(position), price, pnl, symbol)
                                position = 0; entry_price = None; tp1_done = False

                    # Circuit breaker check
                    if circuit_breaker:
                        jprint({"event": "circuit_breaker", "symbol": symbol, "change_pct": change_pct})
                        time.sleep(1)
                        continue

                    # entries
                    if position == 0 and not pd.isna(atr):
                         if long_ok:
                             stop = price - 3.0*atr
                             qty = risk.position_size(price, stop, self.qty_step, self.min_qty, self.max_qty, realized_pnl=self.realized_pnl)
                             if qty > 0:
                                if self.paper:
                                    position = qty; entry_price = price
                                    self.log_trade("BUY", qty, price, 0.0, symbol)
                                    tp1_done = False
                                else:
                                    order = place_order(self.ex, symbol, "buy", qty)
                                    fill_price = order.get("price") or price
                                    position = qty; entry_price = fill_price
                                    self.log_trade("BUY", qty, fill_price, 0.0, symbol)
                                    tp1_done = False
                         elif short_ok:
                             stop = price + 3.0*atr
                             qty = risk.position_size(price, stop, self.qty_step, self.min_qty, self.max_qty, realized_pnl=self.realized_pnl)
                             if qty > 0:
                                qty = -qty
                                if self.paper:
                                    position = qty; entry_price = price
                                    self.log_trade("SELL", abs(qty), price, 0.0, symbol)
                                    tp1_done = False
                                else:
                                    order = place_order(self.ex, symbol, "sell", abs(qty))
                                    fill_price = order.get("price") or price
                                    position = qty; entry_price = fill_price
                                    self.log_trade("SELL", abs(qty), fill_price, 0.0, symbol)
                                    tp1_done = False

                    # Update dicts
                    self.positions[symbol] = position
                    self.entry_prices[symbol] = entry_price
                    self.tp1_dones[symbol] = tp1_done

                except Exception as e:
                    logging.error(f"Loop error for {symbol}: {e}")
                    jprint({"event":"error","symbol":symbol,"msg":str(e)})
                    time.sleep(2)

            # equity kill-switch check (shared across symbols)
            total_unrealized = 0.0
            for s in self.symbols:
                if self.positions[s] != 0 and self.entry_prices[s] is not None:
                    p = self.last_prices[s] or 0
                    pnl = (p - self.entry_prices[s]) * (self.positions[s] if self.positions[s]>0 else -abs(self.positions[s]))
                    total_unrealized += pnl
            if total_unrealized != 0 and risk.breached(self.realized_pnl + total_unrealized):
                # Close all positions
                for s in self.symbols:
                    if self.positions[s] != 0:
                        side = "SELL" if self.positions[s] > 0 else "BUY"
                        qty = abs(self.positions[s])
                        price = self.last_prices[s] or 0
                        pnl = (price - self.entry_prices[s]) * self.positions[s] if self.positions[s]>0 else (self.entry_prices[s] - price) * qty
                        self.log_trade(f"{side}_KILLSWITCH", qty, price, pnl, s)
                        self.positions[s] = 0
                        self.entry_prices[s] = None
                        self.tp1_dones[s] = False
                jprint({"event":"killswitch","reason":"max_daily_loss"})
                break

            # Update equity history for chart
            current_equity = self.equity + self.realized_pnl
            self.equity_history.append(current_equity)
            if len(self.equity_history) > 1000:
                self.equity_history.pop(0)

            time.sleep(5)

# ---------- Backtest ----------
def run_backtest(symbol: str, tf: str, exchange_id: str, walkforward: bool = False):
    ex = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    ex.load_markets()
    df = fetch_ohlcv_df(ex, symbol, tf, limit=2000)

    df_bt = df.rename(columns={"time":"Date","open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
    df_bt.set_index("Date", inplace=True)

    if walkforward:
        # Walk-forward analysis with out-of-sample testing
        total_len = len(df_bt)
        windows = 5
        window_size = total_len // windows
        with multiprocessing.Pool() as pool:
            results = pool.map(run_window, [(i, df_bt, windows, window_size, total_len) for i in range(windows)])

        avg_return = np.mean(results)
        print(f"Walk-forward average Return [%]: {avg_return}")
        print("Window returns:", results)

        out = "logs/backtest_walkforward.txt"
        ensure_dir("logs")
        with open(out, "w", encoding="utf-8") as f:
            f.write(f"Average Return [%]: {avg_return}\n")
            f.write("Window returns: " + str(results) + "\n")
        print(f"Walk-forward backtest saved to {out}")
    else:
        # Parameter optimization
        bt = Backtest(df_bt, BaselineStrategy, cash=10_000, commission=0.0007, finalize_trades=True)
        stats = bt.optimize(
            entry_n=range(10, 31, 5),  # 10,15,20,25,30
            exit_n=range(5, 16, 5),    # 5,10,15
            atr_mult=[2.0, 2.5, 3.0, 3.5],
            rsi_floor=range(45, 56, 5),  # 45,50,55
            maximize='Return [%]'
        )
        print("Optimized Parameters:")
        print(f"entry_n: {stats._strategy.entry_n}")
        print(f"exit_n: {stats._strategy.exit_n}")
        print(f"atr_mult: {stats._strategy.atr_mult}")
        print(f"rsi_floor: {stats._strategy.rsi_floor}")
        print(stats)

        out = "logs/backtest_optimized_stats.txt"
        ensure_dir("logs")
        with open(out, "w", encoding="utf-8") as f: f.write(str(stats))
    print(f"Optimized backtest saved to {out}")

def run_window(args):
    i, df_bt, windows, window_size, total_len = args
    start = i * window_size
    end = (i + 1) * window_size if i < windows - 1 else total_len
    train_end = start + (end - start) * 2 // 3
    train_df = df_bt.iloc[start:train_end]
    test_df = df_bt.iloc[train_end:end]

    bt_train = Backtest(train_df, BaselineStrategy, cash=10_000, commission=0.0007, finalize_trades=True)
    opt_stats = bt_train.optimize(
        entry_n=range(10, 31, 5),
        exit_n=range(5, 16, 5),
        atr_mult=[2.0, 2.5, 3.0, 3.5],
        rsi_floor=range(45, 56, 5),
        maximize='Return [%]'
    )
    best_entry_n = opt_stats._strategy.entry_n
    best_exit_n = opt_stats._strategy.exit_n
    best_atr_mult = opt_stats._strategy.atr_mult
    best_rsi_floor = opt_stats._strategy.rsi_floor

    class WFStrategy(BaselineStrategy):
        entry_n = best_entry_n
        exit_n = best_exit_n
        atr_mult = best_atr_mult
        rsi_floor = best_rsi_floor

    bt_test = Backtest(test_df, WFStrategy, cash=10_000, commission=0.0007, finalize_trades=True)
    test_stats = bt_test.run()
    return test_stats['Return [%]']

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest", action="store_true", help="Run backtest then exit")
    ap.add_argument("--live", action="store_true", help="Run live (default is paper)")
    ap.add_argument("--walkforward", action="store_true", help="Run walk-forward analysis in backtest")
    args = ap.parse_args()

    if args.backtest:
        load_dotenv()
        run_backtest(
            os.getenv("SYMBOL","BTC/USD"),
            os.getenv("TIMEFRAME","1h"),
            os.getenv("EXCHANGE","kraken"),
            walkforward=args.walkforward
        )
        return

    Engine(args).loop()

if __name__ == "__main__":
    main()


