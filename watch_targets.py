import os, sys, time, json, subprocess, argparse, math
from dotenv import load_dotenv

STATE_FILE = ".watch_state.json"

# ---------- Tiny utils ----------
def fmt(x, n=3):
    try:
        return f"{float(x):,.{n}f}"
    except Exception:
        return str(x)

def safe(x, n=3):
    return "-" if x is None else fmt(x, n)

def beep(times=1):
    try:
        import winsound
        for _ in range(times):
            winsound.Beep(1000, 250)
            time.sleep(0.15)
    except Exception:
        sys.stdout.write("\a" * times); sys.stdout.flush()

# ---------- Telegram (HTML formatting) ----------
def send_tg(msg_html: str) -> bool:
    import urllib.request, urllib.parse, json as _json
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        print("[watch] Telegram not configured (missing TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID)")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": chat,
        "text": msg_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        body = urllib.parse.urlencode(data).encode("utf-8")
        with urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"), timeout=10) as resp:
            raw = resp.read()
            try:
                obj = _json.loads(raw.decode("utf-8", "ignore"))
                ok = bool(obj.get("ok"))
                if not ok:
                    print(f"[watch] TG send failed: {obj}")
                return ok
            except Exception:
                return True
    except Exception as e:
        print(f"[watch] TG error: {e}")
        return False

# ---------- State ----------
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"last_level": 0, "had_pos": False}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)

# ---------- Targets snapshot via targets.py ----------
def get_targets():
    p = subprocess.run([sys.executable, "targets.py"], capture_output=True, text=True)
    if p.returncode != 0:
        return {"error": p.stderr.strip()}
    try:
        return json.loads(p.stdout)
    except Exception as e:
        return {"error": f"parse error: {e}", "raw": p.stdout[:300]}

def level_from_progress(progress):
    # 0,<1R ; 1,>=1R ; 2,>=2R ; 3,>=3R
    if progress is None:
        return 0
    if progress >= 3: return 3
    if progress >= 2: return 2
    if progress >= 1: return 1
    return 0

def describe_console(data):
    sym = data.get("symbol")
    tf  = data.get("timeframe")
    mark = data.get("mark"); entry = data.get("entry"); stop = data.get("stop")
    pR = data.get("progress_in_R")
    return f"{sym} {tf} | mark={mark} entry={entry} stop={stop} progress={pR}R"

def build_html(data, header_emoji="🛰️", header_text="Watcher"):
    sym   = data.get("symbol")
    tf    = data.get("timeframe")
    mark  = data.get("mark")
    entry = data.get("entry")
    stop  = data.get("stop")
    tp1   = data.get("tp1_+1R")
    tp2   = data.get("tp2_+2R")
    tp3   = data.get("tp3_+3R")
    qty   = data.get("position_qty")
    pR    = data.get("progress_in_R")
    atr   = data.get("ATR14")
    Rval  = data.get("R_value")

    # Unrealized PnL (only for long here; that matches your engine’s current mode)
    unreal = None
    if qty and entry is not None and mark is not None:
        unreal = (float(mark) - float(entry)) * float(qty)

    # Δ from entry in % (mark vs entry)
    delta_pct = None
    if entry and mark:
        try:
            delta_pct = (float(mark) - float(entry)) / float(entry) * 100
        except Exception:
            delta_pct = None

    lines = [
        f"<b>{header_emoji} {header_text}</b>",
        f"<b>{sym}</b> <code>{tf}</code>",
        f"• Price: <b>{safe(mark)}</b> (entry {safe(entry)}, stop {safe(stop)})",
        f"• Qty: <b>{safe(qty,4)}</b> | ATR14: {safe(atr)} | 1R: {safe(Rval)}",
        f"• Targets: +1R {safe(tp1)} | +2R {safe(tp2)} | +3R {safe(tp3)}",
        f"• Progress: <b>{safe(pR,3)}R</b>",
    ]
    if unreal is not None:
        up = "🟢" if unreal >= 0 else "🔴"
        if delta_pct is not None:
            lines.append(f"• PnL (unrealized): {up} <b>{fmt(unreal,2)}</b> ({fmt(delta_pct,2)}%)")
        else:
            lines.append(f"• PnL (unrealized): {up} <b>{fmt(unreal,2)}</b>")

    return "\n".join(lines)

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=60, help="Seconds between checks")
    ap.add_argument("--test", action="store_true", help="Send a test Telegram message and exit")
    ap.add_argument("--once", action="store_true", help="Run one cycle then exit")
    args = ap.parse_args()

    if args.test:
        data = get_targets()
        if "status" in data:
            msg = f"<b>🛰️ DS_Bot watcher TEST</b>\n{data['status']}"
        elif "error" in data:
            msg = f"<b>🛰️ DS_Bot watcher TEST</b>\nError: {data['error']}"
        else:
            msg = build_html(data, "🛰️", "Watcher TEST")
        ok = send_tg(msg)
        print(f"[watch] test sent: {ok}")
        return

    state = load_state()
    print("[watch] started; interval =", args.interval)

    while True:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        data = get_targets()

        # Handle errors / no position
        if "error" in data:
            print(f"[{ts}] watcher: {data['error']}")
            time.sleep(args.interval)
            if args.once: break
            continue

        if "status" in data:
            print(f"[{ts}] watcher: {data['status']}")
            if state.get("had_pos", False):
                send_tg(f"<b>⚪ Position closed</b>\n{build_html(data, '🧹', 'Closed')}")
                beep(1)
                state["had_pos"] = False
                state["last_level"] = 0
                save_state(state)
            time.sleep(args.interval)
            if args.once: break
            continue

        # Open position snapshot
        print(f"[{ts}] {describe_console(data)}")
        state["had_pos"] = True

        # Level alerts
        pR  = data.get("progress_in_R")
        lvl = level_from_progress(pR)
        last = state.get("last_level", 0)

        if lvl > last:
            stars = "⭐" * lvl
            title = f"+{lvl}R reached {stars}"
            send_tg(build_html(data, "✅", title))
            beep(lvl)
            state["last_level"] = lvl
            save_state(state)

        # Stop alert
        stop = data.get("stop")
        mark = data.get("mark")
        if stop is not None and mark is not None and mark <= stop:
            send_tg(build_html(data, "🛑", "STOP touched/breached"))
            beep(2)

        if args.once: break
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
