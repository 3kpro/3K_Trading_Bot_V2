"""
Shared state object for the web dashboard.
The trading loop writes to this; the web UI reads it.
Enhanced with readiness metrics and time-series tracking.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import statistics as st


@dataclass
class DashboardState:
    # Core trading state
    equity: float = 0.0
    last_price: float = 0.0
    symbol: str = ""
    atr: float = 0.0
    rsi: float = 0.0
    donchian_upper: float = 0.0
    donchian_lower: float = 0.0
    signal: Optional[str] = None

    # Warmup & readiness
    warmup_progress: float = 0.0   # 0.0 → 1.0
    ready: bool = False
    last_update: datetime = field(default_factory=datetime.utcnow)

    # Time series data
    equity_history: List[float] = field(default_factory=list)
    price_history: List[float] = field(default_factory=list)
    rsi_history: List[float] = field(default_factory=list)
    atr_history: List[float] = field(default_factory=list)
    signal_history: List[str] = field(default_factory=list)
    timestamp_history: List[str] = field(default_factory=list)

    # Trade tracking
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    trade_pnls: List[float] = field(default_factory=list)

    # Status flags
    backtest_mode: bool = False
    paper_mode: bool = True
    live_mode: bool = False
    start_time: datetime = field(default_factory=datetime.utcnow)

    def get_readiness_score(self) -> Dict[str, Any]:
        """Calculate readiness metrics for live trading."""
        checks = {
            "data_warmup": self.warmup_progress >= 1.0,
            "has_equity": self.equity > 0,
            "min_trades": self.total_trades >= 10,
            "positive_expectancy": self._calculate_expectancy() > 0,
            "win_rate": self._calculate_win_rate() >= 0.45,
            "max_drawdown": abs(self._calculate_max_drawdown()) <= 0.15,
        }

        passed = sum(1 for v in checks.values() if v)
        total = len(checks)
        score_pct = (passed / total * 100) if total > 0 else 0.0

        return {
            "checks": checks,
            "passed": passed,
            "total": total,
            "score_pct": round(score_pct, 1),
            "can_trade_live": passed >= 5,  # Need at least 5/6 checks
            "eta_hours": self._estimate_eta_hours(),
            "eta_readable": self._format_eta(),
        }

    def _calculate_expectancy(self) -> float:
        """Average PnL per trade."""
        if not self.trade_pnls:
            return 0.0
        return st.mean(self.trade_pnls)

    def _calculate_win_rate(self) -> float:
        """Win rate as decimal (0-1)."""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    def _calculate_max_drawdown(self) -> float:
        """Max drawdown as decimal (e.g., -0.10 = -10%)."""
        if len(self.equity_history) < 2:
            return 0.0
        peak = self.equity_history[0]
        max_dd = 0.0
        for eq in self.equity_history:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return -max_dd  # Return as negative

    def _estimate_eta_hours(self) -> float:
        """Estimate hours until bot is ready (simple heuristic)."""
        eta = 0.0

        # Warmup progress (assume ~2 hours to full warmup)
        if self.warmup_progress < 1.0:
            eta += (1.0 - self.warmup_progress) * 2.0

        # Trade requirement (assuming ~1 trade per hour in typical conditions)
        if self.total_trades < 10:
            eta += (10 - self.total_trades) * 1.0

        # Performance requirements (rough estimates)
        if self._calculate_expectancy() <= 0:
            eta += 2.0  # Time to accumulate positive expectancy

        if self._calculate_win_rate() < 0.45:
            eta += 3.0  # Time to improve win rate

        if abs(self._calculate_max_drawdown()) >= 0.15:
            eta += 4.0  # Time to reduce drawdown

        return round(eta, 1)

    def _format_eta(self) -> str:
        """Format ETA as human-readable string."""
        eta = self._estimate_eta_hours()
        if eta == 0.0:
            return "Ready now! ✓"

        hours = int(eta)
        minutes = int((eta - hours) * 60)

        if hours > 0:
            return f"~{hours}h {minutes}m"
        elif minutes > 0:
            return f"~{minutes}m"
        else:
            return "< 1 minute"

    def add_candle(self, price: float, rsi: float, atr: float, signal: Optional[str] = None):
        """Record a new candle/tick for history."""
        ts = datetime.utcnow().isoformat()

        self.price_history.append(price)
        self.rsi_history.append(rsi)
        self.atr_history.append(atr)
        if signal:
            self.signal_history.append(signal)
        self.timestamp_history.append(ts)

        # Keep only last 100 candles to avoid bloat
        max_len = 100
        if len(self.price_history) > max_len:
            self.price_history = self.price_history[-max_len:]
            self.rsi_history = self.rsi_history[-max_len:]
            self.atr_history = self.atr_history[-max_len:]
            self.timestamp_history = self.timestamp_history[-max_len:]

    def record_trade(self, pnl: float, side: str):
        """Record a trade result."""
        self.total_trades += 1
        self.trade_pnls.append(pnl)

        if pnl > 0:
            self.winning_trades += 1
        elif pnl < 0:
            self.losing_trades += 1

    def to_dict(self) -> Dict[str, Any]:
        readiness = self.get_readiness_score()

        return {
            "equity": round(self.equity, 2),
            "last_price": round(self.last_price, 6),
            "symbol": self.symbol,
            "atr": round(self.atr, 6),
            "rsi": round(self.rsi, 2),
            "donchian_upper": round(self.donchian_upper, 6),
            "donchian_lower": round(self.donchian_lower, 6),
            "signal": self.signal,
            "warmup_progress": round(self.warmup_progress, 3),
            "ready": self.ready,
            "last_update": self.last_update.isoformat(),
            "equity_history": [round(x, 2) for x in self.equity_history[-100:]],
            "price_history": [round(x, 6) for x in self.price_history],
            "rsi_history": [round(x, 2) for x in self.rsi_history],
            "atr_history": [round(x, 6) for x in self.atr_history],
            "timestamp_history": self.timestamp_history,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate_pct": round(self._calculate_win_rate() * 100, 1),
            "expectancy": round(self._calculate_expectancy(), 6),
            "max_drawdown_pct": round(self._calculate_max_drawdown() * 100, 2),
            "readiness": readiness,
            "mode": {
                "backtest": self.backtest_mode,
                "paper": self.paper_mode,
                "live": self.live_mode,
            }
        }


# Global singleton
state = DashboardState()