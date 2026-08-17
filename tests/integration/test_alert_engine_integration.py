import os
import tempfile
from datetime import datetime, timedelta

import pytest
import pytz

from src.persistence.database import Database
from src.services.price_service import PriceService
from src.services.high_calculator import HighCalculator
from src.services.threshold_engine import ThresholdEngine
from src.services.alert_state_manager import AlertStateManager
from src.notifications.notification_service import NotificationService
from src.notifications.base import Notifier, NotificationResult
from src.data_provider.base import MarketDataProvider, Quote, HistoricalHigh, MarketDataError
from src.alert_engine import AlertEngine

IST = pytz.timezone("Asia/Kolkata")
THRESHOLDS = [10, 15, 20, 25, 30, 35, 40, 45, 50]


class FakeProvider(MarketDataProvider):
    name = "fake"

    def __init__(self, price, high_value, price_age_seconds=30, fail_quote=False, fail_high=False):
        self.price = price
        self.high_value = high_value
        self.price_age_seconds = price_age_seconds
        self.fail_quote = fail_quote
        self.fail_high = fail_high

    def get_current_quote(self, symbol):
        if self.fail_quote:
            raise MarketDataError("simulated provider failure")
        now = datetime.now(IST)
        ts = now - timedelta(seconds=self.price_age_seconds)
        return Quote(price=self.price, timestamp=ts, fetched_at=now, source=self.name)

    def get_52_week_high(self, symbol, as_of=None):
        if self.fail_high:
            raise MarketDataError("simulated high lookup failure")
        now = datetime.now(IST)
        return HistoricalHigh(
            high_value=self.high_value,
            high_date=now - timedelta(days=30),
            window_start=now - timedelta(days=365),
            window_end=now,
        )


class RecordingNotifier(Notifier):
    channel_name = "recording"

    def __init__(self):
        self.sent_messages = []

    def send(self, message, subject=""):
        self.sent_messages.append(message)
        return NotificationResult(self.channel_name, True, "sent")


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except PermissionError:
            pass


def build_engine(db_path, provider, notifier):
    db = Database(db_path)
    price_service = PriceService(provider, "^NSEI", max_staleness_seconds=900)
    high_calc = HighCalculator(provider, db, "^NSEI")
    threshold_engine = ThresholdEngine(THRESHOLDS, rearm_buffer_pct=2.0)
    state_manager = AlertStateManager(db, threshold_engine, THRESHOLDS)
    notification_service = NotificationService([notifier], db)
    engine = AlertEngine(
        price_service, high_calc, state_manager, notification_service, db,
        min_configured_threshold=min(THRESHOLDS),
    )
    return db, engine


def test_full_cycle_no_alert_below_threshold(db_path):
    provider = FakeProvider(price=25000 * 0.95, high_value=25000)  # 5% drawdown
    notifier = RecordingNotifier()
    db, engine = build_engine(db_path, provider, notifier)

    result = engine.run_once()
    assert result["status"] == "ok"
    assert result["alerts_sent"] == []
    assert notifier.sent_messages == []


def test_full_cycle_fires_ten_percent_alert(db_path):
    provider = FakeProvider(price=22500, high_value=25000)  # exactly 10%
    notifier = RecordingNotifier()
    db, engine = build_engine(db_path, provider, notifier)

    result = engine.run_once()
    assert result["alerts_sent"] == [10]
    assert len(notifier.sent_messages) == 1
    assert "10%" in notifier.sent_messages[0]
    assert "NIFTY 50 ALERT" in notifier.sent_messages[0]


def test_duplicate_alert_prevention_across_cycles(db_path):
    provider = FakeProvider(price=22500, high_value=25000)
    notifier = RecordingNotifier()
    db, engine = build_engine(db_path, provider, notifier)

    engine.run_once()
    provider.price = 22400  # still ~10.4% drawdown, should not re-fire
    engine.run_once()

    assert len(notifier.sent_messages) == 1


def test_multiple_thresholds_crossed_in_one_jump(db_path):
    provider = FakeProvider(price=25000 * 0.79, high_value=25000)  # 21% drawdown
    notifier = RecordingNotifier()
    db, engine = build_engine(db_path, provider, notifier)

    result = engine.run_once()
    assert result["alerts_sent"] == [10, 15, 20]
    assert len(notifier.sent_messages) == 3


def test_new_fifty_two_week_high_updates_reference(db_path):
    provider = FakeProvider(price=26000, high_value=26000)  # new high, 0% drawdown
    notifier = RecordingNotifier()
    db, engine = build_engine(db_path, provider, notifier)

    result = engine.run_once()
    assert result["drawdown_pct"] == 0.0
    stored = db.get_fifty_two_week_high()
    assert stored["high_value"] == 26000


def test_api_failure_does_not_alert(db_path):
    provider = FakeProvider(price=22500, high_value=25000, fail_quote=True)
    notifier = RecordingNotifier()
    db, engine = build_engine(db_path, provider, notifier)

    result = engine.run_once()
    assert result["status"] == "skipped"
    assert notifier.sent_messages == []


def test_stale_price_does_not_alert(db_path):
    provider = FakeProvider(price=22500, high_value=25000, price_age_seconds=5000)
    notifier = RecordingNotifier()
    db, engine = build_engine(db_path, provider, notifier)

    result = engine.run_once()
    assert result["status"] == "skipped"
    assert notifier.sent_messages == []


def test_restart_does_not_resend_alerts(db_path):
    provider = FakeProvider(price=25000 * 0.85, high_value=25000)  # 15% drawdown
    notifier = RecordingNotifier()
    db, engine = build_engine(db_path, provider, notifier)

    engine.run_once()
    assert len(notifier.sent_messages) == 2  # 10% and 15%

    # Simulate restart: brand new Database + engine wired to same file
    db.close()
    notifier2 = RecordingNotifier()
    db2, engine2 = build_engine(db_path, provider, notifier2)
    engine2.run_once()

    assert notifier2.sent_messages == []  # nothing new sent


def test_high_lookup_failure_falls_back_to_persisted_high(db_path):
    provider = FakeProvider(price=25000, high_value=25000)
    notifier = RecordingNotifier()
    db, engine = build_engine(db_path, provider, notifier)
    engine.run_once()  # establishes persisted high = 25000

    provider.fail_high = True
    provider.price = 22500  # 10% drawdown vs persisted high
    result = engine.run_once()

    assert result["status"] == "ok"
    assert result["alerts_sent"] == [10]
