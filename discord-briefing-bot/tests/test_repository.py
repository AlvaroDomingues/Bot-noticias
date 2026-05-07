"""Tests for user preference persistence."""

from pathlib import Path

from briefing_bot.models import TopicPreference, UserPreferences
from briefing_bot.repositories import JsonUserPreferencesRepository


async def test_json_repository_saves_lists_and_deletes() -> None:
    """Ensure the JSON repository persists and removes preferences."""
    path = _runtime_path("repository-preferences.json")
    path.unlink(missing_ok=True)
    repository = JsonUserPreferencesRepository(path)
    preferences = UserPreferences(
        user_id=42,
        topics=[TopicPreference(name="economia", keywords=["juros"])],
        email="user@example.com",
        discord_channel_id=987654,
    )

    await repository.save(preferences)
    saved = await repository.get(42)
    all_preferences = await repository.list_all()
    await repository.delete(42)

    assert saved == preferences
    assert all_preferences == [preferences]
    assert await repository.get(42) is None
    path.unlink(missing_ok=True)


def _runtime_path(filename: str) -> Path:
    """Build a test runtime file path inside the repository.

    Args:
        filename: Runtime filename.

    Returns:
        Writable path for test artifacts.
    """
    directory = Path(__file__).parent / ".runtime"
    directory.mkdir(exist_ok=True)
    return directory / filename
