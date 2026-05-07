"""Tests for briefing generation."""

from typing import Any

from briefing_bot.agents import BriefingAgent
from briefing_bot.models import NewsArticle, TopicPreference, UserPreferences


class FailingAgnoAgent:
    """Agno-like fake that forces deterministic local rendering."""

    async def arun(self, *_args: Any, **_kwargs: Any) -> Any:
        """Raise to simulate an unavailable LLM."""
        raise RuntimeError("offline")


async def test_briefing_agent_renders_local_fallback() -> None:
    """Ensure briefing generation still works when Agno is unavailable."""
    agent = BriefingAgent("fake-model", agent=FailingAgnoAgent())
    preferences = UserPreferences(
        user_id=42,
        topics=[TopicPreference(name="tecnologia", keywords=["IA"])],
        email="user@example.com",
        discord_channel_id=123456,
    )
    articles = {
        "tecnologia": [
            NewsArticle(
                title="Nova IA lançada", summary="Resumo curto.", source="Fonte"
            ),
        ],
    }

    briefing = await agent.generate_briefing(preferences, articles)

    assert "BRIEFING DIÁRIO" in briefing.content
    assert "Nova IA lançada" in briefing.content
