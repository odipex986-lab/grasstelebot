"""
ai_reminders.py — optional AI-powered reminder generation.

Google Gemini is preferred when GOOGLE_API_KEY is configured because it has a
usable free tier. OpenAI remains available as a fallback when configured.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from typing import Optional

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - optional dependency in local envs
    AsyncOpenAI = None  # type: ignore[assignment]

from config import cfg
from counter import SenderInfo

logger = logging.getLogger(__name__)

_MENTION_TOKEN = "__MENTION__"


class AIReminderGenerator:
    """Generate short reminder messages with an AI provider and cache outputs."""

    def __init__(self) -> None:
        self._recent_messages: deque[str] = deque(maxlen=cfg.ai_recent_messages_limit)
        self._openai_client: Optional[AsyncOpenAI] = None
        self._provider = "none"

        if cfg.ai_reminders_enabled and cfg.google_api_key:
            self._provider = "google"
            logger.info("AI reminders enabled with Google Gemini model %s.", cfg.google_model)
        elif cfg.ai_reminders_enabled and cfg.openai_api_key and AsyncOpenAI is not None:
            self._provider = "openai"
            self._openai_client = AsyncOpenAI(api_key=cfg.openai_api_key)
            logger.info("AI reminders enabled with OpenAI model %s.", cfg.openai_model)
        elif cfg.ai_reminders_enabled and cfg.openai_api_key and AsyncOpenAI is None:
            logger.warning(
                "OPENAI_API_KEY is set but the openai package is unavailable. "
                "Falling back to static reminder templates."
            )
        elif cfg.ai_reminders_enabled:
            logger.warning(
                "AI reminders were enabled but no supported API key is configured. "
                "Falling back to static reminder templates."
            )

    @property
    def enabled(self) -> bool:
        """Return True when AI generation is configured and ready."""
        return self._provider != "none"

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
        if not self.enabled:
            return None

        for attempt in range(1, 4):
            candidate = await self._generate_candidate(
                winner=winner,
                winner_message_count=winner_message_count,
                total_messages=total_messages,
                unique_senders=unique_senders,
            )
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
        """Close provider clients cleanly on shutdown."""
        if self._openai_client is not None:
            await self._openai_client.close()

    async def _generate_candidate(
        self,
        *,
        winner: SenderInfo,
        winner_message_count: int,
        total_messages: int,
        unique_senders: int,
    ) -> Optional[str]:
        """Dispatch generation to the configured provider."""
        if self._provider == "google":
            return await self._generate_with_google(
                winner=winner,
                winner_message_count=winner_message_count,
                total_messages=total_messages,
                unique_senders=unique_senders,
            )

        if self._provider == "openai":
            return await self._generate_with_openai(
                winner=winner,
                winner_message_count=winner_message_count,
                total_messages=total_messages,
                unique_senders=unique_senders,
            )

        return None

    async def _generate_with_google(
        self,
        *,
        winner: SenderInfo,
        winner_message_count: int,
        total_messages: int,
        unique_senders: int,
    ) -> Optional[str]:
        """Call Gemini's generateContent endpoint using the free-tier model."""
        if not cfg.google_api_key:
            return None

        request_body = self._build_google_request(
            winner=winner,
            winner_message_count=winner_message_count,
            total_messages=total_messages,
            unique_senders=unique_senders,
        )
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{urllib.parse.quote(cfg.google_model, safe='')}:generateContent"
            f"?key={urllib.parse.quote(cfg.google_api_key, safe='')}"
        )

        try:
            status, response = await asyncio.to_thread(
                self._post_json,
                url,
                request_body,
            )
        except Exception as exc:
            logger.warning("Gemini reminder generation failed: %s", exc)
            return None

        if status != 200:
            message = response.get("error", {}).get("message", response)
            logger.warning("Gemini reminder generation failed with status %s: %s", status, message)
            return None

        return self._clean_candidate(self._extract_google_text(response))

    async def _generate_with_openai(
        self,
        *,
        winner: SenderInfo,
        winner_message_count: int,
        total_messages: int,
        unique_senders: int,
    ) -> Optional[str]:
        """Call OpenAI's Responses API when configured."""
        if self._openai_client is None:
            return None

        try:
            response = await self._openai_client.responses.create(
                **self._build_openai_request(
                    winner=winner,
                    winner_message_count=winner_message_count,
                    total_messages=total_messages,
                    unique_senders=unique_senders,
                )
            )
        except Exception as exc:
            logger.warning("OpenAI reminder generation failed: %s", exc)
            return None

        return self._clean_candidate(response.output_text or "")

    def _build_google_request(
        self,
        *,
        winner: SenderInfo,
        winner_message_count: int,
        total_messages: int,
        unique_senders: int,
    ) -> dict:
        """Build the Gemini generateContent request payload."""
        return {
            "systemInstruction": {
                "parts": [
                    {
                        "text": self._system_prompt(),
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": self._prompt_context(
                                winner=winner,
                                winner_message_count=winner_message_count,
                                total_messages=total_messages,
                                unique_senders=unique_senders,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 1.15,
                "topP": 0.95,
                "maxOutputTokens": 80,
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_ONLY_HIGH",
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
            ],
        }

    def _build_openai_request(
        self,
        *,
        winner: SenderInfo,
        winner_message_count: int,
        total_messages: int,
        unique_senders: int,
    ) -> dict:
        """Construct a concise OpenAI Responses API request."""
        request = {
            "model": cfg.openai_model,
            "instructions": self._system_prompt(),
            "input": self._prompt_context(
                winner=winner,
                winner_message_count=winner_message_count,
                total_messages=total_messages,
                unique_senders=unique_senders,
            ),
        }

        if cfg.openai_model.startswith("gpt-5"):
            request["reasoning"] = {"effort": "none"}
            request["text"] = {"verbosity": "low"}

        return request

    async def _is_flagged(self, candidate: str) -> bool:
        """Moderate generated output when using OpenAI moderation."""
        if (
            self._provider != "openai"
            or not cfg.ai_moderation_enabled
            or self._openai_client is None
        ):
            return False

        try:
            result = await self._openai_client.moderations.create(
                model="omni-moderation-latest",
                input=candidate,
            )
        except Exception as exc:
            logger.warning("OpenAI moderation failed: %s", exc)
            return False

        return bool(result.results and result.results[0].flagged)

    def _prompt_context(
        self,
        *,
        winner: SenderInfo,
        winner_message_count: int,
        total_messages: int,
        unique_senders: int,
    ) -> str:
        """Build the user prompt context shared across providers."""
        recent_lines = "\n".join(
            f"- {message}" for message in self._recent_messages
        ) or "- none yet"

        return (
            f"Interval minutes: {cfg.interval_minutes}\n"
            f"Winner display name: {winner.first_name}\n"
            f"Winner username: {winner.username or 'none'}\n"
            f"Winner message count: {winner_message_count}\n"
            f"Window total messages: {total_messages}\n"
            f"Unique senders: {unique_senders}\n"
            "Recent reminders to avoid copying:\n"
            f"{recent_lines}\n"
            "Write a fresh reminder now."
        )

    @staticmethod
    def _system_prompt() -> str:
        """Shared system instruction for short, safe roast lines."""
        return (
            "You write one-line Telegram reminders for a playful touch-grass bot. "
            f"Return exactly one sentence under 160 characters. Include the token {_MENTION_TOKEN} "
            "exactly once. Keep it playful, lightly teasing, and original. Avoid slurs, sexual content, "
            "hate, harassment, threats, profanity, hashtags, markdown, and quote marks. "
            "Do not add explanations or multiple options."
        )

    def _is_recent_duplicate(self, candidate: str) -> bool:
        """Reject near-identical phrasing so the bot feels fresher over time."""
        normalized_candidate = self._normalize(candidate)
        return any(
            self._normalize(previous) == normalized_candidate
            for previous in self._recent_messages
        )

    @staticmethod
    def _extract_google_text(response: dict) -> str:
        """Extract plain text from a Gemini generateContent response."""
        candidates = response.get("candidates") or []
        if not candidates:
            return ""

        first_candidate = candidates[0]
        parts = first_candidate.get("content", {}).get("parts") or []
        text_chunks = [
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and part.get("text")
        ]
        return " ".join(text_chunks)

    @staticmethod
    def _post_json(url: str, payload: dict) -> tuple[int, dict]:
        """POST JSON with stdlib so we avoid extra provider SDKs."""
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
                return response.status, json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                return exc.code, json.loads(body)
            except json.JSONDecodeError:
                return exc.code, {"raw": body}

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
