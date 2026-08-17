from datetime import datetime, timedelta
import pytz
import pytest

from src.services.price_service import PriceService, InvalidPriceError, StalePriceError
from src.data_provider.base import Quote

IST = pytz.timezone("Asia/Kolkata")


class FakeProvider:
    def __init__(self, quote):
        self._quote = quote

    def get_current_quote(self, symbol):
        return self._quote

    def get_52_week_high(self, symbol, as_of=None):
        raise NotImplementedError


def make_quote(price, age_seconds=0):
    now = datetime.now(IST)
    ts = now - timedelta(seconds=age_seconds)
    return Quote(price=price, timestamp=ts, fetched_at=now, source="fake")


def test_valid_fresh_quote_passes():
    provider = FakeProvider(make_quote(22500, age_seconds=30))
    svc = PriceService(provider, "^NSEI", max_staleness_seconds=900)
    quote = svc.get_validated_quote()
    assert quote.price == 22500


def test_negative_price_rejected():
    provider = FakeProvider(make_quote(-5, age_seconds=10))
    svc = PriceService(provider, "^NSEI", max_staleness_seconds=900)
    with pytest.raises(InvalidPriceError):
        svc.get_validated_quote()


def test_zero_price_rejected():
    provider = FakeProvider(make_quote(0, age_seconds=10))
    svc = PriceService(provider, "^NSEI", max_staleness_seconds=900)
    with pytest.raises(InvalidPriceError):
        svc.get_validated_quote()


def test_implausible_price_rejected():
    provider = FakeProvider(make_quote(500, age_seconds=10))  # too low for NIFTY
    svc = PriceService(provider, "^NSEI", max_staleness_seconds=900)
    with pytest.raises(InvalidPriceError):
        svc.get_validated_quote()


def test_stale_quote_rejected():
    provider = FakeProvider(make_quote(22500, age_seconds=2000))
    svc = PriceService(provider, "^NSEI", max_staleness_seconds=900)
    with pytest.raises(StalePriceError):
        svc.get_validated_quote()


def test_boundary_freshness_accepted():
    provider = FakeProvider(make_quote(22500, age_seconds=890))
    svc = PriceService(provider, "^NSEI", max_staleness_seconds=900)
    quote = svc.get_validated_quote()
    assert quote.price == 22500
