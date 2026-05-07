"""External service integrations for news, email, and scheduling."""

from briefing_bot.services.email_service import EmailServiceProtocol, SMTPEmailService
from briefing_bot.services.news_service import (
    AgnoWebSearchNewsService,
    CompositeNewsService,
    NewsAPIService,
    NewsServiceProtocol,
)
from briefing_bot.services.scheduler_service import (
    BriefingScheduler,
    MessageSenderProtocol,
)

__all__ = [
    "AgnoWebSearchNewsService",
    "BriefingScheduler",
    "CompositeNewsService",
    "EmailServiceProtocol",
    "MessageSenderProtocol",
    "NewsAPIService",
    "NewsServiceProtocol",
    "SMTPEmailService",
]
