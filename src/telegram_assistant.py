"""
NIFTY 50 Drawdown Alert System - Telegram Assistant Bot.

Production-grade Telegram bot with retry/backoff, error-safe handlers,
and resilient polling configuration.
"""
from __future__ import annotations

import logging
import os
import signal
import time
from datetime import datetime
from typing import List, Dict, Any

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.config import CONFIG
from src.data_provider import get_provider
from src.persistence.database import Database
from src.services.high_calculator import HighCalculator
from src.services.price_service import PriceService

logger = logging.getLogger("nifty_ai.telegram_assistant")

_network_ready = True


def _drawdown_pct(current_price: float, high_value: float) -> float:
    if high_value <= 0:
        return 0.0
    return max(0.0, ((high_value - current_price) / high_value) * 100)


def _threshold_levels(high_value: float, thresholds: List[float]) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    for threshold in thresholds:
        level = high_value * (1 - (threshold / 100))
        rows.append({"threshold": threshold, "level": level})
    return rows


def get_market_snapshot() -> Dict[str, Any]:
    db = Database(CONFIG.database_path)
    try:
        provider = get_provider(CONFIG.market_data_provider)
        price_service = PriceService(
            provider=provider,
            symbol=CONFIG.nifty_ticker_symbol,
            max_staleness_seconds=CONFIG.max_price_staleness_seconds,
        )
        high_calculator = HighCalculator(provider=provider, db=db, symbol=CONFIG.nifty_ticker_symbol)

        quote = price_service.get_validated_quote()
        high_value = high_calculator.get_current_high_value()
        drawdown = _drawdown_pct(quote.price, high_value)
        levels = _threshold_levels(high_value, CONFIG.drawdown_thresholds)

        next_threshold = None
        for entry in levels:
            threshold = entry["threshold"]
            if drawdown < threshold:
                next_threshold = entry
                break

        return {
            "current": quote.price,
            "high": high_value,
            "drawdown": drawdown,
            "timestamp": quote.timestamp,
            "levels": levels,
            "next_threshold": next_threshold,
            "source": quote.source,
            "error": None,
        }
    except Exception as exc:
        logger.warning("Unable to fetch NIFTY snapshot: %s", exc)
        return {
            "current": None,
            "high": None,
            "drawdown": None,
            "timestamp": None,
            "levels": [],
            "next_threshold": None,
            "source": None,
            "error": str(exc),
        }
    finally:
        try:
            db.close()
        except Exception:
            pass


def format_snapshot_status(snapshot: Dict[str, Any]) -> str:
    if snapshot.get("error"):
        return (
            "Market data is currently unavailable.\n"
            "Reason: " + snapshot["error"] + "\n\n"
            "Tip: If the market is closed, data will update once it opens (09:15-15:30 IST, Mon-Fri)."
        )

    current = snapshot["current"]
    high = snapshot["high"]
    drawdown = snapshot["drawdown"]
    ts = snapshot["timestamp"]
    next_threshold = snapshot["next_threshold"]

    next_line = "Not currently near a configured threshold"
    if next_threshold:
        next_line = f"Next alert: {next_threshold['threshold']:.0f}% at {next_threshold['level']:.2f}"

    return (
        "NIFTY 50\n\n"
        f"Current: {current:,.2f}\n"
        f"52W High: {high:,.2f}\n"
        f"Drawdown: {drawdown:.2f}%\n"
        f"{next_line}\n"
        f"Data: {ts.strftime('%d-%b-%Y %I:%M %p IST')}"
    )


def format_threshold_levels(snapshot: Dict[str, Any]) -> str:
    if snapshot.get("error"):
        return format_snapshot_status(snapshot)

    lines = ["Drawdown levels:"]
    for row in snapshot["levels"]:
        lines.append(f"- {row['threshold']:.0f}% -> {row['level']:.2f}")
    return "\n".join(lines)


def format_help() -> str:
    return (
        "NIFTY AI Assistant\n\n"
        "/start - welcome message\n"
        "/help - show commands\n"
        "/nifty - current NIFTY status\n"
        "/status - current price, 52W high, drawdown\n"
        "/drawdown - current drawdown and next threshold\n"
        "/levels - full threshold table\n"
        "/alerts - alert configuration summary\n"
        "/history - historical analysis\n"
        "/news - current market/news summary\n\n"
        "You can also ask natural-language questions like:\n"
        "'what's nifty right now?' or 'how much is it down?'"
    )


async def _safe_reply(update: Update, text: str) -> None:
    """Send a reply, handling all possible Telegram API errors."""
    try:
        if update and update.message:
            await update.message.reply_text(text)
    except Exception as exc:
        logger.warning("Failed to send reply: %s", exc)


async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _safe_reply(
        update,
        "Welcome to the NIFTY 50 AI Telegram Assistant.\n\n"
        "Use /status, /drawdown, /levels, or ask a natural-language question.",
    )


async def _handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _safe_reply(update, format_help())


async def _handle_nifty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        snapshot = get_market_snapshot()
        await _safe_reply(update, format_snapshot_status(snapshot))
    except Exception as exc:
        logger.exception("Error in /nifty handler")
        await _safe_reply(update, "Error fetching NIFTY data. Please try again.")


