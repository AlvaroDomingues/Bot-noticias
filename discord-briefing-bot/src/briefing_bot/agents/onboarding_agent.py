"""Agno agent that extracts onboarding preferences from natural language."""

import logging
import re
from typing import TypeVar

from pydantic import BaseModel, Field

from briefing_bot.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class TopicExtraction(BaseModel):
    """Structured topics extracted from a user message."""

    topics: list[str] = Field(default_factory=list)


class KeywordExtraction(BaseModel):
    """Structured keywords extracted from a user message."""

    keywords: list[str] = Field(default_factory=list)


class MaxResultsExtraction(BaseModel):
    """Structured maximum article count extracted from a user message."""

    max_results: int | None = Field(default=None, ge=1, le=20)


class EmailExtraction(BaseModel):
    """Structured email address extracted from a user message."""

    email: str | None = None


class ChannelExtraction(BaseModel):
    """Structured Discord channel id extracted from a user message."""

    channel_id: int | None = None


class ConfirmationExtraction(BaseModel):
    """Structured confirmation intent extracted from a user message."""

    confirmed: bool = False


class OnboardingAgent(BaseAgent):
    """Agno-powered parser for onboarding conversation answers."""

    def __init__(self, model_id: str, agent: object | None = None) -> None:
        """Create the onboarding agent.

        Args:
            model_id: OpenAI model id used by Agno.
            agent: Optional prebuilt agent, useful for tests.
        """
        super().__init__(model_id, _INSTRUCTIONS, agent)

    @property
    def agent_name(self) -> str:
        """Return the human-readable agent name.

        Returns:
            Agent name used in logs and debugging.
        """
        return "onboarding"

    async def extract_topics(self, message: str) -> list[str]:
        """Extract topic names from free-form text.

        Args:
            message: User response.

        Returns:
            Topic names found in the response.
        """
        result = await self._safe_extract(_topic_prompt(message), TopicExtraction)
        topics = result.topics if result else _split_items(message)
        return _clean_items(topics)

    async def extract_keywords(self, topic: str, message: str) -> list[str]:
        """Extract priority keywords for one topic.

        Args:
            topic: Topic currently being configured.
            message: User response.

        Returns:
            Priority keywords found in the response.
        """
        result = await self._safe_extract(
            _keyword_prompt(topic, message), KeywordExtraction
        )
        keywords = result.keywords if result else _split_items(message)
        return _clean_items(keywords)

    async def extract_max_results(self, message: str, default: int = 5) -> int:
        """Extract the maximum number of articles per topic.

        Args:
            message: User response.
            default: Value used when the response is empty or unclear.

        Returns:
            Article count between 1 and 20.
        """
        result = await self._safe_extract(
            _max_results_prompt(message), MaxResultsExtraction
        )
        value = result.max_results if result else _first_int(message)
        return default if value is None else min(max(value, 1), 20)

    async def extract_email(self, message: str) -> str | None:
        """Extract an email address from free-form text.

        Args:
            message: User response.

        Returns:
            Email address or None when not found.
        """
        result = await self._safe_extract(_email_prompt(message), EmailExtraction)
        return result.email if result and result.email else _find_email(message)

    async def extract_channel_id(self, message: str) -> int | None:
        """Extract a Discord channel id from free-form text.

        Args:
            message: User response.

        Returns:
            Discord channel id or None when not found.
        """
        result = await self._safe_extract(_channel_prompt(message), ChannelExtraction)
        return (
            result.channel_id
            if result and result.channel_id
            else _find_channel_id(message)
        )

    async def extract_confirmation(self, message: str) -> bool:
        """Extract a yes/no confirmation from free-form text.

        Args:
            message: User response.

        Returns:
            True when the user confirmed the preferences.
        """
        result = await self._safe_extract(
            _confirmation_prompt(message), ConfirmationExtraction
        )
        return result.confirmed if result else _looks_affirmative(message)

    async def _safe_extract(self, prompt: str, schema: type[T]) -> T | None:
        """Run structured extraction and fall back on local parsing.

        Args:
            prompt: Prompt sent to the Agno agent.
            schema: Pydantic schema expected from the response.

        Returns:
            Structured extraction result or None on failure.
        """
        try:
            return await self._run_structured(prompt, schema)
        except Exception as error:
            logger.info("onboarding extraction fallback used: %s", error)
            return None


def _topic_prompt(message: str) -> str:
    """Build a prompt for topic extraction.

    Args:
        message: User response.

    Returns:
        Prompt for the onboarding agent.
    """
    return f"Extract only news topics from this answer: {message}"


def _keyword_prompt(topic: str, message: str) -> str:
    """Build a prompt for keyword extraction.

    Args:
        topic: Topic currently being configured.
        message: User response.

    Returns:
        Prompt for the onboarding agent.
    """
    return f"Extract only priority keywords for topic '{topic}': {message}"


def _max_results_prompt(message: str) -> str:
    """Build a prompt for maximum-results extraction.

    Args:
        message: User response.

    Returns:
        Prompt for the onboarding agent.
    """
    return f"Extract the requested maximum number of news per topic: {message}"


def _email_prompt(message: str) -> str:
    """Build a prompt for email extraction.

    Args:
        message: User response.

    Returns:
        Prompt for the onboarding agent.
    """
    return f"Extract the destination email address from this answer: {message}"


def _channel_prompt(message: str) -> str:
    """Build a prompt for Discord channel extraction.

    Args:
        message: User response.

    Returns:
        Prompt for the onboarding agent.
    """
    return f"Extract the Discord channel numeric id from this answer: {message}"


def _confirmation_prompt(message: str) -> str:
    """Build a prompt for confirmation extraction.

    Args:
        message: User response.

    Returns:
        Prompt for the onboarding agent.
    """
    return f"Does this answer confirm the preferences? Answer as boolean: {message}"


def _split_items(message: str) -> list[str]:
    """Split a free-form list into individual items.

    Args:
        message: User response.

    Returns:
        Candidate list items.
    """
    return re.split(r",|;|\n|\s+e\s+", message, flags=re.IGNORECASE)


def _clean_items(items: list[str]) -> list[str]:
    """Clean and deduplicate list items.

    Args:
        items: Raw extracted items.

    Returns:
        Cleaned unique items.
    """
    cleaned = [item.strip(" .:-").strip() for item in items if item.strip(" .:-")]
    return list(dict.fromkeys(cleaned))


def _first_int(message: str) -> int | None:
    """Find the first integer in a message.

    Args:
        message: User response.

    Returns:
        First integer or None.
    """
    match = re.search(r"\d+", message)
    return int(match.group()) if match else None


def _find_email(message: str) -> str | None:
    """Find an email address in a message.

    Args:
        message: User response.

    Returns:
        Email address or None.
    """
    match = re.search(r"[^@\s]+@[^@\s]+\.[^@\s]+", message)
    return match.group().lower() if match else None


def _find_channel_id(message: str) -> int | None:
    """Find a Discord channel id in a message.

    Args:
        message: User response.

    Returns:
        Channel id or None.
    """
    match = re.search(r"<#(\d+)>|(\d{5,})", message)
    value = next(group for group in match.groups() if group) if match else None
    return int(value) if value else None


def _looks_affirmative(message: str) -> bool:
    """Check whether a message looks like an affirmative answer.

    Args:
        message: User response.

    Returns:
        True when the answer appears affirmative.
    """
    normalized = message.strip().lower()
    return normalized in {"s", "sim", "ok", "confirmo", "confirmar", "yes", "y"}


_INSTRUCTIONS = [
    "Extract user preferences from natural language.",
    "Return concise structured data only.",
    "Do not invent missing values.",
]
