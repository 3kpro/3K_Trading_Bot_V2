param()

Set-Location "C:\DEV\Projects\ds_bot"
.\.venv\Scripts\Activate.ps1

# Optional: slow the loop a hair for stability
# (only if your bot.py uses time.sleep(1); change to 5s already? Fine to leave.)
# (No code change needed here.)

# Start trading loop (paper unless you add --live yourself)
$host.UI.RawUI.WindowTitle = "[BOT] DS_Bot Session"
python .\bot.py
