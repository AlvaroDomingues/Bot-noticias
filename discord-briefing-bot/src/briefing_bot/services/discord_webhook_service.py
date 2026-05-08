"""Discord webhook delivery service."""

import asyncio
import json
from urllib.request import Request, urlopen


class DiscordWebhookService:
    """Send briefing messages through a Discord webhook URL."""

    def __init__(self, webhook_url: str) -> None:
        """Create a Discord webhook sender.

        Args:
            webhook_url: Discord webhook URL for the target channel.
        """
        self._webhook_url = webhook_url

    async def send_message(self, _channel_id: int, content: str) -> None:
        """Send content to the configured Discord webhook.

        Args:
            _channel_id: Ignored because the webhook already targets one channel.
            content: Message content to send.
        """
        for chunk in _chunk_content(content):
            await asyncio.to_thread(self._send_blocking, chunk)

    def _send_blocking(self, content: str) -> None:
        """Send one webhook payload with the blocking standard library client.

        Args:
            content: Discord message content.
        """
        payload = json.dumps({"content": content}).encode("utf-8")
        request = Request(
            self._webhook_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "discord-briefing-bot",
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            if response.status >= 400:
                msg = f"Discord webhook failed with HTTP {response.status}"
                raise RuntimeError(msg)


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
    """Split one line into chunks no longer than the Discord limit."""
    return [line[index : index + limit] for index in range(0, len(line), limit)]


def _append_line(
    current: str,
    chunks: list[str],
    line: str,
    limit: int,
) -> tuple[str, list[str]]:
    """Append one line to the current chunk."""
    if len(current) + len(line) <= limit:
        return current + line, chunks
    if not current:
        return line, chunks
    return line, [*chunks, current.rstrip()]
