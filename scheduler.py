"""
scheduler.py — the periodic "touch grass" announcement job.

Uses APScheduler's AsyncIOScheduler so the job runs inside the same
event loop as python-telegram-bot, making it safe to call bot.send_message
directly without extra thread-safety gymnastics.
"""

import html
import logging
import random
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from ai_reminders import ai_reminder_generator
from config import cfg
from counter import SenderInfo, counter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mention formatting
# ---------------------------------------------------------------------------

def _build_mention(info: SenderInfo) -> str:
    """
    Return an HTML mention string for the winner.

    Priority:
      1. @username  — plain text, no special formatting needed
      2. tg://user?id=... link with their first name (works even without username)

    We use HTML parse mode so we can safely escape first_name and still
    produce a clickable mention.
    """
    if info.username:
        # Using @username is the most readable format
        return f"@{html.escape(info.username)}"
    else:
        # Inline mention using Telegram's tg://user?id= scheme
        safe_name = html.escape(info.first_name)
        return f'<a href="tg://user?id={info.user_id}">{safe_name}</a>'


def _pick_fallback_message(mention: str) -> str:
    """Pick a random reminder template and fill in the placeholders."""
    template = random.choice(cfg.reminder_templates)
    return template.format(
        mention=mention,
        minutes=cfg.interval_minutes,
    )


async def _build_message(
    winner: SenderInfo,
    mention: str,
    winner_message_count: int,
    total_messages: int,
    unique_senders: int,
) -> str:
    """Prefer AI output when configured, otherwise use the static fallback."""
    ai_message = await ai_reminder_generator.generate(
        winner=winner,
        mention_html=mention,
        winner_message_count=winner_message_count,
        total_messages=total_messages,
        unique_senders=unique_senders,
    )
    if ai_message:
        return ai_message

    return _pick_fallback_message(mention)


# ---------------------------------------------------------------------------
# The scheduled job
# ---------------------------------------------------------------------------

async def touch_grass_job(bot: Bot) -> None:
    """
    Scheduled coroutine that runs every N minutes.

    Steps:
      1. Ask the counter for the window winner.
      2. If nobody sent anything, skip silently.
      3. Build a witty mention message.
      4. Send it to the allowed group.
      5. Reset the counter for the next window.
    """
    logger.info(
        "touch_grass_job fired. Window total: %d messages from %d unique senders.",
        counter.total_messages(),
        len(counter.snapshot()),
    )
    snapshot = counter.snapshot()
    total_messages = counter.total_messages()
    unique_senders = len(snapshot)

    winner: Optional[SenderInfo] = counter.get_winner()

    if winner is None:
        logger.info("No messages this window — skipping announcement.")
        counter.reset()  # still reset so next window starts clean
        return

    mention = _build_mention(winner)
    message_text = await _build_message(
        winner=winner,
        mention=mention,
        winner_message_count=snapshot.get(winner.user_id, 0),
        total_messages=total_messages,
        unique_senders=unique_senders,
    )

    try:
        await bot.send_message(
            chat_id=cfg.allowed_chat_id,
            text=message_text,
            parse_mode=ParseMode.HTML,
        )
        logger.info(
            "Announcement sent. Winner: user_id=%d, mention=%s",
            winner.user_id,
            mention,
        )
    except TelegramError as exc:
        # Log the error but do NOT crash — the scheduler will try again next window.
        logger.error("Failed to send touch-grass announcement: %s", exc)
    finally:
        # Always reset so the next window starts fresh, even if send failed.
        counter.reset()


# ---------------------------------------------------------------------------
# Scheduler factory
# ---------------------------------------------------------------------------

def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    """
    Create and configure the APScheduler instance.

    Returns an un-started scheduler. Call `.start()` after the Telegram
    Application is initialised so both share the same event loop.
    """
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        touch_grass_job,
        trigger="interval",
        minutes=cfg.interval_minutes,
        args=[bot],
        id="touch_grass",          # named ID prevents accidental duplicates
        replace_existing=True,     # safe to call on restart
        misfire_grace_time=60,     # allow up to 60s late firing before skipping
    )

    logger.info(
        "Scheduler configured: touch_grass_job every %d minute(s).",
        cfg.interval_minutes,
    )
    return scheduler
