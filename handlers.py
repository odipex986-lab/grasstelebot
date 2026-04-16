"""
handlers.py — Telegram update handlers.

Only one handler is needed: listen for messages in the allowed group
and record them in the counter.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import cfg
from counter import counter

logger = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for every message the bot receives.

    Guards (in order):
      1. Must have a message object.
      2. Must have a real sender (not a channel/anonymous post).
      3. Sender must NOT be a bot.
      4. Must be in the one allowed group chat — ignore everything else silently.
      5. Must be a normal text/media message, not a service message.
    """
    message = update.message
    if message is None:
        return  # edited messages, channel posts, etc. arrive as other update types

    user = message.from_user
    if user is None:
        # Anonymous admin or linked channel post — skip
        return

    if user.is_bot:
        logger.debug("Ignoring message from bot user_id=%d", user.id)
        return

    chat = message.chat
    if chat.id != cfg.allowed_chat_id:
        logger.debug(
            "Ignoring message from disallowed chat_id=%d (allowed: %d)",
            chat.id,
            cfg.allowed_chat_id,
        )
        return

    # Service messages (new member joined, pinned message, etc.) have no text/media
    # but python-telegram-bot still delivers them as Message objects.
    # We skip them by checking that at least one content field is populated.
    if not _is_real_message(message):
        logger.debug("Skipping service/empty message in chat_id=%d", chat.id)
        return

    # Record the message
    counter.record(
        user_id=user.id,
        username=user.username,     # may be None — counter handles this
        first_name=user.first_name,
    )
    logger.debug(
        "Recorded message from user_id=%d (@%s) in chat_id=%d",
        user.id,
        user.username or "no_username",
        chat.id,
    )


def _is_real_message(message) -> bool:  # type: ignore[no-untyped-def]
    """
    Return True if the message contains actual user content
    (text, photo, video, sticker, document, audio, voice, etc.).

    Service messages (member join/leave, title changes, etc.) will
    fail this check because none of these fields are set on them.
    """
    return any([
        message.text,
        message.photo,
        message.video,
        message.sticker,
        message.document,
        message.audio,
        message.voice,
        message.video_note,
        message.animation,
        message.location,
        message.contact,
        message.poll,
        message.dice,
    ])
