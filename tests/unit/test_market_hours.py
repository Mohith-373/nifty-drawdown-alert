from datetime import datetime
import pytz

from src.market_hours import MarketHours

IST = pytz.timezone("Asia/Kolkata")
HOLIDAYS = ["2026-01-26", "2026-08-15"]


def mh():
    return MarketHours("09:15", "15:30", "Asia/Kolkata", HOLIDAYS)


def test_open_during_trading_hours_on_weekday():
    # Wed 16-Aug-2026, 11:30 AM
    dt = IST.localize(datetime(2026, 8, 12, 11, 30))
    assert mh().is_market_open(dt) is True


def test_closed_before_open():
    dt = IST.localize(datetime(2026, 8, 12, 9, 0))
    assert mh().is_market_open(dt) is False


def test_closed_after_close():
    dt = IST.localize(datetime(2026, 8, 12, 15, 45))
    assert mh().is_market_open(dt) is False


def test_closed_on_weekend():
    # Sat 15-Aug-2026 happens to also be a holiday, use a plain Saturday
    dt = IST.localize(datetime(2026, 8, 22, 11, 0))  # Saturday
    assert mh().is_market_open(dt) is False


def test_closed_on_holiday():
    dt = IST.localize(datetime(2026, 8, 15, 11, 0))
    assert mh().is_market_open(dt) is False


def test_open_at_exact_open_boundary():
    dt = IST.localize(datetime(2026, 8, 12, 9, 15))
    assert mh().is_market_open(dt) is True


def test_open_at_exact_close_boundary():
    dt = IST.localize(datetime(2026, 8, 12, 15, 30))
    assert mh().is_market_open(dt) is True
