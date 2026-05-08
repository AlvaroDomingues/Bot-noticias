"""State machine for Discord onboarding conversations."""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum, auto

from briefing_bot.agents import OnboardingAgent
from briefing_bot.models import TopicPreference, UserPreferences
from briefing_bot.repositories import UserPreferencesRepositoryProtocol


class OnboardingState(StrEnum):
    """States used by the onboarding conversation."""

    TOPICS = auto()
    KEYWORDS = auto()
    MAX_RESULTS = auto()
    EMAIL = auto()
    CHANNEL = auto()
    SCHEDULE = auto()
    CONFIRMATION = auto()


@dataclass(slots=True)
class ConversationReply:
    """Reply produced by the conversation manager."""

    message: str
    completed: bool = False
    preferences: UserPreferences | None = None


@dataclass(slots=True)
class OnboardingSession:
    """Mutable state for one user's onboarding session."""

    user_id: int
    state: OnboardingState = OnboardingState.TOPICS
    topics: list[str] = field(default_factory=list)
    keywords_by_topic: dict[str, list[str]] = field(default_factory=dict)
    current_topic_index: int = 0
    max_news_per_topic: int = 5
    email: str = ""
    discord_channel_id: int = 0
    briefing_hour: int = 7
    briefing_minute: int = 0


Handler = Callable[[OnboardingSession, str], Awaitable[ConversationReply]]


