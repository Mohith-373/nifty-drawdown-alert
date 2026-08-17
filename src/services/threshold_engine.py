"""
Threshold Engine.

Pure decision logic: given the previous drawdown, the current drawdown, and
the persisted per-threshold armed/disarmed state, decide which thresholds
should fire an alert right now, and which thresholds should be re-armed.

--- Trigger rule ---
A threshold T fires when:
    previous_drawdown < T <= current_drawdown   (crossed on this update)
    AND threshold_state[T].is_armed is True

This means jumps that skip over multiple thresholds in one price update
(e.g. 9% -> 21%) correctly fire every threshold in between (10, 15, 20),
because each one satisfies "previous < T <= current" independently.

--- Re-arm rule (hysteresis) ---
A disarmed threshold T re-arms when:
    current_drawdown < (T - rearm_buffer_pct)

i.e. price must recover to at least `rearm_buffer_pct` percentage points
below the threshold before that threshold becomes eligible to fire again.
This prevents alert spam from the price oscillating right around a
threshold. Re-arming does not itself send an alert - it just makes the
threshold eligible to fire again on a subsequent breach.

--- Dynamic threshold extension ---
If current_drawdown exceeds the highest configured threshold, the engine
generates additional 5-percentage-point thresholds on demand (45 -> 50 -> 55
...), per the spec's "continue in additional 5-percentage-point increments"
requirement, so the system never silently stops alerting during a severe
crash just because the config list ended.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ThresholdDecision:
    thresholds_to_trigger: List[float]
    thresholds_to_rearm: List[float]
    new_thresholds_needed: List[float]  # thresholds that must be added to state store


class ThresholdEngine:
    def __init__(self, configured_thresholds: List[float], rearm_buffer_pct: float,
                 increment: float = 5.0):
        self._configured = sorted(configured_thresholds)
        self._rearm_buffer_pct = rearm_buffer_pct
        self._increment = increment

    def _extend_thresholds_if_needed(self, current_drawdown: float,
                                      known_thresholds: List[float]) -> List[float]:
        """Return any new thresholds that should exist given how deep the
        current drawdown is (auto-extends beyond the configured max)."""
        if not known_thresholds:
            return []
        max_known = max(known_thresholds)
        new_ones = []
        next_t = max_known + self._increment
        # Only extend as far as needed to cover the current drawdown, plus one
        # extra so there's always a next threshold "waiting".
        while next_t <= current_drawdown + self._increment:
            new_ones.append(next_t)
            next_t += self._increment
        return new_ones

    def evaluate(self, previous_drawdown: float, current_drawdown: float,
                 threshold_states: Dict[float, dict]) -> ThresholdDecision:
        """
        threshold_states: {threshold_value: {"is_armed": bool, ...}}, as
        loaded from persistence. Must include at least the configured set.
        """
        known_thresholds = sorted(threshold_states.keys()) or list(self._configured)
        new_thresholds = self._extend_thresholds_if_needed(current_drawdown, known_thresholds)

        all_thresholds = sorted(set(known_thresholds) | set(new_thresholds))

        to_trigger = []
        to_rearm = []

        for t in all_thresholds:
            state = threshold_states.get(t, {"is_armed": True})
            is_armed = state.get("is_armed", True)

            # Crossing check (fires regardless of prior armed state only if armed)
            crossed_now = previous_drawdown < t <= current_drawdown
            if crossed_now and is_armed:
                to_trigger.append(t)

            # Re-arm check (recovery below threshold - buffer)
            if not is_armed and current_drawdown < (t - self._rearm_buffer_pct):
                to_rearm.append(t)

        return ThresholdDecision(
            thresholds_to_trigger=sorted(to_trigger),
            thresholds_to_rearm=sorted(to_rearm),
            new_thresholds_needed=sorted(new_thresholds),
        )
