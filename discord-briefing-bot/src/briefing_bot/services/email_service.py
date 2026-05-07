"""Email delivery abstractions and SMTP implementation."""

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol


class EmailServiceProtocol(Protocol):
    """Small contract for sending briefing emails."""

    async def send_email(self, to_address: str, subject: str, body: str) -> None:
        """Send an email message.

        Args:
            to_address: Recipient email address.
            subject: Email subject line.
            body: Plain-text email body.
        """


class SMTPEmailService:
    """SMTP implementation for email delivery."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_address: str,
    ) -> None:
        """Create an SMTP email service.

        Args:
            host: SMTP hostname.
            port: SMTP port.
            username: SMTP login username.
            password: SMTP login password.
            from_address: Sender email address.
        """
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_address = from_address

    async def send_email(self, to_address: str, subject: str, body: str) -> None:
        """Send an email message.

        Args:
            to_address: Recipient email address.
            subject: Email subject line.
            body: Plain-text email body.
        """
        message = self._build_message(to_address, subject, body)
        await asyncio.to_thread(self._send_blocking, message)

    def _build_message(
        self,
        to_address: str,
        subject: str,
        body: str,
    ) -> EmailMessage:
        """Build a plain-text email message.

        Args:
            to_address: Recipient email address.
            subject: Email subject line.
            body: Plain-text email body.

        Returns:
            Ready-to-send email message.
        """
        message = EmailMessage()
        message["From"] = self._from_address
        message["To"] = to_address
        message["Subject"] = subject
        message.set_content(body)
        return message

    def _send_blocking(self, message: EmailMessage) -> None:
        """Send an email using the blocking smtplib client.

        Args:
            message: Ready-to-send email message.
        """
        with smtplib.SMTP(self._host, self._port, timeout=30) as client:
            client.starttls()
            client.login(self._username, self._password)
            client.send_message(message)
