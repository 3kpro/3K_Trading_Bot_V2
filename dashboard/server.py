from flask import Flask, jsonify, render_template, send_from_directory
from dashboard.state import state

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/state")
def get_state():
    return jsonify(state.to_dict())

@app.route('/favicon.ico')
def favicon():
    return '', 204  # No Content

def run_dashboard():
    app.run(host="0.0.0.0", port=5000, debug=False)