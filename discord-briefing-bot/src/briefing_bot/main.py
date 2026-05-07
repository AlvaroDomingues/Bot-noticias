"""Application composition root for the Discord briefing bot."""

import asyncio
import hashlib
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from tempfile import gettempdir
from typing import BinaryIO

from briefing_bot.agents import BriefingAgent, OnboardingAgent
from briefing_bot.bot import ConversationManager, DiscordBriefingBot
from briefing_bot.config import Settings, load_settings
from briefing_bot.repositories import JsonUserPreferencesRepository
from briefing_bot.services import (
    AgnoWebSearchNewsService,
    BriefingScheduler,
    CompositeNewsService,
    NewsAPIService,
    NewsServiceProtocol,
    SMTPEmailService,
)


def run() -> None:
    """Run the bot from a synchronous console entrypoint."""
    asyncio.run(main())


async def main() -> None:
    """Load dependencies, schedule jobs, and start Discord."""
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    _validate_required_settings(settings)
    with _single_instance(settings):
        repository = JsonUserPreferencesRepository(settings.preferences_file)
        news_service = _build_news_service(settings)
        email_service = _build_email_service(settings)
        onboarding_agent = OnboardingAgent(settings.agno_model_id)
        briefing_agent = BriefingAgent(settings.agno_model_id)
        conversation = _build_conversation(settings, repository, onboarding_agent)
        discord_bot = DiscordBriefingBot(settings, conversation, repository)
        scheduler = BriefingScheduler(
            repository,
            news_service,
            briefing_agent,
            email_service,
            discord_bot,
        )
        await _start_application(discord_bot, scheduler)


@contextmanager
def _single_instance(settings: Settings) -> Iterator[None]:
    lock_path = os.path.join(
        gettempdir(),
        f"discord-briefing-bot-{_token_hash(settings.discord_bot_token)}.lock",
    )
    lock_file = open(lock_path, "a+b")
    try:
        _lock_file(lock_file)
        try:
            yield
        finally:
            _unlock_file(lock_file)
    finally:
        lock_file.close()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _lock_file(lock_file: BinaryIO) -> None:
    lock_file.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError(_already_running_message()) from exc
        return

    import fcntl

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        raise RuntimeError(_already_running_message()) from exc


def _unlock_file(lock_file: BinaryIO) -> None:
    lock_file.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _already_running_message() -> str:
    return "Another briefing bot instance is already running for this Discord token."


def _validate_required_settings(settings: Settings) -> None:
    """Validate settings required before the bot can boot.

    Args:
        settings: Loaded application settings.
    """
    missing = _missing_required_settings(settings)
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing required environment variables: {joined}")


def _missing_required_settings(settings: Settings) -> list[str]:
    """Collect missing required setting names.

    Args:
        settings: Loaded application settings.

    Returns:
        Required environment variable names with empty values.
    """
    values = {
        "DISCORD_BOT_TOKEN": settings.discord_bot_token,
        "OPENAI_API_KEY": settings.openai_api_key,
        "SMTP_USER": settings.smtp_user,
        "SMTP_PASSWORD": settings.smtp_password,
        "EMAIL_FROM": settings.email_from,
    }
    return [name for name, value in values.items() if not value]


def _build_news_service(settings: Settings) -> NewsServiceProtocol:
    """Build the news service with NewsAPI plus Agno fallback.

    Args:
        settings: Loaded application settings.

    Returns:
        News service implementation.
    """
    fallback = AgnoWebSearchNewsService(settings.agno_model_id)
    if not settings.news_api_key:
        return fallback
    primary = NewsAPIService(settings.news_api_key, settings.news_language)
    return CompositeNewsService(primary, fallback)


def _build_email_service(settings: Settings) -> SMTPEmailService:
    """Build the SMTP email service.

    Args:
        settings: Loaded application settings.

    Returns:
        SMTP email service.
    """
    return SMTPEmailService(
        settings.smtp_host,
        settings.smtp_port,
        settings.smtp_user,
        settings.smtp_password,
        settings.email_from,
    )


def _build_conversation(
    settings: Settings,
    repository: JsonUserPreferencesRepository,
    onboarding_agent: OnboardingAgent,
) -> ConversationManager:
    """Build the onboarding conversation manager.

    Args:
        settings: Loaded application settings.
        repository: Preference repository.
        onboarding_agent: Agent that parses onboarding answers.

    Returns:
        Conversation manager.
    """
    return ConversationManager(
        onboarding_agent,
        repository,
        settings.default_timezone,
        settings.default_briefing_hour,
        settings.default_briefing_minute,
    )


async def _start_application(
    discord_bot: DiscordBriefingBot,
    scheduler: BriefingScheduler,
) -> None:
    """Start scheduler and Discord client.

    Args:
        discord_bot: Discord bot facade.
        scheduler: Briefing scheduler service.
    """
    discord_bot.set_scheduler(scheduler)
    scheduler.start()
    await scheduler.schedule_existing_users()
    try:
        await discord_bot.start()
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    run()
