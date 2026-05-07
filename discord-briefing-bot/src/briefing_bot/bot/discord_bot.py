"""Discord.py integration for commands, events, and message delivery."""

import logging
from typing import Any

import discord
from discord.ext import commands

from briefing_bot.bot.conversation import ConversationManager, ConversationReply
from briefing_bot.config import Settings
from briefing_bot.models import UserPreferences
from briefing_bot.repositories import UserPreferencesRepositoryProtocol
from briefing_bot.services.scheduler_service import BriefingScheduler

logger = logging.getLogger(__name__)


class DiscordBriefingBot:
    """Discord bot facade that owns discord.py concerns only."""

    def __init__(
        self,
        settings: Settings,
        conversation: ConversationManager,
        repository: UserPreferencesRepositoryProtocol,
    ) -> None:
        """Create the Discord bot facade.

        Args:
            settings: Application settings.
            conversation: Onboarding conversation manager.
            repository: Preference repository.
        """
        self._settings = settings
        self._conversation = conversation
        self._repository = repository
        self._scheduler: BriefingScheduler | None = None
        self._bot = commands.Bot(
            command_prefix="!", intents=_intents(), help_command=None
        )
        self._register_events()
        self._register_commands()

    def set_scheduler(self, scheduler: BriefingScheduler) -> None:
        """Attach the scheduler after dependency graph construction.

        Args:
            scheduler: Briefing scheduler service.
        """
        self._scheduler = scheduler

    async def start(self) -> None:
        """Start the Discord client."""
        await self._bot.start(self._settings.discord_bot_token)

    async def close(self) -> None:
        """Close the Discord client."""
        await self._bot.close()

    async def send_message(self, channel_id: int, content: str) -> None:
        """Send a message to a Discord channel.

        Args:
            channel_id: Target Discord channel id.
            content: Message content to send.
        """
        channel = self._bot.get_channel(channel_id)
        channel = channel or await self._bot.fetch_channel(channel_id)
        await _send_chunks(channel, content)

    def _register_events(self) -> None:
        """Register all discord.py event callbacks."""
        self._register_ready_event()
        self._register_message_event()

    def _register_ready_event(self) -> None:
        """Register the ready event callback."""

        @self._bot.event
        async def on_ready() -> None:
            """Log readiness once Discord connects."""
            logger.info("discord bot connected as %s", self._bot.user)

    def _register_message_event(self) -> None:
        """Register the message event callback."""

        @self._bot.event
        async def on_message(message: discord.Message) -> None:
            """Route commands and onboarding messages."""
            if message.author.bot:
                return
            if message.content.startswith("!"):
                await self._bot.process_commands(message)
                return
            if self._conversation.has_active_session(message.author.id):
                await self._reply_to_conversation(message)

    async def _reply_to_conversation(self, message: discord.Message) -> None:
        """Send the next onboarding reply for a Discord message.

        Args:
            message: Discord message being handled.
        """
        reply = await self._conversation.handle_message(
            message.author.id, message.content
        )
        await _send_chunks(message.channel, reply.message)
        self._schedule_completed_reply(reply)

    def _schedule_completed_reply(self, reply: ConversationReply) -> None:
        """Schedule a user after onboarding completion.

        Args:
            reply: Conversation reply that may contain saved preferences.
        """
        if reply.completed and reply.preferences and self._scheduler:
            self._scheduler.schedule_user(reply.preferences)

    def _register_commands(self) -> None:
        """Register all bot commands."""
        self._register_start_command()
        self._register_config_command()
        self._register_briefing_command()
        self._register_status_command()
        self._register_help_command()

    def _register_start_command(self) -> None:
        """Register the !start command."""

        @self._bot.command(name="start")
        async def start_command(ctx: commands.Context[Any]) -> None:
            """Start onboarding for the current Discord user."""
            await ctx.send(self._conversation.start(ctx.author.id))

    def _register_config_command(self) -> None:
        """Register the !config command."""

        @self._bot.command(name="config")
        async def config_command(ctx: commands.Context[Any]) -> None:
            """Show saved preferences and restart onboarding."""
            preferences = await self._repository.get(ctx.author.id)
            intro = _config_intro(preferences)
            await _send_chunks(
                ctx.channel, f"{intro}\n\n{self._conversation.start(ctx.author.id)}"
            )

    def _register_briefing_command(self) -> None:
        """Register the !briefing command."""

        @self._bot.command(name="briefing")
        async def briefing_command(ctx: commands.Context[Any]) -> None:
            """Generate and deliver a briefing on demand."""
            if self._scheduler is None:
                await ctx.send("Agendador ainda não inicializado.")
                return
            briefing = await self._scheduler.run_briefing_for_user(ctx.author.id)
            await ctx.send(_briefing_result_message(briefing is not None))

    def _register_status_command(self) -> None:
        """Register the !status command."""

        @self._bot.command(name="status")
        async def status_command(ctx: commands.Context[Any]) -> None:
            """Show current saved preferences."""
            preferences = await self._repository.get(ctx.author.id)
            await _send_chunks(ctx.channel, _status_message(preferences))

    def _register_help_command(self) -> None:
        """Register the !help command."""

        @self._bot.command(name="help")
        async def help_command(ctx: commands.Context[Any]) -> None:
            """Show available bot commands."""
            await ctx.send(_help_message())


