"""Tests for onboarding conversation flow."""

from pathlib import Path
from typing import Any

from briefing_bot.agents import OnboardingAgent
from briefing_bot.bot import ConversationManager
from briefing_bot.repositories import JsonUserPreferencesRepository


class FailingAgnoAgent:
    """Agno-like fake that forces local parser fallbacks."""

    async def arun(self, *_args: Any, **_kwargs: Any) -> Any:
        """Raise to simulate an unavailable LLM."""
        raise RuntimeError("offline")


async def test_conversation_collects_and_saves_preferences() -> None:
    """Ensure onboarding completes and persists the expected preferences."""
    path = _runtime_path("conversation-preferences.json")
    path.unlink(missing_ok=True)
    repository = JsonUserPreferencesRepository(path)
    agent = OnboardingAgent("fake-model", agent=FailingAgnoAgent())
    manager = ConversationManager(agent, repository, "America/Sao_Paulo", 7, 0)

    manager.start(42)
    await manager.handle_message(42, "tecnologia, economia")
    await manager.handle_message(42, "IA, Python")
    await manager.handle_message(42, "juros, inflação")
    await manager.handle_message(42, "3")
    await manager.handle_message(42, "User@Example.com")
    await manager.handle_message(42, "<#1234567890>")
    await manager.handle_message(42, "8:30")
    reply = await manager.handle_message(42, "sim")
    saved = await repository.get(42)

    assert reply.completed is True
    assert saved is not None
    assert saved.max_news_per_topic == 3
    assert saved.discord_channel_id == 1234567890
    assert saved.briefing_hour == 8
    assert saved.briefing_minute == 30
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
