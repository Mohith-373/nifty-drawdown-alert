"""
Formats the human-readable alert message per the spec's required format.
"""
from __future__ import annotations

from datetime import datetime


def format_alert_message(current_price: float, fifty_two_week_high: float,
                          drawdown_pct: float, threshold: float,
                          price_timestamp: datetime, is_first_alert: bool) -> str:
    level_note = "First alert" if is_first_alert else "Subsequent drawdown level alert"
    time_str = price_timestamp.strftime("%d-%b-%Y %I:%M %p IST")

    return (
        "NIFTY 50 ALERT\n\n"
        f"Current NIFTY 50: {current_price:,.2f}\n"
        f"52-Week High: {fifty_two_week_high:,.2f}\n"
        f"Drawdown: {drawdown_pct:.2f}%\n"
        f"Threshold Crossed: {threshold:.0f}%\n\n"
        f"Time: {time_str}\n\n"
        f"({level_note})"
    )
