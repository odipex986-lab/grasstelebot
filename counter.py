"""
counter.py — in-memory message counter for the current 30-minute window.

Designed with a clean interface so the storage layer can be swapped out
for Redis or SQLite later without touching any other module.

Thread/async safety: all mutations happen in the asyncio event loop
(single-threaded), so no locks are needed for the in-memory version.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SenderInfo:
    """
    Display information captured from the Telegram User object.
    Stored alongside the count so the announcement can mention them correctly.
    """

    user_id: int
    username: Optional[str]        # e.g. "john_doe"  (may be None)
    first_name: str                # always present per Telegram spec
    first_message_index: int       # used to break ties — lower = earlier


@dataclass
class WindowStats:
    """
    Everything we track for a single sender in the current window.
    """

    info: SenderInfo
    count: int = 0


class MessageCounter:
    """
    Tracks per-user message counts for the current rolling window.

    Usage
    -----
    counter = MessageCounter()
    counter.record(user_id=123, username="alice", first_name="Alice")
    winner = counter.get_winner()
    counter.reset()
    """

    def __init__(self) -> None:
        # Maps user_id → WindowStats
        self._data: dict[int, WindowStats] = {}
        # Monotonically increasing index to break ties by first-message time
        self._message_index: int = 0

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def record(
        self,
        user_id: int,
        username: Optional[str],
        first_name: str,
    ) -> None:
        """
        Record one message from a user.

        If this is the user's first message this window, store their
        display info. We intentionally refresh username/first_name on
        every message so the final mention uses their latest display name.
        """
        self._message_index += 1

        if user_id not in self._data:
            self._data[user_id] = WindowStats(
                info=SenderInfo(
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                    first_message_index=self._message_index,
                ),
                count=1,
            )
            logger.debug("New sender this window: user_id=%d", user_id)
        else:
            entry = self._data[user_id]
            entry.count += 1
            # Keep display info fresh
            entry.info.username = username
            entry.info.first_name = first_name

    def reset(self) -> None:
        """Clear the current window. Call this after announcing the winner."""
        user_count = len(self._data)
        self._data.clear()
        self._message_index = 0
        logger.info("Counter reset. Had %d unique senders this window.", user_count)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_winner(self) -> Optional[SenderInfo]:
        """
        Return the SenderInfo of the user with the highest message count.

        Tie-breaking: if two users have the same count, the one who sent
        their *first* message earlier (lower first_message_index) wins.

        Returns None if no messages were recorded this window.
        """
        if not self._data:
            return None

        winner_entry = max(
            self._data.values(),
            key=lambda e: (e.count, -e.info.first_message_index),
        )
        logger.info(
            "Winner this window: user_id=%d, count=%d",
            winner_entry.info.user_id,
            winner_entry.count,
        )
        return winner_entry.info

    def total_messages(self) -> int:
        """Return total messages recorded this window (for logging)."""
        return sum(e.count for e in self._data.values())

    def snapshot(self) -> dict[int, int]:
        """
        Return a {user_id: count} snapshot. Useful for debugging or
        future admin commands.
        """
        return {uid: e.count for uid, e in self._data.items()}


# ---------------------------------------------------------------------------
# Module-level singleton — a single shared counter for the whole process.
# ---------------------------------------------------------------------------
counter = MessageCounter()
