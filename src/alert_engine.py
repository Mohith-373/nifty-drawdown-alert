"""
Alert Engine - orchestrates one full evaluation cycle.

Production-grade: every database and notification operation is wrapped
in try/except so a single failure never crashes the cycle.
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
        try:
            quote = self._price_service.get_validated_quote()
        except MarketDataError as e:
            logger.warning("Skipping cycle: %s", e)
            try:
                self._db.record_error("PriceService", str(e))
            except Exception:
                logger.exception("Failed to record PriceService error to database")
            return {"status": "skipped", "reason": str(e)}
        except Exception as e:
            logger.exception("Unexpected error fetching quote")
            try:
                self._db.record_error("PriceService", f"Unexpected: {e}")
            except Exception:
                pass
            return {"status": "skipped", "reason": f"Unexpected: {e}"}

        try:
            high_value = self._high_calculator.get_current_high_value(as_of=quote.timestamp)
        except MarketDataError as e:
            logger.warning("Skipping cycle: could not determine 52-week high: %s", e)
            try:
                self._db.record_error("HighCalculator", str(e))
            except Exception:
                logger.exception("Failed to record HighCalculator error to database")
            return {"status": "skipped", "reason": str(e)}
        except Exception as e:
            logger.exception("Unexpected error fetching 52-week high")
            try:
                self._db.record_error("HighCalculator", f"Unexpected: {e}")
            except Exception:
                pass
            return {"status": "skipped", "reason": f"Unexpected: {e}"}

        drawdown_pct = calculate_drawdown_pct(quote.price, high_value)

        try:
            self._db.record_price(
                price=quote.price,
                price_timestamp=quote.timestamp.isoformat(),
                fetched_at=quote.fetched_at.isoformat(),
                drawdown_pct=drawdown_pct,
                source=quote.source,
            )
        except Exception:
            logger.exception("Failed to record price to database")

        try:
            decision = self._state_manager.decide(drawdown_pct)
        except Exception:
            logger.exception("Failed to get threshold decision — skipping alert evaluation")
            return {
                "status": "ok",
                "price": quote.price,
                "fifty_two_week_high": high_value,
                "drawdown_pct": drawdown_pct,
                "alerts_sent": [],
                "rearmed": [],
            }

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
            try:
                alert_id = self._db.record_alert(
                    threshold=threshold,
                    nifty_price=quote.price,
                    high_value=high_value,
                    drawdown_pct=drawdown_pct,
                    price_timestamp=quote.timestamp.isoformat(),
                    is_first_alert=is_first,
                    message=message,
                )
            except Exception:
                logger.exception("Failed to record alert for threshold %s", threshold)
                alert_id = -1

            try:
                self._notification_service.notify_all(alert_id, message, subject="NIFTY 50 Drawdown Alert")
            except Exception:
                logger.exception("Failed to send notifications for threshold %s", threshold)

            alerts_sent.append(threshold)
            logger.info("Alert fired: threshold=%s%% drawdown=%.2f%%", threshold, drawdown_pct)

        try:
            self._state_manager.apply_decision(decision, drawdown_pct)
        except Exception:
            logger.exception("Failed to persist state after decision")

        return {
            "status": "ok",
            "price": quote.price,
            "fifty_two_week_high": high_value,
            "drawdown_pct": drawdown_pct,
            "alerts_sent": alerts_sent,
            "rearmed": decision.thresholds_to_rearm,
        }