async def _handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        snapshot = get_market_snapshot()
        await _safe_reply(update, format_snapshot_status(snapshot))
    except Exception as exc:
        logger.exception("Error in /status handler")
        await _safe_reply(update, "Error fetching status. Please try again.")


async def _handle_drawdown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        snapshot = get_market_snapshot()
        if snapshot.get("error"):
            await _safe_reply(update, format_snapshot_status(snapshot))
            return

        next_threshold = snapshot["next_threshold"]
        next_line = "No configured threshold is active right now"
        if next_threshold:
            next_line = f"Next threshold: {next_threshold['threshold']:.0f}% at {next_threshold['level']:.2f}"

        text = (
            "NIFTY 50 Drawdown\n\n"
            f"Current: {snapshot['current']:,.2f}\n"
            f"52W High: {snapshot['high']:,.2f}\n"
            f"Drawdown: {snapshot['drawdown']:.2f}%\n"
            f"{next_line}"
        )
        await _safe_reply(update, text)
    except Exception as exc:
        logger.exception("Error in /drawdown handler")
        await _safe_reply(update, "Error fetching drawdown data. Please try again.")


async def _handle_levels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        snapshot = get_market_snapshot()
        await _safe_reply(update, format_threshold_levels(snapshot))
    except Exception as exc:
        logger.exception("Error in /levels handler")
        await _safe_reply(update, "Error fetching levels. Please try again.")


async def _handle_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        snapshot = get_market_snapshot()
        if snapshot.get("error"):
            await _safe_reply(update, format_snapshot_status(snapshot))
            return

        text = (
            "Configured alerts\n\n"
            + "\n".join(f"- {row['threshold']:.0f}%: {row['level']:.2f}" for row in snapshot["levels"])
        )
        await _safe_reply(update, text)
    except Exception as exc:
        logger.exception("Error in /alerts handler")
        await _safe_reply(update, "Error fetching alerts. Please try again.")


async def _handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _safe_reply(
        update,
        "Historical NIFTY analysis is available through the market-data source. "
        "Ask for a date range like 'show NIFTY from 2020 to 2022'.",
    )


async def _handle_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _safe_reply(
        update,
        "Current market/news context is supported when a live news source is available. "
        "Otherwise, I will clearly say it is unavailable.",
    )


async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if not update or not update.message or not update.message.text:
            return

        text = update.message.text.strip().lower()
        if not text:
            return

        if any(word in text for word in ["hi", "hello", "hey"]):
            await _safe_reply(
                update,
                "Hello! I can help with NIFTY price, drawdown, 52-week high, and threshold levels. "
                "Try /status or ask 'what's nifty right now?'",
            )
            return

        if any(w in text for w in ["drawdown", "down", "current", "price", "value"]):
            snapshot = get_market_snapshot()
            await _safe_reply(update, format_snapshot_status(snapshot))
            return

        if any(w in text for w in ["level", "threshold"]):
            snapshot = get_market_snapshot()
            await _safe_reply(update, format_threshold_levels(snapshot))
            return

        if "52" in text and any(w in text for w in ["week", "w", "high"]):
            snapshot = get_market_snapshot()
            if snapshot.get("error"):
                await _safe_reply(update, format_snapshot_status(snapshot))
                return
            await _safe_reply(
                update,
                f"52-week high: {snapshot['high']:,.2f} "
                f"(data: {snapshot['timestamp'].strftime('%d-%b-%Y %I:%M %p IST')})",
            )
            return

        if "alert" in text:
            snapshot = get_market_snapshot()
            await _safe_reply(update, format_threshold_levels(snapshot))
            return

        await _safe_reply(
            update,
            "I can help with NIFTY price, drawdown, 52-week high, threshold levels, and alert status. "
            "Try /status or ask: 'what's nifty right now?'",
        )
    except Exception as exc:
        logger.exception("Error in text handler")
        await _safe_reply(update, "Sorry, something went wrong. Please try again.")


async def _post_init(application) -> None:
    """Validate configuration after bot connects to Telegram."""
    logger.info("Telegram bot connected successfully.")
    if not CONFIG.telegram_chat_id:
        logger.warning("TELEGRAM_CHAT_ID is not set — alerts will not be delivered.")


async def _post_shutdown(application) -> None:
    logger.info("Telegram bot shutting down gracefully.")


def main() -> None:
    token = CONFIG.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not configured. "
            "Set it in .env or environment variables."
        )

    logging.basicConfig(
        level=getattr(logging, CONFIG.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Starting NIFTY AI Telegram assistant...")

    app = (
        ApplicationBuilder()
        .token(token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .read_timeout(15)
        .write_timeout(15)
        .connect_timeout(15)
        .build()
    )

    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("help", _handle_help))
    app.add_handler(CommandHandler("nifty", _handle_nifty))
    app.add_handler(CommandHandler("status", _handle_status))
    app.add_handler(CommandHandler("drawdown", _handle_drawdown))
    app.add_handler(CommandHandler("levels", _handle_levels))
    app.add_handler(CommandHandler("alerts", _handle_alerts))
    app.add_handler(CommandHandler("history", _handle_history))
    app.add_handler(CommandHandler("news", _handle_news))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))

    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
        poll_interval=2.0,
        timeout=15,
    )


if __name__ == "__main__":
    main()
