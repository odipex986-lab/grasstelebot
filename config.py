"""
config.py — loads and validates all environment variables.

All runtime configuration lives here. Import `cfg` from other modules.
"""

import logging
import os
import sys
from dataclasses import dataclass, field

from dotenv import load_dotenv


# Load a local .env file when present. Existing environment variables win,
# so Railway/service-level variables still take precedence in production.
load_dotenv()


@dataclass(frozen=True)
class Config:
    """Immutable configuration loaded from environment variables."""

    bot_token: str
    allowed_chat_id: int
    interval_minutes: int
    log_level: str

    # --- reminder message templates (edit these to change the bot's personality) ---
    reminder_templates: tuple[str, ...] = field(
        default=(
            "🌿 Grass check: {mention} has been typing non-stop for 30 minutes. Log off. Touch grass. Now.",
            "🏆 Most active: {mention}. Congratulations, you need sunlight.",
            "📵 {mention} touched the keyboard way too much. Step outside immediately.",
            "🚨 {mention} wins the no-life award for this window. Grass is waiting.",
            "☀️ Attention: {mention} has forgotten the outside world exists. This is your reminder.",
        )
    )


def load_config() -> Config:
    """
    Read config from environment variables and return a validated Config.
    Exits with a clear error message if required vars are missing.
    """
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        sys.exit("[FATAL] BOT_TOKEN environment variable is not set.")

    raw_chat_id = os.getenv("ALLOWED_CHAT_ID", "").strip()
    if not raw_chat_id:
        sys.exit("[FATAL] ALLOWED_CHAT_ID environment variable is not set.")
    try:
        allowed_chat_id = int(raw_chat_id)
    except ValueError:
        sys.exit(f"[FATAL] ALLOWED_CHAT_ID must be an integer, got: {raw_chat_id!r}")

    raw_interval = os.getenv("TOUCH_GRASS_INTERVAL_MINUTES", "30").strip()
    try:
        interval_minutes = int(raw_interval)
        if interval_minutes < 1:
            raise ValueError
    except ValueError:
        sys.exit(
            f"[FATAL] TOUCH_GRASS_INTERVAL_MINUTES must be a positive integer, got: {raw_interval!r}"
        )

    log_level = os.getenv("LOG_LEVEL", "INFO").upper().strip()
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        log_level = "INFO"

    return Config(
        bot_token=bot_token,
        allowed_chat_id=allowed_chat_id,
        interval_minutes=interval_minutes,
        log_level=log_level,
    )


# Module-level singleton — import this everywhere.
cfg: Config = load_config()


def setup_logging() -> None:
    """Configure root logger based on LOG_LEVEL env var."""
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=getattr(logging, cfg.log_level),
    )
    # Quiet down noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