class ConversationManager:
    """Coordinates onboarding state transitions and persistence."""

    def __init__(
        self,
        onboarding_agent: OnboardingAgent,
        repository: UserPreferencesRepositoryProtocol,
        default_timezone: str,
        default_hour: int,
        default_minute: int,
    ) -> None:
        """Create the conversation manager.

        Args:
            onboarding_agent: Agent that parses natural-language answers.
            repository: Preference repository used when onboarding completes.
            default_timezone: Default timezone for scheduled jobs.
            default_hour: Default briefing hour.
            default_minute: Default briefing minute.
        """
        self._agent = onboarding_agent
        self._repository = repository
        self._default_timezone = default_timezone
        self._default_hour = default_hour
        self._default_minute = default_minute
        self._sessions: dict[int, OnboardingSession] = {}
        self._handlers = self._build_handlers()

    def start(self, user_id: int) -> str:
        """Start or restart onboarding for one user.

        Args:
            user_id: Discord user id.

        Returns:
            First onboarding question.
        """
        self._sessions[user_id] = self._new_session(user_id)
        return _topics_question()

    def has_active_session(self, user_id: int) -> bool:
        """Check whether a user is currently onboarding.

        Args:
            user_id: Discord user id.

        Returns:
            True when an onboarding session exists.
        """
        return user_id in self._sessions

    async def handle_message(self, user_id: int, message: str) -> ConversationReply:
        """Handle one onboarding answer.

        Args:
            user_id: Discord user id.
            message: User message content.

        Returns:
            Reply to send back to Discord.
        """
        session = self._sessions.get(user_id) or self._new_session(user_id)
        self._sessions[user_id] = session
        handler = self._handlers[session.state]
        return await handler(session, message)

    def _new_session(self, user_id: int) -> OnboardingSession:
        """Build a new onboarding session using configured defaults.

        Args:
            user_id: Discord user id.

        Returns:
            Fresh onboarding session.
        """
        return OnboardingSession(
            user_id=user_id,
            briefing_hour=self._default_hour,
            briefing_minute=self._default_minute,
        )

    def _build_handlers(self) -> dict[OnboardingState, Handler]:
        """Build the state-handler lookup table.

        Returns:
            Mapping from onboarding states to handlers.
        """
        return {
            OnboardingState.TOPICS: self._handle_topics,
            OnboardingState.KEYWORDS: self._handle_keywords,
            OnboardingState.MAX_RESULTS: self._handle_max_results,
            OnboardingState.EMAIL: self._handle_email,
            OnboardingState.CHANNEL: self._handle_channel,
            OnboardingState.SCHEDULE: self._handle_schedule,
            OnboardingState.CONFIRMATION: self._handle_confirmation,
        }

    async def _handle_topics(
        self,
        session: OnboardingSession,
        message: str,
    ) -> ConversationReply:
        """Handle the topic collection state.

        Args:
            session: Current onboarding session.
            message: User message content.

        Returns:
            Next conversation reply.
        """
        topics = await self._agent.extract_topics(message)
        if not topics:
            return ConversationReply(_topics_retry())
        session.topics = topics
        session.state = OnboardingState.KEYWORDS
        return ConversationReply(_keyword_question(session))

    async def _handle_keywords(
        self,
        session: OnboardingSession,
        message: str,
    ) -> ConversationReply:
        """Handle the keyword collection state.

        Args:
            session: Current onboarding session.
            message: User message content.

        Returns:
            Next conversation reply.
        """
        topic = session.topics[session.current_topic_index]
        session.keywords_by_topic[topic] = await self._agent.extract_keywords(
            topic, message
        )
        session.current_topic_index += 1
        if session.current_topic_index < len(session.topics):
            return ConversationReply(_keyword_question(session))
        session.state = OnboardingState.MAX_RESULTS
        return ConversationReply(_max_results_question())

    async def _handle_max_results(
        self,
        session: OnboardingSession,
        message: str,
    ) -> ConversationReply:
        """Handle the max-results collection state.

        Args:
            session: Current onboarding session.
            message: User message content.

        Returns:
            Next conversation reply.
        """
        session.max_news_per_topic = await self._agent.extract_max_results(message)
        session.state = OnboardingState.EMAIL
        return ConversationReply(_email_question())

    async def _handle_email(
        self,
        session: OnboardingSession,
        message: str,
    ) -> ConversationReply:
        """Handle the email collection state.

        Args:
            session: Current onboarding session.
            message: User message content.

        Returns:
            Next conversation reply.
        """
        email = await self._agent.extract_email(message)
        if not email:
            return ConversationReply(_email_retry())
        session.email = email
        session.state = OnboardingState.CHANNEL
        return ConversationReply(_channel_question())

    async def _handle_channel(
        self,
        session: OnboardingSession,
        message: str,
    ) -> ConversationReply:
        """Handle the Discord channel collection state.

        Args:
            session: Current onboarding session.
            message: User message content.

        Returns:
            Next conversation reply.
        """
        channel_id = await self._agent.extract_channel_id(message)
        if channel_id is None:
            return ConversationReply(_channel_retry())
        session.discord_channel_id = channel_id
        session.state = OnboardingState.SCHEDULE
        return ConversationReply(_schedule_question())

    async def _handle_schedule(
        self,
        session: OnboardingSession,
        message: str,
    ) -> ConversationReply:
        """Handle the briefing schedule collection state.

        Args:
            session: Current onboarding session.
            message: User message content.

        Returns:
            Next conversation reply.
        """
        schedule = _parse_schedule(message)
        if schedule is None:
            return ConversationReply(_schedule_retry())
        session.briefing_hour, session.briefing_minute = schedule
        session.state = OnboardingState.CONFIRMATION
        return ConversationReply(_confirmation_message(session))

    async def _handle_confirmation(
        self,
        session: OnboardingSession,
        message: str,
    ) -> ConversationReply:
        """Handle the final confirmation state.

        Args:
            session: Current onboarding session.
            message: User message content.

        Returns:
            Completion reply or restart prompt.
        """
        if not await self._agent.extract_confirmation(message):
            return self._restart_session(session.user_id)
        preferences = self._build_preferences(session)
        await self._repository.save(preferences)
        self._sessions.pop(session.user_id, None)
        return ConversationReply(
            _saved_message(), completed=True, preferences=preferences
        )

    def _restart_session(self, user_id: int) -> ConversationReply:
        """Restart onboarding after rejected confirmation.

        Args:
            user_id: Discord user id.

        Returns:
            Reply with the first question again.
        """
        self._sessions[user_id] = self._new_session(user_id)
        return ConversationReply(
            f"Sem problemas. Vamos refazer.\n\n{_topics_question()}"
        )

    def _build_preferences(self, session: OnboardingSession) -> UserPreferences:
        """Build persisted preferences from a completed session.

        Args:
            session: Completed onboarding session.

        Returns:
            Validated user preferences.
        """
        topics = [_topic_preference(topic, session) for topic in session.topics]
        return UserPreferences(
            user_id=session.user_id,
            topics=topics,
            max_news_per_topic=session.max_news_per_topic,
            email=session.email,
            discord_channel_id=session.discord_channel_id,
            timezone=self._default_timezone,
            briefing_hour=session.briefing_hour,
            briefing_minute=session.briefing_minute,
        )


