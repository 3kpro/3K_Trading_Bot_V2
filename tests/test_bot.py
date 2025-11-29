import pytest
import pandas as pd
import numpy as np
from bot import Risk, add_indicators, round_step

def test_round_step():
    assert abs(round_step(1.234, 0.1) - 1.2) < 1e-10
    assert round_step(1.234, None) == 1.234

def test_add_indicators():
    df = pd.DataFrame({
        'time': pd.date_range('2023-01-01', periods=20, freq='H'),
        'open': np.random.rand(20),
        'high': np.random.rand(20) + 1,
        'low': np.random.rand(20),
        'close': np.random.rand(20) + 0.5,
        'volume': np.random.rand(20) * 100
    })
    result = add_indicators(df)
    assert 'ema20' in result.columns
    assert 'rsi' in result.columns
    assert 'atr' in result.columns

def test_risk_position_size():
    risk = Risk(1000, 0.01, 0.05)
    qty = risk.position_size(100, 95)
    expected = (1000 * 0.01) / 5  # risk 10, diff 5
    assert qty == expected

def test_risk_get_risk_frac():
    risk = Risk(1000, 0.01, 0.05)
    assert risk.get_risk_frac(-50) == 0.005  # 5% dd, half risk
    assert risk.get_risk_frac(0) == 0.01