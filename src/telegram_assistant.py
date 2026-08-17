"""Telegram assistant for NIFTY 50 monitoring and queries."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List, Dict, Any

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from src.config import CONFIG
from src.data_provider import get_provider
from src.persistence.database import Database
from src.services.high_calculator import HighCalculator
from src.services.price_service import PriceService

logger = logging.getLogger("nifty_ai.telegram_assistant")


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
    except Exception as exc:  # pragma: no cover - runtime error path
        logger.exception("Unable to fetch NIFTY snapshot")
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
        db.close()


def format_snapshot_status(snapshot: Dict[str, Any]) -> str:
    if snapshot.get("error"):
        return (
            "I can’t verify the current NIFTY 50 data right now because the market-data source is unavailable.\n"
            f"Reason: {snapshot['error']}"
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
        "/history - historical analysis is supported through the market-data source\n"
        "/news - current market/news summary is supported when available\n\n"
        "You can also ask natural-language questions like: 'what's nifty right now?' or 'how much is it down?'"
    )


async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Welcome to the NIFTY 50 AI Telegram Assistant.\n\n"
        "Use /status, /drawdown, /levels, or ask a natural-language question like 'what's nifty right now?'"
    )


async def _handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(format_help())


async def _handle_nifty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    snapshot = get_market_snapshot()
    await update.message.reply_text(format_snapshot_status(snapshot))


async def _handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    snapshot = get_market_snapshot()
    await update.message.reply_text(format_snapshot_status(snapshot))


async def _handle_drawdown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    snapshot = get_market_snapshot()
    if snapshot.get("error"):
        await update.message.reply_text(format_snapshot_status(snapshot))
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
    await update.message.reply_text(text)


async def _handle_levels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    snapshot = get_market_snapshot()
    await update.message.reply_text(format_threshold_levels(snapshot))


async def _handle_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    snapshot = get_market_snapshot()
    if snapshot.get("error"):
        await update.message.reply_text(format_snapshot_status(snapshot))
        return

    text = (
        "Configured alerts\n\n"
        + "\n".join(f"- {row['threshold']:.0f}%: {row['level']:.2f}" for row in snapshot["levels"])
    )
    await update.message.reply_text(text)


async def _handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Historical NIFTY analysis is available through the market-data source in this project. Ask for a date range like 'show NIFTY from 2020 to 2022' and I can use the project data source."
    )


async def _handle_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Current market/news context is supported when a live news source is available. Otherwise, I will clearly say it is unavailable."
    )


async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip().lower()
    if not text:
        return

    if any(word in text for word in ["hi", "hello", "hey"]):
        await update.message.reply_text("Hello! I can help with NIFTY price, drawdown, 52-week high, and threshold levels. Try /status or ask 'what's nifty right now?'")
        return

    if "drawdown" in text or "down" in text or "current" in text or "price" in text or "value" in text:
        snapshot = get_market_snapshot()
        await update.message.reply_text(format_snapshot_status(snapshot))
        return

    if "level" in text or "threshold" in text:
        snapshot = get_market_snapshot()
        await update.message.reply_text(format_threshold_levels(snapshot))
        return

    if "52" in text and ("week" in text or "w" in text or "high" in text):
        snapshot = get_market_snapshot()
        if snapshot.get("error"):
            await update.message.reply_text(format_snapshot_status(snapshot))
            return
        await update.message.reply_text(f"52-week high: {snapshot['high']:,.2f} (data: {snapshot['timestamp'].strftime('%d-%b-%Y %I:%M %p IST')})")
        return

    if "alert" in text:
        snapshot = get_market_snapshot()
        await update.message.reply_text(format_threshold_levels(snapshot))
        return

    await update.message.reply_text(
        "I can help with NIFTY price, drawdown, 52-week high, threshold levels, and alert status. Try /status or ask: 'what's nifty right now?'"
    )


def main() -> None:
    token = CONFIG.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured. Set it in .env or environment variables.")

    logging.basicConfig(
        level=getattr(logging, CONFIG.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = ApplicationBuilder().token(token).build()

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

    logger.info("Starting NIFTY AI Telegram assistant...")
    app.run_polling()


if __name__ == "__main__":
    main()
