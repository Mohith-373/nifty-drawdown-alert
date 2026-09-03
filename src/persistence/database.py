"""
SQLite persistence layer with WAL mode and reconnection support.

Production-grade: handles connection drops, corruption, and
concurrent access safely.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fifty_two_week_high (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    high_value REAL NOT NULL,
    high_date TEXT NOT NULL,
    computed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS threshold_state (
    threshold REAL PRIMARY KEY,
    is_armed INTEGER NOT NULL DEFAULT 1,
    last_triggered_at TEXT,
    last_rearmed_at TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    threshold REAL NOT NULL,
    nifty_price REAL NOT NULL,
    fifty_two_week_high REAL NOT NULL,
    drawdown_pct REAL NOT NULL,
    price_timestamp TEXT NOT NULL,
    alert_generated_at TEXT NOT NULL,
    is_first_alert INTEGER NOT NULL,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER NOT NULL REFERENCES alerts(id),
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    attempted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS error_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component TEXT NOT NULL,
    message TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    price REAL NOT NULL,
    price_timestamp TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    drawdown_pct REAL,
    source TEXT NOT NULL
);
"""


class Database:
    """Thread-safe SQLite wrapper with WAL mode and reconnection support."""

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._path = path
        self._lock = threading.Lock()
        self._conn = None
        self._connect()

    def _connect(self):
        self._conn = sqlite3.connect(self._path, check_same_thread=False, timeout=15)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
        except Exception:
            pass
        self._init_schema()

    def _ensure_connection(self):
        if self._conn is None:
            self._connect()
            return
        try:
            self._conn.execute("SELECT 1")
        except (sqlite3.ProgrammingError, sqlite3.OperationalError, AttributeError):
            try:
                self._conn.close()
            except Exception:
                pass
            self._connect()

    def _init_schema(self):
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    @contextmanager
    def transaction(self):
        with self._lock:
            self._ensure_connection()
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                raise

    # --- 52-week high ------------------------------------------------------

    def get_fifty_two_week_high(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._ensure_connection()
            cur = self._conn.execute("SELECT * FROM fifty_two_week_high WHERE id = 1")
            row = cur.fetchone()
            return dict(row) if row else None

    def upsert_fifty_two_week_high(self, high_value: float, high_date: str, computed_at: str):
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO fifty_two_week_high (id, high_value, high_date, computed_at)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    high_value=excluded.high_value,
                    high_date=excluded.high_date,
                    computed_at=excluded.computed_at
                """,
                (high_value, high_date, computed_at),
            )

    # --- Threshold state -----------------------------------------------------

    def ensure_thresholds(self, thresholds: List[float]):
        with self.transaction() as conn:
            for t in thresholds:
                conn.execute(
                    "INSERT OR IGNORE INTO threshold_state (threshold, is_armed) VALUES (?, 1)",
                    (t,),
                )

    def get_threshold_states(self) -> Dict[float, Dict[str, Any]]:
        with self._lock:
            self._ensure_connection()
            cur = self._conn.execute("SELECT * FROM threshold_state ORDER BY threshold ASC")
            return {row["threshold"]: dict(row) for row in cur.fetchall()}

    def set_threshold_armed(self, threshold: float, armed: bool, when: str):
        field = "last_rearmed_at" if armed else "last_triggered_at"
        with self.transaction() as conn:
            conn.execute(
                f"""
                UPDATE threshold_state
                SET is_armed = ?, {field} = ?
                WHERE threshold = ?
                """,
                (1 if armed else 0, when, threshold),
            )

    def add_threshold_if_missing(self, threshold: float):
        with self.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO threshold_state (threshold, is_armed) VALUES (?, 1)",
                (threshold,),
            )

    # --- System state --------------------------------------------------------

    def set_state(self, key: str, value: str):
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO system_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, datetime.now(timezone.utc).isoformat()),
            )

    def get_state(self, key: str) -> Optional[str]:
        with self._lock:
            self._ensure_connection()
            cur = self._conn.execute("SELECT value FROM system_state WHERE key = ?", (key,))
            row = cur.fetchone()
            return row["value"] if row else None

    # --- Alerts --------------------------------------------------------------

    def record_alert(self, threshold: float, nifty_price: float, high_value: float,
                      drawdown_pct: float, price_timestamp: str, is_first_alert: bool,
                      message: str) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO alerts
                (threshold, nifty_price, fifty_two_week_high, drawdown_pct,
                 price_timestamp, alert_generated_at, is_first_alert, message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (threshold, nifty_price, high_value, drawdown_pct, price_timestamp,
                 datetime.now(timezone.utc).isoformat(), 1 if is_first_alert else 0, message),
            )
            return cur.lastrowid

    def record_notification_delivery(self, alert_id: int, channel: str, status: str, detail: str = ""):
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO notification_deliveries (alert_id, channel, status, detail, attempted_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (alert_id, channel, status, detail, datetime.now(timezone.utc).isoformat()),
            )

    def record_error(self, component: str, message: str):
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO error_log (component, message, occurred_at) VALUES (?, ?, ?)",
                (component, message, datetime.now(timezone.utc).isoformat()),
            )

    def record_price(self, price: float, price_timestamp: str, fetched_at: str,
                      drawdown_pct: Optional[float], source: str):
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO price_history (price, price_timestamp, fetched_at, drawdown_pct, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (price, price_timestamp, fetched_at, drawdown_pct, source),
            )

    def close(self):
        try:
            if self._conn:
                self._conn.close()
        except Exception:
            pass
        finally:
            self._conn = None
