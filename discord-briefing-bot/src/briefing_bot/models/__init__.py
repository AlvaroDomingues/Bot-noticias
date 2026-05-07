"""Domain models for preferences, news articles, and briefings."""

from briefing_bot.models.briefing import Briefing, BriefingSection, NewsArticle
from briefing_bot.models.user_preferences import TopicPreference, UserPreferences

__all__ = [
    "Briefing",
    "BriefingSection",
    "NewsArticle",
    "TopicPreference",
    "UserPreferences",
]
