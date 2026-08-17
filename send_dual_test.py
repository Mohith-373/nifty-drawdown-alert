from src.config import CONFIG
from src.persistence.database import Database
from src.notifications.notification_service import NotificationService, build_notifiers_from_config

msg = """TEST ALERT - DUAL DELIVERY

This is a test message to verify both configured Telegram chat IDs
are receiving alerts from the NIFTY 50 Drawdown Alert System.
"""

db = Database(CONFIG.database_path)
notifiers = build_notifiers_from_config(CONFIG, db)
service = NotificationService(notifiers, db)
results = service.notify_all(alert_id=9999, message=msg, subject="TEST ALERT - DUAL DELIVERY")
for r in results:
    print(f"{r.channel}: success={r.success} detail={r.detail}")
