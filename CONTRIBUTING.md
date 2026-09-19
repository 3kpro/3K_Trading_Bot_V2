# Contributing to 3K Trading Bot

This is an experimental Python trading research project. Contributions that improve correctness, reproducibility, and documentation are welcome. Live order execution is disabled; please discuss any proposal to enable it in an issue before building it.

## Set up

```bash
git clone https://github.com/3kpro/3K_Trading_Bot_V2.git
cd 3K_Trading_Bot_V2
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest tests/ -q
```

Fork the project and create a topic branch for your change. Add a focused regression test for a bug fix. Open a pull request explaining the observed behavior, what changed, and how you verified it.

Useful areas: realistic backtest fills and fees, persistent paper positions, risk limit validation, dashboard tests, and reproducible offline fixtures. Do not claim simulated results predict live returns.

For bug reports, include your Python version, operating system, steps to reproduce, expected and actual behavior, and a sanitized error trace. Never share exchange credentials, tokens, or private account data.

Please keep discussions respectful and technical. Issues are the best place to scope a larger change before starting work.
