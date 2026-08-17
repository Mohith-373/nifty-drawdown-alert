import pytest
from src.services.drawdown_calculator import calculate_drawdown_pct


def test_zero_drawdown_at_high():
    assert calculate_drawdown_pct(25000, 25000) == 0.0


def test_five_percent_drawdown():
    result = calculate_drawdown_pct(23750, 25000)
    assert result == pytest.approx(5.0, abs=1e-6)


def test_exactly_ten_percent_drawdown():
    result = calculate_drawdown_pct(22500, 25000)
    assert result == pytest.approx(10.0, abs=1e-6)


def test_ten_point_zero_one_percent_drawdown():
    price = 25000 * (1 - 0.1001)
    result = calculate_drawdown_pct(price, 25000)
    assert result == pytest.approx(10.01, abs=1e-3)


def test_spec_example_values():
    high = 25000
    assert calculate_drawdown_pct(22500, high) == pytest.approx(10.0)
    assert calculate_drawdown_pct(21250, high) == pytest.approx(15.0)
    assert calculate_drawdown_pct(20000, high) == pytest.approx(20.0)
    assert calculate_drawdown_pct(18750, high) == pytest.approx(25.0)
    assert calculate_drawdown_pct(17500, high) == pytest.approx(30.0)


def test_price_above_high_clamped_to_zero():
    # Should not happen in practice (HighCalculator would update first) but
    # must not produce a negative drawdown.
    assert calculate_drawdown_pct(26000, 25000) == 0.0


def test_negative_price_raises():
    with pytest.raises(ValueError):
        calculate_drawdown_pct(-100, 25000)


def test_zero_high_raises():
    with pytest.raises(ValueError):
        calculate_drawdown_pct(20000, 0)
