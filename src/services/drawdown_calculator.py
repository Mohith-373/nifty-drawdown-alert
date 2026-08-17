"""
Drawdown Calculator.

drawdown_percent = ((52_week_high - current_nifty50) / 52_week_high) * 100
                  = (1 - current_nifty50 / 52_week_high) * 100

Pure function, no I/O, no state - trivially unit-testable.
"""
from __future__ import annotations


def calculate_drawdown_pct(current_price: float, fifty_two_week_high: float) -> float:
    if fifty_two_week_high <= 0:
        raise ValueError("52-week high must be positive")
    if current_price < 0:
        raise ValueError("current price cannot be negative")

    drawdown = (1 - (current_price / fifty_two_week_high)) * 100
    # Round to avoid binary floating-point dust (e.g. 22500/25000 landing on
    # 9.999999999999998 instead of exactly 10.0) causing an exact-threshold
    # crossing to be missed. 6 decimal places preserves meaningful precision
    # (down to 0.0001% moves) while eliminating representation error.
    drawdown = round(drawdown, 6)
    # Drawdown cannot be meaningfully negative in this system's context
    # (price above the high just means a new high should have been recorded
    # by the HighCalculator already) - clamp defensively to 0.
    return max(drawdown, 0.0)
