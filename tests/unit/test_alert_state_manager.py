import os
import tempfile
import pytest

from src.persistence.database import Database
from src.services.threshold_engine import ThresholdEngine
from src.services.alert_state_manager import AlertStateManager

THRESHOLDS = [10, 15, 20, 25, 30, 35, 40, 45, 50]


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # Database() creates it fresh
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except PermissionError:
            pass


def make_manager(db_path):
    db = Database(db_path)
    engine = ThresholdEngine(THRESHOLDS, rearm_buffer_pct=2.0)
    manager = AlertStateManager(db, engine, THRESHOLDS)
    return db, manager


def test_first_evaluation_starts_at_zero_drawdown(db_path):
    db, manager = make_manager(db_path)
    assert manager.get_last_drawdown() == 0.0


def test_trigger_persists_and_survives_reload(db_path):
    db, manager = make_manager(db_path)
    decision = manager.decide(10.0)
    assert decision.thresholds_to_trigger == [10]
    manager.apply_decision(decision, 10.0)

    # Simulate app restart: new Database connection + new manager instance
    db.close()
    db2 = Database(db_path)
    engine2 = ThresholdEngine(THRESHOLDS, rearm_buffer_pct=2.0)
    manager2 = AlertStateManager(db2, engine2, THRESHOLDS)

    assert manager2.get_last_drawdown() == 10.0
    states = db2.get_threshold_states()
    assert states[10]["is_armed"] == 0  # disarmed, persisted


def test_no_duplicate_alert_after_restart_at_same_level(db_path):
    db, manager = make_manager(db_path)
    decision = manager.decide(15.0)
    assert set(decision.thresholds_to_trigger) == {10, 15}
    manager.apply_decision(decision, 15.0)

    db.close()
    db2 = Database(db_path)
    engine2 = ThresholdEngine(THRESHOLDS, rearm_buffer_pct=2.0)
    manager2 = AlertStateManager(db2, engine2, THRESHOLDS)

    # App restarts, next check still shows ~15% drawdown - must not re-fire
    decision2 = manager2.decide(15.2)
    assert decision2.thresholds_to_trigger == []


def test_rearm_and_retrigger_flow(db_path):
    db, manager = make_manager(db_path)

    decision = manager.decide(10.0)
    manager.apply_decision(decision, 10.0)
    assert db.get_threshold_states()[10]["is_armed"] == 0

    # Recover well below 10 - 2 = 8
    decision2 = manager.decide(7.0)
    assert decision2.thresholds_to_rearm == [10]
    manager.apply_decision(decision2, 7.0)
    assert db.get_threshold_states()[10]["is_armed"] == 1

    # Falls through 10% again
    decision3 = manager.decide(10.5)
    assert decision3.thresholds_to_trigger == [10]
