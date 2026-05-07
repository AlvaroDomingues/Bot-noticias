"""News fetching abstractions and concrete integrations."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from briefing_bot.models import NewsArticle

logger = logging.getLogger(__name__)


class NewsServiceProtocol(Protocol):
    """Small contract for fetching topic-specific news articles."""

    async def fetch_news(
        self,
        topic: str,
        keywords: list[str],
        max_results: int,
    ) -> list[NewsArticle]:
        """Fetch recent news for a topic.

        Args:
            topic: Main topic configured by the user.
            keywords: Priority keywords for the topic.
            max_results: Maximum number of articles to return.

        Returns:
            Normalized news articles.
        """


class NewsArticleCollection(BaseModel):
    """Structured output model for Agno web-search fallback results."""

    articles: list[NewsArticle] = Field(default_factory=list)


class NewsAPIService:
    """NewsAPI-backed implementation of the news service contract."""

    def __init__(self, api_key: str, language: str = "pt") -> None:
        """Create a NewsAPI service.

        Args:
            api_key: NewsAPI API key.
            language: ISO language filter used by NewsAPI.
        """
        from newsapi import NewsApiClient

        self._client = NewsApiClient(api_key=api_key)
        self._language = language

    async def fetch_news(
        self,
        topic: str,
        keywords: list[str],
        max_results: int,
    ) -> list[NewsArticle]:
        """Fetch recent news for a topic.

        Args:
            topic: Main topic configured by the user.
            keywords: Priority keywords for the topic.
            max_results: Maximum number of articles to return.

        Returns:
            Normalized news articles.
        """
        query = _build_query(topic, keywords)
        payload = await asyncio.to_thread(self._request_news, query, max_results)
        articles = payload.get("articles", [])
        return [_map_newsapi_article(item) for item in articles][:max_results]

    def _request_news(self, query: str, max_results: int) -> dict[str, Any]:
        """Request raw article payload from NewsAPI.

        Args:
            query: NewsAPI search expression.
            max_results: Maximum number of articles to request.

        Returns:
            Raw NewsAPI response payload.
        """
        return self._client.get_everything(
            q=query,
            language=self._language,
            page_size=max_results,
            sort_by="publishedAt",
        )


class AgnoWebSearchNewsService:
    """Agno web-search fallback implementation for news retrieval."""

    def __init__(self, model_id: str) -> None:
        """Create the Agno fallback news service.

        Args:
            model_id: OpenAI model id used by Agno.
        """
        self._agent = self._create_agent(model_id)

    async def fetch_news(
        self,
        topic: str,
        keywords: list[str],
        max_results: int,
    ) -> list[NewsArticle]:
        """Fetch recent news through Agno web search.

        Args:
            topic: Main topic configured by the user.
            keywords: Priority keywords for the topic.
            max_results: Maximum number of articles to return.

        Returns:
            Normalized news articles.
        """
        prompt = _build_web_search_prompt(topic, keywords, max_results)
        response = await self._agent.arun(prompt, output_schema=NewsArticleCollection)
        content = response.content
        collection = _validate_article_collection(content)
        return collection.articles[:max_results]

    def _create_agent(self, model_id: str) -> Any:
        """Create the Agno agent used for web-search fallback.

        Args:
            model_id: OpenAI model id used by Agno.

        Returns:
            Configured Agno agent.
        """
        from agno.agent import Agent
        from agno.models.openai import OpenAIResponses
        from agno.tools.websearch import WebSearchTools

        return Agent(
            model=OpenAIResponses(id=model_id),
            tools=[WebSearchTools(enable_search=False, enable_news=True)],
            instructions=[_WEB_SEARCH_INSTRUCTIONS],
        )


class CompositeNewsService:
    """News service that falls back when the primary provider fails."""

    def __init__(
        self,
        primary: NewsServiceProtocol,
        fallback: NewsServiceProtocol,
    ) -> None:
        """Create a composite news service.

        Args:
            primary: Preferred news provider.
            fallback: Provider used when the primary fails or returns nothing.
        """
        self._primary = primary
        self._fallback = fallback

    async def fetch_news(
        self,
        topic: str,
        keywords: list[str],
        max_results: int,
    ) -> list[NewsArticle]:
        """Fetch news with fallback support.

        Args:
            topic: Main topic configured by the user.
            keywords: Priority keywords for the topic.
            max_results: Maximum number of articles to return.

        Returns:
            Normalized news articles.
        """
        articles = await self._fetch_primary(topic, keywords, max_results)
        return articles or await self._fallback.fetch_news(topic, keywords, max_results)

    async def _fetch_primary(
        self,
        topic: str,
        keywords: list[str],
        max_results: int,
    ) -> list[NewsArticle]:
        """Fetch from the primary provider without raising upstream errors.

        Args:
            topic: Main topic configured by the user.
            keywords: Priority keywords for the topic.
            max_results: Maximum number of articles to return.

        Returns:
            Primary provider articles or an empty list.
        """
        try:
            return await self._primary.fetch_news(topic, keywords, max_results)
        except Exception as error:
            logger.warning("primary news provider failed: %s", error)
            return []


def _build_query(topic: str, keywords: list[str]) -> str:
    """Build a provider query from topic and keywords.

    Args:
        topic: Main topic configured by the user.
        keywords: Priority keywords for the topic.

    Returns:
        Provider-compatible search expression.
    """
    if not keywords:
        return topic
    keyword_query = " OR ".join(f'"{keyword}"' for keyword in keywords)
    return f'"{topic}" AND ({keyword_query})'


def _map_newsapi_article(payload: dict[str, Any]) -> NewsArticle:
    """Map a raw NewsAPI article into the domain model.

    Args:
        payload: Raw NewsAPI article payload.

    Returns:
        Normalized news article.
    """
    source = payload.get("source") or {}
    return NewsArticle(
        title=payload.get("title") or "Untitled",
        summary=payload.get("description") or payload.get("content") or "",
        source=source.get("name") or "NewsAPI",
        url=payload.get("url"),
        published_at=_parse_datetime(payload.get("publishedAt")),
    )


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse NewsAPI ISO timestamps safely.

    Args:
        value: Raw datetime value from NewsAPI.

    Returns:
        Parsed datetime or None.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _validate_article_collection(content: Any) -> NewsArticleCollection:
    """Validate Agno response content as an article collection.

    Args:
        content: Raw Agno response content.

    Returns:
        Validated article collection.
    """
    if isinstance(content, NewsArticleCollection):
        return content
    return NewsArticleCollection.model_validate(content)


def _build_web_search_prompt(
    topic: str,
    keywords: list[str],
    max_results: int,
) -> str:
    """Build the prompt for Agno web-search fallback.

    Args:
        topic: Main topic configured by the user.
        keywords: Priority keywords for the topic.
        max_results: Maximum number of articles to return.

    Returns:
        Prompt asking Agno to search recent news.
    """
    keyword_text = ", ".join(keywords) if keywords else "no keywords"
    return (
        f"Find up to {max_results} recent news articles about '{topic}'. "
        f"Prioritize these keywords: {keyword_text}. "
        "Return title, 1-line summary, source, URL, and publish date when known."
    )


_WEB_SEARCH_INSTRUCTIONS = (
    "Use news search first. Return only real, recent articles from reliable sources. "
    "Never invent URLs or sources."
)
