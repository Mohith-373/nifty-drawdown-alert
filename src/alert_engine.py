"""
Alert Engine - orchestrates one full evaluation cycle:

  Market Data Provider
        -> Price Service (validate)
        -> High Calculator (52-week high)
        -> Drawdown Calculator
        -> Threshold Engine / Alert State Manager
        -> Notification Service

This is the only module that wires all the pieces together; each piece
above remains independently unit-testable in isolation.
"""
from __future__ import annotations

import logging
from datetime import datetime

from src.data_provider.base import MarketDataError
from src.services.price_service import PriceService
from src.services.high_calculator import HighCalculator
from src.services.drawdown_calculator import calculate_drawdown_pct
from src.services.alert_state_manager import AlertStateManager
from src.services.message_formatter import format_alert_message
from src.notifications.notification_service import NotificationService
from src.persistence.database import Database

logger = logging.getLogger("nifty_alert.engine")


class AlertEngine:
    def __init__(self, price_service: PriceService, high_calculator: HighCalculator,
                 state_manager: AlertStateManager, notification_service: NotificationService,
                 db: Database, min_configured_threshold: float):
        self._price_service = price_service
        self._high_calculator = high_calculator
        self._state_manager = state_manager
        self._notification_service = notification_service
        self._db = db
        self._min_threshold = min_configured_threshold

    def run_once(self) -> dict:
        """
        Execute a single evaluation cycle. Returns a summary dict for
        logging/testing. Never raises for expected failure modes (market
        data errors) - those are caught, logged, and recorded to error_log.
        """
        try:
            quote = self._price_service.get_validated_quote()
        except MarketDataError as e:
            logger.warning("Skipping cycle: %s", e)
            self._db.record_error("PriceService", str(e))
            return {"status": "skipped", "reason": str(e)}

        try:
            high_value = self._high_calculator.get_current_high_value(as_of=quote.timestamp)
        except MarketDataError as e:
            logger.warning("Skipping cycle: could not determine 52-week high: %s", e)
            self._db.record_error("HighCalculator", str(e))
            return {"status": "skipped", "reason": str(e)}

        drawdown_pct = calculate_drawdown_pct(quote.price, high_value)

        self._db.record_price(
            price=quote.price,
            price_timestamp=quote.timestamp.isoformat(),
            fetched_at=quote.fetched_at.isoformat(),
            drawdown_pct=drawdown_pct,
            source=quote.source,
        )

        decision = self._state_manager.decide(drawdown_pct)

        alerts_sent = []
        for threshold in decision.thresholds_to_trigger:
            is_first = (threshold == self._min_threshold)
            message = format_alert_message(
                current_price=quote.price,
                fifty_two_week_high=high_value,
                drawdown_pct=drawdown_pct,
                threshold=threshold,
                price_timestamp=quote.timestamp,
                is_first_alert=is_first,
            )
            alert_id = self._db.record_alert(
                threshold=threshold,
                nifty_price=quote.price,
                high_value=high_value,
                drawdown_pct=drawdown_pct,
                price_timestamp=quote.timestamp.isoformat(),
                is_first_alert=is_first,
                message=message,
            )
            self._notification_service.notify_all(alert_id, message, subject="NIFTY 50 Drawdown Alert")
            alerts_sent.append(threshold)
            logger.info("Alert fired: threshold=%s%% drawdown=%.2f%%", threshold, drawdown_pct)

        # Persist state ONLY after notifications have been attempted, so a
        # crash between decision and notification does not silently mark a
        # threshold as triggered without ever notifying anyone.
        self._state_manager.apply_decision(decision, drawdown_pct)

        return {
            "status": "ok",
            "price": quote.price,
            "fifty_two_week_high": high_value,
            "drawdown_pct": drawdown_pct,
            "alerts_sent": alerts_sent,
            "rearmed": decision.thresholds_to_rearm,
        }
