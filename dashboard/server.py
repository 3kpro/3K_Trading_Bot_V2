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
