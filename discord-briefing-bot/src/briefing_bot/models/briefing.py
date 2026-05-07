"""Pydantic models for fetched news and generated briefings."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator


class NewsArticle(BaseModel):
    """A normalized news article fetched from an external source."""

    title: str = Field(min_length=1)
    summary: str = ""
    source: str = "Unknown"
    url: HttpUrl | None = None
    published_at: datetime | None = None

    @field_validator("title", "summary", "source")
    @classmethod
    def strip_text(cls, value: str) -> str:
        """Remove surrounding whitespace from textual fields.

        Args:
            value: Raw text.

        Returns:
            Text without surrounding whitespace.
        """
        return value.strip()


class BriefingSection(BaseModel):
    """Briefing content for one configured topic."""

    topic: str = Field(min_length=1)
    articles: list[NewsArticle] = Field(default_factory=list)


class Briefing(BaseModel):
    """Generated briefing ready for delivery."""

    user_id: int
    content: str = Field(min_length=1)
    sections: list[BriefingSection] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
