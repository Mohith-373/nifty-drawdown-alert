"""
Alert State Manager.

Bridges the pure ThresholdEngine decision logic with persistent storage, so
that state (which thresholds are armed/disarmed, last known drawdown)
survives application restarts. This is the ONLY component that reads/writes
threshold_state and the "last_drawdown" system_state key.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from src.persistence.database import Database
from src.services.threshold_engine import ThresholdEngine, ThresholdDecision

LAST_DRAWDOWN_KEY = "last_drawdown_pct"


class AlertStateManager:
    def __init__(self, db: Database, engine: ThresholdEngine, configured_thresholds: List[float]):
        self._db = db
        self._engine = engine
        self._db.ensure_thresholds(configured_thresholds)

    def get_last_drawdown(self) -> float:
        """
        The drawdown recorded as of the last successful evaluation. Defaults
        to 0.0 on first-ever run (nothing triggered yet). Persisted so that
        a restart does not treat "0 -> current_drawdown" as one giant jump
        and mass-fire every threshold in between.

        NOTE: because thresholds are individually disarmed once triggered,
        even if this value were lost, already-triggered thresholds would
        still not re-fire (see AlertStateManager.decide docstring). This
        persistence is primarily to get accurate crossing detection for
        thresholds that have never fired.
        """
        raw = self._db.get_state(LAST_DRAWDOWN_KEY)
        return float(raw) if raw is not None else 0.0

    def set_last_drawdown(self, drawdown_pct: float):
        self._db.set_state(LAST_DRAWDOWN_KEY, str(drawdown_pct))

    def decide(self, current_drawdown: float) -> ThresholdDecision:
        """
        Compute which thresholds should trigger / re-arm right now, given
        current_drawdown vs the persisted previous drawdown and persisted
        threshold states. Does NOT mutate state - call apply_decision() to
        persist the outcome after alerts have actually been sent.
        """
        previous_drawdown = self.get_last_drawdown()
        threshold_states = self._db.get_threshold_states()
        return self._engine.evaluate(previous_drawdown, current_drawdown, threshold_states)

    def apply_decision(self, decision: ThresholdDecision, current_drawdown: float):
        """
        Persist the outcome of a decision AFTER alerts have been sent
        successfully: disarm triggered thresholds, re-arm recovered ones,
        register any newly-created dynamic thresholds, and record the new
        last-known drawdown.
        """
        now = datetime.now(timezone.utc).isoformat()

        for t in decision.new_thresholds_needed:
            self._db.add_threshold_if_missing(t)

        for t in decision.thresholds_to_trigger:
            self._db.set_threshold_armed(t, armed=False, when=now)

        for t in decision.thresholds_to_rearm:
            self._db.set_threshold_armed(t, armed=True, when=now)

        self.set_last_drawdown(current_drawdown)

    def is_first_alert_ever(self) -> bool:
        """True if no alert has ever been recorded (used for message wording)."""
        cur = self._db._conn.execute("SELECT COUNT(*) as c FROM alerts")
        row = cur.fetchone()
        return (row["c"] if row else 0) == 0
