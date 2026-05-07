"""Persistence repositories used by the briefing bot."""

from briefing_bot.repositories.user_preferences_repository import (
    JsonUserPreferencesRepository,
    UserPreferencesRepositoryProtocol,
)

__all__ = ["JsonUserPreferencesRepository", "UserPreferencesRepositoryProtocol"]
