import pytest
from src.services.threshold_engine import ThresholdEngine

THRESHOLDS = [10, 15, 20, 25, 30, 35, 40, 45, 50]


def armed_state(thresholds):
    return {t: {"is_armed": True} for t in thresholds}


def test_no_alert_below_threshold():
    engine = ThresholdEngine(THRESHOLDS, rearm_buffer_pct=2.0)
    decision = engine.evaluate(9.0, 9.8, armed_state(THRESHOLDS))
    assert decision.thresholds_to_trigger == []


def test_alert_on_exact_ten_percent():
    engine = ThresholdEngine(THRESHOLDS, rearm_buffer_pct=2.0)
    decision = engine.evaluate(9.8, 10.0, armed_state(THRESHOLDS))
    assert decision.thresholds_to_trigger == [10]


def test_no_duplicate_alert_after_ten_percent_already_triggered():
    engine = ThresholdEngine(THRESHOLDS, rearm_buffer_pct=2.0)
    states = armed_state(THRESHOLDS)
    states[10]["is_armed"] = False  # already triggered, still disarmed
    decision = engine.evaluate(10.0, 10.5, states)
    assert decision.thresholds_to_trigger == []


def test_fifteen_percent_after_ten_already_triggered():
    engine = ThresholdEngine(THRESHOLDS, rearm_buffer_pct=2.0)
    states = armed_state(THRESHOLDS)
    states[10]["is_armed"] = False
    decision = engine.evaluate(10.5, 15.0, states)
    assert decision.thresholds_to_trigger == [15]


def test_jump_from_nine_to_sixteen_triggers_ten_and_fifteen():
    engine = ThresholdEngine(THRESHOLDS, rearm_buffer_pct=2.0)
    decision = engine.evaluate(9.0, 16.0, armed_state(THRESHOLDS))
    assert decision.thresholds_to_trigger == [10, 15]


def test_jump_from_nine_to_twentyone_triggers_ten_fifteen_twenty():
    engine = ThresholdEngine(THRESHOLDS, rearm_buffer_pct=2.0)
    decision = engine.evaluate(9.0, 21.0, armed_state(THRESHOLDS))
    assert decision.thresholds_to_trigger == [10, 15, 20]


def test_rearm_requires_recovery_past_buffer():
    engine = ThresholdEngine(THRESHOLDS, rearm_buffer_pct=2.0)
    states = armed_state(THRESHOLDS)
    states[10]["is_armed"] = False

    # Recovered to 9% drawdown - not far enough below 10 - 2 = 8
    decision = engine.evaluate(10.0, 9.0, states)
    assert decision.thresholds_to_rearm == []

    # Recovered to 7.9% drawdown - below 10 - 2 = 8 -> re-arms
    decision2 = engine.evaluate(9.0, 7.9, states)
    assert decision2.thresholds_to_rearm == [10]


def test_rearmed_threshold_can_trigger_again():
    engine = ThresholdEngine(THRESHOLDS, rearm_buffer_pct=2.0)
    states = armed_state(THRESHOLDS)
    states[10]["is_armed"] = True  # simulate having been re-armed already
    decision = engine.evaluate(9.5, 10.2, states)
    assert decision.thresholds_to_trigger == [10]


def test_dynamic_threshold_extension_beyond_configured_max():
    engine = ThresholdEngine(THRESHOLDS, rearm_buffer_pct=2.0)
    states = armed_state(THRESHOLDS)
    # Drawdown blows past the configured max of 50% to 57%
    decision = engine.evaluate(49.0, 57.0, states)
    assert 50 in decision.thresholds_to_trigger
    assert 55 in decision.thresholds_to_trigger
    assert 55 in decision.new_thresholds_needed


def test_multiple_thresholds_disarmed_independently():
    engine = ThresholdEngine(THRESHOLDS, rearm_buffer_pct=2.0)
    states = armed_state(THRESHOLDS)
    states[10]["is_armed"] = False
    states[15]["is_armed"] = False
    # 20% is still armed and gets crossed
    decision = engine.evaluate(15.0, 22.0, states)
    assert decision.thresholds_to_trigger == [20]
