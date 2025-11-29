from flask import Flask, jsonify, render_template_string
from dashboard.state import state
import os

app = Flask(__name__, 
            template_folder='dashboard',
            static_folder='static')

# Load the HTML template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>3K Trading Bot - Live Dashboard</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 100%);
            color: #e4e6eb;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            padding: 20px;
            min-height: 100vh;
        }

        .container {
            max-width: 1600px;
            margin: 0 auto;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding: 20px;
            background: rgba(0, 255, 170, 0.05);
            border-radius: 12px;
            border-left: 4px solid #00ffaa;
        }

        h1 {
            font-size: 28px;
            font-weight: 700;
            color: #00ffaa;
        }

        .mode-badge {
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .mode-badge.paper {
            background: #1a5f7a;
            color: #4fc3f7;
        }

        .mode-badge.backtest {
            background: #6d4c41;
            color: #ffb74d;
        }

        .mode-badge.live {
            background: #c62828;
            color: #ff5252;
        }

        /* READINESS SECTION */
        .readiness-card {
            background: rgba(76, 175, 80, 0.1);
            border: 2px solid #4caf50;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 25px;
        }

        .readiness-card h2 {
            color: #4caf50;
            margin-bottom: 15px;
            font-size: 18px;
        }

        .eta-container {
            display: flex;
            gap: 30px;
            align-items: center;
            margin-bottom: 20px;
        }

        .eta-value {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .eta-label {
            font-size: 12px;
            color: #b0bec5;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .eta-text {
            font-size: 24px;
            font-weight: 700;
            color: #4caf50;
        }

        .score-circle {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            background: conic-gradient(#4caf50 0deg, #4caf50 calc(var(--score) * 3.6deg), #263238 0deg);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 28px;
            color: #4caf50;
            box-shadow: 0 4px 20px rgba(76, 175, 80, 0.2);
        }

        .readiness-checks {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            margin-top: 20px;
        }

        .check-item {
            padding: 12px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            display: flex;
            gap: 10px;
            align-items: center;
            font-size: 13px;
        }

        .check-item.pass {
            background: rgba(76, 175, 80, 0.2);
            border-left: 3px solid #4caf50;
        }

        .check-item.fail {
            background: rgba(244, 67, 54, 0.2);
            border-left: 3px solid #f44336;
        }

        .check-icon {
            font-size: 16px;
            font-weight: bold;
        }

        /* STATS GRID */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }

        .stat-card {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            padding: 20px;
            backdrop-filter: blur(10px);
        }

        .stat-label {
            font-size: 12px;
            color: #90a4ae;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }

        .stat-value {
            font-size: 24px;
            font-weight: 700;
            color: #ffffff;
        }

        .stat-value.positive {
            color: #4caf50;
        }

        .stat-value.negative {
            color: #f44336;
        }

        .stat-value.neutral {
            color: #ffb74d;
        }

        /* CHART GRID */
        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(450px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }

        .chart-container {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 20px;
            backdrop-filter: blur(10px);
        }

        .chart-container h3 {
            color: #e4e6eb;
            margin-bottom: 15px;
            font-size: 16px;
            font-weight: 600;
        }

        .chart-wrapper {
            position: relative;
            height: 300px;
        }

        /* ACTIVITY TABLE */
        .activity-section {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 20px;
            backdrop-filter: blur(10px);
        }

        .activity-section h3 {
            color: #e4e6eb;
            margin-bottom: 15px;
            font-size: 16px;
            font-weight: 600;
        }

        .activity-log {
            max-height: 300px;
            overflow-y: auto;
            display: flex;
            flex-direction: column-reverse;
        }

        .log-entry {
            padding: 10px;
            border-left: 3px solid #4caf50;
            margin-bottom: 8px;
            font-size: 12px;
            background: rgba(76, 175, 80, 0.1);
            border-radius: 4px;
        }

        .log-entry.signal-long {
            border-left-color: #4caf50;
            background: rgba(76, 175, 80, 0.15);
        }

        .log-entry.signal-short {
            border-left-color: #f44336;
            background: rgba(244, 67, 54, 0.15);
        }

        .log-entry.signal-flat {
            border-left-color: #9e9e9e;
            background: rgba(158, 158, 158, 0.1);
        }

        .log-timestamp {
            color: #90a4ae;
            font-size: 11px;
        }

        .log-message {
            color: #e4e6eb;
            margin-top: 4px;
        }

        /* SCROLLBAR STYLING */
        .activity-log::-webkit-scrollbar {
            width: 6px;
        }

        .activity-log::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
        }

        .activity-log::-webkit-scrollbar-thumb {
            background: rgba(76, 175, 80, 0.4);
            border-radius: 10px;
        }

        .activity-log::-webkit-scrollbar-thumb:hover {
            background: rgba(76, 175, 80, 0.6);
        }

        /* FOOTER */
        footer {
            text-align: center;
            color: #607d8b;
            font-size: 12px;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
        }

        @media (max-width: 1200px) {
            .charts-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🤖 3K Trading Bot</h1>
            <div style="margin-top: 10px; font-size: 18px; color: #00ffaa;">
                <strong>Status:</strong> <span id="simpleStatus">Learning...</span> |
                <strong>Balance:</strong> <span id="simpleBalance">$1000</span> |
                <strong>Signals Today:</strong> <span id="simpleSignals">0</span>
            </div>
            <span id="modeDisplay" class="mode-badge paper">Practice Mode</span>
        </header>

        <!-- READINESS SECTION -->
        <div class="readiness-card">
            <h2>🎯 Ready for Real Money Trading?</h2>
            <div style="text-align: center; margin-bottom: 20px;">
                <div style="font-size: 24px; font-weight: bold; color: #4caf50; margin-bottom: 10px;">
                    <span id="etaDisplay">Calculating...</span>
                </div>
                <div style="font-size: 14px; color: #90a4ae;">
                    Until bot has enough experience to trade safely
                </div>
            </div>
            <div class="progress" style="margin-bottom: 20px;">
                <div id="progress-bar"></div>
            </div>
            <div style="font-size: 13px; color: #90a4ae; text-align: center;">
                <span id="readinessStatus">Bot is learning from market data...</span>
            </div>
        </div>

        <!-- STATS GRID -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Account Balance</div>
                <div class="stat-value" id="statEquity">$0.00</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Current Price</div>
                <div class="stat-value neutral" id="statPrice">0.00</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Trend Strength</div>
                <div class="stat-value neutral" id="statRSI" title="How strong the price movement is (0-100)">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Price Movement</div>
                <div class="stat-value neutral" id="statATR" title="How much price moves on average">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Trades Made</div>
                <div class="stat-value neutral" id="statTrades">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Winning Trades</div>
                <div class="stat-value neutral" id="statWinRate" title="Percentage of profitable trades">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Profit</div>
                <div class="stat-value" id="statPnL">$0.00</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Biggest Loss</div>
                <div class="stat-value negative" id="statDD" title="Worst drop from peak balance">--</div>
            </div>
        </div>

        <!-- CHARTS -->
        <div class="charts-grid">
            <div class="chart-container">
                <h3>💰 Money Over Time</h3>
                <div class="chart-wrapper">
                    <canvas id="equityChart"></canvas>
                </div>
            </div>

            <div class="chart-container">
                <h3>📈 Price with Trend Lines</h3>
                <div class="chart-wrapper">
                    <canvas id="priceChart"></canvas>
                </div>
            </div>

            <div class="chart-container">
                <h3>⚡ Price Momentum</h3>
                <div class="chart-wrapper">
                    <canvas id="rsiChart"></canvas>
                </div>
            </div>

            <div class="chart-container">
                <h3>🎲 Price Risk</h3>
                <div class="chart-wrapper">
                    <canvas id="atrChart"></canvas>
                </div>
            </div>
        </div>

        <!-- ACTIVITY LOG -->
        <div class="activity-section">
            <h3>🤖 What the Bot is Doing</h3>
            <div class="activity-log" id="activityLog">
                <div class="log-entry">
                    <div class="log-timestamp">Now</div>
                    <div class="log-message">Bot started. Scanning market for trading opportunities...</div>
                </div>
            </div>
        </div>

        <footer>
            <p>Real-time dashboard for 3K Trading Bot | Last update: <span id="lastUpdate">--</span></p>
        </footer>
    </div>

    <script>
        let charts = {};

        const chartConfig = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        color: '#e4e6eb',
                        font: { size: 11 }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#90a4ae' }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#90a4ae' }
                }
            }
        };

        function initCharts() {
            charts.equity = new Chart(document.getElementById('equityChart'), {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Equity',
                        data: [],
                        borderColor: '#4caf50',
                        backgroundColor: 'rgba(76, 175, 80, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        pointHoverRadius: 6
                    }]
                },
                options: { ...chartConfig }
            });

            charts.price = new Chart(document.getElementById('priceChart'), {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Price',
                            data: [],
                            borderColor: '#2196f3',
                            borderWidth: 2,
                            tension: 0.4,
                            pointRadius: 0
                        },
                        {
                            label: 'Donchian Upper',
                            data: [],
                            borderColor: '#f44336',
                            borderWidth: 1,
                            borderDash: [5, 5],
                            tension: 0.4,
                            pointRadius: 0
                        },
                        {
                            label: 'Donchian Lower',
                            data: [],
                            borderColor: '#4caf50',
                            borderWidth: 1,
                            borderDash: [5, 5],
                            tension: 0.4,
                            pointRadius: 0
                        }
                    ]
                },
                options: { ...chartConfig }
            });

            charts.rsi = new Chart(document.getElementById('rsiChart'), {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'RSI(14)',
                        data: [],
                        borderColor: '#ffb74d',
                        backgroundColor: 'rgba(255, 183, 77, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0
                    }]
                },
                options: {
                    ...chartConfig,
                    scales: {
                        ...chartConfig.scales,
                        y: {
                            ...chartConfig.scales.y,
                            min: 0,
                            max: 100
                        }
                    }
                }
            });

            charts.atr = new Chart(document.getElementById('atrChart'), {
                type: 'bar',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'ATR(14)',
                        data: [],
                        backgroundColor: 'rgba(103, 58, 183, 0.6)',
                        borderColor: '#673ab7',
                        borderWidth: 1
                    }]
                },
                options: { ...chartConfig }
            });
        }

        async function fetchState() {
            try {
                const response = await fetch('/state');
                const data = await response.json();
                updateDashboard(data);
            } catch (error) {
                console.error('Failed to fetch state:', error);
            }
        }

        function updateDashboard(data) {
            // Simple status bar
            document.getElementById('simpleBalance').textContent = `$${data.equity.toFixed(2)}`;
            document.getElementById('simpleSignals').textContent = data.total_trades;
            document.getElementById('simpleStatus').textContent = data.readiness.can_trade_live ? 'Ready!' : 'Learning...';

            document.getElementById('statEquity').textContent = `$${data.equity.toFixed(2)}`;
            document.getElementById('statPrice').textContent = data.last_price.toFixed(6);
            document.getElementById('statRSI').textContent = data.rsi.toFixed(1);
            document.getElementById('statATR').textContent = data.atr.toFixed(6);
            document.getElementById('statTrades').textContent = data.total_trades;
            document.getElementById('statWinRate').textContent = `${data.win_rate_pct.toFixed(1)}%`;
            document.getElementById('statPnL').textContent = `$${data.expectancy.toFixed(2)}`;
            document.getElementById('statDD').textContent = `${data.max_drawdown_pct.toFixed(2)}%`;

            const pnlEl = document.getElementById('statPnL');
            if (data.expectancy > 0) {
                pnlEl.className = 'stat-value positive';
            } else if (data.expectancy < 0) {
                pnlEl.className = 'stat-value negative';
            } else {
                pnlEl.className = 'stat-value neutral';
            }

            const modeEl = document.getElementById('modeDisplay');
            if (data.mode.live) {
                modeEl.className = 'mode-badge live';
                modeEl.textContent = '🔴 Real Money';
            } else if (data.mode.backtest) {
                modeEl.className = 'mode-badge backtest';
                modeEl.textContent = '📊 Testing';
            } else {
                modeEl.className = 'mode-badge paper';
                modeEl.textContent = '📋 Practice Mode';
            }

            updateReadiness(data.readiness);
            updateCharts(data);
            updateActivity(data);

            document.getElementById('lastUpdate').textContent = new Date(data.last_update).toLocaleTimeString();
        }

        function updateReadiness(readiness) {
            document.getElementById('etaDisplay').textContent = readiness.eta_readable;

            // Update progress bar
            const progressPct = readiness.score_pct;
            document.getElementById('progress-bar').style.width = progressPct + '%';

            let statusText = `Bot has learned ${readiness.passed} out of ${readiness.total} important things`;
            if (readiness.can_trade_live) {
                statusText += ' 🎉 Ready for real money trading!';
            } else {
                statusText += '. Keep watching as it learns more.';
            }
            document.getElementById('readinessStatus').textContent = statusText;
        }

        function updateActivity(data) {
            const activityLog = document.getElementById('activityLog');
            activityLog.innerHTML = '';

            // Add current status
            const statusEntry = document.createElement('div');
            statusEntry.className = 'log-entry';
            statusEntry.innerHTML = `
                <div class="log-timestamp">${new Date().toLocaleTimeString()}</div>
                <div class="log-message">Bot is watching ${data.symbol} for good trades...</div>
            `;
            activityLog.appendChild(statusEntry);

            // Add recent signals from history
            if (data.signal_history && data.timestamp_history) {
                const recentSignals = data.signal_history.slice(-3);
                const recentTimes = data.timestamp_history.slice(-3);

                for (let i = recentSignals.length - 1; i >= 0; i--) {
                    if (recentSignals[i]) {
                        const signalEntry = document.createElement('div');
                        signalEntry.className = `log-entry signal-${recentSignals[i].toLowerCase()}`;
                        const action = recentSignals[i] === 'long' ? 'buy' : 'sell';
                        signalEntry.innerHTML = `
                            <div class="log-timestamp">${new Date(recentTimes[i]).toLocaleTimeString()}</div>
                            <div class="log-message">Bot wants to ${action} ${data.symbol}</div>
                        `;
                        activityLog.appendChild(signalEntry);
                    }
                }
            }
        }

        function updateCharts(data) {
            const labels = data.timestamp_history.map(ts => {
                const d = new Date(ts);
                return d.toLocaleTimeString();
            }).slice(-50);

            if (charts.equity) {
                charts.equity.data.labels = Array.from({ length: data.equity_history.length }, (_, i) => i);
                charts.equity.data.datasets[0].data = data.equity_history;
                charts.equity.update('none');
            }

            if (charts.price && data.price_history.length > 0) {
                charts.price.data.labels = labels;
                charts.price.data.datasets[0].data = data.price_history.slice(-labels.length);
                charts.price.data.datasets[1].data = Array(labels.length).fill(data.donchian_upper);
                charts.price.data.datasets[2].data = Array(labels.length).fill(data.donchian_lower);
                charts.price.update('none');
            }

            if (charts.rsi && data.rsi_history.length > 0) {
                charts.rsi.data.labels = labels;
                charts.rsi.data.datasets[0].data = data.rsi_history.slice(-labels.length);
                charts.rsi.update('none');
            }

            if (charts.atr && data.atr_history.length > 0) {
                charts.atr.data.labels = labels;
                charts.atr.data.datasets[0].data = data.atr_history.slice(-labels.length);
                charts.atr.update('none');
            }
        }

        initCharts();
        fetchState();
        setInterval(fetchState, 1000);
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route("/state")
def get_state():
    return jsonify(state.to_dict())