def _topic_preference(topic: str, session: OnboardingSession) -> TopicPreference:
    """Build one topic preference from session data.

    Args:
        topic: Topic name.
        session: Current onboarding session.

    Returns:
        Topic preference model.
    """
    return TopicPreference(
        name=topic, keywords=session.keywords_by_topic.get(topic, [])
    )


def _topics_question() -> str:
    """Build the initial topics question.

    Returns:
        Question text for Discord.
    """
    return "Quais tópicos você quer acompanhar?"


def _topics_retry() -> str:
    """Build the retry message for topic extraction.

    Returns:
        Retry prompt for Discord.
    """
    return (
        "Não consegui identificar os tópicos. Envie algo como: tecnologia, IA, economia"
    )


def _keyword_question(session: OnboardingSession) -> str:
    """Build the keyword question for the current topic.

    Args:
        session: Current onboarding session.

    Returns:
        Question text for Discord.
    """
    topic = session.topics[session.current_topic_index]
    return f"Para '{topic}', quais palavras-chave priorizar?"


def _max_results_question() -> str:
    """Build the max-results question.

    Returns:
        Question text for Discord.
    """
    return "Qual o número máximo de notícias por tópico?"


def _email_question() -> str:
    """Build the destination email question.

    Returns:
        Question text for Discord.
    """
    return "Qual e-mail deve receber o briefing?"


def _email_retry() -> str:
    """Build the retry message for email extraction.

    Returns:
        Retry prompt for Discord.
    """
    return "Não encontrei um e-mail válido. Envie algo como: nome@email.com"


def _channel_question() -> str:
    """Build the Discord channel question.

    Returns:
        Question text for Discord.
    """
    return "Qual ID do canal Discord receberá o briefing automático?"


def _channel_retry() -> str:
    """Build the retry message for channel extraction.

    Returns:
        Retry prompt for Discord.
    """
    return (
        "Não encontrei o ID do canal. Envie o número do canal ou mencione como <#123>."
    )


def _schedule_question() -> str:
    """Build the preferred briefing time question.

    Returns:
        Question text for Discord.
    """
    return (
        "Que horas prefere receber o seu briefing por e-mail e no canal do Discord?"
    )


def _schedule_retry() -> str:
    """Build the retry message for schedule extraction.

    Returns:
        Retry prompt for Discord.
    """
    return "Não consegui entender o horário. Envie algo como: 07:30 ou 7:30 pm"


def _confirmation_message(session: OnboardingSession) -> str:
    """Build the confirmation message with all preferences.

    Args:
        session: Current onboarding session.

    Returns:
        Confirmation prompt for Discord.
    """
    lines = ["Confirme suas preferências:", *_session_summary(session)]
    return "\n".join([*lines, "", "Responder `sim` para salvar ou `não` para refazer."])


def _session_summary(session: OnboardingSession) -> list[str]:
    """Build summary lines for a pending session.

    Args:
        session: Current onboarding session.

    Returns:
        Human-readable preference summary.
    """
    topics = ", ".join(session.topics)
    return [
        f"- Tópicos: {topics}",
        f"- Máximo por tópico: {session.max_news_per_topic}",
        f"- E-mail: {session.email}",
        f"- Canal Discord: {session.discord_channel_id}",
        f"- Horário: {session.briefing_hour:02d}:{session.briefing_minute:02d}",
    ]


def _saved_message() -> str:
    """Build the onboarding completion message.

    Returns:
        Success message for Discord.
    """
    return "Preferências salvas. Você receberá seus briefings automaticamente."


def _parse_schedule(message: str) -> tuple[int, int] | None:
    """Parse a preferred briefing time from a user message.

    Args:
        message: User message content.

    Returns:
        Parsed hour and minute, or None when no valid time is found.
    """
    match = re.search(
        r"\b(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<period>am|pm)?\b",
        message.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    period = (match.group("period") or "").lower()
    if period:
        if hour < 1 or hour > 12:
            return None
        if period == "pm" and hour != 12:
            hour += 12
        if period == "am" and hour == 12:
            hour = 0
    if hour > 23 or minute > 59:
        return None
    return hour, minute