def _intents() -> discord.Intents:
    """Build Discord intents required by the bot.

    Returns:
        Discord intents with message content enabled.
    """
    intents = discord.Intents.default()
    intents.message_content = True
    return intents


def _config_intro(preferences: UserPreferences | None) -> str:
    """Build the !config introduction message.

    Args:
        preferences: Saved preferences, if any.

    Returns:
        Message shown before restarting onboarding.
    """
    if preferences is None:
        return "Ainda não encontrei preferências salvas. Vamos configurar."
    return f"Preferências atuais:\n{_preferences_text(preferences)}\n\nVamos atualizar."


def _status_message(preferences: UserPreferences | None) -> str:
    """Build the !status response.

    Args:
        preferences: Saved preferences, if any.

    Returns:
        Status message for Discord.
    """
    if preferences is None:
        return "Nenhuma preferência salva. Use `!start` para configurar."
    return f"Preferências atuais:\n{_preferences_text(preferences)}"


def _preferences_text(preferences: UserPreferences) -> str:
    """Build readable preference text.

    Args:
        preferences: Saved preferences.

    Returns:
        Multiline preference summary.
    """
    return "\n".join(f"- {line}" for line in preferences.summary_lines())


def _briefing_result_message(success: bool) -> str:
    """Build the !briefing completion message.

    Args:
        success: Whether a briefing was generated.

    Returns:
        Result message for Discord.
    """
    if success:
        return "Briefing gerado e enviado para o canal/e-mail configurados."
    return "Nenhuma preferência salva. Use `!start` para configurar primeiro."


def _help_message() -> str:
    """Build the command list message.

    Returns:
        Help text for Discord.
    """
    return "\n".join(
        [
            "Comandos disponíveis:",
            "`!start` - inicia o onboarding",
            "`!config` - exibe e atualiza preferências",
            "`!briefing` - gera um briefing imediato",
            "`!status` - mostra preferências atuais",
            "`!help` - lista comandos disponíveis",
        ],
    )


async def _send_chunks(channel: Any, content: str) -> None:
    """Send content to Discord respecting message length limits.

    Args:
        channel: Discord channel-like object with a send method.
        content: Message content.
    """
    for chunk in _chunk_content(content):
        await channel.send(chunk)


def _chunk_content(content: str, limit: int = 1900) -> list[str]:
    """Split long text into Discord-safe chunks.

    Args:
        content: Message content.
        limit: Maximum chunk length.

    Returns:
        Message chunks.
    """
    chunks: list[str] = []
    current = ""
    for line in content.splitlines(keepends=True):
        for part in _line_parts(line, limit):
            current, chunks = _append_line(current, chunks, part, limit)
    result = [*chunks, current.rstrip()] if current else chunks
    return [chunk for chunk in result if chunk]


def _line_parts(line: str, limit: int) -> list[str]:
    """Split a single line into safe parts.

    Args:
        line: Line to split.
        limit: Maximum chunk length.

    Returns:
        Line parts no longer than the limit.
    """
    return [line[index : index + limit] for index in range(0, len(line), limit)]


def _append_line(
    current: str,
    chunks: list[str],
    line: str,
    limit: int,
) -> tuple[str, list[str]]:
    """Append a line to the current Discord message chunk.

    Args:
        current: Current chunk text.
        chunks: Completed chunks.
        line: Next line to append.
        limit: Maximum chunk length.

    Returns:
        Updated current chunk and completed chunks.
    """
    if len(current) + len(line) <= limit:
        return current + line, chunks
    if not current:
        return line, chunks
    return line, [*chunks, current.rstrip()]
