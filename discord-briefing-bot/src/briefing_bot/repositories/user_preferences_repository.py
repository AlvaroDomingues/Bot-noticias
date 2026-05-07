"""Repository for storing Discord user preferences."""

import asyncio
import json
from pathlib import Path
from typing import Any, Protocol

from briefing_bot.models import UserPreferences

PreferencesPayload = dict[str, dict[str, Any]]


class UserPreferencesRepositoryProtocol(Protocol):
    """Small persistence contract for saved user preferences."""

    async def get(self, user_id: int) -> UserPreferences | None:
        """Fetch preferences by Discord user id.

        Args:
            user_id: Discord user id.

        Returns:
            Saved preferences or None when not found.
        """

    async def list_all(self) -> list[UserPreferences]:
        """List all saved preferences.

        Returns:
            All persisted user preferences.
        """

    async def save(self, preferences: UserPreferences) -> None:
        """Persist preferences for one user.

        Args:
            preferences: Preferences to save.
        """

    async def delete(self, user_id: int) -> None:
        """Delete preferences for one user.

        Args:
            user_id: Discord user id.
        """


class JsonUserPreferencesRepository:
    """JSON-file implementation of user preference persistence."""

    def __init__(self, path: Path) -> None:
        """Create a JSON repository.

        Args:
            path: File path used to store preferences.
        """
        self._path = path
        self._lock = asyncio.Lock()

    async def get(self, user_id: int) -> UserPreferences | None:
        """Fetch preferences by Discord user id.

        Args:
            user_id: Discord user id.

        Returns:
            Saved preferences or None when not found.
        """
        async with self._lock:
            payload = await asyncio.to_thread(self._read_all)
            item = payload.get(str(user_id))
        return None if item is None else UserPreferences.model_validate(item)

    async def list_all(self) -> list[UserPreferences]:
        """List all saved preferences.

        Returns:
            All persisted user preferences.
        """
        async with self._lock:
            payload = await asyncio.to_thread(self._read_all)
        return [UserPreferences.model_validate(item) for item in payload.values()]

    async def save(self, preferences: UserPreferences) -> None:
        """Persist preferences for one user.

        Args:
            preferences: Preferences to save.
        """
        async with self._lock:
            payload = await asyncio.to_thread(self._read_all)
            payload[str(preferences.user_id)] = preferences.model_dump(mode="json")
            await asyncio.to_thread(self._write_all, payload)

    async def delete(self, user_id: int) -> None:
        """Delete preferences for one user.

        Args:
            user_id: Discord user id.
        """
        async with self._lock:
            payload = await asyncio.to_thread(self._read_all)
            payload.pop(str(user_id), None)
            await asyncio.to_thread(self._write_all, payload)

    def _read_all(self) -> PreferencesPayload:
        """Read all preferences from disk.

        Returns:
            Raw preference payload keyed by user id.
        """
        if not self._path.exists():
            return {}
        content = self._path.read_text(encoding="utf-8")
        return json.loads(content) if content.strip() else {}

    def _write_all(self, payload: PreferencesPayload) -> None:
        """Write all preferences to disk.

        Args:
            payload: Raw preference payload keyed by user id.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        self._path.write_text(f"{content}\n", encoding="utf-8")
