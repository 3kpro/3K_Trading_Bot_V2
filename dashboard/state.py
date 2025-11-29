"""
Shared state object for the web dashboard.
The trading loop writes to this; the web UI reads it.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DashboardState:
    equity: float = 0.0
    last_price: float = 0.0
    symbol: str = ""
    atr: float = 0.0
    rsi: float = 0.0
    donchian_upper: float = 0.0
    donchian_lower: float = 0.0
    signal: Optional[str] = None
    warmup_progress: float = 0.0   # 0.0 → 1.0
    ready: bool = False
    last_update: datetime = field(default_factory=datetime.utcnow)
    equity_history: list = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "equity": self.equity,
            "last_price": self.last_price,
            "symbol": self.symbol,
            "atr": self.atr,
            "rsi": self.rsi,
            "donchian_upper": self.donchian_upper,
            "donchian_lower": self.donchian_lower,
            "signal": self.signal,
            "warmup_progress": self.warmup_progress,
            "ready": self.ready,
            "last_update": self.last_update.isoformat(),
            "equity_history": self.equity_history,
        }


# Global singleton
state = DashboardState()
state.equity = 1000.0
state.equity_history = [1000.0]
state.symbol = "BTC/USDT"
state.last_price = 50000.0
state.ready = False
state.warmup_progress = 0.0