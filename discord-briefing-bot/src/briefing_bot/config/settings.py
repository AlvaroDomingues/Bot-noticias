"""Environment-backed application settings."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    discord_bot_token: str
    discord_webhook_url: str
    openai_api_key: str
    agno_model_id: str
    news_api_key: str
    news_language: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_from: str
    default_briefing_hour: int
    default_briefing_minute: int
    default_timezone: str
    preferences_file: Path


def load_settings() -> Settings:
    """Load settings from `.env` and process environment variables.

    Returns:
        The fully parsed application settings.
    """
    load_dotenv()
    return Settings(
        discord_bot_token=_env("DISCORD_BOT_TOKEN"),
        discord_webhook_url=_env("DISCORD_WEBHOOK_URL"),
        openai_api_key=_env("OPENAI_API_KEY"),
        agno_model_id=_env("AGNO_MODEL_ID", "gpt-4.1-mini"),
        news_api_key=_env("NEWS_API_KEY"),
        news_language=_env("NEWS_LANGUAGE", "pt"),
        smtp_host=_env("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=_env_int("SMTP_PORT", 587),
        smtp_user=_env("SMTP_USER"),
        smtp_password=_env("SMTP_PASSWORD"),
        email_from=_env("EMAIL_FROM"),
        default_briefing_hour=_env_int("DEFAULT_BRIEFING_HOUR", 7),
        default_briefing_minute=_env_int("DEFAULT_BRIEFING_MINUTE", 0),
        default_timezone=_env("DEFAULT_TIMEZONE", "America/Sao_Paulo"),
        preferences_file=Path(_env("PREFERENCES_FILE", "data/user_preferences.json")),
    )


def _env(name: str, default: str = "") -> str:
    """Read a string environment variable.

    Args:
        name: Environment variable name.
        default: Value used when the variable is missing.

    Returns:
        The configured or default string.
    """
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable.

    Args:
        name: Environment variable name.
        default: Value used when parsing fails.

    Returns:
        The parsed integer or the provided default.
    """
    value = os.getenv(name)
    return default if value is None else _parse_int(value, default)


def _parse_int(value: str, default: int) -> int:
    """Parse an integer while preserving a safe default.

    Args:
        value: Raw string to parse.
        default: Fallback value when parsing fails.

    Returns:
        The parsed integer or default.
    """
    try:
        return int(value)
    except ValueError:
        return default
