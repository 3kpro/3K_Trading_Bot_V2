import pandas as pd
import pytest

from bot import BotConfig, backtest_symbol, donchian_channels, generate_signal_for_symbol, run_loop


def config(mode="paper"):
    return BotConfig(
        exchange_id="kraken", symbols=["BTC/USD"], timeframe="1h",
        equity=1000.0, risk_frac=0.005, donchian_lookback=3,
        atr_period=3, rsi_period=3, rsi_min=0, rsi_max=100,
        mode=mode,
    )


def candles():
    index = pd.date_range("2024-01-01", periods=8, freq="h", tz="UTC")
    closes = [10, 10, 10, 10, 10, 10, 10, 15]
    return pd.DataFrame({
        "open": closes, "high": [v + 1 for v in closes],
        "low": [v - 1 for v in closes], "close": closes,
        "volume": [100] * len(closes),
    }, index=index)


def test_channels_exclude_current_candle():
    df = candles()
    upper, lower = donchian_channels(df.high, df.low, 3)
    assert upper.iloc[-1] == 11
    assert lower.iloc[-1] == 9


def test_breakout_signal_uses_previous_candles():
    signal = generate_signal_for_symbol(candles(), config(), "BTC/USD")
    assert signal is not None
    assert signal.side == "long"
    assert signal.entry_price == 15
    assert signal.stop_price < signal.entry_price
    assert signal.size > 0


def test_backtest_can_enter_on_breakout(monkeypatch):
    monkeypatch.setattr("bot.fetch_ohlcv_df", lambda *args, **kwargs: candles())
    result = backtest_symbol(object(), "BTC/USD", config("backtest"))
    assert any(trade.get("note") == "Entry" for trade in result["trades"])


def test_live_mode_is_rejected_before_order_execution():
    with pytest.raises(NotImplementedError, match="not implemented"):
        run_loop(object(), config("live"))
