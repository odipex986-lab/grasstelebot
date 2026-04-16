"""
ai_reminders.py — optional OpenAI-powered reminder generation.

When AI is enabled, we ask the model for a short, fresh reminder line and keep a
small in-memory history to avoid repeating ourselves too often. If anything goes
wrong, callers should fall back to the static templates.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from typing import Optional

from openai import AsyncOpenAI

from config import cfg
from counter import SenderInfo

logger = logging.getLogger(__name__)

_MENTION_TOKEN = "__MENTION__"


class AIReminderGenerator:
    """Generate short reminder messages with OpenAI and cache recent outputs."""

    def __init__(self) -> None:
        self._recent_messages: deque[str] = deque(maxlen=cfg.ai_recent_messages_limit)
        self._client: Optional[AsyncOpenAI] = None

        if cfg.ai_reminders_enabled and cfg.openai_api_key:
            self._client = AsyncOpenAI(api_key=cfg.openai_api_key)
        elif cfg.ai_reminders_enabled:
            logger.warning(
                "AI reminders were enabled but OPENAI_API_KEY is missing. "
                "Falling back to static reminder templates."
            )

    @property
    def enabled(self) -> bool:
        """Return True when AI generation is configured and ready."""
        return self._client is not None

    async def generate(
        self,
        winner: SenderInfo,
        mention_html: str,
        winner_message_count: int,
        total_messages: int,
        unique_senders: int,
    ) -> Optional[str]:
        """
        Generate a fresh reminder line.

        Returns None when AI is disabled, generation fails, moderation blocks the
        result, or the output is too similar to recent messages.
        """
        if not self.enabled or self._client is None:
            return None

        for attempt in range(1, 4):
            try:
                response = await self._client.responses.create(
                    **self._build_request(
                        winner=winner,
                        winner_message_count=winner_message_count,
                        total_messages=total_messages,
                        unique_senders=unique_senders,
                    )
                )
            except Exception as exc:
                logger.warning("OpenAI reminder generation failed: %s", exc)
                return None

            candidate = self._clean_candidate(response.output_text or "")
            if not candidate:
                logger.debug("AI reminder attempt %d produced empty output.", attempt)
                continue

            if candidate.count(_MENTION_TOKEN) != 1:
                logger.debug(
                    "AI reminder attempt %d missed the mention token contract: %r",
                    attempt,
                    candidate,
                )
                continue

            if self._is_recent_duplicate(candidate):
                logger.debug("AI reminder attempt %d was too similar to recent output.", attempt)
                continue

            if await self._is_flagged(candidate):
                logger.warning("AI reminder attempt %d was blocked by moderation.", attempt)
                continue

            self._recent_messages.append(candidate)
            return candidate.replace(_MENTION_TOKEN, mention_html)

        logger.warning("AI reminder generator exhausted retries. Using static template.")
        return None

    async def aclose(self) -> None:
        """Close the async API client cleanly on shutdown."""
        if self._client is not None:
            await self._client.close()

    def _build_request(
        self,
        *,
        winner: SenderInfo,
        winner_message_count: int,
        total_messages: int,
        unique_senders: int,
    ) -> dict:
        """Construct a concise Responses API request."""
        recent_lines = "\n".join(
            f"- {message}" for message in self._recent_messages
        ) or "- none yet"

        request = {
            "model": cfg.openai_model,
            "instructions": (
                "You write one-line Telegram reminders for a playful touch-grass bot. "
                f"Return exactly one sentence under 160 characters. Include the token {_MENTION_TOKEN} "
                "exactly once. Keep it playful, lightly teasing, and original. Avoid slurs, sexual content, "
                "hate, harassment, threats, profanity, hashtags, markdown, and quote marks. "
                "Do not add explanations or multiple options."
            ),
            "input": (
                f"Interval minutes: {cfg.interval_minutes}\n"
                f"Winner display name: {winner.first_name}\n"
                f"Winner username: {winner.username or 'none'}\n"
                f"Winner message count: {winner_message_count}\n"
                f"Window total messages: {total_messages}\n"
                f"Unique senders: {unique_senders}\n"
                "Recent reminders to avoid copying:\n"
                f"{recent_lines}\n"
                "Write a fresh reminder now."
            ),
        }

        if cfg.openai_model.startswith("gpt-5"):
            request["reasoning"] = {"effort": "none"}
            request["text"] = {"verbosity": "low"}

        return request

    async def _is_flagged(self, candidate: str) -> bool:
        """Moderate the generated output when moderation is enabled."""
        if not cfg.ai_moderation_enabled or self._client is None:
            return False

        try:
            result = await self._client.moderations.create(
                model="omni-moderation-latest",
                input=candidate,
            )
        except Exception as exc:
            logger.warning("OpenAI moderation failed: %s", exc)
            return False

        return bool(result.results and result.results[0].flagged)

    def _is_recent_duplicate(self, candidate: str) -> bool:
        """Reject near-identical phrasing so the bot feels fresher over time."""
        normalized_candidate = self._normalize(candidate)
        return any(
            self._normalize(previous) == normalized_candidate
            for previous in self._recent_messages
        )

    @staticmethod
    def _clean_candidate(text: str) -> str:
        """Normalize whitespace and strip wrapping punctuation."""
        collapsed = " ".join(text.split()).strip()
        cleaned = collapsed.strip("\"'`")
        return cleaned[:160].rstrip()

    @staticmethod
    def _normalize(text: str) -> str:
        """Reduce superficial differences before duplicate checks."""
        without_mention = text.replace(_MENTION_TOKEN, "")
        lowered = without_mention.lower()
        return re.sub(r"[^a-z0-9]+", "", lowered)


ai_reminder_generator = AIReminderGenerator()
