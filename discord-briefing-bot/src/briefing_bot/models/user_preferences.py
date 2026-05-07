"""Pydantic models representing user briefing preferences."""

import re
from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


class TopicPreference(BaseModel):
    """News topic and its prioritized keywords."""

    name: str = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Normalize topic names.

        Args:
            value: Raw topic name.

        Returns:
            Topic name without surrounding spaces.
        """
        return value.strip()

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        """Normalize keyword lists.

        Args:
            value: Raw keywords.

        Returns:
            Deduplicated keywords with surrounding spaces removed.
        """
        cleaned = [keyword.strip() for keyword in value if keyword.strip()]
        return list(dict.fromkeys(cleaned))


class UserPreferences(BaseModel):
    """Saved preferences that drive scheduled briefing delivery."""

    user_id: int
    topics: list[TopicPreference] = Field(min_length=1)
    max_news_per_topic: int = Field(default=5, ge=1, le=20)
    email: str
    discord_channel_id: int
    timezone: str = "America/Sao_Paulo"
    briefing_hour: int = Field(default=7, ge=0, le=23)
    briefing_minute: int = Field(default=0, ge=0, le=59)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        """Validate the configured delivery email.

        Args:
            value: Raw email address.

        Returns:
            Normalized email address.
        """
        normalized = value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(normalized):
            msg = "email must be a valid address"
            raise ValueError(msg)
        return normalized

    def summary_lines(self) -> list[str]:
        """Build human-readable preference lines.

        Returns:
            Lines suitable for Discord status messages.
        """
        topics = "; ".join(_topic_summary(topic) for topic in self.topics)
        schedule = f"{self.briefing_hour:02d}:{self.briefing_minute:02d}"
        return [
            f"Tópicos: {topics}",
            f"Máximo por tópico: {self.max_news_per_topic}",
            f"E-mail: {self.email}",
            f"Canal Discord: {self.discord_channel_id}",
            f"Horário: {schedule} ({self.timezone})",
        ]


def _topic_summary(topic: TopicPreference) -> str:
    """Build a compact topic summary with keywords.

    Args:
        topic: Topic preference to summarize.

    Returns:
        Topic summary with its configured keywords.
    """
    keywords = ", ".join(topic.keywords) or "sem palavras-chave"
    return f"{topic.name} ({keywords})"


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
