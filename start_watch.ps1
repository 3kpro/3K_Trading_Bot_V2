param()

Set-Location "C:\DEV\Projects\ds_bot"
.\.venv\Scripts\Activate.ps1

$host.UI.RawUI.WindowTitle = "[WATCH] DS_Bot Session"

# One-shot test to Telegram so we know the pipe is good
python .\watch_targets.py --test --once | Out-Host

# Then run the 60s watcher loop
python .\watch_targets.py