def run_dashboard():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
            const activityLog = document.getElementById('activityLog');
            activityLog.innerHTML = '';

            // Add current status
            const statusEntry = document.createElement('div');
            statusEntry.className = 'log-entry';
            statusEntry.innerHTML = `
                <div class="log-timestamp">${new Date().toLocaleTimeString()}</div>
                <div class="log-message">Bot is watching ${data.symbol} for good trades...</div>
            `;
            activityLog.appendChild(statusEntry);

            // Add recent signals from history
            if (data.signal_history && data.timestamp_history) {
                const recentSignals = data.signal_history.slice(-3);
                const recentTimes = data.timestamp_history.slice(-3);

                for (let i = recentSignals.length - 1; i >= 0; i--) {
                    if (recentSignals[i]) {
                        const signalEntry = document.createElement('div');
                        signalEntry.className = `log-entry signal-${recentSignals[i].toLowerCase()}`;
                        const action = recentSignals[i] === 'long' ? 'buy' : 'sell';
                        signalEntry.innerHTML = `
                            <div class="log-timestamp">${new Date(recentTimes[i]).toLocaleTimeString()}</div>
                            <div class="log-message">Bot wants to ${action} ${data.symbol}</div>
                        `;
                        activityLog.appendChild(signalEntry);
                    }
                }
            }
        }

        function updateCharts(data) {
            const labels = data.timestamp_history.map(ts => {
                const d = new Date(ts);
                return d.toLocaleTimeString();
            }).slice(-50);

            if (charts.equity) {
                charts.equity.data.labels = Array.from({ length: data.equity_history.length }, (_, i) => i);
                charts.equity.data.datasets[0].data = data.equity_history;
                charts.equity.update('none');
            }

            if (charts.price && data.price_history.length > 0) {
                charts.price.data.labels = labels;
                charts.price.data.datasets[0].data = data.price_history.slice(-labels.length);
                charts.price.data.datasets[1].data = Array(labels.length).fill(data.donchian_upper);
                charts.price.data.datasets[2].data = Array(labels.length).fill(data.donchian_lower);
                charts.price.update('none');
            }

            if (charts.rsi && data.rsi_history.length > 0) {
                charts.rsi.data.labels = labels;
                charts.rsi.data.datasets[0].data = data.rsi_history.slice(-labels.length);
                charts.rsi.update('none');
            }

            if (charts.atr && data.atr_history.length > 0) {
                charts.atr.data.labels = labels;
                charts.atr.data.datasets[0].data = data.atr_history.slice(-labels.length);
                charts.atr.update('none');
            }
        }

        initCharts();
        fetchState();
        setInterval(fetchState, 1000);
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route("/state")
def get_state():
    return jsonify(state.to_dict())

def run_dashboard():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
