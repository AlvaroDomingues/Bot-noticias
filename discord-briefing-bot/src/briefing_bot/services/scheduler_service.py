"""Daily scheduling and briefing delivery orchestration."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from briefing_bot.agents import BriefingAgent
from briefing_bot.models import Briefing, NewsArticle, TopicPreference, UserPreferences
from briefing_bot.repositories import UserPreferencesRepositoryProtocol
from briefing_bot.services.email_service import EmailServiceProtocol
from briefing_bot.services.news_service import NewsServiceProtocol
from briefing_bot.services.retry import retry_async

logger = logging.getLogger(__name__)


class MessageSenderProtocol(Protocol):
    """Small contract for sending Discord messages."""

    async def send_message(self, channel_id: int, content: str) -> None:
        """Send a message to a Discord channel.

        Args:
            channel_id: Target Discord channel id.
            content: Message content to send.
        """


class BriefingScheduler:
    """Schedules and runs briefing delivery jobs."""

    def __init__(
        self,
        repository: UserPreferencesRepositoryProtocol,
        news_service: NewsServiceProtocol,
        briefing_agent: BriefingAgent,
        email_service: EmailServiceProtocol,
        message_sender: MessageSenderProtocol,
    ) -> None:
        """Create the scheduler service.

        Args:
            repository: Repository with user preferences.
            news_service: News provider abstraction.
            briefing_agent: Agent that generates final briefing text.
            email_service: Email delivery service.
            message_sender: Discord message sender abstraction.
        """
        self._repository = repository
        self._news_service = news_service
        self._briefing_agent = briefing_agent
        self._email_service = email_service
        self._message_sender = message_sender
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        """Start APScheduler when it is not already running."""
        if not self._scheduler.running:
            self._scheduler.start()

    def shutdown(self) -> None:
        """Stop APScheduler without waiting for new jobs."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    async def schedule_existing_users(self) -> None:
        """Schedule daily jobs for all saved users."""
        preferences_list = await self._repository.list_all()
        for preferences in preferences_list:
            self.schedule_user(preferences)

    def schedule_user(self, preferences: UserPreferences) -> None:
        """Schedule or replace the daily job for one user.

        Args:
            preferences: User preferences that contain schedule metadata.
        """
        trigger = _cron_trigger(preferences)
        self._scheduler.add_job(
            self.run_briefing_for_user,
            trigger=trigger,
            args=[preferences.user_id],
            id=_job_id(preferences.user_id),
            replace_existing=True,
        )

    def remove_user(self, user_id: int) -> None:
        """Remove a scheduled job for one user.

        Args:
            user_id: Discord user id.
        """
        job = self._scheduler.get_job(_job_id(user_id))
        if job is not None:
            self._scheduler.remove_job(job.id)

    async def run_briefing_for_user(self, user_id: int) -> Briefing | None:
        """Generate and deliver one briefing immediately.

        Args:
            user_id: Discord user id.

        Returns:
            Delivered briefing or None when the user has no preferences.
        """
        preferences = await self._repository.get(user_id)
        if preferences is None:
            return None
        briefing = await self._build_briefing(preferences)
        await self._deliver_briefing(preferences, briefing)
        return briefing

    async def _build_briefing(self, preferences: UserPreferences) -> Briefing:
        """Fetch articles and generate the briefing content.

        Args:
            preferences: User preferences.

        Returns:
            Generated briefing.
        """
        articles = await self._fetch_all_topics(preferences)
        operation = _briefing_operation(self._briefing_agent, preferences, articles)
        return await retry_async(operation, operation_name="briefing generation")

    async def _fetch_all_topics(
        self,
        preferences: UserPreferences,
    ) -> dict[str, list[NewsArticle]]:
        """Fetch articles for every configured topic.

        Args:
            preferences: User preferences.

        Returns:
            Articles grouped by topic name.
        """
        tasks = [
            self._fetch_topic(topic, preferences.max_news_per_topic)
            for topic in preferences.topics
        ]
        results = await _gather_articles(tasks)
        return {
            topic.name: articles
            for topic, articles in zip(preferences.topics, results, strict=True)
        }

    async def _fetch_topic(
        self,
        topic: TopicPreference,
        max_results: int,
    ) -> list[NewsArticle]:
        """Fetch articles for one topic with retry.

        Args:
            topic: Topic preference.
            max_results: Maximum article count.

        Returns:
            Fetched articles.
        """
        operation = _news_operation(self._news_service, topic, max_results)
        return await retry_async(operation, operation_name=f"news fetch: {topic.name}")

    async def _deliver_briefing(
        self,
        preferences: UserPreferences,
        briefing: Briefing,
    ) -> None:
        """Deliver a briefing to Discord and email.

        Args:
            preferences: User delivery preferences.
            briefing: Generated briefing.
        """
        results = await asyncio.gather(
            self._send_discord(preferences, briefing.content),
            self._send_email(preferences, briefing.content),
            return_exceptions=True,
        )
        _handle_delivery_results(results)

    async def _send_discord(self, preferences: UserPreferences, content: str) -> None:
        """Send briefing content to Discord with retry.

        Args:
            preferences: User delivery preferences.
            content: Briefing content.
        """
        operation = _discord_operation(self._message_sender, preferences, content)
        await retry_async(operation, operation_name="discord delivery")

    async def _send_email(self, preferences: UserPreferences, content: str) -> None:
        """Send briefing content by email with retry.

        Args:
            preferences: User delivery preferences.
            content: Briefing content.
        """
        subject = _email_subject(preferences)
        operation = _email_operation(self._email_service, preferences, subject, content)
        await retry_async(operation, operation_name="email delivery")


