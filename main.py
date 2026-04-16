"""
main.py — entry point for the Touch Grass Telegram bot.

Startup sequence:
  1. Load and validate config (config.py exits if anything is wrong).
  2. Configure logging.
  3. Build the Telegram Application with our message handler.
  4. Register post-init hook to start APScheduler after the event loop
     is running (so scheduler and bot share the same loop).
  5. Start polling — python-telegram-bot handles reconnections and backoff.

Shutdown is handled gracefully by python-telegram-bot's signal handlers
(SIGINT / SIGTERM), which will stop polling and shut down cleanly.
"""

import logging

from telegram.ext import Application, MessageHandler, filters

from config import cfg, setup_logging
from handlers import handle_message
from scheduler import create_scheduler

# Set up logging before anything else
setup_logging()
logger = logging.getLogger(__name__)


async def _on_startup(application: Application) -> None:  # type: ignore[type-arg]
    """
    post_init hook — called by python-telegram-bot after the Application
    is fully initialised and the event loop is running.

    This is the safe place to start APScheduler because:
      - The event loop exists and is the one the scheduler will use.
      - The Bot object is fully configured.
    """
    scheduler = create_scheduler(application.bot)
    scheduler.start()
    # Stash on application so we can shut it down cleanly if needed
    application.bot_data["scheduler"] = scheduler
    logger.info(
        "Bot started. Listening in chat_id=%d. "
        "Touch-grass interval: %d min.",
        cfg.allowed_chat_id,
        cfg.interval_minutes,
    )


async def _on_shutdown(application: Application) -> None:  # type: ignore[type-arg]
    """post_shutdown hook — stop the scheduler cleanly."""
    scheduler = application.bot_data.get("scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


def main() -> None:
    """Build and run the bot."""

    logger.info("Initialising Touch Grass Bot...")

    application = (
        Application.builder()
        .token(cfg.bot_token)
        .post_init(_on_startup)
        .post_shutdown(_on_shutdown)
        .build()
    )

    # --- Register handlers ---
    # filters.ALL includes text, photo, sticker, etc. — our handler
    # does its own fine-grained filtering inside.
    application.add_handler(
        MessageHandler(filters.ALL, handle_message)
    )

    logger.info("Starting polling...")

    # run_polling blocks until SIGINT/SIGTERM.
    # - allowed_updates: we only care about "message" updates.
    # - drop_pending_updates: ignore any backlog that built up while offline.
    application.run_polling(
        allowed_updates=["message"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
