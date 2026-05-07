"""Tests for domain models."""

import pytest

from briefing_bot.models import TopicPreference, UserPreferences


def test_user_preferences_normalizes_email_and_keywords() -> None:
    """Ensure user preference fields are normalized."""
    preferences = UserPreferences(
        user_id=1,
        topics=[
            TopicPreference(name=" tecnologia ", keywords=[" IA ", "IA", "Python"])
        ],
        email="USER@Example.COM",
        discord_channel_id=123456,
    )

    assert preferences.email == "user@example.com"
    assert preferences.topics[0].name == "tecnologia"
    assert preferences.topics[0].keywords == ["IA", "Python"]


def test_user_preferences_rejects_invalid_email() -> None:
    """Ensure invalid email addresses are rejected."""
    with pytest.raises(ValueError, match="email"):
        UserPreferences(
            user_id=1,
            topics=[TopicPreference(name="tech")],
            email="not-an-email",
            discord_channel_id=123456,
        )
