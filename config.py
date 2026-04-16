"""
config.py — loads and validates all environment variables.

All runtime configuration lives here. Import `cfg` from other modules.
"""

import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

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
    ai_reminders_enabled: bool
    google_api_key: Optional[str]
    google_model: str
    openai_api_key: Optional[str]
    openai_model: str
    ai_moderation_enabled: bool
    ai_recent_messages_limit: int

    # --- reminder message templates (edit these to change the bot's personality) ---
    reminder_templates: tuple[str, ...] = field(
        default=(
            "🌿 Grass check: {mention} has been typing non-stop for {minutes} minutes. Log off. Touch grass. Now.",
            "🏆 Most active: {mention}. Congratulations, you need sunlight.",
            "📵 {mention} touched the keyboard way too much. Step outside immediately.",
            "🚨 {mention} wins the no-life award for this window. Grass is waiting.",
            "☀️ Attention: {mention} has forgotten the outside world exists. This is your reminder.",
        )
    )


def _env_bool(name: str, default: bool) -> bool:
    """Parse a permissive boolean environment variable."""
    raw = os.getenv(name)
    if raw is None:
        return default

    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


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

    google_api_key = (
        os.getenv("GOOGLE_API_KEY", "").strip()
        or os.getenv("GEMINI_API_KEY", "").strip()
        or None
    )
    google_model = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash-lite").strip() or "gemini-2.5-flash-lite"

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip() or None
    ai_reminders_enabled = _env_bool(
        "AI_REMINDERS_ENABLED",
        default=bool(google_api_key or openai_api_key),
    )
    openai_model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini").strip() or "gpt-5.4-mini"
    ai_moderation_enabled = _env_bool("AI_MODERATION_ENABLED", True)

    raw_recent_messages = os.getenv("AI_RECENT_MESSAGES_LIMIT", "20").strip()
    try:
        ai_recent_messages_limit = int(raw_recent_messages)
        if ai_recent_messages_limit < 1:
            raise ValueError
    except ValueError:
        sys.exit(
            "[FATAL] AI_RECENT_MESSAGES_LIMIT must be a positive integer, "
            f"got: {raw_recent_messages!r}"
        )

    return Config(
        bot_token=bot_token,
        allowed_chat_id=allowed_chat_id,
        interval_minutes=interval_minutes,
        log_level=log_level,
        ai_reminders_enabled=ai_reminders_enabled,
        google_api_key=google_api_key,
        google_model=google_model,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        ai_moderation_enabled=ai_moderation_enabled,
        ai_recent_messages_limit=ai_recent_messages_limit,
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
