"""Tests for briefing delivery orchestration."""

import pytest

from briefing_bot.models import Briefing, TopicPreference, UserPreferences
from briefing_bot.services.scheduler_service import BriefingScheduler


class FakeRepository:
    """Repository fake with one saved user."""

    def __init__(self, preferences: UserPreferences) -> None:
        self._preferences = preferences

    async def get(self, user_id: int) -> UserPreferences | None:
        """Return preferences for the configured user."""
        return self._preferences if user_id == self._preferences.user_id else None

    async def list_all(self) -> list[UserPreferences]:
        """Return all fake preferences."""
        return [self._preferences]


class FakeNewsService:
    """News service fake with deterministic empty results."""

    async def fetch_news(
        self, 
        _topic: str,
        _keywords: list[str],
        _max_results: int,
    ) -> list:
        """Return no articles."""
        return []


class FakeBriefingAgent:
    """Briefing agent fake with deterministic content."""

    async def generate_briefing(
        self,
        preferences: UserPreferences,
        _articles: dict,
    ) -> Briefing:
        """Return a ready briefing."""
        return Briefing(user_id=preferences.user_id, content="Briefing pronto")


class FailingMessageSender:
    """Discord sender fake that always fails."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def send_message(self, channel_id: int, content: str) -> None:
        """Record the call and fail."""
        self.calls.append((channel_id, content))
        raise RuntimeError("discord offline")


class FakeEmailService:
    """Email service fake that records messages."""

    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.messages: list[tuple[str, str, str]] = []

    async def send_email(self, to_address: str, subject: str, body: str) -> None:
        """Record the email or fail when configured."""
        self.messages.append((to_address, subject, body))
        if self.should_fail:
            raise RuntimeError("smtp offline")


async def test_email_is_sent_when_discord_delivery_fails() -> None:
    """Ensure Discord failures do not block email delivery."""
    preferences = _preferences()
    email_service = FakeEmailService()
    message_sender = FailingMessageSender()
    scheduler = BriefingScheduler(
        FakeRepository(preferences),
        FakeNewsService(),
        FakeBriefingAgent(),
        email_service,
        message_sender,
    )

    briefing = await scheduler.run_briefing_for_user(preferences.user_id)

    assert briefing is not None
    assert message_sender.calls == [(123456, "Briefing pronto")] * 3
    assert len(email_service.messages) == 1
    assert email_service.messages[0][0] == "user@example.com"
    assert email_service.messages[0][2] == "Briefing pronto"


async def test_delivery_raises_when_discord_and_email_fail() -> None:
    """Ensure total delivery failure still surfaces to callers."""
    preferences = _preferences()
    scheduler = BriefingScheduler(
        FakeRepository(preferences),
        FakeNewsService(),
        FakeBriefingAgent(),
        FakeEmailService(should_fail=True),
        FailingMessageSender(),
    )

    with pytest.raises(RuntimeError, match="All briefing delivery channels failed"):
        await scheduler.run_briefing_for_user(preferences.user_id)


def _preferences() -> UserPreferences:
    """Build shared fake user preferences."""
    return UserPreferences(
        user_id=42,
        topics=[TopicPreference(name="tecnologia")],
        email="user@example.com",
        discord_channel_id=123456,
    )