def _briefing_operation(
    agent: BriefingAgent,
    preferences: UserPreferences,
    articles: dict[str, list[NewsArticle]],
) -> Callable[[], Awaitable[Briefing]]:
    """Create a zero-argument briefing generation operation.

    Args:
        agent: Briefing generation agent.
        preferences: User preferences.
        articles: Articles grouped by topic.

    Returns:
        Async operation suitable for retry.
    """
    return lambda: agent.generate_briefing(preferences, articles)


def _news_operation(
    service: NewsServiceProtocol,
    topic: TopicPreference,
    max_results: int,
) -> Callable[[], Awaitable[list[NewsArticle]]]:
    """Create a zero-argument news fetching operation.

    Args:
        service: News provider abstraction.
        topic: Topic preference.
        max_results: Maximum article count.

    Returns:
        Async operation suitable for retry.
    """
    return lambda: service.fetch_news(topic.name, topic.keywords, max_results)


def _discord_operation(
    sender: MessageSenderProtocol,
    preferences: UserPreferences,
    content: str,
) -> Callable[[], Awaitable[None]]:
    """Create a zero-argument Discord delivery operation.

    Args:
        sender: Discord message sender abstraction.
        preferences: User delivery preferences.
        content: Briefing content.

    Returns:
        Async operation suitable for retry.
    """
    return lambda: sender.send_message(preferences.discord_channel_id, content)


def _email_operation(
    service: EmailServiceProtocol,
    preferences: UserPreferences,
    subject: str,
    content: str,
) -> Callable[[], Awaitable[None]]:
    """Create a zero-argument email delivery operation.

    Args:
        service: Email delivery service.
        preferences: User delivery preferences.
        subject: Email subject.
        content: Briefing content.

    Returns:
        Async operation suitable for retry.
    """
    return lambda: service.send_email(preferences.email, subject, content)


def _handle_delivery_results(results: list[object]) -> None:
    """Log partial delivery failures and raise only when all channels failed.

    Args:
        results: Delivery results from Discord and email, in that order.
    """
    failures = [
        (channel, result)
        for channel, result in zip(("discord", "email"), results, strict=True)
        if isinstance(result, Exception)
    ]
    for channel, failure in failures:
        logger.warning("%s delivery failed: %s", channel, failure)
    if len(failures) == len(results):
        msg = "All briefing delivery channels failed."
        raise RuntimeError(msg) from failures[0][1]


async def _gather_articles(
    tasks: list[Awaitable[list[NewsArticle]]],
) -> list[list[NewsArticle]]:
    """Gather topic article tasks concurrently.

    Args:
        tasks: Article fetching tasks.

    Returns:
        Article lists in task order.
    """
    return list(await asyncio.gather(*tasks))


def _cron_trigger(preferences: UserPreferences) -> CronTrigger:
    """Build a cron trigger from user preferences.

    Args:
        preferences: User preferences with schedule metadata.

    Returns:
        Cron trigger in the user's timezone.
    """
    timezone = pytz.timezone(preferences.timezone)
    return CronTrigger(
        hour=preferences.briefing_hour,
        minute=preferences.briefing_minute,
        timezone=timezone,
    )


def _email_subject(preferences: UserPreferences) -> str:
    """Build the daily briefing email subject.

    Args:
        preferences: User delivery preferences.

    Returns:
        Email subject.
    """
    timezone = pytz.timezone(preferences.timezone)
    date_text = datetime.now(timezone).strftime("%d/%m/%Y")
    return f"Briefing diário - {date_text}"


def _job_id(user_id: int) -> str:
    """Build the APScheduler job id for one user.

    Args:
        user_id: Discord user id.

    Returns:
        Stable scheduler job id.
    """
    return f"briefing:{user_id}"
